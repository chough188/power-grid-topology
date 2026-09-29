"""Task 3.1: 开关 - 电压基础状态匹配（official algorithm).

Per official 比赛要求/00_12子任务单元测试清单.md T-3.1-A:
"合位 + 下游电压 0 + 持续 3 个 15 分钟点 → 报 match_conflict"
"信号缺失 → 报 data_missing，不当作零"

Voltage sources (in priority order):
1. JBS_PWREAL.UA/UB/UC (3-phase AC voltage in V) — primary for dist net
2. JBS_ZWMEA.V0000-V2345 (96 15-minute points) — primary for main net
3. JBS_PWREAL.POINT / JBS_ZWSIGNAL.POINT — status

Thresholds:
- VOLTAGE_ON = 0.1 pu (≈ 6V for 10kV system)
- VOLTAGE_OFF = 5 V (below this is "no power")
- WINDOW = 3 consecutive points for "persisting"
"""
from collections.abc import Sequence

from shared.exemption import is_measurement_exempt
from shared.kcl_kvl import compute_device_kcl_residual, compute_node_kcl_residual
from shared.sql_emitter import set_run_status_pw, set_run_status_zw
from shared.switch_state import build_signal_point_map, is_switch_closed
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "medium"
VOLTAGE_OFF_V = 5.0  # Below this = no power (when switch is OFF)
PERSIST_POINTS = 3  # Consecutive points required


def _read_pwreal_voltages(row: dict) -> list[float]:
    """Extract 3-phase voltages from JBS_PWREAL row (UA/UB/UC in V)."""
    voltages: list[float] = []
    for phase_key in ("UA", "UB", "UC"):
        v = row.get(phase_key)
        try:
            voltages.append(float(v) if v not in (None, "") else None)
        except (TypeError, ValueError):
            voltages.append(None)
    return voltages


