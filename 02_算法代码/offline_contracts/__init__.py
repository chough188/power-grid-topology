"""Offline contract package with no real-data or SQL side effects."""

from .api_contract import synthetic_request, synthetic_response, validate_request, validate_response
from .contract import (
    CATEGORY_OPTIONS,
    MEASUREMENT_FIELDS,
    OFFICIAL_SHEET_NAMES,
    SHEET_HEADERS,
    TABLE_CONTRACTS,
    canonicalize_identifier,
    empty_output_book,
    validate_output_book,
    validate_sql_preview,
    validate_tables,
)
from .sqlite_bridge import SHEET_COLUMNS, build_bridge, init_bridge, seed_dropdown_options, write_rows, SHEET_NAMES
from .svg_contract import synthetic_svg, validate_svg_document
from .synthetic import build_synthetic_tables, write_synthetic_fixture

__all__ = [
    "CATEGORY_OPTIONS",
    "MEASUREMENT_FIELDS",
    "OFFICIAL_SHEET_NAMES",
    "SHEET_HEADERS",
    "TABLE_CONTRACTS",
    "canonicalize_identifier",
    "empty_output_book",
    "validate_output_book",
    "validate_sql_preview",
    "validate_tables",
    "validate_request",
    "validate_response",
    "build_synthetic_tables",
    "write_synthetic_fixture",
    "synthetic_request",
    "synthetic_response",
    "synthetic_svg",
    "validate_svg_document",
    "SHEET_COLUMNS",
    "build_bridge",
    "init_bridge",
    "seed_dropdown_options",
    "write_rows",
    "SHEET_NAMES",
]