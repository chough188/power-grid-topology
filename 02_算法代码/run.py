# -*- coding: utf-8 -*-
"""一站式官方轨 CLI: 自动检测输入 + 运行全部 12 任务 + 自评 + 输出 xlsx。

用法:
    python run.py                                 # 自动找 data/snapshot.json 或 snapshot_v4.json
    python run.py path/to/snapshot.json            # 指定输入
    python run.py path/to/snapshot.json -o out/     # 指定输出目录
    python run.py --tasks 1.1,1.2,1.3              # 指定任务
    python run.py --no-grade                        # 跳过自评
    python run.py --inject                           # self_grade 注入异常再评分
    python run.py --list                            # 列出 16 个任务和状态

环境要求:
    - Python 3.13+
    - 工作目录 02_算法代码/

输出 (在 _dianli_output/<snapshot>_<timestamp>/):
    - official_result.xlsx   6 sheets 标准输出
    - run_summary.json        详细记录
    - run_manifest.json       运行清单
    - score.txt               自评分数
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

PY = sys.executable
ROOT = HERE  # alias for subprocess cwd


def find_default_snapshot() -> Path | None:
    """Search for default snapshot.json or snapshot_v4.json in data/."""
    candidates = [
        HERE / "data" / "snapshot_v4.json",
        HERE / "data" / "snapshot.json",
        HERE / "data" / "_bisha_snapshot.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    data_dir = HERE / "data"
    if data_dir.exists():
        for p in sorted(data_dir.glob("*.json")):
            if "snapshot" in p.stem.lower():
                return p
    return None


def cmd_list(_args) -> int:
    """Print all 16 catalog tasks and their status."""
    from tasks_official.catalog import OFFICIAL_TASKS
    print("=" * 60)
    print("Official Tasks (CP-202606)")
    print("=" * 60)
    print(f"{'Code':5s} {'Status':6s} {'Name':35s}")
    print("-" * 60)
    for t in OFFICIAL_TASKS:
        flag = "✓" if t.implementation_status == "ready" else "✗"
        print(f"  {t.code:5s} {flag} {t.implementation_status:5s} {t.name}")
    print()
    print(f"Total: {len(OFFICIAL_TASKS)} tasks, "
          f"{sum(1 for t in OFFICIAL_TASKS if t.implementation_status == 'ready')} ready")
    return 0


def cmd_grade(args) -> int:
    """Run self-grade on snapshot."""
    from data_loader.snapshot import load_json_snapshot
    from tasks_official.execution import OfficialRunner
    from tasks_official.registry import LazyTaskRegistry
    from tasks_official.self_grade import ALL_TASKS
    import re

    snap = Path(args.snapshot)
    if not snap.exists():
        print(f"ERROR: snapshot not found: {snap}")
        return 2
    print(f"Snapshot: {snap}")
    ds = load_json_snapshot(str(snap))
    ds.validate()

    runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
    result = runner.run(list(ALL_TASKS), ds)
    recs = [r for rs in result.records_by_task.values() for r in rs]
    print(f"\nTotal records: {len(recs)}")
    print("\nPer-task:")
    for code in ALL_TASKS:
        rs = result.records_by_task.get(code, ())
        print(f"  {code:5s}  {len(rs):4d}")

    # Compute self-grade inline
    from tasks_official.self_grade import parse_sql, _exemption_score_from_source, KEY_TASKS
    hit = sum(1 for c in ALL_TASKS if len(result.records_by_task.get(c, ())) > 0)
    sqls = [r.correction_sql for r in recs if r.correction_sql]
    sql_ok = sum(1 for s in sqls if parse_sql(s))
    exempt = _exemption_score_from_source()
    key_hit = sum(1 for c in KEY_TASKS if len(result.records_by_task.get(c, ())) > 0)

    coverage = 0.40 * hit / len(ALL_TASKS)
    exempt_score = 0.20 * exempt / 8
    sql_score = 0.20 * sql_ok / max(len(sqls), 1)
    key_score = 0.20 * key_hit / 4
    total = coverage + exempt_score + sql_score + key_score

    print(f"\nSelf-grade breakdown:")
    print(f"  coverage: {hit}/{len(ALL_TASKS)}  ({coverage:.3f})")
    print(f"  exempt:   {exempt}/8  ({exempt_score:.3f})")
    print(f"  SQL:      {sql_ok}/{len(sqls)}  ({sql_score:.3f})")
    print(f"  key:      {key_hit}/{len(KEY_TASKS)}  ({key_score:.3f})")
    print(f"  TOTAL:    {total:.4f}")
    if total >= 0.90:
        rating = "优"
    elif total >= 0.75:
        rating = "良"
    elif total >= 0.60:
        rating = "中"
    else:
        rating = "差"
    print(f"  RATING:   {rating}")
    return 0


def cmd_run(args) -> int:
    """One-click: load + run all 12 tasks + xlsx + grade."""
    snap_arg = args.snapshot
    if snap_arg is None:
        snap = find_default_snapshot()
        if snap is None:
            print("ERROR: no snapshot found. Place one at data/snapshot.json or pass --snapshot.")
            return 2
    else:
        snap = Path(snap_arg)
    if not snap.exists():
        print(f"ERROR: snapshot not found: {snap}")
        return 2

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        out_dir = Path(args.output)
    else:
        output_root = Path(os.environ.get("DIANLI_OUTPUT_ROOT",
                                         str(HERE.parent.parent / "_dianli_output")))
        out_dir = output_root / f"{snap.stem}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DIANLI_OUTPUT_ROOT"] = str(out_dir.resolve())

    print("=" * 70)
    print(f"CP-202606 一站式运行 · {ts}")
    print("=" * 70)
    print(f"  Snapshot: {snap}")
    print(f"  Output:   {out_dir}")
    print(f"  Tasks:    {args.tasks or 'all 12 (default)'}")
    print()

    from gui.auto_pipeline import run_pipeline, ALL_TASKS

    task_codes = (
        tuple(t.strip() for t in args.tasks.split(",") if t.strip())
        if args.tasks else ALL_TASKS
    )
    file_paths = [str(snap)]

    options = type("Opts", (), {
        "task_codes": task_codes,
        "write_xlsx": True,
        "run_score": not args.no_grade,
        "use_synthetic_if_empty": False,
        # 与 gui.auto_pipeline.RunOptions 默认一致：开启 5.3 自动出图
        "run_auto_draw": True,
    })()

    # If --inject, also run self-grade with --inject after pipeline
    if args.inject and not args.no_grade:
        print()
        print("=" * 70)
        print("JUDGE.md §9.1 self-grade with anomaly injection")
        print("=" * 70)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(HERE)
        inject_r = subprocess.run(
            [PY, "-m", "tasks_official.self_grade", str(snap), "--inject"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
        )
        print(inject_r.stdout)
        if inject_r.returncode != 0:
            print(f"[warn] injected self-grade rc={inject_r.returncode}")
    t0 = time.time()
    try:
        result = run_pipeline(file_paths=file_paths, output_dir=out_dir, options=options)
    except Exception as e:
        print(f"ERROR: pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    elapsed = time.time() - t0

    print()
    print("=" * 70)
    print("运行结果")
    print("=" * 70)
    print(f"  数据源模式:  {result.source_mode}")
    print(f"  检出表数:    {len(result.detected_tables)}")
    print(f"  总记录数:    {result.total_records}")
    print(f"  耗时:        {elapsed:.2f}s")

    print("\n  各任务记录数:")
    for code in sorted(result.records_by_task.keys()):
        print(f"    {code:5s}: {len(result.records_by_task[code]):4d} 条")

    if result.xlsx_path:
        xlsx = Path(result.xlsx_path)
        print(f"\n  ✅ xlsx: {xlsx} ({xlsx.stat().st_size:,} bytes)")
    if result.score_overall is not None:
        print(f"  ✅ 自评分: {result.score_overall:.4f}")

    if result.warnings:
        print(f"\n  警告 ({len(result.warnings)} 条):")
        for w in result.warnings[:5]:
            print(f"    ⚠ {w}")
        if len(result.warnings) > 5:
            print(f"    ... 共 {len(result.warnings)} 条")

    summary_path = out_dir / "run_summary.json"
    summary = {
        "timestamp": datetime.now().isoformat(),
        "snapshot": str(snap),
        "output_dir": str(out_dir),
        "elapsed_sec": round(elapsed, 2),
        "task_codes": list(task_codes),
        "source_mode": result.source_mode,
        "total_records": result.total_records,
        "records_by_task": {k: len(v) for k, v in result.records_by_task.items()},
        "xlsx_path": str(result.xlsx_path) if result.xlsx_path else None,
        "score_overall": result.score_overall,
        "warnings_count": len(result.warnings),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\n  ✅ 摘要: {summary_path}")
    print(f"\n{'=' * 70}")
    print("完成！")
    print(f"{'=' * 70}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CP-202606 一站式官方轨 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                                 一键（自动找 data/ 下 snapshot）
  python run.py data/snapshot_v4.json            指定输入
  python run.py data/snapshot_v4.json -o out/   指定输出
  python run.py --tasks 1.1,1.2,1.3            指定任务子集
  python run.py --no-grade                       跳过自评
  python run.py --list                           列出 16 个任务
  python run.py --grade data/snapshot_v4.json    只跑自评
        """,
    )
    parser.add_argument("snapshot", nargs="?", default=None,
                        help="Snapshot file path (default: auto-detect from data/)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory (default: _dianli_output/<snap>_<ts>/)")
    parser.add_argument("--tasks", default=None,
                        help="Comma-separated task codes (default: all 12)")
    parser.add_argument("--no-grade", action="store_true",
                        help="Skip self-grade scoring")
    parser.add_argument("--inject", action="store_true",
                        help="Apply anomaly_injection in self_grade (JUDGE.md §9.1)")
    parser.add_argument("--list", action="store_true",
                        help="List all catalog tasks and exit")
    parser.add_argument("--grade", default=None, metavar="SNAPSHOT",
                        help="Run self-grade only on given snapshot")
    args = parser.parse_args()

    if args.list:
        return cmd_list(args)
    if args.grade:
        args.snapshot = args.grade
        return cmd_grade(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())