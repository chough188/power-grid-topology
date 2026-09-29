# -*- coding: utf-8 -*-
"""
LLM推理引擎 - 可选的本地大模型推理接口

支持的模型:
  - Qwen2.5-1.5B-Instruct (推荐, 中文能力强)
  - Phi-3-mini-4k-instruct (推理能力强)
  - DeepSeek-R1-Distill-Qwen-1.5B (推理链)

推理框架: llama.cpp (CPU) / transformers (GPU)

使用方式:
  engine = LLMEngine("models/qwen2.5-1.5b-instruct-q4.gguf")
  result = engine.diagnose(anomalies, correlation, context)
"""

import logging
from typing import Dict, List, Optional

from .postprocess import process as _pp_process, DIAGNOSIS_SCHEMA, fallback_diagnosis

logger = logging.getLogger(__name__)


class LLMEngine:
    """本地LLM推理引擎"""

    def __init__(self, model_path: str, device: str = "cpu", n_threads: int = 4):
        self.model_path = model_path
        self.device = device
        self.n_threads = n_threads
        self.model = None
        self._load_model()

    def _load_model(self):
        """加载模型"""
        try:
            from llama_cpp import Llama
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=self.n_threads,
                verbose=False,
            )
            logger.info("LLM模型加载成功: %s", self.model_path)
        except ImportError:
            logger.warning("llama-cpp-python未安装, LLM功能不可用")
            raise
        except Exception as e:
            logger.warning("LLM模型加载失败: %s", e)
            raise

    def diagnose(self, anomalies: List[Dict], correlation: Dict,
                 network_context: Dict = None) -> Dict:
        """使用LLM生成诊断"""
        if not self.model:
            raise RuntimeError("LLM模型未加载")

        prompt = self._build_diagnosis_prompt(anomalies, correlation, network_context)
        response = self._generate(prompt, max_tokens=512)

        # v18.7.12: post-process (schema + grounding + budget) before returning
        ctx_strings = self._grounding_context(anomalies, correlation)
        result = _pp_process(
            raw_text=response,
            ctx_strings=ctx_strings,
            tool_registry={},
            schema=DIAGNOSIS_SCHEMA,
            max_latency_s=60.0,
            max_tokens=2048,
            extract_tool_calls_text=False,
        )
        if result.success:
            return result.payload
        # Fall back to rules
        return fallback_diagnosis(anomalies, correlation)

    def generate_report_text(self, anomalies: List[Dict], 
                             correlation: Dict) -> str:
        """使用LLM生成报告文本"""
        if not self.model:
            raise RuntimeError("LLM模型未加载")

        prompt = self._build_report_prompt(anomalies, correlation)
        return self._generate(prompt, max_tokens=1024)

    def _generate(self, prompt: str, max_tokens: int = 512) -> str:
        """生成文本"""
        response = self.model(
            prompt,
            max_tokens=max_tokens,
            temperature=0.1,  # 低温度, 减少幻觉
            top_p=0.9,
            stop=["\n\n\n", "```"],
        )
        return response["choices"][0]["text"]

    def _build_diagnosis_prompt(self, anomalies: List[Dict], 
                                correlation: Dict, context: Dict = None) -> str:
        """构建诊断提示词"""
        type_counts = {}
        for a in anomalies:
            t = a.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        prompt = """你是一个配电网故障诊断专家。请根据以下检测结果, 分析最可能的根因。

检测到的异常:
"""
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            prompt += f"- {t}: {c}个\n"

        scenarios = correlation.get("fault_scenarios", [])
        if scenarios:
            prompt += "\n关联分析结果:\n"
            for s in scenarios[:2]:
                prompt += f"- {s['fault_name']}: 置信度{s['confidence']:.0%}\n"

        if context:
            prompt += f"\n网络信息: {context.get('bus_count', '?')}节点, "
            prompt += f"{context.get('line_count', '?')}线路\n"

        prompt += """
请用JSON格式回答:
{
  "root_cause": "最可能的根因",
  "reasoning": "分析推理过程",
  "affected_scope": "影响范围",
  "confidence": 0.0到1.0的置信度,
  "recommendation": "建议的处理方案"
}

注意: 只输出JSON, 不要幻觉。如果信息不足, confidence应低于0.5。
"""
        return prompt

    def _build_report_prompt(self, anomalies: List[Dict], correlation: Dict) -> str:
        """构建报告生成提示词"""
        prompt = """你是一个配电网运维报告撰写专家。请根据以下诊断结果, 生成一份简明的中文诊断报告。

"""
        prompt += correlation.get("summary", "") + "\n\n"
        prompt += "请生成200字以内的诊断报告, 包含: 异常概述、可能原因、建议措施。\n"
        return prompt

    def _parse_diagnosis(self, response: str) -> Dict:
        """解析LLM输出"""
        import json
        try:
            # 尝试提取JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        # 解析失败, 返回保守结论
        return {
            "root_cause": "需要进一步分析",
            "reasoning": response[:200],
            "affected_scope": "待确认",
            "confidence": 0.3,
            "recommendation": "建议人工确认",
            "needs_human_review": True,
        }


    def _grounding_context(self, anomalies: List[Dict], correlation: Dict) -> List[str]:
        """Build grounding context strings for post-process gate."""
        ctx: List[str] = []
        for a in (anomalies or [])[:50]:
            t = a.get("type", "")
            loc = a.get("location", "")
            conf = a.get("confidence", 0)
            ctx.append(f"{t} at {loc} conf={conf}")
        for s in (correlation.get("fault_scenarios") or [])[:5]:
            ctx.append(f"{s.get('fault_name', '')}: {s.get('description', '')[:100]}")
        return ctx
