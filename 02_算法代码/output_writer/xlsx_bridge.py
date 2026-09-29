"""Dependency-free payload validation before writing the official workbook."""

from collections.abc import Mapping, Sequence
from typing import Any

from .workbook_schema import SHEETS_BY_NAME


def normalize_rows(sheet_name: str, rows: Sequence[Mapping[str, Any]]) -> list[list[Any]]:
    try:
        sheet = SHEETS_BY_NAME[sheet_name]
    except KeyError as error:
        raise ValueError(f"Unknown workbook sheet: {sheet_name}") from error
    return [[row.get(column, "") for column in sheet.columns] for row in rows]


def validate_workbook_payload(payload: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    unknown = sorted(set(payload) - set(SHEETS_BY_NAME))
    if unknown:
        raise ValueError(f"Unknown workbook sheets: {', '.join(unknown)}")
    for sheet_name, rows in payload.items():
        normalize_rows(sheet_name, rows)
