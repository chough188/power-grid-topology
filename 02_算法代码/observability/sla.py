# -*- coding: utf-8 -*-
"""SLA metrics (F.2).

聚合可用率、检测 P50/P95、工单闭环时长等。数据来源：
- audit log (api/middleware.py)
- workorders.db
- benchmark result 摘要

Returns: {"availability_pct": float, "p50_detect_s": float, "p95_detect_s": float,
          "median_close_minutes": float, "window_days": int, "samples": int}
"""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from statistics import median

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKORDER_DB = DATA_DIR / "workorders.db"
AUDIT_LOG = DATA_DIR / "audit.log"


def _audit_window(days: int) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    cutoff = time.time() - days * 86400
    rows: list[dict] = []
    try:
        with open(AUDIT_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith("{"):
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
                if ts >= cutoff:
                    rows.append(d)
    except Exception:
        return []
    return rows


def compute_sla(days: int = 30) -> dict:
    rows = _audit_window(days)
    if not rows:
        return {
            "availability_pct": 100.0,
            "p50_detect_s": 0.0,
            "p95_detect_s": 0.0,
            "median_close_minutes": 0.0,
            "window_days": days,
            "samples": 0,
            "status": "no_audit_data",
        }
    ok = sum(1 for r in rows if r.get("status") in ("ok", 200, "OK") or r.get("ok"))
    availability = ok / max(len(rows), 1) * 100.0
    detect_times = [float(r.get("duration_s", 0.0)) for r in rows
                    if r.get("event") == "detect" and r.get("duration_s") is not None]
    detect_times.sort()
    p50 = median(detect_times) if detect_times else 0.0
    p95_idx = max(0, int(len(detect_times) * 0.95) - 1)
    p95 = detect_times[p95_idx] if detect_times else 0.0
    closes = [float(r.get("close_minutes", 0.0)) for r in rows if r.get("close_minutes") is not None]
    close_med = median(closes) if closes else 0.0
    return {
        "availability_pct": round(availability, 2),
        "p50_detect_s": round(p50, 3),
        "p95_detect_s": round(p95, 3),
        "median_close_minutes": round(close_med, 2),
        "window_days": days,
        "samples": len(rows),
        "status": "ok" if availability >= 99.0 else "degraded",
    }


__all__ = ["compute_sla"]
