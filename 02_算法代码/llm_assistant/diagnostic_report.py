# -*- coding: utf-8 -*-
"""
诊断报告生成器 - 整合关联分析和修正建议, 生成完整的诊断报告

输出格式:
  - JSON结构化报告(供API返回)
  - Markdown文本报告(供人工阅读)
  - HTML可视化报告(供前端展示)
"""

import json
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path

from llm_assistant.knowledge_base import KnowledgeBase
from llm_assistant.anomaly_correlator import AnomalyCorrelator
from llm_assistant.correction_advisor import CorrectionAdvisor

logger = logging.getLogger(__name__)

REPORT_DIR = Path(r"E:\项目大全\电力拓扑图修正\02_算法代码\output\diagnostic_reports")


class DiagnosticReporter:
    """诊断报告生成器 - 核心接口"""

    def __init__(self, use_llm: bool = False, llm_model_path: str = None):
        """
        Args:
            use_llm: 是否使用LLM增强(可选, 默认使用规则引擎)
            llm_model_path: LLM模型路径(仅use_llm=True时需要)
        """
        self.kb = KnowledgeBase()
        self.correlator = AnomalyCorrelator()
        self.advisor = CorrectionAdvisor()
        self.use_llm = use_llm
        self.llm_engine = None

        if use_llm and llm_model_path:
            try:
                from llm_assistant.llm_engine import LLMEngine
                self.llm_engine = LLMEngine(llm_model_path)
                logger.info("LLM引擎已加载: %s", llm_model_path)
            except Exception as e:
                logger.warning("LLM加载失败, 使用规则引擎兜底: %s", e)
                self.use_llm = False

    def generate(self, anomalies: List[Dict], 
                 network_context: Dict = None) -> Dict:
        """
        生成完整的诊断报告

        Args:
            anomalies: 检测结果列表
            network_context: 网络上下文信息(可选)
                - bus_count: 母线数
                - line_count: 线路数
                - topology_type: 拓扑类型(radial/meshed)
                - network_name: 网络名称

        Returns:
            完整的诊断报告字典
        """
        start_time = time.time()

        # Step 1: 异常关联分析
        correlation = self.correlator.correlate(anomalies)

        # Step 2: 生成修正方案
        correction_plan = self.advisor.generate_plan(anomalies, correlation)

        # Step 3: 为每个异常生成解释
        explanations = self._generate_explanations(anomalies)

        # Step 4: 生成整体诊断(可选LLM增强)
        diagnosis = self._generate_diagnosis(anomalies, correlation, network_context)

        # Step 5: 组装报告
        report = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version": "v18_llm_assistant",
                "engine": "LLM-enhanced" if self.use_llm else "Rule-based",
                "generation_time_ms": int((time.time() - start_time) * 1000),
            },
            "network_context": network_context or {},
            "detection_summary": {
                "total_anomalies": len(anomalies),
                "unique_types": len(set(a.get("type", "") for a in anomalies)),
                "type_distribution": self._type_distribution(anomalies),
            },
            "correlation_analysis": correlation,
            "correction_plan": correction_plan,
            "anomaly_explanations": explanations,
            "diagnosis": diagnosis,
        }

        return report

    def generate_and_save(self, anomalies: List[Dict],
                          network_context: Dict = None) -> Dict:
        """生成报告并保存到文件"""
        report = self.generate(anomalies, network_context)
        self._save_report(report)
        return report

    def to_markdown(self, report: Dict) -> str:
        """将报告转换为Markdown格式"""
        md = []
        md.append("# 配电网异常诊断报告\n")
        md.append(f"**生成时间**: {report['metadata']['timestamp']}")
        md.append(f"**诊断引擎**: {report['metadata']['engine']}\n")

        # 网络信息
        ctx = report.get("network_context", {})
        if ctx:
            md.append("## 网络信息\n")
            md.append(f"- 母线数: {ctx.get('bus_count', 'N/A')}")
            md.append(f"- 线路数: {ctx.get('line_count', 'N/A')}")
            md.append(f"- 拓扑类型: {ctx.get('topology_type', 'N/A')}\n")

        # 检测摘要
        summary = report.get("detection_summary", {})
        md.append("## 检测摘要\n")
        md.append(f"- 异常总数: **{summary.get('total_anomalies', 0)}**")
        md.append(f"- 异常类型数: **{summary.get('unique_types', 0)}**\n")

        dist = summary.get("type_distribution", {})
        if dist:
            md.append("### 异常类型分布\n")
            md.append("| 异常类型 | 数量 | 严重度 |")
            md.append("|---------|------|--------|")
            for t, info in sorted(dist.items(), key=lambda x: -x[1]["count"]):
                md.append(f"| {info['name_cn']} | {info['count']} | {info['severity']} |")
            md.append("")

        # 关联分析
        corr = report.get("correlation_analysis", {})
        md.append("## 关联分析\n")
        md.append(f"**分析摘要**: {corr.get('summary', 'N/A')}\n")

        scenarios = corr.get("fault_scenarios", [])
        if scenarios:
            md.append("### 可能的故障场景\n")
            for i, s in enumerate(scenarios, 1):
                md.append(f"{i}. **{s['fault_name']}** (置信度: {s['confidence']:.0%})")
                md.append(f"   - {s['description']}")
                md.append(f"   - 关联异常: {', '.join(s['matched_anomalies'])}")
            md.append("")

        # 修正方案
        plan = report.get("correction_plan", {})
        md.append("## 修正方案\n")
        md.append(f"**风险评估**: {plan.get('risk_assessment', 'N/A')}")
        md.append(f"**预估时间**: {plan.get('estimated_time', 'N/A')}\n")

        if plan.get("safety_warnings"):
            md.append("### ⚠️ 安全警告\n")
            for w in plan["safety_warnings"]:
                md.append(f"- {w}")
            md.append("")

        steps = plan.get("correction_steps", [])
        if steps:
            for phase in steps:
                md.append(f"### {phase['name']}\n")
                for s in phase["steps"]:
                    risk_icon = "🔴" if s["risk"] in ("high", "critical") else "🟡" if s["risk"] == "medium" else "🟢"
                    md.append(f"- {risk_icon} [{s['anomaly_name']}] {s['action']}")
                md.append("")

        # 诊断结论
        diag = report.get("diagnosis", {})
        if diag:
            md.append("## 诊断结论\n")
            md.append(f"**根因**: {diag.get('root_cause', '需要进一步分析')}")
            md.append(f"**影响范围**: {diag.get('affected_scope', 'N/A')}")
            md.append(f"**整体置信度**: {diag.get('confidence', 0):.0%}\n")

        return "\n".join(md)

    def _generate_explanations(self, anomalies: List[Dict]) -> List[Dict]:
        """为每个异常生成解释"""
        explanations = []
        for a in anomalies:
            atype = a.get("type", "unknown")
            info = self.kb.get_anomaly_info(atype)
            explanations.append({
                "anomaly_type": atype,
                "name_cn": info.get("name_cn", atype),
                "location": a.get("location", ""),
                "confidence": a.get("confidence", 0),
                "layer": a.get("layer", ""),
                "explanation": self.kb.explain_anomaly(
                    atype, a.get("location", ""), a.get("confidence", 0)),
                "possible_causes": info.get("possible_causes", []),
                "physical_effects": info.get("physical_effects", []),
            })
        return explanations

    def _generate_diagnosis(self, anomalies: List[Dict], 
                            correlation: Dict, network_context: Dict = None) -> Dict:
        """生成整体诊断"""
        # 优先使用LLM(如果可用)
        if self.use_llm and self.llm_engine:
            try:
                return self.llm_engine.diagnose(anomalies, correlation, network_context)
            except Exception as e:
                logger.warning("LLM诊断失败, 使用规则引擎: %s", e)

        # 规则引擎兜底
        root_causes = correlation.get("root_causes", [])
        scenarios = correlation.get("fault_scenarios", [])

        if scenarios:
            top = scenarios[0]
            return {
                "root_cause": top["fault_name"],
                "reasoning": top["description"],
                "affected_scope": f"涉及{len(top['matched_anomalies'])}种异常类型",
                "confidence": top["confidence"],
                "recommendation": f"建议按照{top['fault_name']}的处理流程进行修正",
            }
        elif root_causes:
            top = root_causes[0]
            return {
                "root_cause": top["cause"],
                "reasoning": top["description"],
                "affected_scope": f"涉及{len(top.get('evidence', []))}种异常",
                "confidence": top["confidence"],
                "recommendation": "建议按优先级逐步处理异常",
            }
        else:
            type_counts = {}
            for a in anomalies:
                t = a.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            most_common = max(type_counts, key=type_counts.get) if type_counts else "unknown"
            info = self.kb.get_anomaly_info(most_common)
            return {
                "root_cause": info.get("name_cn", most_common),
                "reasoning": "规则引擎诊断, 未匹配到已知故障场景",
                "affected_scope": f"涉及{len(type_counts)}种异常类型",
                "confidence": 0.5,
                "recommendation": "建议人工确认异常类型和位置后, 按优先级逐个处理",
                "needs_human_review": True,
            }

    def _type_distribution(self, anomalies: List[Dict]) -> Dict:
        """统计异常类型分布"""
        dist = {}
        for a in anomalies:
            t = a.get("type", "unknown")
            if t not in dist:
                info = self.kb.get_anomaly_info(t)
                dist[t] = {
                    "name_cn": info.get("name_cn", t),
                    "severity": info.get("severity", "medium"),
                    "count": 0,
                }
            dist[t]["count"] += 1
        return dist

    def _save_report(self, report: Dict):
        """保存报告"""
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # JSON报告
        json_path = REPORT_DIR / f"diagnosis_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Markdown报告
        md_path = REPORT_DIR / f"diagnosis_{timestamp}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown(report))

        logger.info("诊断报告已保存: %s / %s", json_path, md_path)
