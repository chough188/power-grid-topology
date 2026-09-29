# -*- coding: utf-8 -*-
"""schema-only SQL 导入与样本数据自动生成 (CP-202606 比赛 date.sql 模式)。

比赛最后对应的 date.sql 通常仅给出 14 张表的 CREATE TABLE 定义;
真实的 INSERT 数据要等到组委会下发。本模块让 date.sql 即使只有 DDL
也能跑通整条 pipeline,自动从 schema 推断列类型并生成最小可用的
样本数据。

设计原则:
1. 零依赖,纯文本解析。
2. 仅在 SQL 文本中未识别到任何官方表的 INSERT 时,才回退到 schema-only 模式。
3. 生成的样本数据严格遵循 ``schema.TABLE_SCHEMAS`` 的 required/optional 字段,
   字段缺失时用占位值;类型推断失败时按字符串处理。
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .schema import REQUIRED_TABLES


# 表名归一(同 sql_importer._TABLE_ALIASES)
_TABLE_ALIASES = {"JBS_VOLTAGETYPE": "JBS_ZD_VOLTAGETYPE"}

# 类型推断:从 SQL 数据类型映射到 Python 占位值生成策略
_TYPE_HINTS = {
    "INT": "int", "INTEGER": "int", "BIGINT": "int", "SMALLINT": "int",
    "DEC": "float", "DECIMAL": "float", "NUMERIC": "float", "FLOAT": "float",
    "DOUBLE": "float", "REAL": "float",
    "VARCHAR": "str", "VARCHAR2": "str", "CHAR": "str", "TEXT": "str",
    "TIMESTAMP": "str", "DATE": "str",
}

# 已知 ID 字段前缀(便于生成更有意义的样本)
_ID_FIELD_HINTS = {
    "EQUIP_ID": "TMP", "ST_ID": "ST", "ROOM_ID": "RM",
    "LINE_ID": "F", "LINEEND_ID": "LE", "FEEDER_ID": "F",
    "ID": "T", "OBJ_ID": "OBJ", "DSUBSTATION_ID": "RM",
    "TRAN_ID": "T", "NUM": "M", "POINT": "P", "BDZ_ID": "BDZ",
    "OBJ_CODE": "OBJ", "CONNECTIVITYNODE_ID": "N",
    "CODE": "MC", "MEAS_TYPE": "M",
}

# 匹配 CREATE TABLE 起始(贪婪,直到首个顶层 '(')
_CREATE_TABLE_HEAD_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:"(?P<schema>[^"]+)"\s*\.\s*)?"?(?P<table>[A-Za-z_][A-Za-z0-9_$]*)"?\s*\(', re.IGNORECASE,
)


def extract_schemas(sql_text: str) -> dict[str, list[dict]]:
    """Parse CREATE TABLE statements, return ``{TABLE: [{name, type, not_null}, ...]}``."""
    schemas: dict[str, list[dict]] = {}
    pos = 0
    while True:
        m = _CREATE_TABLE_HEAD_RE.search(sql_text, pos)
        if not m:
            break
        table_raw = m.group("table").upper()
        canonical = _TABLE_ALIASES.get(table_raw, table_raw)
        # 找到与 m.end()-1 那个 '(' 匹配的 ')',body 在两者之间
        body, end_pos = _extract_balanced_body(sql_text, m.end() - 1)
        cols = _parse_columns(body)
        if cols:
            schemas[canonical] = cols
        pos = end_pos
    return schemas


def _extract_balanced_body(text: str, open_pos: int) -> tuple[str, int]:
    """从 text[open_pos] == '(' 开始,找到与之平衡的 ')',返回内部 body 和结束位置(不含 ')')。"""
    depth = 0
    i = open_pos
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "'":
                # 处理 SQL 转义 ''
                if i + 1 < n and text[i + 1] == "'":
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1:i], i + 1
        i += 1
    return text[open_pos + 1:], n


def _parse_columns(body: str) -> list[dict]:
    """``"col1" VARCHAR2(50) NOT NULL, "col2" INT NULL`` -> list of dicts."""
    parts = _split_top_commas(body)
    cols: list[dict] = []
    for raw in parts:
        line = raw.strip().rstrip(",").strip()
        if not line:
            continue
        upper = line.upper().lstrip()
        if upper.startswith(("CLUSTER", "PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "UNIQUE", "INDEX", "KEY ")):
            continue
        m = re.match(
            r'^\s*\"?(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\"?\s+'
            r'(?P<type>VARCHAR2?|CHAR|INTEGER|INT|BIGINT|SMALLINT|DEC(?:IMAL)?|NUMERIC|FLOAT|DOUBLE|REAL|TIMESTAMP(?:(?:\(\d+\))?)|DATE)'
            r'(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?\s*'
            r'(?P<constraints>.*?)$',
            line, re.IGNORECASE,
        )
        if not m:
            continue
        name = m.group("name").upper()
        sql_type = m.group("type").upper()
        constraints = (m.group("constraints") or "").upper()
        not_null = ("NOT NULL" in constraints) or (
            name.endswith("_ID") and "NULL" not in constraints
        )
        cols.append({
            "name": name,
            "type": sql_type,
            "python_type": _TYPE_HINTS.get(sql_type, "str"),
            "not_null": not_null,
        })
    return cols


def _split_top_commas(text: str) -> list[str]:
    """Split on commas not inside parentheses or single-quoted strings."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    for ch in text:
        if in_string:
            buf.append(ch)
            if ch == "'":
                in_string = False
            continue
        if ch == "'":
            in_string = True
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf)
    if tail.strip():
        parts.append(tail)
    return parts


