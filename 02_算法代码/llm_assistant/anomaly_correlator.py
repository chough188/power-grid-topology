# -*- coding: utf-8 -*-
"""
异常关联分析器 - 将多个独立异常归因为同一故障场景

核心逻辑:
  1. 空间关联: 同一位置/相邻位置的异常可能相关
  2. 时间关联: 同一检测周期内的异常可能相关
  3. 类型关联: 知识库中定义的异常类型关联关系
  4. 因果关联: 一个异常可能是另一个异常的因果链结果
"""

import logging
from typing import Dict, List, Set, Tuple
from collections import defaultdict
from llm_assistant.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class AnomalyCorrelator:
    """异常关联分析器"""

    def __init__(self):
        self.kb = KnowledgeBase()

    def correlate(self, anomalies: List[Dict]) -> Dict:
        """
        将异常列表关联分析, 输出结构化的故障场景

        Args:
            anomalies: 检测结果列表, 每个元素包含:
                - type: 异常类型
                - location: 位置
                - confidence: 置信度
                - layer: 检测层

        Returns:
            {
                "fault_scenarios": [...],  # 识别的故障场景
                "anomaly_groups": [...],   # 异常分组
                "root_causes": [...],      # 推断的根因
                "severity": str,           # 整体严重度
                "summary": str,            # 摘要
            }
        """
        if not anomalies:
            return self._empty_result()

        # Step 1: 按类型统计
        type_counts = defaultdict(int)
        type_anomalies = defaultdict(list)
        for a in anomalies:
            t = a.get("type", "unknown")
            type_counts[t] += 1
            type_anomalies[t].append(a)

        # Step 2: 按位置分组
        location_groups = self._group_by_location(anomalies)

        # Step 3: 基于知识库的故障场景匹配
        scenarios = self.kb.find_fault_scenarios(list(type_counts.keys()))

        # Step 4: 空间关联分析
        spatial_groups = self._spatial_correlation(anomalies)

        # Step 5: 合并分析结果
        anomaly_groups = self._merge_groups(type_anomalies, location_groups, spatial_groups)

        # Step 6: 推断根因
        root_causes = self._infer_root_causes(scenarios, anomaly_groups)

        # Step 7: 确定整体严重度
        severity = self._determine_severity(anomalies)

        # Step 8: 生成摘要
        summary = self._generate_summary(anomalies, scenarios, root_causes, severity)

        return {
            "fault_scenarios": scenarios[:3],  # 最多3个最可能的故障场景
            "anomaly_groups": anomaly_groups,
            "root_causes": root_causes,
            "severity": severity,
            "summary": summary,
            "total_anomalies": len(anomalies),
            "unique_types": len(type_counts),
        }

    def _group_by_location(self, anomalies: List[Dict]) -> Dict[str, List[Dict]]:
        """按位置分组"""
        groups = defaultdict(list)
        for a in anomalies:
            loc = a.get("location", "unknown")
            # 提取母线号(忽略前缀)
            bus_id = self._extract_bus_id(loc)
            groups[f"bus_{bus_id}"].append(a) if bus_id >= 0 else groups["unknown"].append(a)
        return dict(groups)

    def _extract_bus_id(self, location: str) -> int:
        """从位置字符串提取母线号"""
        import re
        match = re.search(r'(\d+)', str(location))
        return int(match.group(1)) if match else -1

    def _spatial_correlation(self, anomalies: List[Dict]) -> List[List[Dict]]:
        """空间关联: 同一母线或相邻母线的异常归为一组"""
        bus_anomalies = defaultdict(list)
        for a in anomalies:
            bus_id = self._extract_bus_id(a.get("location", ""))
            if bus_id >= 0:
                bus_anomalies[bus_id].append(a)

        # 合并相邻母线的异常(距离<=1)
        groups = []
        visited = set()
        for bus_id in sorted(bus_anomalies.keys()):
            if bus_id in visited:
                continue
            group = list(bus_anomalies[bus_id])
            visited.add(bus_id)
            # 检查相邻母线
            for neighbor in [bus_id - 1, bus_id + 1]:
                if neighbor in bus_anomalies and neighbor not in visited:
                    group.extend(bus_anomalies[neighbor])
                    visited.add(neighbor)
            if len(group) > 1:
                groups.append(group)

        return groups

    def _merge_groups(self, type_anomalies: Dict, location_groups: Dict,
                      spatial_groups: List) -> List[Dict]:
        """合并不同维度的分组"""
        merged = []

        # 按类型分组
        for type_name, anomalies in type_anomalies.items():
            info = self.kb.get_anomaly_info(type_name)
            merged.append({
                "group_type": "by_anomaly_type",
                "anomaly_type": type_name,
                "name_cn": info.get("name_cn", type_name),
                "count": len(anomalies),
                "locations": [a.get("location", "") for a in anomalies],
                "avg_confidence": sum(a.get("confidence", 0) for a in anomalies) / max(len(anomalies), 1),
                "severity": info.get("severity", "medium"),
            })

        # 按位置分组(仅保留有多个异常的位置)
        for loc, anomalies in location_groups.items():
            if len(anomalies) > 1:
                types = set(a.get("type", "") for a in anomalies)
                merged.append({
                    "group_type": "by_location",
                    "location": loc,
                    "count": len(anomalies),
                    "anomaly_types": list(types),
                    "avg_confidence": sum(a.get("confidence", 0) for a in anomalies) / len(anomalies),
                })

        # 按空间关联分组
        for i, group in enumerate(spatial_groups):
            types = set(a.get("type", "") for a in group)
            locations = set(a.get("location", "") for a in group)
            merged.append({
                "group_type": "spatial_cluster",
                "cluster_id": i,
                "count": len(group),
                "anomaly_types": list(types),
                "locations": list(locations),
                "avg_confidence": sum(a.get("confidence", 0) for a in group) / len(group),
            })

        return merged

    def _infer_root_causes(self, scenarios: List[Dict], 
                           groups: List[Dict]) -> List[Dict]:
        """推断根因"""
        root_causes = []

        for scenario in scenarios:
            root_causes.append({
                "cause": scenario["fault_name"],
                "description": scenario["description"],
                "confidence": scenario["confidence"],
                "evidence": scenario["matched_anomalies"],
            })

        # 如果没有匹配的故障场景, 使用通用推理
        if not root_causes:
            for group in groups:
                if group.get("group_type") == "by_anomaly_type" and group["count"] >= 2:
                    root_causes.append({
                        "cause": f"批量{group.get('name_cn', group.get('anomaly_type', ''))}",
                        "description": f"检测到{group['count']}个{group.get('name_cn', '')}异常, 可能存在系统性问题",
                        "confidence": 0.5,
                        "evidence": [group.get("anomaly_type", "")],
                    })

        return root_causes[:5]  # 最多5个根因

    def _determine_severity(self, anomalies: List[Dict]) -> str:
        """确定整体严重度"""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        min_severity = "low"

        for a in anomalies:
            info = self.kb.get_anomaly_info(a.get("type", ""))
            s = info.get("severity", "medium")
            if severity_order.get(s, 3) < severity_order.get(min_severity, 3):
                min_severity = s

        # 多个异常升级严重度
        if len(anomalies) >= 5 and min_severity in ("medium", "low"):
            min_severity = "high"
        if len(anomalies) >= 10:
            min_severity = "critical"

        return min_severity

    def _generate_summary(self, anomalies: List[Dict], scenarios: List[Dict],
                          root_causes: List[Dict], severity: str) -> str:
        """生成分析摘要"""
        type_counts = defaultdict(int)
        for a in anomalies:
            type_counts[a.get("type", "unknown")] += 1

        summary = f"共检测到{len(anomalies)}个异常, 涉及{len(type_counts)}种类型。"

        # 主要异常类型
        top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:3]
        type_strs = []
        for t, c in top_types:
            info = self.kb.get_anomaly_info(t)
            type_strs.append(f"{info.get('name_cn', t)}({c}个)")
        summary += f" 主要异常: {'、'.join(type_strs)}。"

        # 故障场景
        if scenarios:
            top_scenario = scenarios[0]
            summary += f" 最可能的故障场景: {top_scenario['fault_name']}"
            summary += f"(置信度{top_scenario['confidence']:.0%})。"

        # 严重度
        severity_cn = {"critical": "危急", "high": "严重", "medium": "中等", "low": "轻微"}
        summary += f" 整体严重度: {severity_cn.get(severity, severity)}。"

        return summary

    def _empty_result(self) -> Dict:
        """空结果"""
        return {
            "fault_scenarios": [],
            "anomaly_groups": [],
            "root_causes": [],
            "severity": "low",
            "summary": "未检测到异常。",
            "total_anomalies": 0,
            "unique_types": 0,
        }
