#!/usr/bin/env python3
"""Daily audit summary script — designed for Task Scheduler.

Usage: py -3 E:\\path\\to\\daily_summary_run.py [days]
"""
import sys
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
# llm_assistant package lives at PROJECT_DIR/llm_assistant/, so cwd must be PROJECT_DIR
PROJECT_DIR = SCRIPT_DIR.parent
LLM_ASSISTANT_DIR = PROJECT_DIR / "llm_assistant"


def run_module(module: str, args: list) -> int:
    cmd = ["py", "-3", "-m", module] + args
    print(f"[{datetime.now().isoformat(timespec='seconds')}] running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_DIR), check=False, capture_output=True, text=True, encoding="utf-8")
        print(f"  exit code: {result.returncode}")
        if result.stdout:
            print(f"  stdout: {result.stdout.strip()[:500]}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()[:500]}")
        return result.returncode
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return 1


def main() -> int:
    days = 1
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"invalid days arg: {sys.argv[1]}")
            return 1

    rc = 0
    # Step 1: index recent audit logs into ELK format
    rc |= run_module("llm_assistant.audit_log_indexer", ["--days", "7"])
    # Step 2: roll up daily summary for the last N days
    rc |= run_module("llm_assistant.daily_summary", ["--days", str(days)])

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
