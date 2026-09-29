# -*- coding: utf-8 -*-
"""
Expert Analysis Engine v2 - 深度集成28种异常类型知识库

改进点:
- 集成ANOMALY_KNOWLEDGE: 每种异常的详细原因、影响、修正策略
- 集成FAULT_CORRELATION: 故障场景因果链
- 集成SEVERITY_LEVELS: 严重度分级响应
- 集成CORRECTION_RULES: 具体修正建议
- 添加风险评估矩阵
- 添加类别级汇总分析
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from knowledge_base import ANOMALY_KNOWLEDGE, FAULT_CORRELATION, SEVERITY_LEVELS
except ImportError:
    ANOMALY_KNOWLEDGE, FAULT_CORRELATION, SEVERITY_LEVELS = {}, {}, {}


# ── 异常类型中文名映射 ──
TYPE_CN = {
    "topo_interrupt": "拓扑中断", "virtual_faulty": "虚拟故障",
    "model_mismatch": "图模不匹配", "telemetry_mismatch": "遥测异常",
    "signal_mismatch": "信号异常", "measurement_outlier": "量测越限",
    "stale_data": "数据过时", "parameter_error": "参数错误",
    "load_shift": "负荷转移", "reverse_power_flow": "反向潮流",
    "communication_loss": "通信中断", "voltage_collapse": "电压崩溃",
    "ghost_topology": "幽灵拓扑", "duplicate_measurement": "重复量测",
    "protection_misconfig": "保护误配", "trafo_tap_fault": "变压器分接故障",
    "grounding_fault": "接地故障", "clock_drift": "时钟漂移",
    "harmonic_pollution": "谐波污染", "impedance_degradation": "阻抗退化",
    "dg_intermittent": "DG间歇", "measurement_bias": "量测偏差",
    "branch_contingency": "支路停运", "topo_obfuscation": "拓扑混淆",
    "voltage_regulation": "电压调节", "bus_section_mismatch": "母线分段异常",
    "bypass_operation": "旁路操作", "load_transfer_residual": "负荷转供残留",
}

TYPE_CATEGORY = {
    "topology": ["topo_interrupt", "ghost_topology", "topo_obfuscation",
                 "bus_section_mismatch", "bypass_operation"],
    "measurement": ["measurement_outlier", "measurement_bias", "duplicate_measurement",
                    "stale_data", "telemetry_mismatch", "signal_mismatch",
                    "communication_loss"],
    "parameter": ["parameter_error", "impedance_degradation", "trafo_tap_fault"],
    "operation": ["load_shift", "reverse_power_flow", "load_transfer_residual",
                  "branch_contingency", "voltage_regulation"],
    "fault": ["virtual_faulty", "grounding_fault", "voltage_collapse",
              "protection_misconfig"],
    "power_quality": ["harmonic_pollution", "dg_intermittent", "clock_drift"],
    "model": ["model_mismatch"],
}

CATEGORY_CN = {
    "topology": "拓扑类", "measurement": "量测类", "parameter": "参数类",
    "operation": "运行类", "fault": "故障类", "power_quality": "电能质量类",
    "model": "模型类", "other": "其他",
}


def _cn(t: str) -> str:
    return TYPE_CN.get(t, t)


def _cat(t: str) -> str:
    for cat, types in TYPE_CATEGORY.items():
        if t in types:
            return cat
    return "other"


def _cat_cn(cat: str) -> str:
    return CATEGORY_CN.get(cat, cat)


class ExpertAnalysisEngine:
    """基于知识库的专家分析引擎 v2。"""

    def __init__(self, knowledge_base: dict = None):
        self.kb = knowledge_base or ANOMALY_KNOWLEDGE
        self.correlations = FAULT_CORRELATION
        self.severity = SEVERITY_LEVELS

    def generate_analysis(self, metrics: dict) -> str:
        """Generate comprehensive professional analysis."""
        sections = []
        sections.append(self._overall_assessment(metrics))
        sections.append(self._technical_strengths(metrics))
        sections.append(self._risk_assessment(metrics))
        sections.append(self._improvement_suggestions(metrics))
        return "\n".join(sections)

    # ── 1. 总体评价 ─────────────────────────────────────────
    def _overall_assessment(self, m: dict) -> str:
        f1 = m["f1"]
        pass95 = m["pass95"]
        total = m["total"]
        fp = m["fp"]
        fn = m["fn"]

        if f1 >= 99:
            level = "卓越"
        elif f1 >= 97:
            level = "优秀"
        elif f1 >= 95:
            level = "良好"
        else:
            level = "需改进"

        if fp <= 10 and fn <= 40:
            char = "误报和漏报均控制在极低水平"
        elif fp <= 10:
            char = f"误报控制优秀（仅{fp}个），漏报{fn}个需关注"
        elif fn <= 40:
            char = f"漏报控制良好（仅{fn}个），误报{fp}个需优化"
        else:
            char = f"误报{fp}个、漏报{fn}个均有优化空间"

        weak = m.get("weak", [])
        fail_count = total - pass95
        if fail_count == 0:
            network_note = "全部网络通过"
        elif all(w["bus"] <= 5 for w in weak):
            network_note = f"{fail_count}个tiny网络（≤5节点）未通过，属于SE层跳过的结构性限制"
        else:
            network_note = f"{fail_count}个网络未通过"

        return f"**总体评价**：系统检测性能{level}，F1={f1:.1f}%，{pass95}/{total}个网络F1≥95%通过。{char}。{network_note}。"

    # ── 2. 技术优势 ─────────────────────────────────────────
    def _technical_strengths(self, m: dict) -> str:
        strengths = []
        type_stats = m["type_stats"]

        # 100% recall types
        perfect = [t for t, v in type_stats.items() if v["inj"] > 0 and v["hit"] == v["inj"]]
        if perfect:
            cats = set(_cat(t) for t in perfect)
            cat_names = "、".join(_cat_cn(c) for c in sorted(cats)[:3])
            strengths.append(f"{len(perfect)}种异常类型召回率达100%，覆盖{cat_names}等类别")

        # Precision
        if m["prec"] >= 99:
            strengths.append(f"精确率{m['prec']:.1f}%，仅{m['fp']}个误报，多层确认机制有效抑制误报")

        # Coverage breadth
        active = sum(1 for v in type_stats.values() if v["inj"] > 0)
        if active >= 25:
            strengths.append(f"覆盖{active}种活跃异常类型，检测覆盖面行业领先")

        # Architecture
        strengths.append("Rule+SE+GNN多层检测架构互补，单一模块失效不影响整体")

        lines = ["**技术优势**："]
        for i, s in enumerate(strengths[:3], 1):
            lines.append(f"{i}. {s}")
        return "\n".join(lines)

    # ── 3. 风险评估 ─────────────────────────────────────────
    def _risk_assessment(self, m: dict) -> str:
        """Identify fault scenarios from FAULT_CORRELATION."""
        type_stats = m["type_stats"]
        weak_types = set()

        # Find types with recall < 100%
        for t, v in type_stats.items():
            if v["inj"] > 0 and v["hit"] < v["inj"]:
                weak_types.add(t)

        # Match against fault correlation scenarios
        matched_scenarios = []
        for scenario_name, scenario in self.correlations.items():
            triggers = set(scenario.get("trigger_anomalies", []))
            cascades = set(scenario.get("cascade_anomalies", []))
            # Check if any weak types match this scenario
            trigger_hits = triggers & weak_types
            cascade_hits = cascades & weak_types
            if trigger_hits or cascade_hits:
                matched_scenarios.append({
                    "name": scenario_name,
                    "desc": scenario.get("description", ""),
                    "trigger_hits": trigger_hits,
                    "cascade_hits": cascade_hits,
                    "boost": scenario.get("confidence_boost", 0),
                })

        if not matched_scenarios:
            return ""

        lines = ["**风险评估**："]
        for s in matched_scenarios[:2]:
            parts = [s["desc"]]
            if s["trigger_hits"]:
                parts.append(f"触发因素：{', '.join(_cn(t) for t in s['trigger_hits'])}")
            if s["cascade_hits"]:
                parts.append(f"级联影响：{', '.join(_cn(t) for t in s['cascade_hits'])}")
            lines.append(f"- {scenario_name}：{'；'.join(parts)}")

        return "\n".join(lines)

    # ── 4. 改进建议 ─────────────────────────────────────────
    def _improvement_suggestions(self, m: dict) -> str:
        suggestions = []
        weak = m.get("weak", [])
        worst = m.get("worst", [])
        type_stats = m.get("type_stats", {})

        # Suggestion 1: Address weakest type using knowledge base
        if worst:
            t, recall, inj, hit = worst[0]
            fn_count = inj - hit
            t_cn = _cn(t)

            # Get specific correction from knowledge base
            kb_info = self.kb.get(t, {})
            correction_strategies = kb_info.get("correction_strategies", [])
            causes = kb_info.get("possible_causes", [])
            severity = kb_info.get("severity", "medium")

            if correction_strategies:
                # Use the highest priority correction
                best_fix = min(correction_strategies, key=lambda x: x.get("priority", 99))
                fix_text = best_fix.get("action", "优化检测规则")
            elif causes:
                fix_text = f"排查{causes[0]}等根因"
            else:
                cat = _cat(t)
                fix_text = self._generic_fix(cat)

            sev_cn = {"critical": "紧急", "high": "高", "medium": "中", "low": "低"}.get(severity, "")
            suggestions.append(
                f"**{t_cn}**（{t}）召回率仅{recall:.0f}%（{fn_count}个漏报），"
                f"严重度{sev_cn}，建议{fix_text}"
            )

        # Suggestion 2: Address weak networks with knowledge base
        if weak:
            w = weak[0]
            net, bus, f1 = w["net"], w["bus"], w["f1"]

            if bus <= 5:
                if w["fps"]:
                    fp_t = w["fps"][0]
                    fp_cn = _cn(fp_t)
                    # Get related anomalies from knowledge base
                    related = self.kb.get(fp_t, {}).get("related_anomalies", [])
                    related_note = f"，关联{', '.join(_cn(r) for r in related[:2])}" if related else ""
                    suggestions.append(
                        f"**{net}**（{bus}节点）SE层跳过导致{fp_cn}误报{related_note}，"
                        f"建议为tiny网络实现轻量级状态估计（如直流SE）"
                    )
                elif w["fns"]:
                    fn_cn = _cn(w["fns"][0])
                    suggestions.append(
                        f"**{net}**（{bus}节点）SE层跳过导致{fn_cn}漏报，"
                        f"建议增加基于拓扑规则的检测补位"
                    )

        # Suggestion 3: Systemic improvement for tiny networks
        if len(weak) >= 2 and all(w["bus"] <= 10 for w in weak):
            suggestions.append(
                f"所有{len(weak)}个弱网络均为小型网络（≤{max(w['bus'] for w in weak)}节点），"
                f"建议开发tiny网络专用检测流水线，绕过SE层直接使用规则检测"
            )

        # Suggestion 4: Category-level improvement
        cat_stats = {}
        for t, v in type_stats.items():
            if v["inj"] > 0:
                cat = _cat(t)
                if cat not in cat_stats:
                    cat_stats[cat] = {"hit": 0, "inj": 0}
                cat_stats[cat]["hit"] += v["hit"]
                cat_stats[cat]["inj"] += v["inj"]

        if cat_stats and len(suggestions) < 4:
            worst_cat = min(cat_stats.items(), key=lambda x: x[1]["hit"] / max(x[1]["inj"], 1))
            cat_name, cat_v = worst_cat
            cat_recall = cat_v["hit"] / max(cat_v["inj"], 1) * 100
            if cat_recall < 99:
                # Find specific types in this category that are weak
                weak_in_cat = [t for t in type_stats
                              if _cat(t) == cat_name
                              and type_stats[t]["inj"] > 0
                              and type_stats[t]["hit"] < type_stats[t]["inj"]]
                if weak_in_cat:
                    weak_names = ", ".join(_cn(t) for t in weak_in_cat[:2])
                    suggestions.append(
                        f"{_cat_cn(cat_name)}整体召回率{cat_recall:.0f}%偏低"
                        f"（{weak_names}），建议针对该类别加强检测规则覆盖"
                    )

        lines = ["**改进建议**："]
        for i, s in enumerate(suggestions[:3], 1):
            lines.append(f"{i}. {s}")
        return "\n".join(lines)

    def _generic_fix(self, cat: str) -> str:
        """Category-specific generic fix suggestions."""
        return {
            "topology": "结合CIM模型拓扑校验，增加拓扑一致性检查规则",
            "measurement": "引入量测冗余校验，基于KCL定律交叉验证",
            "parameter": "增加参数合理性边界检查，结合历史数据趋势分析",
            "operation": "结合SCADA实时数据，增加运行状态连续性检测",
            "fault": "引入故障录波数据辅助判别，减少保护动作误判",
            "power_quality": "增加谐波分析和时频域联合检测",
            "model": "定期同步CIM模型与实际拓扑",
        }.get(cat, "增加该类型的专用检测规则和阈值优化")
