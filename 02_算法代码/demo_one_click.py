# -*- coding: utf-8 -*-
"""\u4e00\u952e demo: \u4f7f\u7528\u5b98\u65b9 date.sql + \u5408\u6210 SVG \u8d70\u5b8c\u6574\u7ba1\u7ebf,\u9a8c\u8bc1\u6240\u6709\u529f\u80fd\u80fd\u8d70\u901a\u3002

\u7528\u6cd5:
    python demo_one_click.py

\u8f93\u51fa\u5728 output/demo_<timestamp>/ \u4e0b:
    - snapshot.json   (\u6807\u51c6 14 \u8868\u5feb\u7167)
    - official_result.xlsx  (6 Sheet \u4e0e\u5b98\u65b9\u5b57\u8282\u7ea7\u5bf9\u9f50)
    - LINE215_test_beautified.svg  (\u7f8e\u5316\u540e SVG,\u62d3\u6251\u7b49\u4ef7)
    - run_summary.txt  (\u8fd0\u884c\u62a5\u544a)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from data_loader.svg_synth import write_synthetic_svg
from gui.auto_pipeline import run_pipeline


def main() -> int:
    date_sql = HERE.parent / "比赛要求" / "date.sql"
    if not date_sql.exists():
        print(f"\u274c \u672a\u627e\u5230 date.sql: {date_sql}")
        print("\u8bf7\u5c06\u5b98\u65b9 date.sql \u653e\u5230 \u6bd4\u8d5b\u8981\u6c42/ \u76ee\u5f55\u4e0b\u3002")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = HERE / "output" / f"demo_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 生成测试 SVG (\u5b98\u65b9 SVG \u672a\u4e0b\u53d1\u65f6\u7528)
    svg_path = out_dir / "LINE215_test.svg"
    write_synthetic_svg(svg_path, n_devices=12, seed=42)

    print("=" * 60)
    print(f"\u26a1 CP-202606 \u4e00\u952e demo \u00b7 {timestamp}")
    print("=" * 60)
    print(f"\u8f93\u5165: date.sql = {date_sql}")
    print(f"\u8f93\u5165: SVG \u5408\u6210 = {svg_path}")
    print(f"\u8f93\u51fa\u76ee\u5f55: {out_dir}")
    print()

    # 2. \u8d70\u5b8c\u6574 pipeline
    result = run_pipeline(file_paths=[date_sql, svg_path], output_dir=out_dir)

    # 3. \u5199\u8fd0\u884c\u62a5\u544a
    summary = out_dir / "run_summary.txt"
    lines = [
        f"CP-202606 \u4e00\u952e demo \u8fd0\u884c\u62a5\u544a",
        f"\u751f\u6210\u65f6\u95f4: {timestamp}",
        f"\u8f93\u5165: {date_sql.name} + {svg_path.name}",
        f"\u8f93\u51fa: {out_dir}",
        "",
        f"\u2705 \u68c0\u6d4b\u51fa {result.total_records} \u6761\u8bb0\u5f55",
        f"\u2705 \u8bc6\u522b {len(result.detected_tables)} \u5f20\u5b98\u65b9\u8868",
        f"\u2705 \u8f93\u51fa xlsx: {result.xlsx_path}",
        f"\u2705 \u81ea\u8bc4\u5206: {result.score_overall}",
        f"\u2705 SVG \u7f8e\u5316: {len(result.svg_outputs)} \u4e2a",
    ]
    for so in result.svg_outputs:
        lines.append(f"   - {Path(so['src']).name} \u2192 {Path(so['out']).name} (\u8bbe\u5907 {so['devices']}, \u62d3\u6251\u7b49\u4ef7={so['topology_ok']})")
    if result.warnings:
        lines.append("")
        lines.append("\u26a0\ufe0f \u8b66\u544a:")
        for w in result.warnings:
            lines.append(f"   - {w}")
    summary.write_text("\n".join(lines), encoding="utf-8")
    print()
    print("\n".join(lines))
    print()
    print(f"\u2705 \u8be6\u7ec6\u62a5\u544a: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
