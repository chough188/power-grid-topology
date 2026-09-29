# -*- coding: utf-8 -*-
"""Rollback (reverse) SQL generation for the official 6-Sheet deliverable.

Review manual core commitment (评审手册 §核心承诺 / §可回滚性):
    "所有修正有反向 SQL，前置快照可恢复"

For every non-empty correction SQL cell in Sheet1 (问题清单, 「修正sql」列)
and Sheet2 (断点定位, sql 列) this module emits an inverse statement:

- INSERT -> DELETE scoped on stable business keys (no sequence capture
  needed; bind names from the forward statement are reused so the operator
  binds exactly the values used at apply time).
- UPDATE -> restore of the pre-correction value resolved from snapshot.json
  whenever the forward statement carries literal keys; otherwise a
  bind-scoped capture-and-restore pair (operator captures the old value
  before applying the forward statement).
- Forward statements that are no-ops against the pre-correction snapshot
  (target row absent) -> documented NO-OP comment lines.

Outputs written into ``out_dir``:
- ``rollback.sql``         ordered reverse statements with per-row context headers
- ``rollback_report.md``   statistics + coverage assertion (unparsed must be 0)

Note on DELETE: the competition rule "禁 DELETE" applies to the FORWARD
correction SQL (Sheet1「修正sql」列). The inverse of an INSERT is
necessarily a DELETE of the inserted row, so rollback.sql legitimately
contains DELETE statements.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Statement shape parsers (Run-10 verified inventory, 9 shapes)
# ---------------------------------------------------------------------------

_RE_INSERT_PW_EQUIP = re.compile(
    r"^INSERT\s+INTO\s+JBS_PWEQUIPINFO\s*\(\s*EQUIP_ID\s*,\s*EQUIP_NAME\s*,\s*"
    r"EQUIP_TYPE\s*,\s*FEEDER_ID\s*,\s*VOLTAGE_TYPE\s*\)\s*VALUES\s*\((.*)\)\s*;?\s*$",
    re.I | re.S,
)
_RE_INSERT_TERM = re.compile(
    r"^INSERT\s+INTO\s+(JBS_[PZ]WTERMINAL)\s*\(\s*ID\s*,\s*EQUIP_ID\s*,\s*"
    r"CONNECTIVITYNODE_ID\s*\)\s*VALUES\s*\(\s*(SEQ_\w+\.NEXTVAL|[\w'?:]+)\s*,\s*"
    r"(?P<equip>:[\w]+|'[^']*')\s*,\s*(?P<node>:[\w]+|'[^']*')\s*\)\s*;?\s*$",
    re.I | re.S,
)
_RE_INSERT_CN_DICT = re.compile(
    r"^INSERT\s+INTO\s+JBS_PWCNODE_DICT\s*\(\s*CN_ID\s*,\s*VOLTAGE_TYPE\s*,\s*"
    r"ST_ID\s*,\s*CREATE_DATE\s*\)\s*VALUES\s*\(\s*(?P<cn>:[\w]+|\S+?)\s*,",
    re.I | re.S,
)
_RE_UPD_FEEDER = re.compile(
    r"^UPDATE\s+JBS_PWEQUIPINFO\s+SET\s+FEEDER_ID\s*=\s*:?[\w]*\s*"
    r"WHERE\s+EQUIP_ID\s*=\s*'?(?P<tid>[^'\s;]+)'?\s*;?\s*$",
    re.I,
)
_RE_UPD_TERM_IN = re.compile(
    r"^UPDATE\s+(JBS_[PZ]WTERMINAL)\s+SET\s+(?P<col>\w+)\s*=\s*:?[\w]*\s*"
    r"WHERE\s+ID\s+IN\s*\((?P<ids>.*)\)\s*;?\s*$",
    re.I | re.S,
)
_RE_QUOTED = re.compile(r"'([^']*)'")
_RE_UPD_FLAG_BIND = re.compile(
    r"^UPDATE\s+(JBS_[PZ]WTERMINAL)\s+SET\s+(?P<col>\w+)\s*=\s*(?P<val>:[\w]+|\d+)\s*"
    r"WHERE\s+ID\s*=\s*(?P<id>:[\w]+|'[^']*'|[\w-]+)\s*;?\s*$",
    re.I,
)
_RE_UPD_FLAG_EQUIP = re.compile(
    r"^UPDATE\s+(JBS_[PZ]WTERMINAL)\s+SET\s+(?P<col>\w+)\s*=\s*(?P<val>\d+)\s*"
    r"WHERE\s+EQUIP_ID\s*=\s*'(?P<eid>[^']+)'\s*;?\s*$",
    re.I,
)


def _unquote(v: str) -> str:
    v = v.strip()
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1].replace("''", "'")
    return v


class RollbackContext:
    """Snapshot lookups + counters shared by the shape handlers."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        tables = snapshot.get("tables", {})
        self.pw_term_by_id: dict[str, dict[str, Any]] = {
            str(r["ID"]): r for r in tables.get("JBS_PWTERMINAL", ()) if r.get("ID")
        }
        self.zw_term_by_id: dict[str, dict[str, Any]] = {
            str(r["ID"]): r for r in tables.get("JBS_ZWTERMINAL", ()) if r.get("ID")
        }
        self.pw_equip_by_id: dict[str, dict[str, Any]] = {
            str(r["EQUIP_ID"]): r for r in tables.get("JBS_PWEQUIPINFO", ()) if r.get("EQUIP_ID")
        }
        self.pw_term_by_equip: dict[str, list[dict[str, Any]]] = {}
        for r in tables.get("JBS_PWTERMINAL", ()):
            if r.get("EQUIP_ID") and r.get("ID"):
                self.pw_term_by_equip.setdefault(str(r["EQUIP_ID"]), []).append(r)
        self.counts: Counter[str] = Counter()
        self.unparsed: list[str] = []

    def term_table(self, table: str) -> dict[str, dict[str, Any]]:
        return self.zw_term_by_id if "ZW" in table.upper() else self.pw_term_by_id


