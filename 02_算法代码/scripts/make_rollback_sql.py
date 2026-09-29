# -*- coding: utf-8 -*-
"""CLI wrapper: generate rollback.sql + rollback_report.md for a run dir.

Usage:
    python -X utf8 scripts/make_rollback_sql.py <official_result.xlsx> <snapshot.json> <out_dir>

Core logic lives in shared/rollback_sql.py (also wired into gui/auto_pipeline.py).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    xlsx_path, snapshot_path, out_dir = argv[1], argv[2], argv[3]
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from shared.rollback_sql import generate_rollback_sql

    summary = generate_rollback_sql(xlsx_path, snapshot_path, out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["coverage_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
