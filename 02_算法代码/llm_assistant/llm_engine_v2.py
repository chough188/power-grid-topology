# -*- coding: utf-8 -*-
"""
LLM推理引擎 - 可迁移的轻量级LLM接口

支持后端:
  1. llama-cpp-python (推荐, CPU/GPU自适应)
  2. 规则引擎 (fallback, 100%可用)

    模型: Qwen3.5-2B (2.27B参数, ~4.3GB safetensors)
用途: 仅用于报告润色，不参与核心推理
"""
import os
import logging
from typing import Dict, List, Optional

from .postprocess import process as _pp_process, POLISHED_REPORT_SCHEMA, ANOMALY_EXPLANATION_SCHEMA, fallback_polished_report, fallback_explanation
from pathlib import Path

logger = logging.getLogger(__name__)

# 模型配置
MODEL_CONFIG = {
        "default_model": "Qwen3.5-4B-Claude-Opus",
        "model_repo": "Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-GGUF",
    "n_ctx": 8192,
    "n_threads": None,  # None = auto (os.cpu_count())
    "temperature": 0.3,  # 低温度，减少幻觉
    "max_tokens": 512,
}


class LLMEngine:
    """可迁移的LLM推理引擎
    
    特性:
      - 自动检测llama-cpp-python
      - 失败时自动降级到规则引擎
      - CPU/GPU自适应
      - 模型可选，不强制依赖
    """
    
    def __init__(self, model_path: Optional[str] = None, 
                 device: str = "auto",
                 n_threads: Optional[int] = None):
        """
        Args:
            model_path: GGUF模型路径，None则使用默认模型
            device: "auto", "cpu", "cuda"
            n_threads: CPU线程数，None=自动
        """
        self.model_path = model_path
        self.device = device
        self.n_threads = n_threads or os.cpu_count() or 4
        self.model = None
        self.backend = "none"  # "llamacpp" | "rules" | "none"
        
        # 尝试加载模型
        if model_path:
            self._try_load_model(model_path)
        else:
            # 尝试默认路径
            default_path = self._get_default_model_path()
            if default_path and os.path.exists(default_path):
                self._try_load_model(default_path)
        
        # 如果没有模型，降级到规则引擎
        if self.backend == "none":
            self.backend = "rules"
            logger.info("LLM引擎降级到规则引擎模式")
    
    def _get_default_model_path(self) -> Optional[str]:
        """获取默认模型路径"""
        # 检查常见位置
        model_name = MODEL_CONFIG["default_model"]
        candidates = [
            Path(r"E:\llm_models") / model_name,
            Path(__file__).parent / "models" / model_name,
            Path(__file__).parent.parent / "models" / model_name,
            Path.home() / ".cache" / "llm_models" / model_name,
        ]

        for d in candidates:
            if d.is_dir():
                # 查找目录中的 .gguf 文件
                ggufs = sorted(d.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True)
                if ggufs:
                    return str(ggufs[0])
            elif d.suffix == ".gguf" and d.exists():
                return str(d)

        return None
    
    def _try_load_model(self, model_path: str):
        """尝试加载模型"""
        try:
            from llama_cpp import Llama
            
            logger.info(f"加载LLM模型: {model_path}")
            self.model = Llama(
                model_path=model_path,
                n_ctx=MODEL_CONFIG["n_ctx"],
                n_threads=self.n_threads,
                verbose=False,
            )
            self.backend = "llamacpp"
            logger.info("LLM模型加载成功")
            
        except ImportError:
            logger.warning("llama-cpp-python未安装，无法加载模型")
            self.backend = "rules"
        except Exception as e:
            logger.warning(f"LLM模型加载失败: {e}")
            self.backend = "rules"
    
    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self.backend == "llamacpp" and self.model is not None
    
    def get_backend(self) -> str:
        """获取当前后端"""
        return self.backend
    
    def generate(self, prompt: str, max_tokens: int = None) -> str:
        """生成文本"""
        if not self.is_available():
            return ""
        
        try:
            response = self.model(
                prompt,
                max_tokens=max_tokens or MODEL_CONFIG["max_tokens"],
                temperature=MODEL_CONFIG["temperature"],
                top_p=0.9,
                stop=["\n\n\n", "```", "###"],
            )
            return response["choices"][0]["text"].strip()
        except Exception as e:
            logger.error(f"LLM生成失败: {e}")
            return ""
    
    def polish_report(self, report: Dict) -> Dict:
        """润色诊断报告
        
        Args:
            report: 原始报告（规则引擎生成）
            
        Returns:
            润色后的报告
        """
        if not self.is_available():
            return report
        
        # v18.7.12: 后处理包裹 — 把 LLM 润色输出过 schema + grounding gate
        if "one_line_summary" in report:
            polished = self._polish_summary(report["one_line_summary"])
            if polished:
                ok = self._post_check(
                    raw=polished,
                    schema={"type": "object", "required": ["one_line_summary_polished"],
                            "properties": {"one_line_summary_polished": {"type": "string"}}},
                    ctx=[report["one_line_summary"]],
                )
                if ok.success:
                    report["one_line_summary_polished"] = ok.payload.get("one_line_summary_polished", polished)
                else:
                    report["one_line_summary_polished"] = report["one_line_summary"]

        if "detailed_report" in report:
            polished = self._polish_detailed(report["detailed_report"])
            if polished:
                ok = self._post_check(
                    raw=polished,
                    schema={"type": "object", "required": ["detailed_report_polished"],
                            "properties": {"detailed_report_polished": {"type": "string"}}},
                    ctx=[report["detailed_report"][:1000]],
                )
                if ok.success:
                    report["detailed_report_polished"] = ok.payload.get("detailed_report_polished", polished)
                else:
                    report["detailed_report_polished"] = report["detailed_report"]

        return report
    
    def _polish_summary(self, summary: str) -> str:
        """润色一句话摘要"""
        prompt = f"""请将以下诊断摘要润色得更专业、更简洁：

原始摘要：{summary}

要求：
1. 保持原意不变
2. 使用电力系统专业术语
3. 不超过50字

润色后："""
        
        result = self.generate(prompt, max_tokens=100)
        return result if result else summary
    
    def _polish_detailed(self, detailed: str) -> str:
        """润色详细报告"""
        prompt = f"""请将以下诊断报告润色得更专业：

原始报告：
{detailed}

要求：
1. 保持所有事实不变
2. 使用更专业的表达
3. 结构清晰
4. 不超过300字

润色后："""
        
        result = self.generate(prompt, max_tokens=500)
        return result if result else detailed
    
    def explain_anomaly(self, anomaly_type: str, context: Dict = None) -> str:
        """解释异常类型（用于知识问答）"""
        if not self.is_available():
            return ""
        
        prompt = f"""请用专业但易懂的语言解释配电网中的"{anomaly_type}"异常：

要求：
1. 解释什么是{anomaly_type}
2. 可能的原因
3. 可能的影响
4. 建议的处理方法

回答："""
        
        return self.generate(prompt, max_tokens=300)


    def _post_check(self, raw: str, schema: Dict, ctx: List[str],
                    audit_stack: str = "A",
                    audit_source: str = "llm_engine_v2.LLMEngine._post_check",
                    audit_schema_name: str = ""):
        """Run post-process gates against raw LLM text. Returns PostProcessResult."""
        try:
            return _pp_process(
                raw_text=raw,
                ctx_strings=ctx,
                tool_registry={},
                schema=schema,
                max_latency_s=30.0,
                max_tokens=1024,
                extract_tool_calls_text=False,
                audit_stack=audit_stack,
                audit_source=audit_source,
                audit_schema_name=audit_schema_name,
            )
        except Exception as e:
            logger.warning("_post_check failed: %s", e)
            from .postprocess import PostProcessResult
            return PostProcessResult(success=False, payload=None, fallback_used=True, note=str(e))

def test_llm_engine():
    """测试LLM引擎"""
    logger.info("=" * 60)
    logger.info("Testing LLM Engine")
    logger.info("=" * 60)
    
    # 测试1: 无模型（规则引擎模式）
    logger.info("\n1. Testing without model (rules mode)")
    engine = LLMEngine()
    logger.info(f"   Backend: {engine.get_backend()}")
    logger.info(f"   Available: {engine.is_available()}")
    
    # 测试2: 尝试加载模型
    logger.info("\n2. Testing with model (if available)")
    model_path = engine._get_default_model_path()
    if model_path:
        logger.info(f"   Found model: {model_path}")
        engine2 = LLMEngine(model_path)
        logger.info(f"   Backend: {engine2.get_backend()}")
        logger.info(f"   Available: {engine2.is_available()}")
    else:
        logger.info("   No model found, skipping")
    
    logger.info("\n" + "=" * 60)
    logger.info("LLM Engine tests completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_llm_engine()
