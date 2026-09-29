"""Synthetic-only fixtures for offline contract and integration tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import MEASUREMENT_FIELDS


def build_synthetic_tables() -> dict[str, list[dict[str, Any]]]:
    measurement = {
        "CREATE_DATE": "2026-01-01T00:00:00",
        "ID": "TMP00000001",
        "MEAS_TYPE": "UA",
    }
    measurement.update({field: 11000.0 for field in MEASUREMENT_FIELDS})
    return {
        "JBS_ZWSUBSTATION": [{"ST_ID": "SUB001", "ST_NAME": "合成变电站", "TOP_AC_VOLTAGE_TYPE": "110kV"}],
        "JBS_ZWEQUIPINFO": [{"EQUIP_ID": "ZW001", "EQUIP_NAME": "合成主网开关", "EQUIP_TYPE": "断路器", "ST_ID": "SUB001", "VOLTAGE_TYPE": "10kV"}],
        "JBS_ZWLINEEND": [{"LINEEND_ID": "LINEEND001", "LINEEND_NAME": "合成出线端", "VOLTAGE_TYPE": "10kV", "ST_ID": "SUB001"}],
        "JBS_ZWTERMINAL": [
            {"ID": "ZWT001", "EQUIP_ID": "ZW001", "CONNECTIVITYNODE_ID": "ZWN001"},
            {"ID": "ZWT002", "EQUIP_ID": "ZW001", "CONNECTIVITYNODE_ID": "ZWN002"},
        ],
        "JBS_ZWMEA": [measurement],
        "JBS_ZWSIGNAL": [{"ID": "ZW001", "POINT": 0}],
        "JBS_PWFEEDERLINE": [{"LINE_ID": "LINE001", "LINE_NAME": "合成馈线", "START_ST_ID": "SUB001", "VOLTAGE_TYPE": "10kV"}],
        "JBS_PWROOM": [{"ROOM_ID": "ROOM001", "ROOM_NAME": "合成环网柜", "TOP_VOLTAGE_TYPE": "10kV", "FEEDER_ID": "LINE001"}],
        "JBS_PWEQUIPINFO": [
            {"EQUIP_ID": "SW001", "EQUIP_NAME": "合成联络开关", "EQUIP_TYPE": "负荷开关", "VOLTAGE_TYPE": "10kV", "FEEDER_ID": "LINE001", "DSUBSTATION_ID": "ROOM001", "COMPOSITESWITCH": ""},
            {"EQUIP_ID": "TMP00034205", "EQUIP_NAME": "合成配变0486", "EQUIP_TYPE": "用户配变", "VOLTAGE_TYPE": "10kV", "FEEDER_ID": "LINE001", "DSUBSTATION_ID": "", "COMPOSITESWITCH": ""},
        ],
        "JBS_PWTERMINAL": [
            {"ID": "PWT001", "EQUIP_ID": "SW001", "CONNECTIVITYNODE_ID": "PWN001"},
            {"ID": "PWT002", "EQUIP_ID": "SW001", "CONNECTIVITYNODE_ID": "PWN002"},
            {"ID": "PWT003", "EQUIP_ID": "TMP00034205", "CONNECTIVITYNODE_ID": "PWN003"},
        ],
        "JBS_PWREAL": [{"NUM": "REAL001", "TRAN_ID": "SW001", "DATA_DATE": "2026-01-01T00:00:00", "UA": 10000.0, "UB": 10000.0, "UC": 10000.0, "IA": 0.0, "IB": 0.0, "IC": 0.0, "AP": 0.0, "RP": 0.0, "POINT": 0, "BDZ_ID": "SUB001", "FEEDER_ID": "LINE001"}],
        "JBS_ZD_OBJECT": [
            {"OBJ_ID": "OBJ001", "OBJ_CODE": "SWITCH", "OBJ_CNNAME": "开关", "OBJ_ENNAME": "switch"},
            {"OBJ_ID": "OBJ002", "OBJ_CODE": "USER_TRANSFORMER", "OBJ_CNNAME": "电力用户配变", "OBJ_ENNAME": "user transformer"},
        ],
        "JBS_ZD_VOLTAGETYPE": [{"VOLTAGE_ID": "10KV", "VOLTAGE_NAME": "10kV"}],
        "JBS_ZD_MEASTYPE": [{"CODE": "UA", "NAME_CHN": "A相电压"}],
    }


def write_synthetic_fixture(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_synthetic_tables(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target