# -*- coding: utf-8 -*-
"""Universal dataset loading: auto-dispatch by input kind.

支持三种输入，统一归一为 :class:`OfficialDataset`（14 表契约）：

- ``.json`` 文件 → :func:`data_loader.snapshot.load_json_snapshot`（合成基准 / 已有快照）
- ``.sql`` 文件  → :func:`data_loader.sql_importer.import_sql`（单文件含 INSERT，自动 GBK 编码探测 / 表名别名归一）
- 目录          → 收集目录内 ``*.sql`` → :func:`data_loader.sql_importer.import_sql_files`（官方 15 分表合并）

用法：把 llm_stage / llm_svg_tools / llm_data_qa 等入口的 snapshot 参数直接换成
SQL 文件或 SQL 目录即可，无需先转 JSON。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import OfficialDataset
from .snapshot import load_json_snapshot
from .sql_importer import import_sql, import_sql_files


def load_dataset(path: str | Path) -> OfficialDataset:
    """按路径形态自动分派加载：.json 快照 / .sql 文件 / 含 *.sql 的目录。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Dataset path not found: {p}")
    if p.is_dir():
        sql_files = sorted(p.glob("*.sql"))
        if not sql_files:
            raise FileNotFoundError(f"No *.sql files found in dataset dir: {p}")
        tables: dict[str, list[dict[str, Any]]] = import_sql_files(sql_files)
    elif p.suffix.lower() == ".sql":
        tables = import_sql(p)
    elif p.suffix.lower() == ".json":
        return load_json_snapshot(p)
    else:
        raise ValueError(f"Unsupported dataset path (need .json / .sql / sql dir): {p}")
    return OfficialDataset(tables)
