# -*- coding: utf-8 -*-
"""
修正建议生成器 - 基于知识库和异常关联分析生成修正方案

设计原则:
  - 所有建议必须有知识库依据, 不允许LLM自由发挥
  - 高风险操作必须标注安全警告
  - 建议按优先级排序, 先处理最高严重度的异常
"""

import logging
from typing import Dict, List
from llm_assistant.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class CorrectionAdvisor:
    """修正建议生成器"""

    def __init__(self):
        self.kb = KnowledgeBase()

    def generate_plan(self, anomalies: List[Dict], 
                      correlation_result: Dict = None) -> Dict:
        """
        生成修正方案

        Args:
            anomalies: 检测结果列表
            correlation_result: 关联分析结果(可选)

        Returns:
            {
                "priority_actions": [...],   # 优先执行的操作
                "correction_steps": [...],   # 修正步骤
                "safety_warnings": [...],    # 安全警告
                "estimated_time": str,       # 预估时间
                "risk_assessment": str,      # 风险评估
            }
        """
        if not anomalies:
            return self._empty_plan()

        # Step 1: 按严重度排序异常
        sorted_anomalies = self._sort_by_severity(anomalies)

        # Step 2: 为每个异常生成修正建议
        all_steps = []
        safety_warnings = set()

        for a in sorted_anomalies:
            atype = a.get("type", "unknown")
            info = self.kb.get_anomaly_info(atype)
            strategies = self.kb.get_correction_plan(atype, info.get("severity"))

            for strategy in strategies:
                step = {
                    "anomaly_type": atype,
                    "anomaly_name": info.get("name_cn", atype),
                    "location": a.get("location", ""),
                    "action": strategy["action"],
                    "priority": strategy["priority"],
                    "risk": strategy["risk"],
                    "confidence": a.get("confidence", 0),
                }
                all_steps.append(step)

                if strategy["risk"] in ("high", "critical"):
                    safety_warnings.add(
                        f"⚠️ {info.get('name_cn', atype)}的修正操作\"{strategy['action']}\"风险等级为{strategy['risk']}, "
                        f"建议在监护下执行"
                    )

        # Step 3: 去重并排序
        priority_actions = self._deduplicate_actions(all_steps)

        # Step 4: 评估整体风险
        risk_assessment = self._assess_risk(sorted_anomalies)

        # Step 5: 估算时间
        estimated_time = self._estimate_time(priority_actions)

        return {
            "priority_actions": priority_actions[:10],  # 最多10个优先操作
            "correction_steps": self._organize_steps(priority_actions),
            "safety_warnings": list(safety_warnings),
            "estimated_time": estimated_time,
            "risk_assessment": risk_assessment,
            "total_actions": len(priority_actions),
        }

    def _sort_by_severity(self, anomalies: List[Dict]) -> List[Dict]:
        """按严重度排序"""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def get_severity(a):
            info = self.kb.get_anomaly_info(a.get("type", ""))
            return severity_order.get(info.get("severity", "medium"), 3)

        return sorted(anomalies, key=get_severity)

    def _deduplicate_actions(self, steps: List[Dict]) -> List[Dict]:
        """去重: 同一类型异常的相同操作只保留一次"""
        seen = set()
        result = []
        for step in steps:
            key = (step["anomaly_type"], step["action"])
            if key not in seen:
                seen.add(key)
                result.append(step)
        # 按priority排序
        result.sort(key=lambda x: (x["priority"], -x["confidence"]))
        return result

    def _organize_steps(self, actions: List[Dict]) -> List[Dict]:
        """组织修正步骤: 按阶段分组"""
        phases = {
            "phase1_confirm": {"name": "确认阶段", "steps": []},
            "phase2_isolate": {"name": "隔离阶段", "steps": []},
            "phase3_correct": {"name": "修正阶段", "steps": []},
            "phase4_verify": {"name": "验证阶段", "steps": []},
        }

        for action in actions:
            if action["priority"] <= 1:
                phases["phase1_confirm"]["steps"].append(action)
            elif action["priority"] <= 2:
                phases["phase2_isolate"]["steps"].append(action)
            elif action["priority"] <= 3:
                phases["phase3_correct"]["steps"].append(action)
            else:
                phases["phase4_verify"]["steps"].append(action)

        return [v for v in phases.values() if v["steps"]]

    def _assess_risk(self, anomalies: List[Dict]) -> str:
        """评估整体风险"""
        high_risk_count = sum(1 for a in anomalies
                              if self.kb.get_anomaly_info(a.get("type", "")).get("severity") in ("critical", "high"))

        if high_risk_count >= 3:
            return "高风险: 存在多个严重异常, 建议启动应急预案, 优先处理安全相关异常"
        elif high_risk_count >= 1:
            return "中等风险: 存在严重异常, 建议按优先级逐步处理"
        else:
            return "低风险: 异常均为一般性问题, 可按计划处理"

    def _estimate_time(self, actions: List[Dict]) -> str:
        """估算处理时间"""
        n = len(actions)
        if n <= 3:
            return "约30分钟"
        elif n <= 6:
            return "约1小时"
        elif n <= 10:
            return "约2小时"
        else:
            return "约4小时或更长(建议分批处理)"

    def _empty_plan(self) -> Dict:
        """空方案"""
        return {
            "priority_actions": [],
            "correction_steps": [],
            "safety_warnings": [],
            "estimated_time": "无需处理",
            "risk_assessment": "无风险",
            "total_actions": 0,
        }
