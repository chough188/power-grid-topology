# -*- coding: utf-8 -*-
"""ELK-shaped audit log indexer — converts JSONL audit records to ECS-style JSON.

v18.7.12-stack-consolidated — reads output/llm_calls/*.jsonl and emits one
ECS-ish JSON document per record to output/llm_calls/elk/{YYYY-MM-DD}.jsonl.

Designed to be ingested by Logstash/Filebeat. Field layout follows the
Elastic Common Schema (ECS) where reasonable:
  @timestamp, ecs.version, event.kind, event.category,
  service.name, service.version,
  host.hostname, process.pid,
  llm.stack, llm.source, llm.schema_name, llm.caller, llm.call_id,
  llm.success, llm.fallback_used,
  llm.gates_passed, llm.gates_failed, llm.flagged_strings,
  llm.elapsed_s, llm.tokens_in, llm.tokens_out, llm.raw_len,
  llm.raw_truncated

Run: py -3 -m llm_assistant.audit_log_indexer [--days 7] [--out <dir>]
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Iterable

from . import audit

logger = logging.getLogger(__name__)

ECS_VERSION = "8.11.0"
SERVICE_NAME = "power-topology-llm"
SERVICE_VERSION = "v18.7.12-stack-consolidated"


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _pid() -> int:
    try:
        return os.getpid()
    except Exception:
        return 0


def to_ecs(record: Dict[str, Any], hostname: str = "", pid: int = 0) -> Dict[str, Any]:
    """Convert an audit JSONL record to an ECS-shaped dict.

    The original record's fields are preserved under `llm.*`.
    """
    raw_ts = record.get("ts", datetime.now().isoformat(timespec="seconds"))
    try:
        # record ts is "2026-07-04T13:59:35" — promote to full ISO with TZ
        dt = datetime.fromisoformat(raw_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ecs_ts = dt.astimezone(timezone.utc).isoformat()
    except Exception:
        ecs_ts = datetime.now(timezone.utc).isoformat()

    gates_passed = list(record.get("gates_passed") or [])
    gates_failed = list(record.get("gates_failed") or [])

    return {
        "@timestamp": ecs_ts,
        "ecs": {"version": ECS_VERSION},
        "event": {
            "kind": "event",
            "category": ["process"],
            "type": ["info"] if record.get("success") else ["error"],
            "outcome": "success" if record.get("success") else "failure",
            "action": "llm.postprocess",
        },
        "service": {
            "name": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "type": "agent",
        },
        "host": {
            "hostname": hostname or _hostname(),
            "os": {"platform": platform.platform()},
        },
        "process": {
            "pid": pid or _pid(),
            "name": "python",
        },
        "llm": {
            "call_id": record.get("call_id", ""),
            "stack": record.get("stack", "?"),
            "source": record.get("source", ""),
            "caller": record.get("caller", ""),
            "schema_name": record.get("schema_name", ""),
            "success": bool(record.get("success")),
            "fallback_used": bool(record.get("fallback_used")),
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
            "flagged_strings": list(record.get("flagged_strings") or []),
            "elapsed_s": float(record.get("elapsed_s", 0.0) or 0.0),
            "tokens_in": int(record.get("tokens_in", 0) or 0),
            "tokens_out": int(record.get("tokens_out", 0) or 0),
            "raw_len": int(record.get("raw_len", 0) or 0),
            "raw_truncated": bool(record.get("raw_truncated")),
            # raw_preview and payload are intentionally dropped here
            # (raw_preview is large; payload is in original audit, re-derive)
        },
    }


def iter_records(days: int = 7) -> Iterable[Dict[str, Any]]:
    """Iterate audit records within the last `days` days."""
    cutoff_ts = datetime.now().timestamp() - days * 86400
    for fp in sorted(audit.AUDIT_DIR.glob("*.jsonl"), reverse=True):
        if not fp.exists():
            continue
        # date in filename: YYYY-MM-DD.jsonl
        try:
            file_date = datetime.strptime(fp.stem, "%Y-%m-%d").timestamp()
            if file_date < cutoff_ts - 86400:
                continue
        except ValueError:
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def index(days: int = 7, out_dir: Path = None) -> Dict[str, int]:
    """Read recent audit JSONL, write ECS JSONL per day. Returns counts."""
    out_dir = out_dir or (audit.AUDIT_DIR / "elk")
    out_dir.mkdir(parents=True, exist_ok=True)

    hostname = _hostname()
    pid = _pid()
    counts: Dict[str, int] = {}
    handles: Dict[str, Any] = {}

    try:
        for rec in iter_records(days=days):
            ecs_doc = to_ecs(rec, hostname=hostname, pid=pid)
            day = (rec.get("ts") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
            out_path = out_dir / f"{day}.jsonl"
            if day not in handles:
                handles[day] = open(out_path, "a", encoding="utf-8")
            handles[day].write(json.dumps(ecs_doc, ensure_ascii=False) + "\n")
            counts[day] = counts.get(day, 0) + 1
    finally:
        for f in handles.values():
            f.close()

    total = sum(counts.values())
    logger.info("indexed %d records across %d days -> %s", total, len(counts), out_dir)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Index LLM audit JSONL to ECS JSONL")
    parser.add_argument("--days", type=int, default=7, help="window in days (default 7)")
    parser.add_argument("--out", type=str, default=None, help="output dir (default output/llm_calls/elk)")
    args = parser.parse_args()
    out = Path(args.out) if args.out else None
    counts = index(days=args.days, out_dir=out)
    print(json.dumps({"indexed_by_day": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
