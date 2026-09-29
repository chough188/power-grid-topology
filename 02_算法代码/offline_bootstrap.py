# -*- coding: utf-8 -*-
"""Offline ingestion + scoring bootstrap.

For the local LLM (Qwen3.6-35B-A3B) running offline:
  - Reads the offline-delivered 14-table JSON (or a folder of CSVs)
  - Validates against the official schema
  - Runs all 12 detectors end-to-end
  - Verifies T1/T2 必杀题
  - Generates the 6-Sheet official_result.xlsx
  - Computes the PDF 4-dimension score

Usage:
    python -X utf8 offline_bootstrap.py ingest <src_dir_or_json> <out_snapshot.json>
    python -X utf8 offline_bootstrap.py run <snapshot.json>
    python -X utf8 offline_bootstrap.py score <snapshot.json>
    python -X utf8 offline_bootstrap.py full <src_dir> <out_dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_loader.loader import OfficialDataset  # noqa: E402
from data_loader.schema import REQUIRED_TABLES, TABLE_SCHEMAS  # noqa: E402
from tasks_official.execution import OfficialRunner  # noqa: E402

ALL_TASKS = ("1.1","1.2","1.3","1.4","1.5","2.1","2.2","2.3","2.4","3.1","4.1","4.2")
KEY_TASKS = ("1.1","1.3","3.1","4.1")


def _ingest_csv_folder(src_dir: Path) -> dict:
    """Ingest a folder of CSVs (one per table)."""
    tables: dict = {name: [] for name in REQUIRED_TABLES}
    for csv_path in sorted(src_dir.glob("*.csv")):
        stem = csv_path.stem.upper()
        # Try exact match, then any case-insensitive match
        matched = None
        for table_name in REQUIRED_TABLES:
            if table_name.upper() == stem:
                matched = table_name
                break
        if matched is None:
            print(f"[warn] no matching table for {csv_path.name}, skipping")
            continue
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as fp:
            tables[matched] = [dict(r) for r in csv.DictReader(fp)]
    return tables


def _ingest_json(src_path: Path) -> dict:
    """Ingest a single JSON snapshot."""
    payload = json.loads(src_path.read_text(encoding="utf-8-sig"))
    tables = payload.get("tables", payload) if isinstance(payload, Mapping) else None
    if not isinstance(tables, Mapping):
        raise ValueError("JSON snapshot must be a table-name mapping")
    return {name: list(rows) for name, rows in tables.items()}


def cmd_ingest(src: str, out: str) -> int:
    src_path = Path(src).expanduser().resolve()
    out_path = Path(out).expanduser().resolve()
    if not src_path.exists():
        print(f"[error] source not found: {src_path}")
        return 2
    if src_path.is_dir():
        tables = _ingest_csv_folder(src_path)
    else:
        tables = _ingest_json(src_path)
    # Validate against schema (warn-only)
    for tname, schema in TABLE_SCHEMAS.items():
        rows = tables.get(tname, [])
        if rows and schema.required_fields:
            missing = set(schema.required_fields) - set(rows[0])
            if missing:
                print(f"[warn] {tname}: missing required fields {sorted(missing)}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"tables": tables}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK ingested {len(tables)} tables -> {out_path} ({out_path.stat().st_size} bytes)")
    return 0


def cmd_run(snapshot: str) -> int:
    snap_path = Path(snapshot).expanduser().resolve()
    if not snap_path.is_file():
        print(f"[error] snapshot not found: {snap_path}")
        return 2
    ds = OfficialDataset(json.loads(snap_path.read_text(encoding="utf-8-sig"))["tables"])
    ds.validate()
    runner = OfficialRunner()
    result = runner.run(list(ALL_TASKS), ds)
    total = sum(len(v) for v in result.records_by_task.values())
    print(f"OK ran {len(ALL_TASKS)} tasks -> {total} records total")
    for code in ALL_TASKS:
        n = len(result.records_by_task.get(code, ()))
        print(f"  {code}: {n} records")
    return 0


def cmd_score(snapshot: str) -> int:
    snap_path = Path(snapshot).expanduser().resolve()
    if not snap_path.is_file():
        print(f"[error] snapshot not found: {snap_path}")
        return 2
    # Delegate to v2 grader
    from tasks_official.self_grade_v2 import grade as grade_v2
    return grade_v2(snap_path)


def cmd_full(src: str, out_dir: str) -> int:
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / "snapshot.json"
    rc = cmd_ingest(src, str(snapshot))
    if rc != 0:
        return rc
    rc = cmd_run(str(snapshot))
    if rc != 0:
        return rc
    # xlsx
    ds = OfficialDataset(json.loads(snapshot.read_text(encoding="utf-8-sig"))["tables"])
    result = OfficialRunner().run(list(ALL_TASKS), ds)
    records = [r for recs in result.records_by_task.values() for r in recs]
    try:
        from output_writer.writer import write_workbook
        xlsx_path = write_workbook(records, out / "official_result.xlsx", dataset=ds)
        print(f"OK wrote xlsx {xlsx_path}")
    except Exception as exc:
        print(f"[warn] xlsx write failed: {exc}")
    # score
    rc = cmd_score(str(snapshot))
    return rc



def cmd_report(snapshot: str, out_path: str = "-") -> int:
    snap_path = Path(snapshot).expanduser().resolve()
    if not snap_path.is_file():
        print(f"[error] snapshot not found: {snap_path}")
        return 2
    from tasks_official.improvement_advisor import advise
    md = advise(snap_path)
    if out_path == "-":
        sys.stdout.write(md + chr(10))
    else:
        out = Path(out_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"OK wrote {out} ({out.stat().st_size} bytes)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline bootstrap for local LLM")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ingest = sub.add_parser("ingest", help="Ingest CSV folder or JSON -> canonical snapshot")
    p_ingest.add_argument("src")
    p_ingest.add_argument("out")
    p_run = sub.add_parser("run", help="Run all 12 detectors")
    p_run.add_argument("snapshot")
    p_score = sub.add_parser("score", help="PDF 4-dim scoring")
    p_score.add_argument("snapshot")
    p_full = sub.add_parser("full", help="ingest + run + xlsx + score")
    p_full.add_argument("src")
    p_full.add_argument("out_dir")
    p_report = sub.add_parser("report", help="generate improvement report (markdown)")
    p_report.add_argument("snapshot")
    p_report.add_argument("-o", "--out", default="-", help="output path; - for stdout")
    args = parser.parse_args(argv)
    if args.cmd == "ingest":
        return cmd_ingest(args.src, args.out)
    if args.cmd == "run":
        return cmd_run(args.snapshot)
    if args.cmd == "score":
        return cmd_score(args.snapshot)
    if args.cmd == "full":
        return cmd_full(args.src, args.out_dir)
    if args.cmd == "report":
        return cmd_report(args.snapshot, args.out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
