# -*- coding: utf-8 -*-
"""Official exemption rules referenced by JUDGE.md.

Eight exemption categories (must all be reflected in detector code):

1. ROOM (配电站)  — all switches inside excluded from tie-switch recognition
2. XF   (箱变)     — all switches inside excluded from tie-switch recognition
3. TRANS (用户/配变) — not flagged as dangling
4. CABLE_HEAD       — not flagged as dangling
5. SPARE (备用间隔) — not flagged as dangling
6. DISCONNECTOR     — single-side connection allowed (only SWITCH/BREAKER strict)
7. LOOP (合环)      — same-voltage parallel operation is not a violation
8. MEASURE (量测)   — measurement points not paired with device: skip check

All helper functions return bool. Use them inside `detect(ctx)` to filter
candidates BEFORE yielding ProblemRecord, so exempted rows never appear in
the output (which would otherwise deduct points per JUDGE.md).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

# Substring (case-insensitive) flags recognised in EQUIP_NAME / EQUIP_TYPE / OBJ_CODE
_DANGLE_EXEMPT_KEYWORDS = (
    "TRANS",        # 用户 / 配变
    "CUSTOMER",     # 用户
    "XF",           # 箱变
    "CABLE_HEAD",   # 电缆终端头
    "SPARE",        # 备用间隔
    "ROOM",         # 末端站房本身
)

# Chinese literal fallbacks (when data is in Chinese)
_DANGLE_EXEMPT_KEYWORDS_CN = (
    "配变", "用户", "客户",
    "箱变", "箱式",
    "电缆终端", "终端头",
    "备用",
)


def _norm(value: object) -> str:
    return str(value or "").strip().upper()


def _has_any_ci(value: object, keywords: Iterable[str]) -> bool:
    blob = _norm(value)
    return any(kw.upper() in blob for kw in keywords)


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def is_dangle_exempt(device_row: Mapping) -> bool:
    """Rule 1-5: Returns True if device must NOT be flagged as dangling.

    `device_row` is one row of JBS_PWEQUIPINFO / JBS_ZWEQUIPINFO. Any of
    these fields may carry the marker: EQUIP_NAME, EQUIP_TYPE, OBJ_CODE.
    """
    for field in ("EQUIP_NAME", "EQUIP_TYPE", "OBJ_CODE"):
        if _has_any_ci(device_row.get(field), _DANGLE_EXEMPT_KEYWORDS):
            return True
        if _has_any_ci(device_row.get(field), _DANGLE_EXEMPT_KEYWORDS_CN):
            return True
    return False


def is_single_side_allowed(device_row: Mapping) -> bool:
    """Rule 6: DISCONNECTOR (隔离开关) is allowed to have only one CONNECTIVITYNODE.

    Returns True for DISCONNECTOR. SWITCH and BREAKER are NOT exempted.
    """
    equip_type = _norm(device_row.get("EQUIP_TYPE"))
    name = _norm(device_row.get("EQUIP_NAME"))
    if equip_type == "DISCONNECTOR":
        return True
    if "隔离开关" in name or "刀闸" in name:
        return True
    return False


def is_loop_exempt(candidate_devices: Iterable[Mapping]) -> bool:
    """Rule 7: All candidate devices share the same VOLTAGE_TYPE -> no violation.

    `candidate_devices` is the iterable of equip rows forming a loop. Returns
    True when at least two distinct feeders/substations are involved but
    ALL share the same voltage level (intentional parallel operation).
    """
    voltages = {_norm(d.get("VOLTAGE_TYPE")) for d in candidate_devices}
    voltages.discard("")
    return len(voltages) == 1


def _measurement_device_key(meas_row: Mapping) -> str:
    """Resolve the device key a measurement row refers to.

    Different measurement tables use different key columns:
      - JBS_PWREAL   -> TRAN_ID
      - JBS_ZWMEA    -> ID          (主网 96 点量测的主键)
      - generic      -> MEA_ID / EQUIP_ID (fallback)

    Without this, JBS_ZWMEA (which carries no TRAN_ID) was treated as
    unpaired and silently exempted, so 3.1 never checked main-net switches.
    """
    for field in ("TRAN_ID", "ID", "MEA_ID", "EQUIP_ID"):
        key = _norm(meas_row.get(field))
        if key:
            return key
    return ""


def is_measurement_exempt(meas_row: Mapping, device_lookup: Mapping[str, Mapping]) -> bool:
    """Rule 8: Skip measurement/signal check when its device key cannot be paired.

    `device_lookup` maps EQUIP_ID -> device row. Returns True if the resolved
    device key (TRAN_ID / ID / MEA_ID / EQUIP_ID) is missing/empty or not in
    the lookup.
    """
    key = _measurement_device_key(meas_row)
    if not key:
        return True
    return key not in device_lookup


# -------------------------------------------------------------------
# Tie-switch exemptions (legacy compatibility for shared.exemption
# imports already present in tests/test_common_contracts.py)
# -------------------------------------------------------------------

EXEMPT_ROOM_TYPES = frozenset({"配电站", "箱式变电站", "箱变"})


def normalize_room_type(room_type: object) -> str:
    return str(room_type or "").strip().replace(" ", "")


def is_internal_tie_switch_exempt(room_type: object, same_room: bool) -> bool:
    """Original single-rule helper kept for backward compatibility.

    Use `is_tie_switch_exempt(...)` for the full 2-rule check.
    """
    return same_room and normalize_room_type(room_type) in EXEMPT_ROOM_TYPES


def is_tie_switch_exempt(device_row: Mapping, same_room: bool) -> bool:
    """Combined Rule 1+2: tie-switch is exempt when:

    - same_room AND room type is 配电站 / 箱变, OR
    - the device's EQUIP_TYPE / EQUIP_NAME indicates 箱变 (XF prefix)
    """
    if is_internal_tie_switch_exempt(device_row.get("OBJ_CODE") or device_row.get("EQUIP_TYPE"), same_room):
        return True
    if _has_any_ci(device_row.get("EQUIP_NAME"), ("XF", "箱变", "箱式")):
        return True
    if _has_any_ci(device_row.get("OBJ_CODE"), ("XF", "箱变", "箱式")):
        return True
    return False


__all__ = [
    "EXEMPT_ROOM_TYPES",
    "is_dangle_exempt",
    "is_internal_tie_switch_exempt",
    "is_loop_exempt",
    "is_measurement_exempt",
    "is_single_side_allowed",
    "is_tie_switch_exempt",
    "normalize_room_type",
]