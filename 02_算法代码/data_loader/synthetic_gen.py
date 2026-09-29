"""Synthetic dataset helpers for official tests before real data arrives.

Provides both empty (validate-only) and realistic (small but structurally
complete) dataset factories. Use `make_synthetic_dataset(seed=42)` to get
a deterministic 14-table mock that satisfies schema.py field contracts.
"""
from __future__ import annotations

import random
from typing import Any

from .loader import OfficialDataset
from .schema import REQUIRED_TABLES


def make_empty_dataset() -> OfficialDataset:
    return OfficialDataset({table_name: [] for table_name in REQUIRED_TABLES})


def _mk_equip(i, equip_type="BREAKER", feeder="F1", sub="RM1", voltage=10):
    return {
        "EQUIP_ID": f"TMP{i:08d}",
        "EQUIP_NAME": f"{equip_type}{i}",
        "EQUIP_TYPE": equip_type,
        "VOLTAGE_TYPE": voltage,
        "FEEDER_ID": feeder,
        "DSUBSTATION_ID": sub,
        "COMPOSITESWITCH": "",
    }


def make_synthetic_dataset(
    n_substations: int = 2,
    n_feeders: int = 4,
    n_devices_per_feeder: int = 8,
    seed: int = 42,
) -> OfficialDataset:
    """Build a deterministic, structurally complete 14-table mock.

    Topology forms a single radial feeder chain per (substation, feeder),
    with a tie switch between feeder-1 of sub-1 and feeder-1 of sub-2.
    PWREAL rows include UA/UB/UC voltage (220V nominal, varies per device).
    ZWMEA rows include V0000-V2345 96-point voltage (mostly stable).

    This guarantees detectors 1.1, 1.2, 1.3, 1.5, 2.3, 2.4, 3.1, 4.1, 4.2
    all have at least one candidate record to find.
    """
    rng = random.Random(seed)
    tables: dict[str, list[dict[str, Any]]] = {t: [] for t in REQUIRED_TABLES}

    # JBS_ZWSUBSTATION
    for i in range(n_substations):
        tables["JBS_ZWSUBSTATION"].append({
            "ST_ID": f"ST{i + 1:03d}",
            "ST_NAME": f"变电站{i + 1}",
            "TOP_AC_VOLTAGE_TYPE": 110,
        })

    # JBS_ZWLINEEND
    for i in range(n_substations):
        tables["JBS_ZWLINEEND"].append({
            "LINEEND_ID": f"LE{i + 1:03d}",
            "LINEEND_NAME": f"主网线路端{i + 1}",
            "VOLTAGE_TYPE": 110,
            "ST_ID": f"ST{i + 1:03d}",
        })

    # JBS_PWFEEDERLINE
    for sub_idx in range(n_substations):
        for f_idx in range(n_feeders):
            tables["JBS_PWFEEDERLINE"].append({
                "LINE_ID": f"F{sub_idx + 1}{f_idx + 1:02d}",
                "LINE_NAME": f"馈线{sub_idx + 1}-{f_idx + 1}",
                "START_ST_ID": f"ST{sub_idx + 1:03d}",
                "VOLTAGE_TYPE": 10,
            })

    # JBS_PWROOM
    for sub_idx in range(n_substations):
        tables["JBS_PWROOM"].append({
            "ROOM_ID": f"RM{sub_idx + 1:03d}",
            "ROOM_NAME": f"配电站{sub_idx + 1}",
            "TOP_VOLTAGE_TYPE": 10,
            "FEEDER_ID": f"F{sub_idx + 1}01",
        })

    # JBS_ZWEQUIPINFO + JBS_PWEQUIPINFO
    equip_id_counter = 1
    for sub_idx in range(n_substations):
        tables["JBS_ZWEQUIPINFO"].append({
            "EQUIP_ID": f"ZWB{sub_idx + 1:03d}",
            "EQUIP_NAME": f"主网断路器{sub_idx + 1}",
            "EQUIP_TYPE": "BREAKER",
            "ST_ID": f"ST{sub_idx + 1:03d}",
            "VOLTAGE_TYPE": 110,
            "RUN_STATUS": 1,
        })

    # Add a DISCONNECTOR for task 1.4 suspect-tie testing (rs=0 + cross-station)
    tables["JBS_PWEQUIPINFO"].append({
        "EQUIP_ID": "DISC001",
        "EQUIP_NAME": "隔离开关001",
        "EQUIP_TYPE": "DISCONNECTOR",
        "VOLTAGE_TYPE": 10,
        "FEEDER_ID": "F101",
        "DSUBSTATION_ID": "RM001",
        "COMPOSITESWITCH": "",
        "RUN_STATUS": 0,
    })
    # Give DISC001 terminals connecting to both RM001 and RM002 (cross-station)
    tables["JBS_PWTERMINAL"].append({"ID": "PT_DISC_001", "EQUIP_ID": "DISC001", "CONNECTIVITYNODE_ID": "DISC_NODE_A"})
    # Connect DISC_NODE_A to a device in RM001 (via re-using its terminal)
    tables["JBS_PWTERMINAL"].append({"ID": "PT_DISC_002", "EQUIP_ID": "ZWB001", "CONNECTIVITYNODE_ID": "DISC_NODE_A"})
    # Connect DISC_NODE_A to a device in RM002 via F201 feeder
    # (already connected through tie; add explicit cross-link)
    # Actually use TIENODE1 which connects both


    equip_rows = []
    for sub_idx in range(n_substations):
        for f_idx in range(n_feeders):
            feeder = f"F{sub_idx + 1}{f_idx + 1:02d}"
            sub_room = f"RM{sub_idx + 1:03d}"
            for d in range(n_devices_per_feeder):
                eid = equip_id_counter
                equip_id_counter += 1
                if d == 0:
                    etype = "BREAKER"
                elif d == n_devices_per_feeder - 1:
                    etype = "TRANS"
                elif d == 3 and sub_idx == 1 and f_idx == 1:
                    etype = "XF"
                else:
                    etype = "SWITCH"
                row = _mk_equip(eid, equip_type=etype, feeder=feeder, sub=sub_room, voltage=10)
                # Some devices have RUN_STATUS=0 (split) for 2.4 / 3.1 testing
                row["RUN_STATUS"] = 1 if etype in ("BREAKER", "SWITCH") else 0
                equip_rows.append(row)
                tables["JBS_PWEQUIPINFO"].append(row)

    # JBS_ZWTERMINAL + JBS_PWTERMINAL
    for sub_idx in range(n_substations):
        eid = f"ZWB{sub_idx + 1:03d}"
        for k, nid in enumerate([f"ZN{sub_idx + 1}A", f"ZN{sub_idx + 1}B"]):
            tables["JBS_ZWTERMINAL"].append({
                "ID": f"ZT{sub_idx + 1}{k}",
                "EQUIP_ID": eid,
                "CONNECTIVITYNODE_ID": nid,
            })

    pwterm_id = 1
    for sub_idx in range(n_substations):
        for f_idx in range(n_feeders):
            feeder_devices = [
                d for d in tables["JBS_PWEQUIPINFO"]
                if d.get("FEEDER_ID") == f"F{sub_idx + 1}{f_idx + 1:02d}"
            ]
            feeder_devices.sort(key=lambda x: x["EQUIP_ID"])
            for i, dev in enumerate(feeder_devices):
                eid = dev["EQUIP_ID"]
                if i == 0:
                    nid = f"N{sub_idx + 1}{f_idx + 1}H"
                    tables["JBS_PWTERMINAL"].append({
                        "ID": f"PT{pwterm_id:06d}", "EQUIP_ID": eid, "CONNECTIVITYNODE_ID": nid,
                    })
                    pwterm_id += 1
                elif i == len(feeder_devices) - 1:
                    nid_prev = f"N{sub_idx + 1}{f_idx + 1}{i - 1:02d}"
                    tables["JBS_PWTERMINAL"].append({
                        "ID": f"PT{pwterm_id:06d}", "EQUIP_ID": eid, "CONNECTIVITYNODE_ID": nid_prev,
                    })
                    pwterm_id += 1
                else:
                    own = f"N{sub_idx + 1}{f_idx + 1}{i:02d}"
                    prev = f"N{sub_idx + 1}{f_idx + 1}{i - 1:02d}"
                    tables["JBS_PWTERMINAL"].append({
                        "ID": f"PT{pwterm_id:06d}", "EQUIP_ID": eid, "CONNECTIVITYNODE_ID": own,
                    })
                    pwterm_id += 1
                    tables["JBS_PWTERMINAL"].append({
                        "ID": f"PT{pwterm_id:06d}",
                        "EQUIP_ID": feeder_devices[i - 1]["EQUIP_ID"],
                        "CONNECTIVITYNODE_ID": own,
                    })
                    pwterm_id += 1

    # Add a tie switch
    f1_dev = next(d for d in tables["JBS_PWEQUIPINFO"] if d.get("FEEDER_ID") == "F101" and d.get("EQUIP_TYPE") == "SWITCH")
    f2_dev = next(d for d in tables["JBS_PWEQUIPINFO"] if d.get("FEEDER_ID") == "F201" and d.get("EQUIP_TYPE") == "SWITCH")
    tie_eid = "TIE001"
    tables["JBS_PWEQUIPINFO"].append({
        "EQUIP_ID": tie_eid, "EQUIP_NAME": "联络开关001",
        "EQUIP_TYPE": "SWITCH", "VOLTAGE_TYPE": 10,
        "FEEDER_ID": "F101", "DSUBSTATION_ID": "RM001",
        "COMPOSITESWITCH": "", "RUN_STATUS": 1,
    })
    tables["JBS_PWTERMINAL"].append({"ID": f"PT{pwterm_id:06d}", "EQUIP_ID": tie_eid, "CONNECTIVITYNODE_ID": "TIENODE1"})
    pwterm_id += 1
    tables["JBS_PWTERMINAL"].append({"ID": f"PT{pwterm_id:06d}", "EQUIP_ID": f1_dev["EQUIP_ID"], "CONNECTIVITYNODE_ID": "TIENODE1"})
    pwterm_id += 1
    tables["JBS_PWTERMINAL"].append({"ID": f"PT{pwterm_id:06d}", "EQUIP_ID": f2_dev["EQUIP_ID"], "CONNECTIVITYNODE_ID": "TIENODE1"})
    pwterm_id += 1

    # Deliberate topological break for 1.2 testing (replaces the previously skipped stub):
    # Insert an isolated SWITCH in feeder F102 whose two terminals share a private node.
    # - 2 terminals => it is NOT a 1.1 dangle (single-terminal) candidate.
    # - shares NO CONNECTIVITYNODE_ID with any other F102 device => in the model graph
    #   it has no path to any peer => the 1.2 detector must flag a 拓扑断连/状态未知
    #   break, so Sheet2 (断点定位) is populated with a non-empty start/end pair.
    break_eid = "BRK001"
    tables["JBS_PWEQUIPINFO"].append({
        "EQUIP_ID": break_eid, "EQUIP_NAME": "断点测试开关001",
        "EQUIP_TYPE": "SWITCH", "VOLTAGE_TYPE": 10,
        "FEEDER_ID": "F102", "DSUBSTATION_ID": "RM001",
        "COMPOSITESWITCH": "", "RUN_STATUS": 1,
    })
    tables["JBS_PWTERMINAL"].append({
        "ID": f"PT{pwterm_id:06d}", "EQUIP_ID": break_eid, "CONNECTIVITYNODE_ID": "N12BREAK",
    })
    pwterm_id += 1
    tables["JBS_PWTERMINAL"].append({
        "ID": f"PT{pwterm_id:06d}", "EQUIP_ID": break_eid, "CONNECTIVITYNODE_ID": "N12BREAK",
    })
    pwterm_id += 1

    # JBS_ZWMEA — 主网量测，主键 ID 直接对应 JBS_ZWEQUIPINFO.EQUIP_ID
    # (原 ZW_M* 占位键无法关联设备，导致 3.1 永不上主网开关电压 -> 主网漏检)。
    for sub_idx in range(n_substations):
        meas_row: dict[str, Any] = {
            "CREATE_DATE": "2026-07-21",
            "ID": f"ZWB{sub_idx + 1:03d}",
            "MEAS_TYPE": "V",
        }
        if sub_idx == 1:
            # 主网失电压用例：ZWB002 合位但 96 点全 0 -> 3.1 应报 mismatch_on_no_voltage
            for i in range(96):
                meas_row[f"V{i:04d}"] = 0.0
        else:
            # 96 点稳定约 110kV（单位 V）
            for i in range(96):
                meas_row[f"V{i:04d}"] = 110000.0 + rng.uniform(-1000, 1000)
        tables["JBS_ZWMEA"].append(meas_row)

    # JBS_ZWSIGNAL
    for sub_idx in range(n_substations):
        tables["JBS_ZWSIGNAL"].append({"ID": f"ZW_S{sub_idx + 1}", "POINT": 1})

    # JBS_PWREAL — paired to devices, with 3-phase voltage (UA/UB/UC)
    # For some devices, voltage is 0 (matching OFF state for 3.1 testing)
    for sub_idx in range(n_substations):
        for f_idx in range(n_feeders):
            head_dev = next(
                d for d in tables["JBS_PWEQUIPINFO"]
                if d.get("FEEDER_ID") == f"F{sub_idx + 1}{f_idx + 1:02d}" and d.get("EQUIP_TYPE") == "BREAKER"
            )
            real_row: dict[str, Any] = {
                "NUM": f"{f_idx + 1}", "TRAN_ID": head_dev["EQUIP_ID"],
                "DATA_DATE": "2026-07-21", "POINT": "1",
                "BDZ_ID": f"BDZ{sub_idx + 1}{f_idx + 1:02d}",
                "FEEDER_ID": f"F{sub_idx + 1}{f_idx + 1:02d}",
                "UA": "5774.0",  # 10kV / sqrt(3)
                "UB": "5774.0",
                "UC": "5774.0",
                "IA": "100.0",
                "IB": "100.0",
                "IC": "100.0",
                "AP": "1500.0",
                "RP": "200.0",
            }
            tables["JBS_PWREAL"].append(real_row)

    # Add deliberate mismatch for 3.1: one device has voltage=0 (should be off, but is on)
    # Pick a SWITCH in F101 with RUN_STATUS=1 but no voltage
    mismatch_dev = next(
        (d for d in tables["JBS_PWEQUIPINFO"]
         if d.get("FEEDER_ID") == "F101" and d.get("EQUIP_TYPE") == "SWITCH" and d.get("RUN_STATUS") == 1),
        None,
    )
    if mismatch_dev:
        tables["JBS_PWREAL"].append({
            "NUM": "999", "TRAN_ID": mismatch_dev["EQUIP_ID"],
            "DATA_DATE": "2026-07-21", "POINT": "1",
            "BDZ_ID": "BDZ-MISMATCH", "FEEDER_ID": "F101",
            "UA": "0.0", "UB": "0.0", "UC": "0.0",
            "IA": "0.0", "IB": "0.0", "IC": "0.0",
            "AP": "0.0", "RP": "0.0",
        })

    # JBS_ZD_OBJECT
    obj_codes = [
        ("O001", "BREAKER", "断路器", "Breaker"),
        ("O002", "SWITCH", "开关", "Switch"),
        ("O003", "DISCONNECTOR", "隔离开关", "Disconnector"),
        ("O004", "TRANSFORMER", "变压器", "Transformer"),
        ("O005", "TRANS", "用户配变", "Customer Transformer"),
        ("O006", "XF", "箱变", "Box Transformer"),
        ("O007", "ROOM", "配电站", "Distribution Room"),
        ("O008", "CABLE_HEAD", "电缆终端头", "Cable Head"),
        ("O009", "SPARE_BAY", "备用间隔", "Spare Bay"),
        ("O010", "TIE", "联络开关", "Tie Switch"),
        ("O011", "BUS", "母线", "Bus"),
        ("O012", "LINE", "线路", "Line"),
        ("O013", "SOURCE", "电源", "Source"),
    ]
    for row in obj_codes:
        tables["JBS_ZD_OBJECT"].append({
            "OBJ_ID": row[0], "OBJ_CODE": row[1], "OBJ_CNNAME": row[2], "OBJ_ENNAME": row[3],
        })

    # JBS_ZD_VOLTAGETYPE
    for vid, vname in [(110, "110kV"), (35, "35kV"), (10, "10kV"), (0.4, "0.4kV")]:
        tables["JBS_ZD_VOLTAGETYPE"].append({"VOLTAGE_ID": vid, "VOLTAGE_NAME": vname})

    # JBS_ZD_MEASTYPE
    for code, name in [(1, "电压A相"), (2, "电压B相"), (3, "电压C相"), (4, "电流A相")]:
        tables["JBS_ZD_MEASTYPE"].append({"CODE": code, "NAME_CHN": name})

    return OfficialDataset(tables)


__all__ = ["make_empty_dataset", "make_synthetic_dataset"]