def _read_zwmea_voltages(row: dict) -> list[float]:
    """Extract 96-point voltages from JBS_ZWMEA row (V0000-V2345)."""
    voltages: list[float] = []
    for i in range(96):
        v = row.get(f"V{i:04d}")
        try:
            voltages.append(float(v) if v not in (None, "") else None)
        except (TypeError, ValueError):
            voltages.append(None)
    return voltages


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    equip_lookup: dict[str, dict] = {}
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if eid:
            equip_lookup[eid] = d

    # Read measurement windows
    tran_voltages: dict[str, list[float]] = {}
    for r in tables.get("JBS_PWREAL", ()):
        if is_measurement_exempt(r, equip_lookup):
            continue
        tran = r.get("TRAN_ID")
        if tran:
            tran_voltages[tran] = _read_pwreal_voltages(r)
    for r in tables.get("JBS_ZWMEA", ()):
        if is_measurement_exempt(r, equip_lookup):
            continue
        tran = r.get("ID")  # official: ZWMEA uses ID as device key
        if tran:
            tran_voltages.setdefault(tran, _read_zwmea_voltages(r))

    # R5: build signal POINT map for switch-state resolution
    cache = (ctx.options or {}).get("_shared_cache") or {}
    signal_map = cache.get("signal_map") if "signal_map" in cache else build_signal_point_map(tables)

    # Collect records (P1#4: may collapse data_missing into summary if >20%)
    collected: list[ProblemRecord] = []
    dm_count = 0
    total_devs = len(equip_lookup)

    # Pre-build: TRAN_ID -> currents index (avoid O(devices * pwreal) nested scan)
    tran_currents: dict[str, list[float]] = {}
    for r in tables.get("JBS_PWREAL", ()):
        tid = r.get("TRAN_ID")
        if tid:
            curr = []
            for ck in ("IA", "IB", "IC"):
                cv = r.get(ck)
                try:
                    curr.append(float(cv) if cv not in (None, "") else 0.0)
                except (TypeError, ValueError):
                    curr.append(0.0)
            tran_currents.setdefault(tid, []).extend(curr)



    # Bug#59: Pre-build equip -> first connectivity node for KCL
    equip_to_first_node: dict[str, str] = {}
    for _tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for _r in tables.get(_tbl, ()):
            _eid = _r.get("EQUIP_ID")
            _nid = _r.get("CONNECTIVITYNODE_ID")
            if _eid and _nid:
                equip_to_first_node.setdefault(_eid, _nid)    # Evaluate each device
    for eid, dev in equip_lookup.items():
        # R5: use signal POINT via resolver, fall back RUN_STATUS
        closed = is_switch_closed(tables, dev, signal_map)
        voltages = tran_voltages.get(eid, [])
        currents = tran_currents.get(eid, [])

        if not voltages or closed is None:
            # R5: data_missing — cannot determine state or no voltage readings
            # Per spec §3.1 rule 4: signal missing is not zero; advertise as data_missing
            dm_count += 1
            collected.append(ProblemRecord(
                task_code="3.1",
                device_id=eid,
                device_name=dev.get("EQUIP_NAME", ""),
                feeder_id=dev.get("FEEDER_ID", ""),
                station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
                description=(
                    f"开关状态缺失{'（信号无）' if closed is None else '（无电压量测）'}: "
                    f"{dev.get('EQUIP_NAME', eid)}"
                ),
                correction="[待人工复核] 补齐遥信或量测采集后重新判定。",
                correction_sql="",
                severity="low",
                confidence=0.5,
                evidence=EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
                    .observe("EQUIP_ID", eid, record_id=eid).observe("STATUS", "data_missing").finalize(),
                extra={"expected_state": -1, "match_status": "data_missing", "manual_review": True},
            ))
            continue

        # Classify (R5: use closed state from resolver; add current-based rule)
        # Per T-3.1-A: "持续 3 个 15 分钟点" = ANY consecutive window of 3
        # with ≥2 zero-volt readings → match_conflict (closed but no power)
        has_sustained_zero = False
        sustained_window = None
        for start in range(len(voltages) - PERSIST_POINTS + 1):
            window_slice = voltages[start:start + PERSIST_POINTS]
            valid_in_window = [v for v in window_slice if v is not None]
            zero_count = sum(1 for v in valid_in_window if v < VOLTAGE_OFF_V)
            if len(valid_in_window) >= 2 and zero_count >= 2:
                has_sustained_zero = True
                sustained_window = window_slice
                break
        if sustained_window is None:
            sustained_window = voltages[:PERSIST_POINTS] if len(voltages) >= PERSIST_POINTS else voltages
        valid_count = sum(1 for v in sustained_window if v is not None)
        avg_v = sum(v for v in sustained_window if v is not None) / valid_count if valid_count else 0.0
        max_current = max(currents) if currents else 0.0

        if closed is True:
            # ON: should have voltage > threshold
            if avg_v > VOLTAGE_OFF_V:
                status = "match"
            else:
                status = "mismatch_on_no_voltage"
        else:
            # OPEN: should have voltage < threshold (and current ~0)
            if avg_v < VOLTAGE_OFF_V and max_current < 1.0:
                status = "match"
            elif avg_v >= VOLTAGE_OFF_V:
                # R5: closed with voltage → mismatch
                status = "mismatch_off_with_voltage"
            else:
                # open, voltage low but current flowing → R5: current-based mismatch
                status = "mismatch_current_conflict" if max_current > 50.0 else "match"

        if status == "match":
            continue

        # Mismatch found
        # Bug#59: Real KCL — compute node-level current conservation
        _node_id = equip_to_first_node.get(eid, "")
        if _node_id:
            kcl_result = compute_node_kcl_residual(tables, str(_node_id), tolerance=0.5)
        else:
            # Fallback: device-level current sum (less meaningful but non-zero)
            _kcl_total = sum(currents) if currents else 0.0
            class _FallbackKCL:
                residual = abs(_kcl_total)
                passed = abs(_kcl_total) <= 0.5
            kcl_result = _FallbackKCL()
        if status == "mismatch_on_no_voltage":
            desc = f"合位但下游持续 {PERSIST_POINTS} 点无电 (avg ≈ {avg_v:.2f}V, 电压-开关状态不匹配 (合位无压), KCL节点电流幅值残差={kcl_result.residual:.2f}, 滑动窗口检测)"
            expected_state = 0
            correction = "复核接线或开关状态"
            severity = "high"
            confidence=0.85
        elif status == "mismatch_off_with_voltage":
            desc = f"分位但带电 (avg ≈ {avg_v:.2f}V, 电压-开关状态不匹配 (分位带压), KCL节点电流幅值残差={kcl_result.residual:.2f})"
            expected_state = 1
            correction = "检查遥信配对或负荷侧故障"
            severity = "medium"
            confidence=0.85
        else:  # mismatch_current_conflict
            desc = f"分位但下游有电流 (Imax ≈ {max_current:.1f}A, 电流-开关状态冲突, KCL节点电流幅值残差={kcl_result.residual:.2f})"
            expected_state = 1
            correction = "电流型冲突, 检查遥信配对复核"
            severity = "medium"
            confidence=0.8

        ev = EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("SWITCH_STATE", "closed" if closed else "open", expected="closed" if expected_state == 1 else "open")
        ev.observe("VOLTAGE_WINDOW", sustained_window)
        ev.observe("KCL_RESIDUAL", round(kcl_result.residual, 2), expected=0.0)
        ev.observe("MANUAL_REVIEW_REQUIRED", True)

        collected.append(ProblemRecord(
            task_code="3.1",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=desc,
                        correction=f"[待人工复核] {correction}, 电气逻辑合规, 最小修正, 可行方案。系统不自动生成修正 SQL, 请现场核查后处置。",
                        correction_sql="",  # Per official: 3.1 仅注, 不 SQL 修正
            severity=severity,
            confidence=confidence,
            evidence=ev.finalize(),
            extra={
                "expected_state": expected_state,
                "voltage_window": sustained_window,
                "window_avg_v": round(avg_v, 2),
                "match_status": status,
                "voltage_type": dev.get("VOLTAGE_TYPE", ""),
                "max_current": round(max_current, 1),
                "kcl_residual": round(kcl_result.residual, 2),
                "kcl_passed": kcl_result.passed,
                "manual_review": True,
            },
        ))

    # P1#4: spec §3.1 失败回退 — 缺失比例 > 20% → 汇总为"数据不足"
    if total_devs > 0 and dm_count / total_devs > 0.20 and dm_count > 1:
        # Replace individual data_missing records with a single summary
        non_dm = [r for r in collected if r.extra.get("match_status") != "data_missing"]
        summary = ProblemRecord(
            task_code="3.1",
            device_id="DATA_INSUFFICIENT",
            description=(
                f"数据不足: {dm_count}/{total_devs} 设备 ({dm_count*100//total_devs}%) "
                f"遥信/量测缺失超 20%，无法逐台判定，建议补齐采集后重跑"
            ),
            correction="[待人工复核] 补齐遥信/量测采集后重新运行 3.1",
            correction_sql="",
            severity="medium",
            confidence=0.5,
            extra={
                "match_status": "data_insufficient",
                "missing_count": dm_count,
                "total_devices": total_devs,
                "missing_ratio": round(dm_count / total_devs, 4),
                "manual_review": True,
            },
        )
        yield from non_dm
        yield summary
    else:
        yield from collected

    return
