#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
官方任务一键运行 CLI
====================
打通 run_task1.bat 的核心脚本。

调用链：
    run_task1.bat -> run_official_pipeline.py -> gui.auto_pipeline.run_pipeline

功能：
    1. 自动识别输入目录中的 sql/json/csv/svg 文件
    2. 执行全部 15 个官方任务（1.1-5.3）
    3. 输出标准 6-Sheet xlsx
    4. 输出自评分报告
    5. 输出运行清单 manifest.json

用法：
    python run_official_pipeline.py --input <数据目录> --output <输出目录>
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保当前目录在路径中
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gui.auto_pipeline import RunOptions, run_pipeline, ALL_TASKS


def find_input_files(input_dir: str) -> list[str]:
    """扫描目录，找出所有有效的输入文件。"""
    p = Path(input_dir)
    files = []
    exts = (".sql", ".json", ".csv", ".svg")
    for ext in exts:
        files.extend(p.glob(f"**/*{ext}"))
    if p.is_file():
        files = [p]
    return [str(f) for f in files]


def main():
    parser = argparse.ArgumentParser(description="官方任务一键运行")
    parser.add_argument("--input", required=True, help="输入数据目录或文件")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--tasks", default=",".join(ALL_TASKS),
                        help="要执行的任务代码，逗号分隔（默认全部）")
    parser.add_argument("--no-score", action="store_true", help="跳过自评分")
    parser.add_argument("--no-xlsx", action="store_true", help="跳过 xlsx 输出")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # 设置 project_io 的输出根，避免隔离守卫拦截
    os.environ["DIANLI_OUTPUT_ROOT"] = str(output_path.resolve())

    task_codes = tuple(t.strip() for t in args.tasks.split(",") if t.strip())

    if input_path.is_dir():
        file_paths = find_input_files(str(input_path))
    else:
        file_paths = [str(input_path)]

    if not file_paths:
        print(f"[ERROR] 未在 {args.input} 中找到有效的输入文件")
        print("支持的格式: .sql, .json, .csv, .svg")
        sys.exit(1)

    print("=" * 60)
    print("官方任务一键运行")
    print("=" * 60)
    print(f"输入: {args.input}")
    print(f"输出: {args.output}")
    print(f"任务: {', '.join(task_codes)}")
    print(f"发现 {len(file_paths)} 个输入文件:")
    for fp in file_paths[:10]:
        print(f"  - {Path(fp).name}")
    if len(file_paths) > 10:
        print(f"  ... 共 {len(file_paths)} 个")
    print()

    # 运行 pipeline（让 pipeline 自己处理 xlsx，因为已设置 DIANLI_OUTPUT_ROOT）
    options = RunOptions(
        task_codes=task_codes,
        write_xlsx=not args.no_xlsx,
        run_score=not args.no_score,
        use_synthetic_if_empty=False,
    )

    try:
        result = run_pipeline(file_paths=file_paths, output_dir=output_path, options=options)
    except Exception as e:
        print(f"[ERROR] Pipeline 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 如果 pipeline 中 xlsx 因隔离守卫失败，在此回退写入
    xlsx_path = result.xlsx_path
    if not args.no_xlsx and not xlsx_path:
        try:
            from output_writer.writer import write_workbook
            flat_records = [r for recs in result.records_by_task.values() for r in recs]
            fallback_xlsx = output_path / "拓扑校验问题标准输出.xlsx"
            write_workbook(flat_records, fallback_xlsx, dataset=result.dataset, strict=False)
            xlsx_path = str(fallback_xlsx)
            print(f"[OK] 回退写入 xlsx: {fallback_xlsx}")
        except Exception as exc:
            print(f"[WARN] 回退 xlsx 写入也失败: {exc}")

    # 打印结果摘要
    print("=" * 60)
    print("运行结果")
    print("=" * 60)
    print(f"数据源模式: {result.source_mode}")
    print(f"检测到的表: {', '.join(result.detected_tables)}")
    print(f"总记录数: {result.total_records}")

    if xlsx_path:
        print(f"Excel 输出: {xlsx_path}")
    if result.score_overall is not None:
        print(f"自评分: {result.score_overall}")

    print("\n各任务记录数:")
    for task_code, records in sorted(result.records_by_task.items()):
        print(f"  {task_code}: {len(records)} 条")

    if result.warnings:
        print("\n警告:")
        for w in result.warnings[:20]:
            print(f"  ⚠ {w}")
        if len(result.warnings) > 20:
            print(f"  ... 共 {len(result.warnings)} 条警告")

    # 写摘要文件
    summary_path = output_path / "run_summary.json"
    summary = {
        "timestamp": datetime.now().isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "task_codes": list(task_codes),
        "source_mode": result.source_mode,
        "total_records": result.total_records,
        "records_by_task": {k: len(v) for k, v in result.records_by_task.items()},
        "xlsx_path": xlsx_path,
        "score_overall": result.score_overall,
        "warnings_count": len(result.warnings),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n摘要已保存: {summary_path}")

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
