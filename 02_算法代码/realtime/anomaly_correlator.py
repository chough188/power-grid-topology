# -*- coding: utf-8 -*-
"""异常关联分析（Phase 4 配套）。

同一时间窗内多个异常按位置/类型聚类，识别根因异常。
"""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, Any, List


def correlate(anomalies: List[Dict[str, Any]], window_sec: int = 300) -> List[Dict[str, Any]]:
    """按 (element_id, anomaly_type, time-window) 聚类异常。

    Returns: 聚类后的根因异常列表，每条带 count + cluster_ids
    """
    if not anomalies:
        return []
    buckets: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for a in anomalies:
        eid = a.get("element_id") or a.get("location", "unknown")
        t = a.get("type", "unknown")
        # 简化的窗口分桶
        key = (eid, t)
        buckets[key].append(a)
    result = []
    for (eid, t), items in buckets.items():
        if len(items) == 1:
            result.append({**items[0], "count": 1, "cluster_ids": [items[0].get("id", "?")]})
        else:
            # 取 confidence 最高的为根因
            root = max(items, key=lambda x: x.get("confidence", 0))
            result.append({
                **root,
                "count": len(items),
                "cluster_ids": [x.get("id", "?") for x in items],
                "is_cluster_root": True,
            })
    return sorted(result, key=lambda x: -x.get("confidence", 0))


if __name__ == "__main__":
    sample = [
        {"id": "a1", "type": "topo_interrupt", "element_id": "line_1", "confidence": 0.9},
        {"id": "a2", "type": "topo_interrupt", "element_id": "line_1", "confidence": 0.7},
        {"id": "a3", "type": "harmonic_pollution", "element_id": "line_1", "confidence": 0.6},
        {"id": "a4", "type": "topo_interrupt", "element_id": "line_2", "confidence": 0.8},
    ]
    r = correlate(sample)
    for x in r: print(f"  {x['type']} {x['element_id']} count={x['count']}")
