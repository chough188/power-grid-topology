# -*- coding: utf-8 -*-
"""SQL emission helpers for the official 12 detectors.

Each helper returns an Oracle-flavoured SQL string with named bind
variables (`:device_id`, `:terminal_id`, etc.). The output is what
goes into `ProblemRecord.correction_sql` and is later checked by
self_grade.py (sqlglot preferred, stdlib shape validator fallback).

Conventions (see SQL_PATTERNS.md):
- Tables UPPER, columns UPPER_SNAKE
- Strings single-quoted
- Bind vars prefixed `:`
- Sequence IDs use SEQ_PWTERMINAL.NEXTVAL / SEQ_ZWTERMINAL.NEXTVAL
- Each statement terminated with newline (no trailing semicolon, the
  shape validator strips it anyway)
"""
from __future__ import annotations

import re

_SEQ_PW = "SEQ_PWTERMINAL.NEXTVAL"
_SEQ_ZW = "SEQ_ZWTERMINAL.NEXTVAL"


def _q(s: str) -> str:
    """Quote a string literal: single quotes doubled for escape."""
    return "'" + str(s).replace("'", "''") + "'"


# ---------------------------------------------------------------------
# Topology (TERMINAL) mutations
# ---------------------------------------------------------------------

def insert_pw_terminal(device_id: str, new_node_id: str) -> str:
    return (
        "INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
        f"VALUES ({_SEQ_PW}, :device_id, :new_node_id)"
    )


def insert_zw_terminal(device_id: str, new_node_id: str) -> str:
    return (
        "INSERT INTO JBS_ZWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
        f"VALUES ({_SEQ_ZW}, :device_id, :new_node_id)"
    )


def update_pw_terminal_node(terminal_id: str, shared_node: str) -> str:
    return (
        "UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node "
        "WHERE ID = :terminal_id"
    )


def delete_pw_terminal(terminal_id: str) -> str:
    return "DELETE FROM JBS_PWTERMINAL WHERE ID = :terminal_id"


def delete_zw_terminal(terminal_id: str) -> str:
    return "DELETE FROM JBS_ZWTERMINAL WHERE ID = :terminal_id"


# ---------------------------------------------------------------------
# Device (EQUIPINFO) mutations
# ---------------------------------------------------------------------

def mark_tie_pw(device_id: str) -> str:
    return "UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = 'TIE' WHERE EQUIP_ID = :device_id"


def mark_tie_zw(device_id: str) -> str:
    return "UPDATE JBS_ZWEQUIPINFO SET EQUIP_TYPE = 'TIE' WHERE EQUIP_ID = :device_id"


def set_run_status_pw(device_id: str, expected_state: int) -> str:
    return (
        "UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = :expected_state "
        "WHERE EQUIP_ID = :device_id"
    )


def set_run_status_zw(device_id: str, expected_state: int) -> str:
    return (
        "UPDATE JBS_ZWEQUIPINFO SET RUN_STATUS = :expected_state "
        "WHERE EQUIP_ID = :device_id"
    )


def insert_pw_equip(
    device_id: str,
    device_name: str,
    equip_type: str,
    voltage: int | str,
    feeder_id: str,
    substation_id: str = "",
) -> str:
    # substation_id 通过 :substation_id 绑定变量传入（调用方负责绑定），
    # 不在此处内联字面量，避免与下游 SQL 校验器的绑定变量契约不一致。
    return (
        "INSERT INTO JBS_PWEQUIPINFO "
        "(EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, VOLTAGE_TYPE, FEEDER_ID, DSUBSTATION_ID) "
        f"VALUES (:device_id, :device_name, :equip_type, :voltage, :feeder_id, :substation_id)"
    )


def insert_zw_terminal_for_interface(
    main_device_id: str,
    shared_node: str,
) -> str:
    return (
        "INSERT INTO JBS_ZWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
        f"VALUES ({_SEQ_ZW}, :main_device_id, :shared_node)"
    )


def update_zw_terminal_node(terminal_id: str, correct_node: str) -> str:
    return (
        "UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID = :correct_node "
        "WHERE ID = :terminal_id"
    )


def set_pw_terminal_valid_flag(terminal_id: str, flag: int = 0) -> str:
    return (
        "UPDATE JBS_PWTERMINAL SET VALID_FLAG = :flag "
        "WHERE ID = :terminal_id"
    )


def delete_pw_equip(device_id: str) -> str:
    """Inverse of ``insert_pw_equip`` for rollback-supported corrections.

    Requires FK CASCADE constraints on JBS_PWTERMINAL/EQUIP_ID, or
    manual delete of dependent terminals first.
    """
    return (
        "DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = :device_id"
    )


def delete_zw_equip(device_id: str) -> str:
    """Inverse of any device INSERT on ZW side; rolls back mark_tie_zw or
    inserts of new ZW devices. Requires FK CASCADE or upstream cleanup.
    """
    return (
        "DELETE FROM JBS_ZWEQUIPINFO WHERE EQUIP_ID = :device_id"
    )