# ---------------------------------------------------------------------------
# Per-shape inverse emission. Each handler returns a list of SQL lines.
# ---------------------------------------------------------------------------

def _inv_insert_pw_equip(sql: str, ctx_device_id: str | None, rc: RollbackContext) -> list[str]:
    m = _RE_INSERT_PW_EQUIP.match(sql.strip())
    if not m:
        return []
    rc.counts["delete_inverse"] += 1
    values = [v.strip() for v in m.group(1).split(",")]
    first = values[0] if values else ""
    if first.startswith("'"):
        eid = _unquote(first)
        return [f"DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = '{eid}'"]
    if ctx_device_id:
        return [f"DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = '{ctx_device_id}'"]
    return ["DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = :inserted_equip_id"]


def _inv_insert_terminal(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    m = _RE_INSERT_TERM.match(sql.strip())
    if not m:
        return []
    rc.counts["delete_inverse"] += 1
    table, equip, node = m.group(1), m.group("equip"), m.group("node")
    return [
        f"DELETE FROM {table} WHERE EQUIP_ID = {equip} AND CONNECTIVITYNODE_ID = {node}"
    ]


def _inv_insert_cn_dict(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    m = _RE_INSERT_CN_DICT.match(sql.strip())
    if not m:
        return []
    rc.counts["delete_inverse"] += 1
    cn = m.group("cn")
    return [f"DELETE FROM JBS_PWCNODE_DICT WHERE CN_ID = {cn}"]


def _inv_update_feeder(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    m = _RE_UPD_FEEDER.match(sql.strip())
    if not m:
        return []
    tid = _unquote(m.group("tid"))
    row = rc.pw_equip_by_id.get(tid)
    if row is None:
        rc.counts["noop"] += 1
        return [
            f"-- NO-OP: {tid} absent from JBS_PWEQUIPINFO pre-correction snapshot "
            "(device exists on ZW side only, which has no FEEDER_ID column); "
            "forward UPDATE affected 0 rows, nothing to roll back."
        ]
    orig = row.get("FEEDER_ID", "")
    rc.counts["literal_restore"] += 1
    return [f"UPDATE JBS_PWEQUIPINFO SET FEEDER_ID = '{orig}' WHERE EQUIP_ID = '{tid}'"]


def _inv_update_term_in(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    m = _RE_UPD_TERM_IN.match(sql.strip())
    if not m:
        return []
    table, col = m.group(1), m.group("col")
    ids = _RE_QUOTED.findall(m.group("ids"))
    by_id = rc.term_table(table)
    lines: list[str] = []
    for tid in ids:
        row = by_id.get(tid)
        if row is None:
            rc.counts["noop"] += 1
            lines.append(f"-- NO-OP: terminal {tid} absent pre-correction; nothing to roll back.")
            continue
        orig = row.get(col, "")
        rc.counts["literal_restore"] += 1
        lines.append(f"UPDATE {table} SET {col} = '{orig}' WHERE ID = '{tid}'")
    return lines


def _inv_update_flag_bind(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    """Bind-scoped capture-and-restore (no literal key in the cell)."""
    m = _RE_UPD_FLAG_BIND.match(sql.strip())
    if not m:
        return []
    table, col, _val, wid = m.group(1), m.group("col"), m.group("val"), m.group("id")
    rc.counts["bind_capture"] += 1
    return [
        f"-- capture before apply: SELECT {col} INTO :prev_{col.lower()} "
        f"FROM {table} WHERE ID = {wid}",
        f"UPDATE {table} SET {col} = :prev_{col.lower()} WHERE ID = {wid}",
    ]


def _inv_update_flag_equip(sql: str, _ctx: str | None, rc: RollbackContext) -> list[str]:
    """Forward sets a flag on ALL terminals of one equipment id (literal)."""
    m = _RE_UPD_FLAG_EQUIP.match(sql.strip())
    if not m:
        return []
    table, col, eid = m.group(1), m.group("col"), m.group("eid")
    rows = rc.pw_term_by_equip.get(eid, [])
    if not rows:
        rc.counts["noop"] += 1
        return [
            f"-- NO-OP: equipment {eid} has no JBS_PWTERMINAL rows pre-correction; "
            "forward UPDATE affected 0 rows, nothing to roll back."
        ]
    rc.counts["bind_capture"] += 1
    lines: list[str] = []
    for r in rows:
        tid = str(r["ID"])
        lines.append(
            f"-- capture before apply: SELECT {col} INTO :prev_flag_{tid} "
            f"FROM {table} WHERE ID = '{tid}'"
        )
        lines.append(f"UPDATE {table} SET {col} = :prev_flag_{tid} WHERE ID = '{tid}'")
    return lines


_HANDLERS = (
    (_RE_INSERT_PW_EQUIP, _inv_insert_pw_equip),
    (_RE_INSERT_TERM, _inv_insert_terminal),
    (_RE_INSERT_CN_DICT, _inv_insert_cn_dict),
    (_RE_UPD_FEEDER, _inv_update_feeder),
    (_RE_UPD_TERM_IN, _inv_update_term_in),
    (_RE_UPD_FLAG_EQUIP, _inv_update_flag_equip),
    (_RE_UPD_FLAG_BIND, _inv_update_flag_bind),
)


def invert_statement(sql: str, rc: RollbackContext, ctx_device_id: str | None = None) -> list[str]:
    """Return inverse SQL lines for one forward correction statement."""
    s = sql.strip()
    for pattern, handler in _HANDLERS:
        if pattern.match(s):
            lines = handler(s, ctx_device_id, rc)
            if lines:
                return lines
    rc.unparsed.append(s[:160])
    rc.counts["unparsed"] += 1
    return [f"-- UNPARSED forward statement (manual review required): {s[:200]}"]


# ---------------------------------------------------------------------------
# Workbook + snapshot driver
# ---------------------------------------------------------------------------

def _sql_columns(header: tuple[Any, ...]) -> list[int]:
    out = []
    for i, h in enumerate(header):
        if h and "sql" in str(h).lower():
            out.append(i)
    return out


def generate_rollback_sql(
    xlsx_path: str | Path,
    snapshot_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Generate rollback.sql + rollback_report.md from the official xlsx.

    Returns a summary dict (also embedded into the pipeline manifest).
    Raises RuntimeError when any forward statement could not be inverted.
    """
    from openpyxl import load_workbook

    xlsx_path = Path(xlsx_path)
    snapshot_path = Path(snapshot_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rc = RollbackContext(snap)

    wb = load_workbook(xlsx_path, read_only=True)
    body: list[str] = [
        "-- ============================================================",
        "-- rollback.sql — 修正反向 SQL（评审手册核心承诺：所有修正有反向SQL）",
        f"-- 正向修正权威载体: {xlsx_path.name} Sheet1「修正sql」列 + Sheet2 sql 列",
        "-- 前置快照: " + snapshot_path.name + "（全量恢复路径）",
        "-- 说明: 禁DELETE规则约束正向修正SQL；INSERT 的反向天然是 DELETE。",
        "--       绑定变量(:xxx)由操作者在执行正向语句时绑定同样的值。",
        "--       NO-OP 行: 正向语句对前置快照为空操作，无需回滚。",
        "-- ============================================================",
        "",
    ]
    cell_total = 0
    per_sheet: Counter[str] = Counter()

    try:
        for idx in (0, 1):
            ws = wb[wb.sheetnames[idx]]
            rows = list(ws.iter_rows(values_only=True))
            header = tuple(rows[0]) if rows else ()
            sql_cols = _sql_columns(header)
            dev_col = None
            for i, h in enumerate(header):
                if h and "设备id" in str(h):
                    dev_col = i
                    break
            for n, r in enumerate(rows[1:], start=2):
                for c in sql_cols:
                    if c >= len(r) or not r[c]:
                        continue
                    sql = str(r[c]).strip()
                    ctx_id = None
                    if dev_col is not None and dev_col < len(r) and r[dev_col]:
                        ctx_id = str(r[dev_col]).strip()
                    lines = invert_statement(sql, rc, ctx_id)
                    cell_total += 1
                    per_sheet[ws.title] += 1
                    body.append(f"-- [{ws.title}] 行{n}")
                    body.extend(lines)
                    body.append("")
    finally:
        wb.close()

    rollback_path = out_dir / "rollback.sql"
    rollback_path.write_text("\n".join(body), encoding="utf-8")

    coverage_ok = not rc.unparsed
    report = [
        "# rollback.sql 生成报告\n",
        f"- 正向 xlsx: `{xlsx_path}`",
        f"- 前置快照: `{snapshot_path}`",
        f"- 处理修正单元格: {cell_total}",
        "- 按 Sheet: " + ", ".join(f"{k}={v}" for k, v in sorted(per_sheet.items())),
        "\n## 反向语句分类（按生成的反向语句/注释行计；IN-list 与设备级单元格会展开多行）\n",
        "| 类别 | 数量 | 含义 |",
        "|---|---|---|",
        f"| delete_inverse | {rc.counts['delete_inverse']} | INSERT 的反向：DELETE（禁DELETE规则只约束正向SQL） |",
        f"| literal_restore | {rc.counts['literal_restore']} | 从前置快照解析原值，字面量恢复 UPDATE |",
        f"| bind_capture | {rc.counts['bind_capture']} | 绑定作用域 capture+restore（执行前抓取旧值） |",
        f"| noop | {rc.counts['noop']} | 正向为空操作（目标行前置不存在），无需回滚 |",
        f"| unparsed | {len(rc.unparsed)} | 未识别形态（必须为 0） |",
        f"\n**覆盖断言**: {'PASS — 每条正向修正均有反向语句或 NO-OP 说明' if coverage_ok else 'FAIL — 存在未识别语句'}\n",
        "\n## 备注\n",
        "- JBS_PWTERMINAL 官方样本 DDL 仅 3 列（无 VALID_FLAG），而官方伪代码 L664/L744/L959 "
        "规定 VALID_FLAG 软删除模板；按『规范模板优先于样本 DDL』裁定保留正向语句，",
        "  若目标库确无该列则正向与回滚均为空操作（见 rollback.sql 头注）。",
        "- 1.4 feeder_conflict 的 40 条 UPDATE 目标全部仅存在于 JBS_ZWEQUIPINFO（ZW 侧，",
        "  该表无 FEEDER_ID 列），对 JBS_PWEQUIPINFO 为空操作 → NO-OP 注释。",
    ]
    (out_dir / "rollback_report.md").write_text("\n".join(report), encoding="utf-8")

    summary = {
        "cells": cell_total,
        "per_sheet": dict(per_sheet),
        "counts": dict(rc.counts),
        "unparsed": len(rc.unparsed),
        "coverage_ok": coverage_ok,
        "rollback_sql": str(rollback_path),
    }
    if not coverage_ok:
        raise RuntimeError(f"rollback coverage FAIL: {len(rc.unparsed)} unparsed statements")
    return summary


__all__ = ["RollbackContext", "generate_rollback_sql", "invert_statement"]
