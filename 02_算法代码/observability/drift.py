# -*- coding: utf-8 -*-
"""Drift detection (F.3).

KS 检验对比 recent confidence 分布 vs baseline (前一段窗口)。
来源: audit log 中的 detect 事件 confidence 字段。
"""
from __future__ import annotations
import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUDIT_LOG = DATA_DIR / "audit.log"


def _read_window(start: float, end: float) -> list[float]:
    if not AUDIT_LOG.exists():
        return []
    out: list[float] = []
    try:
        with open(AUDIT_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts = d.get("ts") or d.get("timestamp") or 0
                if isinstance(ts, str):
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts.replace("Z", "")).timestamp()
                    except Exception:
                        continue
                if start <= ts <= end and d.get("event") == "detect":
                    c = d.get("confidence")
                    if c is not None:
                        out.append(float(c))
    except Exception:
        return []
    return out


def _ks_2sample(a: list[float], b: list[float]) -> tuple[float, float]:
    """精简版两样本 KS: 返回 (D, p_approx)。样本数都太小时返回 (0, 1.0)。"""
    if len(a) < 5 or len(b) < 5:
        return 0.0, 1.0
    a_sorted = sorted(a)
    b_sorted = sorted(b)
    i = j = 0
    n1, n2 = len(a_sorted), len(b_sorted)
    d = 0.0
    while i < n1 and j < n2:
        if a_sorted[i] <= b_sorted[j]:
            v = a_sorted[i]; i += 1
        else:
            v = b_sorted[j]; j += 1
        d = max(d, abs(i / n1 - j / n2))
        if i < n1 and a_sorted[i] == v: pass
    # 近似 p-value（保守阈值 0.05 对应 D > 1.36 * sqrt((n1+n2)/(n1*n2))）
    import math
    crit = 1.36 * math.sqrt((n1 + n2) / (n1 * n2))
    p_approx = 0.05 if d > crit else 0.5
    return d, p_approx


def detect_drift(days: int = 7) -> dict:
    now = time.time()
    recent = _read_window(now - days * 86400, now)
    baseline = _read_window(now - 2 * days * 86400, now - days * 86400)
    d, p = _ks_2sample(baseline, recent)
    return {
        "status": "drift" if d > 0.2 else "stable",
        "ks_stat": round(d, 4),
        "p_value": round(p, 4),
        "recent_samples": len(recent),
        "baseline_samples": len(baseline),
        "window_days": days,
        "as_of": now,
    }


__all__ = ["detect_drift"]
