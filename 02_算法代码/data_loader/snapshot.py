"""JSON snapshot loading for the official desktop application."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .loader import OfficialDataset


def load_json_snapshot(path: str | Path) -> OfficialDataset:
    snapshot_path = Path(path).expanduser().resolve()
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Official dataset snapshot not found: {snapshot_path}")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    tables = payload.get("tables", payload) if isinstance(payload, Mapping) else None
    if not isinstance(tables, Mapping):
        raise ValueError("Official dataset snapshot must be a table-name mapping")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for table_name, rows in tables.items():
        if not isinstance(rows, list):
            raise ValueError(f"Official table {table_name} must contain a row list")
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"Official table {table_name} contains a non-object row")
            normalized_rows.append(dict(row))
        normalized[str(table_name)] = normalized_rows
    return OfficialDataset(normalized)
