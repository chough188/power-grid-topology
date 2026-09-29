# -*- coding: utf-8 -*-
"""增量检测（Phase 5）。"""
from __future__ import annotations
import hashlib
import json
import time
from typing import Dict, Any, Optional, List

_CACHE: Dict[str, Any] = {}


def _hash_state(net_state: Dict[str, Any]) -> str:
    key_fields = {
        "bus_count": len(net_state.get("buses", [])),
        "line_count": len(net_state.get("lines", [])),
        "meas_count": len(net_state.get("measurements", [])),
        "vm_sum": sum(b.get("vm_pu", 0) for b in net_state.get("buses", [])),
    }
    s = json.dumps(key_fields, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()


def get_cached(state_hash: str) -> Optional[Dict[str, Any]]:
    return _CACHE.get(state_hash)


def set_cached(state_hash: str, result: Dict[str, Any]) -> None:
    _CACHE[state_hash] = {"result": result, "ts": time.time()}


def run_detect_incremental(prev_state: Optional[Dict[str, Any]],
                          new_state: Dict[str, Any]) -> Dict[str, Any]:
    """增量检测。"""
    new_hash = _hash_state(new_state)
    if prev_state:
        prev_hash = _hash_state(prev_state)
        if new_hash == prev_hash:
            cached = get_cached(new_hash)
            if cached:
                return {
                    "anomalies": cached["result"].get("anomalies", []),
                    "cached": True,
                    "new_anomalies": [],
                }

    from api import service
    net_name = new_state.get("network", "case14")
    r = service.run_detect(net_name, inject_anomalies=False, anomaly_count=0, random_seed=42)
    result = {
        "anomalies": r.get("anomalies", []),
        "cached": False,
        "new_anomalies": r.get("anomalies", []),
    }
    set_cached(new_hash, result)
    return result


if __name__ == "__main__":
    import time as _t
    t0 = _t.time()
    r1 = run_detect_incremental(None, {"network": "case14", "buses": [{"vm_pu":1.0}]*14, "lines":[], "measurements":[]})
    t1 = _t.time()
    print(f"First run (full): {(t1-t0)*1000:.0f}ms, {len(r1['anomalies'])} anomalies")