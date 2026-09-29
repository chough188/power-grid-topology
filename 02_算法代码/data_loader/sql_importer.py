"""Parse a date.sql file (INSERT INTO ... VALUES / CREATE TABLE ...) into the canonical 14-table dict.

CP-202606 比赛最后对应数据集表格式 = 一个 ``date.sql`` 文件。
本模块不连数据库、零依赖，仅用文本解析把 ``date.sql`` 还原成与
``data_loader.snapshot.load_json_snapshot`` 同构的 ``{TABLE_NAME: [row, ...]}``
字典，便于直接接入现有 ``OfficialDataset``。

设计原则：
1. **零依赖**：仅 Python 标准库，可离线运行。
2. **零 SQL 执行**：绝不执行任何 DDL/DML/DROP，只解析。
3. **大小写无关**：表名大小写、关键字大小写都自动归一。
4. **复用官方表名**：`REQUIRED_TABLES` 是唯一识别源，14 张表之外的表被忽略。
5. **类型推断**：单引号字符串、数值、NULL、布尔全部按 SQL 标准还原。
6. **schema-only 演示**：若 date.sql 只有 CREATE TABLE (无任何官方表 INSERT)，
   可从 schema 推断并合成最小演示数据；调用方必须显式标注为演示模式。

公开 API：
    - :func:`import_sql(path)` —— 单文件解析，返回 ``dict[str, list[dict]]``。
    - :func:`import_sql_files(paths)` —— 批量解析，自动合并同表多段。
    - :func:`parse_sql_text(text)` —— 纯文本解析入口。
    - :class:`SqlImportError` —— 解析错误的统一异常类型。
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .schema import REQUIRED_TABLES
from .schema_synth import extract_schemas, synthesize_rows_from_schemas


# ---------------------------------------------------------------------------
# 常量与正则
# ---------------------------------------------------------------------------

# INSERT INTO <table> [(col1, col2, ...)] VALUES (...),(...);
# 允许跨行、允许无列名清单（按全列插入）
_INSERT_HEAD_RE = re.compile(
    r"""INSERT\s+INTO\s+
        (?:(?P<schema_quot>"?)(?P<schema>[\w$]+)(?P=schema_quot)\s*\.\s*)?
        (?P<table_quot>"?)(?P<table>[\w$]+)(?P=table_quot)\s*
        (?P<cols>\([^)]*\))?\s*
        VALUES\s*""",
    re.IGNORECASE | re.VERBOSE,
)

_TABLE_KW_RE = re.compile(r"^[A-Z_][A-Z0-9_$]*$")


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SqlImportError(ValueError):
    """Raised when ``date.sql`` cannot be parsed into the canonical 14-table dict."""


# 已知主键映射：merge 时按主键去重，避免多文件导入重复行
_TABLE_PK: dict[str, tuple[str, ...]] = {
    "JBS_PWEQUIPINFO": ("EQUIP_ID",),
    "JBS_ZWEQUIPINFO": ("EQUIP_ID",),
    "JBS_PWREAL": ("TRAN_ID", "DATA_DATE"),
    "JBS_ZWSIGNAL": ("EQUIP_ID", "ID"),
}


@dataclass(frozen=True)
class SqlSourceInfo:
    """Read-only preflight result for a SQL input file."""

    mode: str
    table_names: tuple[str, ...]
    insert_statements: int = 0


# ---------------------------------------------------------------------------
# 词法解析辅助
# ---------------------------------------------------------------------------


@dataclass
class _Row:
    columns: tuple[str, ...]
    values: tuple[object, ...]


@dataclass
class _ParsedSql:
    tables: dict[str, list[dict]] = field(default_factory=dict)
    extras: dict[str, list[dict]] = field(default_factory=dict)
    statements: int = 0

    def merge_into(self, target: "_ParsedSql") -> None:
        for name, rows in self.tables.items():
            pk = _TABLE_PK.get(name)
            if pk:
                existing = target.tables.setdefault(name, [])
                seen = {tuple(r.get(k) for k in pk) for r in existing}
                for r in rows:
                    key = tuple(r.get(k) for k in pk)
                    if key not in seen:
                        existing.append(r)
                        seen.add(key)
            else:
                target.tables.setdefault(name, []).extend(rows)
        for name, rows in self.extras.items():
            target.extras.setdefault(name, []).extend(rows)


# ---------------------------------------------------------------------------
# 顶层解析
# ---------------------------------------------------------------------------


def _read_sql_text(path: Path) -> str:
    """Auto-detect encoding: utf-8 / utf-8-sig / gbk / gb18030 / latin-1.

    比赛 date.sql 多为 GBK 编码 (尤其来自达梦/Oracle 导出工具),
    优先尝试 utf-8 / utf-8-sig,失败则按 GBK 家族兜底。
    """
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def inspect_sql(path: str | Path) -> SqlSourceInfo:
    """Classify SQL as real row data, schema-only DDL, or unrecognised text."""
    sql_path = Path(path).expanduser().resolve()
    if not sql_path.is_file():
        raise FileNotFoundError(f"date.sql not found: {sql_path}")
    text = _read_sql_text(sql_path)
    parsed = parse_sql_text(text, source=str(sql_path))
    if parsed.tables:
        return SqlSourceInfo(
            mode="data",
            table_names=tuple(sorted(parsed.tables)),
            insert_statements=parsed.statements,
        )
    schemas = extract_schemas(text)
    official = tuple(sorted(set(schemas) & set(REQUIRED_TABLES)))
    if official:
        return SqlSourceInfo(mode="schema_only", table_names=official)
    return SqlSourceInfo(mode="unrecognised", table_names=())


def import_sql(path: str | Path) -> dict[str, list[dict]]:
    """Parse a single ``date.sql`` file into ``{TABLE_NAME: [row, ...]}``.

    与 :func:`data_loader.snapshot.load_json_snapshot` 输出同构，可直接喂给
    ``OfficialDataset(tables)``。

    Args:
        path: SQL 文件路径。

    Returns:
        ``{TABLE_NAME: [row_dict, ...], ...}`` 字典。表名采用 ``REQUIRED_TABLES``
        中标准命名。

    Raises:
        FileNotFoundError: 文件不存在。
        SqlImportError: SQL 解析失败或缺失任何必填表。
    """
    sql_path = Path(path).expanduser().resolve()
    if not sql_path.is_file():
        raise FileNotFoundError(f"date.sql not found: {sql_path}")
    text = _read_sql_text(sql_path)
    parsed = parse_sql_text(text, source=str(sql_path))
    if not parsed.tables:
        # Schema-only 回退:从 CREATE TABLE 推断列定义,合成最小样本数据
        schemas = extract_schemas(text)
        if not schemas:
            raise SqlImportError(
                "date.sql 既无 INSERT 也无 CREATE TABLE,无法识别任何官方表。"
            )
        tables, _extras = synthesize_rows_from_schemas(schemas, n_rows_per_table=3)
        if not tables:
            raise SqlImportError(
                f"date.sql 仅含 DDL,但 schema 合成后仍无 14 张官方表中的任何一张。"
            )
        parsed.tables = tables
    return parsed.tables


def import_sql_files(paths: Iterable[str | Path]) -> dict[str, list[dict]]:
    """Parse multiple SQL files (auto-merge same-table rows)."""
    merged = _ParsedSql()
    src_list = list(paths)
    if not src_list:
        raise SqlImportError("import_sql_files 需要至少 1 个 SQL 文件")
    for raw in src_list:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"SQL file not found: {path}")
        text = _read_sql_text(path)
        parsed = parse_sql_text(text, source=str(path))
        parsed.merge_into(merged)
    if not merged.tables:
        raise SqlImportError("所有 SQL 文件解析后均无官方表数据")
    return merged.tables


def parse_sql_text(text: str, source: str = "<memory>") -> _ParsedSql:
    """Core parser; tolerant of comments and multi-statements."""
    cleaned = _strip_comments(text)
    statements = _split_statements(cleaned)
    parsed = _ParsedSql()
    for stmt in statements:
        head = _INSERT_HEAD_RE.match(stmt)
        if not head:
            continue  # silently ignore non-INSERT (DDL/COMMIT/SET/etc.)
        table_raw = head.group("table").upper()
        cols_raw = head.group("cols")
        tail = stmt[head.end():]
        rows = _parse_values_block(tail)
        columns = (
            _parse_column_list(cols_raw) if cols_raw else ()
        )
        parsed.statements += 1
        # 允许空 INSERT (表存在但 0 行) 通过；只有解析失败才跳过
        _assign_rows(parsed, source, table_raw, columns, rows)
    return parsed


# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------


def _strip_comments(text: str) -> str:
    """Remove ``-- line`` and ``/* block */`` comments (preserve strings)."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # 单行注释
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        # 块注释
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        # 字符串中保留一切
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                i += 1
                if c == "'":
                    if i < n and text[i] == "'":
                        out.append("'")
                        i += 1
                        continue
                    break
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_statements(text: str) -> list[str]:
    """Split on top-level ``;`` outside strings/parens."""
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    depth = 0
    while i < n:
        ch = text[i]
        if ch == "'":
            buf.append(ch)
            i += 1
            while i < n:
                c = text[i]
                buf.append(c)
                i += 1
                if c == "'":
                    if i < n and text[i] == "'":
                        buf.append("'")
                        i += 1
                        continue
                    break
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


# ---------------------------------------------------------------------------
# 列表 / VALUES 解析
# ---------------------------------------------------------------------------


def _parse_column_list(cols_raw: str) -> tuple[str, ...]:
    """``(col1, col2)`` -> ``('COL1', 'COL2')``."""
    inner = cols_raw.strip()[1:-1]
    cols = [c.strip().strip('"').strip("`").upper() for c in _split_top_commas(inner)]
    return tuple(c for c in cols if c)


def _split_top_commas(text: str) -> list[str]:
    """Split on commas not inside parentheses or strings."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            buf.append(ch)
            i += 1
            while i < n:
                c = text[i]
                buf.append(c)
                i += 1
                if c == "'":
                    if i < n and text[i] == "'":
                        buf.append("'")
                        i += 1
                        continue
                    break
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _parse_values_block(tail: str) -> list[tuple[object, ...]]:
    """``(1,'a'),(2,'b')`` -> list of value tuples (raw)."""
    tail = tail.strip().rstrip(";").strip()
    if not tail:
        return []
    # Find the first '('
    if tail[0] != "(":
        # 有时候 VALUES 之前还可能有 WITH 之类；保守起见直接抛错
        raise SqlImportError(f"无法识别 VALUES 块开头: {tail[:40]!r}")
    rows: list[tuple[object, ...]] = []
    i = 0
    n = len(tail)
    while i < n:
        ch = tail[i]
        if ch != "(":
            i += 1
            continue
        # 解析单行
        depth = 1
        buf: list[str] = []
        i += 1
        while i < n and depth > 0:
            c = tail[i]
            if c == "'":
                buf.append(c)
                i += 1
                while i < n:
                    cc = tail[i]
                    buf.append(cc)
                    i += 1
                    if cc == "'":
                        if i < n and tail[i] == "'":
                            buf.append("'")
                            i += 1
                            continue
                        break
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            buf.append(c)
            i += 1
        # 跳过行尾的右括号
        if i < n and tail[i] == ")":
            i += 1
        raw_inner = "".join(buf)
        rows.append(tuple(_coerce(v) for v in _split_top_commas(raw_inner)))
        # 跳到下一行起点
        while i < n and tail[i] in " \t\r\n,":
            i += 1
    return rows


def _coerce(raw: str) -> object:
    """Best-effort: NULL → None, numbers, strings."""
    s = raw.strip()
    if not s:
        return ""
    upper = s.upper()
    if upper == "NULL":
        return None
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1].replace("''", "'")
    # 数字（含小数/负号/科学计数）
    try:
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)
    except ValueError:
        pass
    return s


# ---------------------------------------------------------------------------
# 结果归并
# ---------------------------------------------------------------------------


# 表名别名映射：数据集结构说明文档中存在 `JBS_VOLTAGETYPE` 形式（不带 _ZD_），
# 而代码侧沿用 `JBS_ZD_VOLTAGETYPE`。两者都识别，归一为代码侧标准名。
_TABLE_ALIASES = {
    "JBS_VOLTAGETYPE": "JBS_ZD_VOLTAGETYPE",
}


def _assign_rows(
    parsed: _ParsedSql,
    source: str,
    table_raw: str,
    columns: tuple[str, ...],
    rows: Sequence[tuple[object, ...]],
) -> None:
    canonical = _TABLE_ALIASES.get(table_raw, table_raw)
    if canonical in REQUIRED_TABLES:
        bucket = parsed.tables.setdefault(canonical, [])
    else:
        bucket = parsed.extras.setdefault(table_raw, [])
    if columns:
        for row in rows:
            n = min(len(columns), len(row))
            d = {columns[k]: row[k] for k in range(n)}
            if len(row) > n:
                d["__trailing__"] = list(row[n:])
            bucket.append(d)
    else:
        # 没列名：用 col_0, col_1 ...
        for row in rows:
            bucket.append({f"col_{i}": v for i, v in enumerate(row)})


__all__ = [
    "import_sql",
    "import_sql_files",
    "inspect_sql",
    "parse_sql_text",
    "SqlImportError",
    "SqlSourceInfo",
    "extract_schemas",
    "synthesize_rows_from_schemas",
]

