"""SQLite bridge that mirrors the official 6-sheet contract in a local file."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path

from .contract import (
    CATEGORY_OPTIONS,
    OFFICIAL_SHEET_NAMES,
    SHEET_HEADERS,
)


SHEET_COLUMNS: dict[str, tuple[str, ...]] = {
    sheet_name: tuple(header for header in headers if header is not None)
    for sheet_name, headers in SHEET_HEADERS.items()
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _joined_columns(columns: Iterable[str]) -> str:
    return ", ".join(_quote_identifier(column) for column in columns)


def init_bridge(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    for sheet_name, columns in SHEET_COLUMNS.items():
        create_sql = "CREATE TABLE IF NOT EXISTS " + _quote_identifier(sheet_name) + " (" + _joined_columns(columns) + ")"
        cursor.execute(create_sql)
    connection.commit()


def write_rows(connection: sqlite3.Connection, sheet_name: str, rows: Iterable[Mapping[str, object]]) -> int:
    if sheet_name not in SHEET_COLUMNS:
        raise ValueError("unknown sheet name: " + sheet_name)
    columns = SHEET_COLUMNS[sheet_name]
    if not columns:
        return 0
    placeholders = ", ".join(["?"] * len(columns))
    payload = [
        tuple(row.get(column) for column in columns) for row in rows if isinstance(row, Mapping)
    ]
    cursor = connection.cursor()
    insert_sql = (
        "INSERT INTO " + _quote_identifier(sheet_name) + " (" + _joined_columns(columns) + ") VALUES (" + placeholders + ")"
    )
    cursor.executemany(insert_sql, payload)
    connection.commit()
    return cursor.rowcount


def seed_dropdown_options(connection: sqlite3.Connection) -> int:
    rows = ({"一级分类": level_one, "二级分类": level_two} for level_one, level_two in CATEGORY_OPTIONS)
    return write_rows(connection, OFFICIAL_SHEET_NAMES[5], rows)


def build_bridge(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    init_bridge(connection)
    return connection


SHEET_NAMES = OFFICIAL_SHEET_NAMES