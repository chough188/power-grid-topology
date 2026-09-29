# -*- coding: utf-8 -*-
"""告警时间窗聚合（A.1）。

5min 内同类 anomaly 合并成 cluster。
"""
from __future__ import annotations
import time
import uuid
from collections import defaultdict
from typing import Dict, Any, List


def _key(a):
    eid = a.get("element_id") or a.get("location", "unknown")
    return (str(eid), str(a.get("type", "unknown")))


def _severity_from_conf(conf):
    if conf >= 0.9: return "critical"
    if conf >= 0.7: return "warning"
    return "info"


def aggregate(anomalies, window_sec=300):
    """按 (element_id, anomaly_type) 在 window_sec 内聚合。

    count >= 2 才聚合 (单条仍输出 cluster 但 count=1)。
    """
    if not anomalies:
        return []
    now = time.time()
    buckets = defaultdict(list)
    for a in anomalies:
        ts = float(a.get("timestamp", now) or now)
        a["_ts"] = ts
        buckets[_key(a)].append(a)
    clusters = []
    for (eid, atype), items in buckets.items():
        if len(items) == 1:
            a = items[0]
            clusters.append({
                "cluster_id": "CL-" + uuid.uuid4().hex[:8],
                "element_id": eid,
                "type": atype,
                "count": 1,
                "first_seen": a["_ts"],
                "last_seen": a["_ts"],
                "max_confidence": float(a.get("confidence", 0.0) or 0.0),
                "avg_confidence": float(a.get("confidence", 0.0) or 0.0),
                "severity": a.get("severity") or _severity_from_conf(float(a.get("confidence", 0) or 0)),
                "root_cause_hint": a.get("root_cause", ""),
                "samples": [a],
            })
            continue
        items.sort(key=lambda x: x["_ts"])
        groups = [[items[0]]]
        for it in items[1:]:
            if it["_ts"] - groups[-1][0]["_ts"] <= window_sec:
                groups[-1].append(it)
            else:
                groups.append([it])
        for g in groups:
            if len(g) < 2:
                continue
            confs = [float(x.get("confidence", 0) or 0) for x in g]
            max_c = max(confs)
            avg_c = sum(confs) / len(confs)
            clusters.append({
                "cluster_id": "CL-" + uuid.uuid4().hex[:8],
                "element_id": eid,
                "type": atype,
                "count": len(g),
                "first_seen": g[0]["_ts"],
                "last_seen": g[-1]["_ts"],
                "max_confidence": round(max_c, 4),
                "avg_confidence": round(avg_c, 4),
                "severity": _severity_from_conf(max_c),
                "root_cause_hint": g[confs.index(max_c)].get("root_cause", ""),
                "samples": g,
            })
    clusters.sort(key=lambda x: (-x["max_confidence"], -x["count"]))
    for a in anomalies:
        a.pop("_ts", None)
    return clusters


if __name__ == "__main__":
    sample = [
        {"type":"topo_interrupt","location":"line_1","confidence":0.9,"timestamp":time.time()},
        {"type":"topo_interrupt","location":"line_1","confidence":0.85,"timestamp":time.time()+10},
        {"type":"topo_interrupt","location":"line_1","confidence":0.95,"timestamp":time.time()+60},
        {"type":"harmonic_pollution","location":"bus_5","confidence":0.6,"timestamp":time.time()},
    ]
    c = aggregate(sample, window_sec=300)
    for cl in c:
        print(cl["cluster_id"], cl["type"], cl["element_id"], "count=" + str(cl["count"]))
