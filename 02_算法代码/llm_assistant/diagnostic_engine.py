# -*- coding: utf-8 -*-
"""
诊断引擎 - 规则引擎为主，LLM为辅

架构设计:
  - 检测: 由确定性算法完成（Rule/SE/GNN）
  - 推理: 由规则引擎完成（知识库+因果图）
  - 报告: 规则引擎生成，LLM可选润色

设计原则:
  - LLM只做"润色"，不做"判定"
  - 无LLM时100%可用
  - 延迟<100ms（无LLM）/ 3-5秒（有LLM）
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DiagnosticEngine:
    """诊断引擎：规则引擎+可选LLM润色
    
    使用方式:
        # 无LLM模式（默认）
        engine = DiagnosticEngine()
        
        # 有LLM模式
        engine = DiagnosticEngine(
            use_llm=True,
            llm_model_path="models/Qwen3-0.6B-Instruct-Q4_K_M.gguf"
        )
        
        # 诊断
        result = engine.diagnose(anomalies, network_context)
    """
    
    def __init__(self, use_llm: bool = False, 
                 llm_model_path: Optional[str] = None):
        """
        Args:
            use_llm: 是否启用LLM润色
            llm_model_path: LLM模型路径
        """
        # 初始化规则引擎组件
        from llm_assistant.enhanced_llm_v19 import (
            EnhancedKnowledgeBase,
            AnomalyCorrelator,
            CorrectionAdvisor,
            DiagnosticReporter,
        )
        
        self.kb = EnhancedKnowledgeBase()
        self.correlator = AnomalyCorrelator(self.kb)
        self.advisor = CorrectionAdvisor(self.kb)
        self.reporter = DiagnosticReporter(self.kb)
        
        # 初始化LLM（可选）
        self.llm = None
        self.use_llm = use_llm
        
        if use_llm:
            from llm_assistant.llm_engine_v2 import LLMEngine
            self.llm = LLMEngine(model_path=llm_model_path)
            logger.info(f"LLM引擎状态: {self.llm.get_backend()}")
    
    def diagnose(self, anomalies: List[Dict], 
                 network_context: Dict = None) -> Dict:
        """完整诊断流程
        
        Args:
            anomalies: 检测到的异常列表
            network_context: 网络上下文（bus_count, line_count等）
            
        Returns:
            完整诊断结果
        """
        if not anomalies:
            return {
                "status": "success",
                "anomaly_count": 0,
                "report": {
                    "one_line_summary": "未检测到异常，系统运行正常。",
                    "detailed_report": "# 诊断报告\n\n未检测到异常，系统运行正常。",
                    "professional_report": "# 专业报告\n\n系统运行正常。",
                },
                "correlation": {"scenarios": [], "total_anomalies": 0},
                "correction": {"recommendations": [], "priority_actions": []},
                "llm_used": False,
            }
        
        # Step 1: 关联分析（规则引擎）
        logger.info("Step 1: 关联分析...")
        correlation = self.correlator.correlate(anomalies, network_context)
        
        # Step 2: 修正建议（规则引擎）
        logger.info("Step 2: 修正建议...")
        correction = self.advisor.advise(anomalies, correlation, network_context)
        
        # Step 3: 报告生成（规则引擎）
        logger.info("Step 3: 报告生成...")
        report = self.reporter.generate(
            anomalies, correlation, correction, network_context
        )
        
        # Step 4: 可选LLM润色
        llm_used = False
        if self.llm and self.llm.is_available():
            logger.info("Step 4: LLM润色...")
            report = self.llm.polish_report(report)
            llm_used = True
        
        return {
            "status": "success",
            "anomaly_count": len(anomalies),
            "report": report,
            "correlation": correlation,
            "correction": correction,
            "llm_used": llm_used,
            "backend": self.llm.get_backend() if self.llm else "rules",
        }
    
    def diagnose_markdown(self, anomalies: List[Dict],
                          network_context: Dict = None) -> str:
        """生成Markdown格式的诊断报告"""
        result = self.diagnose(anomalies, network_context)
        
        # 优先使用LLM润色的版本
        report = result["report"]
        if "detailed_report_polished" in report:
            return report["detailed_report_polished"]
        return report.get("detailed_report", "")
    
    def diagnose_professional(self, anomalies: List[Dict],
                              network_context: Dict = None) -> str:
        """生成专业报告"""
        result = self.diagnose(anomalies, network_context)
        return result["report"].get("professional_report", "")
    
    def get_knowledge(self, anomaly_type: str) -> Optional[Dict]:
        """获取异常类型知识"""
        knowledge = self.kb.get_knowledge(anomaly_type)
        if not knowledge:
            return None
        
        return {
            "type": anomaly_type,
            "name_cn": knowledge.name_cn,
            "name_en": knowledge.name_en,
            "category": knowledge.category,
            "severity": knowledge.severity.value,
            "description": knowledge.description,
            "possible_causes": knowledge.possible_causes,
            "physical_effects": knowledge.physical_effects,
            "detection_methods": knowledge.detection_methods,
            "correction_strategies": knowledge.correction_strategies,
            "related_anomalies": knowledge.related_anomalies,
            "causal_chains": knowledge.causal_chains,
            "professional_terms": knowledge.professional_terms,
        }
    
    def get_glossary(self) -> Dict[str, str]:
        """获取专业术语表"""
        return self.kb.professional_glossary
    
    def explain_term(self, term: str) -> Optional[str]:
        """解释专业术语"""
        return self.kb.explain_term(term)


def test_diagnostic_engine():
    """测试诊断引擎"""
    logger.info("=" * 60)
    logger.info("Testing Diagnostic Engine")
    logger.info("=" * 60)
    
    # 测试数据
    test_anomalies = [
        {"type": "topo_interrupt", "location": "bus_5", "confidence": 0.95, "layer": "Rule"},
        {"type": "topo_interrupt", "location": "bus_12", "confidence": 0.88, "layer": "Rule"},
        {"type": "voltage_collapse", "location": "bus_8", "confidence": 0.72, "layer": "SE"},
        {"type": "load_shift", "location": "bus_15", "confidence": 0.65, "layer": "Rule"},
    ]
    
    network_context = {
        "bus_count": 33,
        "line_count": 37,
        "network_name": "case33bw",
    }
    
    # 测试1: 无LLM模式
    logger.info("\n1. Testing without LLM (rules only)")
    engine = DiagnosticEngine(use_llm=False)
    result = engine.diagnose(test_anomalies, network_context)
    
    logger.info(f"   Status: {result['status']}")
    logger.info(f"   Anomaly count: {result['anomaly_count']}")
    logger.info(f"   LLM used: {result['llm_used']}")
    logger.info(f"   Backend: {result['backend']}")
    logger.info(f"   Summary: {result['report']['one_line_summary']}")
    
    # 测试2: 知识查询
    logger.info("\n2. Testing knowledge query")
    knowledge = engine.get_knowledge("topo_interrupt")
    if knowledge:
        logger.info(f"   Type: {knowledge['type']}")
        logger.info(f"   Name: {knowledge['name_cn']}")
        logger.info(f"   Severity: {knowledge['severity']}")
    
    # 测试3: 术语表
    logger.info("\n3. Testing glossary")
    glossary = engine.get_glossary()
    logger.info(f"   Glossary size: {len(glossary)}")
    logger.info(f"   PT: {glossary.get('PT', 'N/A')}")
    
    logger.info("\n" + "=" * 60)
    logger.info("Diagnostic Engine tests completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_diagnostic_engine()
