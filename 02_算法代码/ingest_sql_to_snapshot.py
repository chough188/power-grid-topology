# -*- coding: utf-8 -*-
"""将 CP-202606 赛方离线交付的 date.sql（或含 *.sql 的目录）转换为
``offline_bootstrap.py`` / ``run.py`` 消费的规范 14 表 ``snapshot.json``。

零额外依赖：仅 Python 标准库 + 项目内 ``data_loader.sql_importer``。
``sql_importer`` 已内置编码自动探测（utf-8 / utf-8-sig / gbk / gb18030 / latin-1），
并只解析不执行任何 DDL/DML，安全。

用法（必须在 02_算法代码 目录执行）：
    python -X utf8 ingest_sql_to_snapshot.py <date.sql 或 目录> <out_snapshot.json>

完成后用：
    python -X utf8 run.py <out_snapshot.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from data_loader.sql_importer import (  # noqa: E402
    import_sql,
    import_sql_files,
    inspect_sql,
)


def _preflight(src: Path) -> tuple[list[Path], list]:
    """返回 (sql 文件列表, inspect 结果列表)。"""
    if src.is_dir():
        sql_files = sorted(src.glob("*.sql"))
        if not sql_files:
            print(f"[error] 目录内无 .sql 文件: {src}")
            raise SystemExit(2)
    else:
        sql_files = [src]
    infos = [inspect_sql(f) for f in sql_files]
    return sql_files, infos


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: python -X utf8 ingest_sql_to_snapshot.py <date.sql|目录> <out_snapshot.json>")
        return 2

    src = Path(sys.argv[1]).expanduser().resolve()
    out = Path(sys.argv[2]).expanduser().resolve()
    if not src.exists():
        print(f"[error] 源不存在: {src}")
        return 2

    sql_files, infos = _preflight(src)

    # 预检报告（让模型/人一眼看清数据是真还是演示）
    for f, i in zip(sql_files, infos):
        print(f"[inspect] {f.name}: mode={i.mode} "
              f"official_tables={len(i.table_names)} inserts={i.insert_statements}")
        if i.mode == "schema_only":
            print("    ⚠ 仅 DDL（CREATE TABLE），无任何官方表 INSERT —— 将按 schema 合成演示数据，非真实数据！")
        elif i.mode == "unrecognised":
            print("    ⚠ 未识别到任何官方表，请检查 SQL 文件格式（是否真的含 JBS_* INSERT）。")

    # 解析
    if src.is_dir():
        tables = import_sql_files([str(f) for f in sql_files])
    else:
        tables = import_sql(src)

    total_rows = sum(len(v) for v in tables.values())
    print(f"[ok] 解析完成: {len(tables)} 张表, 共 {total_rows} 行")
    for name in sorted(tables):
        print(f"    {name}: {len(tables[name])} 行")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"tables": tables}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] 已写出 -> {out} ({out.stat().st_size:,} bytes)")
    print("[next] 执行: python -X utf8 run.py " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