def _sample_value(col: dict, idx: int, table: str) -> object:
    """Generate a single placeholder value matching the column's inferred type."""
    name = col["name"]
    py = col["python_type"]
    if py == "int":
        if name in ("VOLTAGE_TYPE", "TOP_VOLTAGE_TYPE", "TOP_AC_VOLTAGE_TYPE"):
            return 110 if ("ZW" in table or "ZD" in table) else 10
        if name in ("RUN_STATUS", "IS_END_DEVICE", "MEAS_TYPE"):
            return 1
        if name == "CODE":
            return 1000 + idx
        return idx
    if py == "float":
        if name.startswith("V") and len(name) == 5 and name[1:].isdigit():
            return 220.0 + idx * 0.1
        if name in ("UA", "UB", "UC"):
            return 220.0 + idx * 0.5
        if name in ("IA", "IB", "IC"):
            return 50.0 + idx
        if name == "AP":
            return 1000.0 + idx * 10
        if name == "RP":
            return 500.0 + idx * 5
        return 1.0
    prefix = _ID_FIELD_HINTS.get(name, "")
    if prefix:
        return f"{prefix}{idx:08d}"
    if name.endswith("_NAME"):
        return f"sample-{name}-{idx}"
    if name == "VOLTAGE_NAME":
        return "10kV" if idx % 2 == 0 else "110kV"
    if name == "NAME_CHN":
        return f"meas-type-{idx}"
    if name == "OBJ_CNNAME":
        return f"main-obj-{idx}"
    if name == "OBJ_ENNAME":
        return f"obj_{idx}"
    if name in ("ST_NAME", "ROOM_NAME"):
        return f"sample-{table}-{idx}"
    if name == "LINE_NAME":
        return f"feeder-{idx}"
    if name == "LINEEND_NAME":
        return f"line-end-{idx}"
    if name == "DATA_DATE":
        return "2026-07-23"
    if name == "CREATE_DATE":
        return "2026-07-23 00:00:00"
    return f"sample-{name}-{idx}"


def synthesize_rows_from_schemas(
    schemas: Mapping[str, Sequence[dict]],
    n_rows_per_table: int = 3,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """根据 schema 推断生成最小可用样本数据,每张表 n_rows 行。

    Returns:
        (tables, extras) - tables 仅含 REQUIRED_TABLES,extras 存放其他表。
    """
    tables: dict[str, list[dict]] = {name: [] for name in REQUIRED_TABLES}
    extras: dict[str, list[dict]] = {}
    for table_name, cols in schemas.items():
        bucket = tables[table_name] if table_name in REQUIRED_TABLES else extras.setdefault(table_name, [])
        for idx in range(1, n_rows_per_table + 1):
            row: dict = {}
            for col in cols:
                row[col["name"]] = _sample_value(col, idx, table_name)
            bucket.append(row)
    return tables, extras


__all__ = [
    "extract_schemas",
    "synthesize_rows_from_schemas",
]
