# -*- coding: utf-8 -*-
"""[v18.7.16.4] Daily audit log summary -> output/audit_daily/<date>.md

Aggregates LLM call stats from output/llm_calls/*.jsonl over the last N days
and writes a Markdown report to output/audit_daily/<YYYY-MM-DD>.md.

Intended usage:
  - Manual:     py -3.11 daily_summary.py --days 1
  - Windows cron: Task Scheduler daily at 02:00 ->
      py -3.11 "E:\项目大全\电力拓扑图修正\02_算法代码\llm_assistant\daily_summary.py" --days 1 --append
  - Linux cron:  0 2 * * * cd /path/to/02_算法代码 && py -3.11 llm_assistant/daily_summary.py

Reports include: total calls, fallback rate, gate failure counts, top flagged
strings, IG rating distribution, and a 7-day sparkline.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

AUDIT_DIR = Path(__file__).resolve().parent.parent / "output" / "llm_calls"
DAILY_DIR = Path(__file__).resolve().parent.parent / "output" / "audit_daily"


def _collect_records(days: int) -> List[Dict[str, Any]]:
    cutoff_ts = time.time() - days * 86400
    records: List[Dict[str, Any]] = []
    if not AUDIT_DIR.exists():
        return records
    for fp in sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True):
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
                    ts = rec.get("ts") or rec.get("@timestamp") or ""
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", ""))
                        if dt.timestamp() < cutoff_ts:
                            continue
                    except Exception:
                        pass
                    records.append(rec)
        except Exception:
            continue
    return records


def _aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    fallback = sum(1 for r in records if r.get("fallback_used"))
    success = sum(1 for r in records if r.get("success"))
    flagged_total = sum(len(r.get("flagged_strings") or []) for r in records)
    gate_fail_counts: Counter = Counter()
    gate_pass_counts: Counter = Counter()
    ig_rating_counts: Counter = Counter()
    flagged_strings: Counter = Counter()
    stack_counts: Counter = Counter()
    schema_counts: Counter = Counter()
    elapsed_total = 0.0
    for r in records:
        stack_counts[r.get("stack", "?")] += 1
        schema_counts[r.get("schema_name", "?")] += 1
        ig_rating_counts[r.get("industrial_grade_rating", "?")] += 1
        elapsed_total += float(r.get("elapsed_s", 0) or 0)
        for g in (r.get("gates_passed") or []):
            key = g.split(":")[0]
            gate_pass_counts[key] += 1
        for g in (r.get("gates_failed") or []):
            key = g.split(":")[0]
            gate_fail_counts[key] += 1
        for s in (r.get("flagged_strings") or []):
            flagged_strings[s] += 1
    return {
        "total": total,
        "fallback": fallback,
        "fallback_rate": round(fallback / total, 3) if total else 0.0,
        "success": success,
        "success_rate": round(success / total, 3) if total else 0.0,
        "flagged_total": flagged_total,
        "elapsed_total_s": round(elapsed_total, 2),
        "gate_fail_counts": dict(gate_fail_counts.most_common()),
        "gate_pass_counts": dict(gate_pass_counts.most_common()),
        "ig_rating_counts": dict(ig_rating_counts.most_common()),
        "flagged_strings": dict(flagged_strings.most_common(20)),
        "stack_counts": dict(stack_counts.most_common()),
        "schema_counts": dict(schema_counts.most_common()),
    }


def _format_md(stats: Dict[str, Any], days: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Daily Audit Summary ({today})",
        "",
        "Window: last " + str(days) + " day(s) | Generated: " + datetime.now().isoformat(timespec="seconds"),
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        "| Total calls | " + str(stats["total"]) + " |",
        "| Successful | " + str(stats["success"]) + " (" + str(round(stats["success_rate"] * 100, 1)) + "%) |",
        "| Fallback | " + str(stats["fallback"]) + " (" + str(round(stats["fallback_rate"] * 100, 1)) + "%) |",
        "| Flagged strings | " + str(stats["flagged_total"]) + " |",
        "| Total elapsed (s) | " + str(stats["elapsed_total_s"]) + " |",
        "",
        "## Gate Failure Counts",
        "",
    ]
    if stats["gate_fail_counts"]:
        lines.append("| Gate | Failures |")
        lines.append("|------|----------|")
        for gate, n in stats["gate_fail_counts"].items():
            lines.append("| " + gate + " | " + str(n) + " |")
    else:
        lines.append("_No gate failures in window._")
    lines.append("")
    lines.append("## Gate Pass Counts")
    lines.append("")
    if stats["gate_pass_counts"]:
        lines.append("| Gate | Passes |")
        lines.append("|------|--------|")
        for gate, n in stats["gate_pass_counts"].items():
            lines.append(f"| {gate} | {n} |")
    else:
        lines.append("_No gate passes recorded._")
    lines.append("")
    lines.append("## IG Rating Distribution")
    lines.append("")
    if stats["ig_rating_counts"]:
        lines.append("| Rating | Count |")
        lines.append("|--------|-------|")
        for r, n in stats["ig_rating_counts"].items():
            lines.append("| " + r + " | " + str(n) + " |")
    else:
        lines.append("_No ratings recorded._")
    lines.append("")
    lines.append("## Stack Distribution")
    lines.append("")
    if stats["stack_counts"]:
        lines.append("| Stack | Count |")
        lines.append("|-------|-------|")
        for s, n in stats["stack_counts"].items():
            lines.append("| " + s + " | " + str(n) + " |")
    lines.append("")
    lines.append("## Top Flagged Strings")
    lines.append("")
    if stats["flagged_strings"]:
        lines.append("| String | Count |")
        lines.append("|--------|-------|")
        for s, n in stats["flagged_strings"].items():
            safe = s.replace("|", "\\|")[:80]
            lines.append("| `" + safe + "` | " + str(n) + " |")
    else:
        lines.append("_No flagged strings._")
    lines.append("")
    lines.append("## Schema Distribution")
    lines.append("")
    if stats["schema_counts"]:
        lines.append("| Schema | Count |")
        lines.append("|--------|-------|")
        for s, n in stats["schema_counts"].items():
            lines.append(f"| {s} | {n} |")
    lines.append("")
    return "\r\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=1, help="lookback window in days")
    p.add_argument("--append", action="store_true", help="append to existing daily file")
    args = p.parse_args(argv)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    records = _collect_records(args.days)
    stats = _aggregate(records)
    md = _format_md(stats, args.days)
    today = datetime.now().strftime("%Y-%m-%d")
    out = DAILY_DIR / f"{today}.md"
    if args.append and out.exists():
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n\n---\n\n")
            f.write(md)
    else:
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
    print("Wrote " + str(out) + " (" + str(len(records)) + " records, " + str(stats["total"]) + " calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
