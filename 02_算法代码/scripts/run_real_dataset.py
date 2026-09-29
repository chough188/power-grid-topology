#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the official pipeline on the real competition dataset.

Usage:
    python -X utf8 scripts\\run_real_dataset.py <data_root> <output_dir>

<data_root> is the folder that contains one SQL sub-directory and one SVG
sub-directory (e.g. the released dataset). Backup directories (names
containing ``backup`` or starting with ``_``) are skipped automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def find_data_dirs(data_root: Path) -> tuple[list[str], list[str]]:
    """Return (sql_files, svg_files) found under first-level sub-directories."""
    sql_files: list[str] = []
    svg_files: list[str] = []
    if not data_root.is_dir():
        raise SystemExit(f"data root not found: {data_root}")
    for child in sorted(data_root.iterdir()):
        if not child.is_dir():
            continue
        name_l = child.name.lower()
        if "backup" in name_l or name_l.startswith("_"):
            print(f"[skip] {child.name} (backup)")
            continue
        sqls = sorted(p for p in child.rglob("*.sql") if p.is_file())
        svgs = sorted(p for p in child.rglob("*.svg") if p.is_file())
        if sqls:
            sql_files.extend(str(p) for p in sqls)
            print(f"[sql ] {child.name}: {len(sqls)} files")
        if svgs:
            svg_files.extend(str(p) for p in svgs)
            print(f"[svg ] {child.name}: {len(svgs)} files")
    return sql_files, svg_files


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    data_root = Path(sys.argv[1]).expanduser().resolve()
    output_dir = Path(sys.argv[2]).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    sql_files, svg_files = find_data_dirs(data_root)
    if not sql_files:
        print("[ERROR] no .sql inputs found")
        return 1
    print(f"total: {len(sql_files)} sql + {len(svg_files)} svg")

    os_environ_output = output_dir
    import os
    os.environ["DIANLI_OUTPUT_ROOT"] = str(os_environ_output)

    from gui.auto_pipeline import ALL_TASKS, RunOptions, run_pipeline

    options = RunOptions(
        task_codes=ALL_TASKS,
        write_xlsx=True,
        run_score=True,
        use_synthetic_if_empty=False,
    )
    result = run_pipeline(
        file_paths=[*sql_files, *svg_files],
        output_dir=output_dir,
        options=options,
    )

    print("=" * 60)
    print("PIPELINE RESULT")
    print("=" * 60)
    print(f"source_mode      : {result.source_mode}")
    print(f"detected_tables  : {', '.join(result.detected_tables)}")
    print(f"extra_tables     : {', '.join(result.extra_tables) or '-'}")
    print(f"total_records    : {result.total_records}")
    print(f"xlsx             : {result.xlsx_path}")
    print(f"score_overall    : {result.score_overall}")
    print(f"snapshot         : {result.snapshot_path}")
    print(f"manifest         : {result.manifest_path}")
    print("\nrecords by task:")
    for code in sorted(result.records_by_task):
        print(f"  {code}: {len(result.records_by_task[code])}")
    print(f"\nsvg beautified   : {len(result.svg_outputs)}")
    bad_topo = [o for o in result.svg_outputs if o.get("topology_ok") == "False"]
    print(f"svg topo broken  : {len(bad_topo)}")
    print(f"\nwarnings ({len(result.warnings)}):")
    for w in result.warnings[:40]:
        print(f"  - {w}")
    if len(result.warnings) > 40:
        print(f"  ... +{len(result.warnings) - 40} more (see run_manifest.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
