# -*- coding: utf-8 -*-
"""异常案例库（Phase 8.2）。"""
from __future__ import annotations
import json
import os
import time
from typing import Dict, Any, List, Optional

CASE_DIR = os.path.join(os.path.dirname(__file__), "case_library")


def _ensure_dir():
    os.makedirs(CASE_DIR, exist_ok=True)
    for t in ["topo_interrupt", "voltage_collapse", "harmonic_pollution"]:
        os.makedirs(os.path.join(CASE_DIR, t), exist_ok=True)


def add_case(anomaly_type: str, network: str, ground_truth: Dict[str, Any],
             detection_result: Dict[str, Any], root_cause: str = "",
             fix_action: str = "", lessons: str = "") -> str:
    """添加一个案例。"""
    _ensure_dir()
    case_id = f"CASE-{int(time.time()*1000)}"
    case = {
        "id": case_id,
        "anomaly_type": anomaly_type,
        "network": network,
        "ground_truth": ground_truth,
        "detection_result": detection_result,
        "root_cause": root_cause,
        "fix_action": fix_action,
        "lessons": lessons,
        "created_at": time.time(),
    }
    sub = os.path.join(CASE_DIR, anomaly_type)
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, f"{case_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    return case_id


def query_similar(current_state: Dict[str, Any], anomaly_type: str,
                 top_k: int = 5) -> List[Dict[str, Any]]:
    """查询相似案例。简单实现：返回同类型的最近案例。"""
    _ensure_dir()
    sub = os.path.join(CASE_DIR, anomaly_type)
    if not os.path.exists(sub):
        return []
    files = sorted(os.listdir(sub), reverse=True)[:top_k]
    out = []
    for f in files:
        if f.endswith(".json"):
            with open(os.path.join(sub, f), encoding="utf-8") as fp:
                out.append(json.load(fp))
    return out


def update_feedback(case_id: str, field: str, value: Any) -> bool:
    """更新案例反馈。"""
    _ensure_dir()
    for t in os.listdir(CASE_DIR):
        sub = os.path.join(CASE_DIR, t)
        if not os.path.isdir(sub):
            continue
        path = os.path.join(sub, f"{case_id}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                case = json.load(f)
            case[field] = value
            case["updated_at"] = time.time()
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(case, fp, ensure_ascii=False, indent=2)
            return True
    return False


def list_cases(anomaly_type: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    """列出案例。"""
    _ensure_dir()
    out = []
    if anomaly_type:
        subs = [os.path.join(CASE_DIR, anomaly_type)]
    else:
        subs = [os.path.join(CASE_DIR, t) for t in os.listdir(CASE_DIR)
                if os.path.isdir(os.path.join(CASE_DIR, t))]
    for sub in subs:
        if not os.path.exists(sub):
            continue
        for f in sorted(os.listdir(sub), reverse=True)[:limit]:
            if f.endswith(".json"):
                with open(os.path.join(sub, f), encoding="utf-8") as fp:
                    out.append(json.load(fp))
    return out[:limit]


if __name__ == "__main__":
    cid = add_case(
        "topo_interrupt", "case118",
        ground_truth={"location": "line_15", "expected_conf": 0.95},
        detection_result={"location": "line_15", "detected_conf": 0.93},
        root_cause="switch_open",
        fix_action="close switch",
        lessons="例行巡检发现"
    )
    print(f"Added case: {cid}")

    similar = query_similar({}, "topo_interrupt", top_k=3)
    print(f"Similar cases: {len(similar)}")
    for c in similar:
        print(f"  {c['id']}: {c['root_cause']}")