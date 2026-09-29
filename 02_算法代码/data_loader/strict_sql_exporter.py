"""Export snapshot tables as a date.sql that exactly follows an authoritative DDL."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from .schema import REQUIRED_TABLES

_TABLE_ALIASES = {
    "JBS_ZD_VOLTAGETYPE": "JBS_VOLTAGETYPE",
}
_CREATE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:"[^"]+"\.)?"?([A-Za-z0-9_]+)"?\s*\((.*?)\)\s*;',
    re.IGNORECASE | re.DOTALL,
)


def read_text(path: str | Path) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Unsupported SQL encoding: {path}")


def extract_contract(ddl_text: str) -> dict[str, tuple[str, ...]]:
    contract: dict[str, tuple[str, ...]] = {}
    for match in _CREATE_RE.finditer(ddl_text):
        table = match.group(1).upper()
        columns = []
        for line in match.group(2).splitlines():
            column = re.match(r'\s*"([^"]+)"\s+', line)
            if column:
                columns.append(column.group(1).upper())
        contract[table] = tuple(columns)
    return contract


def _sql_value(value: object) -> str:
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _rows_for_contract(
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    contract_table: str,
) -> Sequence[Mapping[str, object]]:
    canonical = next(
        (name for name, alias in _TABLE_ALIASES.items() if alias == contract_table),
        contract_table,
    )
    return tables.get(canonical, tables.get(contract_table, ()))


def export_strict_sql(
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    ddl_path: str | Path,
    output_path: str | Path,
    source_label: str,
) -> dict[str, object]:
    ddl_text, ddl_encoding = read_text(ddl_path)
    contract = extract_contract(ddl_text)
    required_contract_tables = {_TABLE_ALIASES.get(name, name) for name in REQUIRED_TABLES}
    missing = sorted(required_contract_tables - set(contract))
    if missing:
        raise ValueError(f"Authoritative DDL is missing required tables: {missing}")

    output = [ddl_text.rstrip(), "", "-- ================= STRICT DATA INSERTS ================="]
    manifest: dict[str, int] = {}
    for table in sorted(required_contract_tables):
        rows = list(_rows_for_contract(tables, table))
        manifest[table] = len(rows)
        output.append(f"-- {table}: {len(rows)} rows; source={source_label}")
        if not rows:
            continue
        columns = contract[table]
        output.append(
            f'INSERT INTO "EQUIP"."{table}" '
            f'({", ".join(chr(34) + column + chr(34) for column in columns)}) VALUES'
        )
        values = []
        for row in rows:
            normalized = {str(key).upper(): value for key, value in row.items()}
            values.append("  (" + ", ".join(_sql_value(normalized.get(column)) for column in columns) + ")")
        output.append(",\n".join(values) + ";\n")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return {
        "output": str(output_path.resolve()),
        "source": source_label,
        "ddl": str(Path(ddl_path).resolve()),
        "ddl_encoding": ddl_encoding,
        "rows_by_table": manifest,
        "total_rows": sum(manifest.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("output")
    parser.add_argument("--ddl", default=str(Path(__file__).resolve().parent.parent.parent / "比赛要求" / "date.sql"))
    args = parser.parse_args()
    snapshot_path = Path(args.snapshot)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    tables = payload.get("tables", payload)
    result = export_strict_sql(tables, args.ddl, args.output, str(snapshot_path.resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
