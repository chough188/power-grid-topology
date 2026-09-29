# -*- coding: utf-8 -*-
"""Monthly KPI report (F.1).

输入: days (int)
输出: {
  "summary": str,                # 一行总结
  "period": {"start": ts, "end": ts, "days": int},
  "metrics": {
     "detect_calls": int, "anomalies": int, "fp": int,
     "workorders_created": int, "workorders_resolved": int,
     "median_close_minutes": float, "false_positive_count": int,
     "top_types": [{"type": str, "count": int}, ...]
  },
  "as_of": ts
}
"""
from __future__ import annotations
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKORDER_DB = DATA_DIR / "workorders.db"
AUDIT_LOG = DATA_DIR / "audit.log"
BENCHMARK = Path(__file__).resolve().parent.parent / "output" / "benchmark_v9_expanded.json"


def _audit_rows(days: int) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    cutoff = time.time() - days * 86400
    out: list[dict] = []
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
                if ts >= cutoff:
                    out.append(d)
    except Exception:
        return []
    return out


def _workorder_stats(days: int) -> dict:
    if not WORKORDER_DB.exists():
        return {"created": 0, "resolved": 0, "median_close_minutes": 0.0}
    con = sqlite3.connect(str(WORKORDER_DB))
    con.row_factory = sqlite3.Row
    try:
        cutoff = time.time() - days * 86400
        created = con.execute(
            "SELECT COUNT(*) c FROM workorders WHERE created_at>=? OR created_at IS NULL", (cutoff,)
        ).fetchone()["c"]
        # resolved_at may be missing on old rows
        try:
            resolved_rows = con.execute(
                "SELECT created_at, resolved_at FROM workorders WHERE resolved_at IS NOT NULL AND resolved_at>=?",
                (cutoff,),
            ).fetchall()
        except Exception:
            resolved_rows = []
        resolved = len(resolved_rows)
        closes = []
        for r in resolved_rows:
            try:
                ca = r["created_at"] or r["resolved_at"]
                closes.append((float(r["resolved_at"]) - float(ca)) / 60.0)
            except Exception:
                pass
        close_med = median(closes) if closes else 0.0
        return {
            "created": int(created),
            "resolved": int(resolved),
            "median_close_minutes": round(close_med, 2),
        }
    finally:
        con.close()


def _fp_count(days: int) -> int:
    if not WORKORDER_DB.exists():
        return 0
    con = sqlite3.connect(str(WORKORDER_DB))
    try:
        cutoff = time.time() - days * 86400
        return int(
            con.execute(
                "SELECT COUNT(*) FROM false_positive_samples WHERE created_at>=?", (cutoff,)
            ).fetchone()[0]
        )
    except Exception:
        return 0
    finally:
        con.close()


def _benchmark_summary() -> dict:
    if not BENCHMARK.exists():
        return {"avg_f1": None, "networks": 0}
    try:
        j = json.loads(BENCHMARK.read_text(encoding="utf-8").replace("﻿", ""))
        f1s = [r.get("f1", 0.0) for r in j.get("results", [])]
        return {
            "avg_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "networks": len(f1s),
        }
    except Exception:
        return {"avg_f1": None, "networks": 0}


def generate_monthly(days: int = 30) -> dict:
    rows = _audit_rows(days)
    detect_rows = [r for r in rows if r.get("event") == "detect"]
    anomalies = sum(int(r.get("anomaly_count", 0) or 0) for r in detect_rows)
    types = Counter()
    for r in detect_rows:
        for t in r.get("anomaly_types", []) or []:
            types[t] += 1
    top = [{"type": k, "count": v} for k, v in types.most_common(5)]
    wo = _workorder_stats(days)
    fp = _fp_count(days)
    bench = _benchmark_summary()
    summary = (
        f"近 {days}天检测 {len(detect_rows)} 次, "
        f"发现异常 {anomalies} 个, "
        f"创建工单 {wo['created']} 张, "
        f"闭环 {wo['resolved']} 张, "
        f"误报 {fp} 个; "
        f"benchmark avg_f1={bench.get('avg_f1')}"
    )
    return {
        "summary": summary,
        "period": {
            "start": time.time() - days * 86400,
            "end": time.time(),
            "days": days,
        },
        "metrics": {
            "detect_calls": len(detect_rows),
            "anomalies": anomalies,
            "workorders_created": wo["created"],
            "workorders_resolved": wo["resolved"],
            "median_close_minutes": wo["median_close_minutes"],
            "false_positive_count": fp,
            "top_types": top,
            "benchmark_avg_f1": bench.get("avg_f1"),
            "benchmark_networks": bench.get("networks", 0),
        },
        "as_of": time.time(),
    }


__all__ = ["generate_monthly"]
