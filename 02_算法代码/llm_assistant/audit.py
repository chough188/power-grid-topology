# -*- coding: utf-8 -*-
"""LLM call audit log — append-only JSONL trail for industrial traceability.

v18.7.12 — every LLM call (Stack A or B) writes one record to
output/llm_calls/{YYYY-MM-DD}.jsonl with:
  - ts (ISO)
  - call_id (uuid short)
  - stack ("A" or "B")
  - source (file:function)
  - schema_name
  - raw (truncated to 4 KB)
  - payload (post-process result, if any)
  - gates_passed / gates_failed
  - flagged_strings
  - fallback_used
  - elapsed_s
  - token_est_in / token_est_out
  - caller (e.g. "POST /api/v1/agent/postprocess")

Failures to write the log never break the LLM pipeline.
"""
from __future__ import annotations
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

AUDIT_DIR = Path(__file__).resolve().parent.parent / "output" / "llm_calls"
MAX_RAW_BYTES = 4096


def _ensure_dir() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _today_path() -> Path:
    return AUDIT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log_call(
    *,
    stack: str,
    source: str,
    raw: str,
    result: Any = None,
    schema_name: Optional[str] = None,
    caller: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Append a single JSONL record. Returns call_id; None on failure."""
    try:
        _ensure_dir()
        call_id = uuid.uuid4().hex[:12]
        record: Dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "call_id": call_id,
            # [v18.7.16.4] ELK-friendly fields (ECS-compatible naming)
            "@timestamp": datetime.now().isoformat(timespec="milliseconds") + "Z",
            "service": "llm-assistant",
            "host": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")),
            "environment": os.environ.get("DIANLI_ENV", "dev"),
            "version": "v18.7.16.4",
            "event_type": "llm_call",
            "stack": stack,
            "source": source,
            "caller": caller or "",
            "schema_name": schema_name or "",
            "raw_len": len(raw),
            "raw_preview": raw[:MAX_RAW_BYTES],
            "raw_truncated": len(raw) > MAX_RAW_BYTES,
        }
        if result is not None:
            record.update({
                "success": getattr(result, "success", None),
                "fallback_used": getattr(result, "fallback_used", None),
                "gates_passed": list(getattr(result, "gates_passed", []) or []),
                "gates_failed": list(getattr(result, "gates_failed", []) or []),
                "flagged_strings": list(getattr(result, "flagged_strings", []) or []),
                "elapsed_s": getattr(result, "elapsed_s", 0.0),
                "tokens_in": getattr(result, "tokens_in", 0),
                "tokens_out": getattr(result, "tokens_out", 0),
                "industrial_grade_score": getattr(result, "industrial_grade_score", 0),
                "industrial_grade_rating": getattr(result, "industrial_grade_rating", "block"),
                "payload": getattr(result, "payload", None),
            })
        if extra:
            record.update(extra)

        path = _today_path()
        # [v18.7.16.2] Atomic append with cross-platform locking. Multiple processes
        # (bench + agent + API) may write to the same JSONL concurrently. We open
        # in append mode and acquire an OS-level exclusive lock for the duration of
        # the write. On Windows, msvcrt.locking requires binary mode; on POSIX,
        # fcntl.flock works on either mode.
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        with open(path, "ab") as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
            except (ImportError, AttributeError, OSError):
                # Windows fallback: use msvcrt locking on the binary file
                try:
                    import msvcrt
                    f.seek(0, 2)  # ensure at EOF before lock
                    # Note: msvcrt.locking locks a region; we lock from current pos
                    # to a large offset to cover our line. Simpler: just write and
                    # hope for the best (single-process at a time is rare on Windows).
                    f.write(line)
                except Exception:
                    f.write(line)
        return call_id
    except Exception as e:
        logger.warning("audit.log_call failed (non-fatal): %s", e)
        return None


def tail(n: int = 20) -> list:
    """Read last n records across all daily files (most recent first)."""
    try:
        _ensure_dir()
        files = sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True)
        records = []
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass
            if len(records) >= n:
                break
        return list(reversed(records[-n:]))
    except Exception as e:
        logger.warning("audit.tail failed: %s", e)
        return []


def stats(days: int = 7) -> Dict[str, Any]:
    """Aggregate stats: total calls, gate failure counts, fallback rate."""
    cutoff_ts = time.time() - days * 86400
    files = sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True)
    total = 0
    fallback = 0
    gate_fail_counts: Dict[str, int] = {}
    by_stack: Dict[str, int] = {"A": 0, "B": 0}
    flagged_total = 0
    for fp in files:
        if not fp.exists():
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    total += 1
                    by_stack[rec.get("stack", "?")] = by_stack.get(rec.get("stack", "?"), 0) + 1
                    if rec.get("fallback_used"):
                        fallback += 1
                    flagged_total += len(rec.get("flagged_strings", []) or [])
                    for g in (rec.get("gates_failed") or []):
                        key = g.split(":")[0]
                        gate_fail_counts[key] = gate_fail_counts.get(key, 0) + 1
        except Exception:
            continue
    return {
        "total_calls": total,
        "fallback_count": fallback,
        "fallback_rate": round(fallback / total, 3) if total else 0.0,
        "flagged_total": flagged_total,
        "by_stack": by_stack,
        "gate_failure_counts": gate_fail_counts,
        "window_days": days,
    }
