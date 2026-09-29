# -*- coding: utf-8 -*-
"""告警频率限制（A.3）。

同一 (element_id, type) 在 window_sec 内最多 max_count 次。
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from typing import Dict, Any, List

_HISTORY = defaultdict(lambda: deque(maxlen=100))


def _key(a):
    eid = a.get("element_id") or a.get("location", "unknown")
    return (str(eid), str(a.get("type", "unknown")))


def reset_history():
    _HISTORY.clear()


def throttle(anomalies, history=None, window_sec=3600, max_count=3):
    """标记超过 max_count 的告警为 _throttled=True。"""
    now = time.time()
    hist = history if history is not None else _HISTORY
    for a in anomalies:
        k = _key(a)
        ts = float(a.get("timestamp", now) or now)
        dq = hist[k]
        while dq and now - dq[0] > window_sec:
            dq.popleft()
        if len(dq) >= max_count:
            a["_throttled"] = True
            a["_throttle_skip"] = len(dq) - max_count + 1
        else:
            dq.append(ts)
            a["_throttled"] = False
    return anomalies


if __name__ == "__main__":
    reset_history()
    sample = [{"type":"topo_interrupt","location":"line_1","confidence":0.9,"timestamp":time.time()} for _ in range(5)]
    out = throttle(sample, window_sec=3600, max_count=3)
    throttled = sum(1 for a in out if a.get("_throttled"))
    print("throttled: " + str(throttled) + " / " + str(len(out)))