# ---------------------------------------------------------------------
# Composite / multi-row corrections
# ---------------------------------------------------------------------

def multi_step(*statements: str) -> str:
    """Concatenate multiple statements with newlines.

    self_grade.sqlglot parser handles `;` separated multi-statements
    just as well as single statements. We emit them in execution order
    so operators can audit the dependency sequence.
    """
    return "\n".join(s.rstrip().rstrip(";") for s in statements if s.strip())


# ---------------------------------------------------------------------
# Reverse SQL (rollback support) — implements JUDGE.md §10 mandatory
# "all corrections have reverse SQL" requirement.
# ---------------------------------------------------------------------

# Mapping of forward SQL templates to their corresponding inverse, with
# the column that needs flipping. Used by invert_sql() to derive the
# rollback operation from a generated SQL.
_INVERSES = {
    # Forward: insert into table -- Inverse: delete the same row by id
    "INSERT INTO JBS_PWTERMINAL":    ("DELETE FROM JBS_PWTERMINAL WHERE ID = :terminal_id",
                                       "ID"),
    "INSERT INTO JBS_ZWTERMINAL":    ("DELETE FROM JBS_ZWTERMINAL WHERE ID = :terminal_id",
                                       "ID"),
    "INSERT INTO JBS_PWEQUIPINFO":   # 删设备级操作（仅删刚插入的行）— 不可逆风险提示
                                       ("DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = :device_id",
                                       "EQUIP_ID"),
    "INSERT INTO JBS_ZWEQUIPINFO":   ("DELETE FROM JBS_ZWEQUIPINFO WHERE EQUIP_ID = :device_id",
                                       "EQUIP_ID"),
    # Forward: update connective node -- Inverse: another update back to original
    "UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node":
        ("UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :previous_node "
         "WHERE ID = :terminal_id"),
    "UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID = :correct_node":
        ("UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID = :previous_node "
         "WHERE ID = :terminal_id"),
    # Forward: set RUN_STATUS -- Inverse: toggle back to previous
    "UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = :expected_state":
        ("UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = :previous_state "
         "WHERE EQUIP_ID = :device_id"),
    "UPDATE JBS_ZWEQUIPINFO SET RUN_STATUS = :expected_state":
        ("UPDATE JBS_ZWEQUIPINFO SET RUN_STATUS = :previous_state "
         "WHERE EQUIP_ID = :device_id"),
    # Forward: mark tie -- Inverse: restore original EQUIP_TYPE
    "UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = 'TIE'":
        ("UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = :previous_type "
         "WHERE EQUIP_ID = :device_id"),
    "UPDATE JBS_ZWEQUIPINFO SET EQUIP_TYPE = 'TIE'":
        ("UPDATE JBS_ZWEQUIPINFO SET EQUIP_TYPE = :previous_type "
         "WHERE EQUIP_ID = :device_id"),
    # Forward: set VALID_FLAG=0 -- Inverse: VALID_FLAG=1
    "UPDATE JBS_PWTERMINAL SET VALID_FLAG = :flag":
        ("UPDATE JBS_PWTERMINAL SET VALID_FLAG = :previous_flag "
         "WHERE ID = :terminal_id"),
}


def invert_sql(sql: str) -> str | None:
    """Derive rollback SQL from a forward SQL emitted by this module.

    Returns:
        A SQL string that, if executed with the same bind variables plus
        `previous_*` for the previous value, undoes the forward change.
        Returns None if no reverse template is registered (e.g. for free-form
        SQL or statements this module does not know about).

    Per JUDGE.md §10 "可回滚" — every correction must have an executable
    reverse SQL. The correct previous state must be supplied by the operator
    via bind parameters `previous_state`, `previous_node`, `previous_type`,
    or `previous_flag`.
    """
    if not sql or not sql.strip():
        return None
    stmt = sql.strip().rstrip(";").strip()
    # Drop leading comments
    for line in stmt.splitlines():
        s = line.strip()
        if s.startswith("--") or not s:
            continue
        stmt = s
        break
    for prefix, (inverse, *_rest) in _INVERSES.items():
        if stmt.startswith(prefix):
            return inverse
    return None


def forward_with_inverse(sql: str) -> tuple[str, str | None]:
    """Return (forward, inverse-or-None) for a SQL statement.

    Convenience helper for ProblemRecord consumers: pass the forward SQL,
    get back the inverse so it can be placed in `extra['reverse_sql']`
    or shown alongside the correction in the xlsx Sheet.
    """
    return sql, invert_sql(sql)


__all__ = [
    "delete_pw_equip",
    "delete_pw_terminal",
    "delete_zw_equip",
    "delete_zw_terminal",
    "forward_with_inverse",
    "insert_pw_equip",
    "insert_pw_terminal",
    "insert_zw_terminal",
    "insert_zw_terminal_for_interface",
    "invert_sql",
    "mark_tie_pw",
    "mark_tie_zw",
    "multi_step",
    "set_pw_terminal_valid_flag",
    "set_run_status_pw",
    "set_run_status_zw",
    "update_pw_terminal_node",
    "update_zw_terminal_node",
]

