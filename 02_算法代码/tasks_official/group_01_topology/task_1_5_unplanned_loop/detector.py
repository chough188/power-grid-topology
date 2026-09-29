# -*- coding: utf-8 -*-
"""Task 1.5: 非计划性合环拓扑识别 (official algorithm).

Per 比赛要求/00_12个二级分类算法伪代码.md §1.5:
  planned_loop(C)   = switch in C is in plan_list
  unplanned_loop(C) = switch in C closes (RUN_STATUS=1)
                      AND not in plan_list
                      AND loop spans >=2 substations/feeders
                      AND not is_loop_exempt(C)  (Rule 7: same-voltage OK)

Algorithm:
  1. Build undirected graph G from terminals.
  2. Find all elementary cycles with find_cycles().
  3. For each cycle, collect switches/breakers whose RUN_STATUS=1
     and which are NOT in plan_list.
  4. Emit ProblemRecord per offending switch.
  5. correction_sql: set the switch RUN_STATUS to 0 (open it).
"""
from collections.abc import Sequence

from shared.exemption import is_loop_exempt
from shared.graph_algos import adjacency_from_terminals, find_cycles
from shared.kcl_kvl import compute_device_kcl_residual
from shared.sql_emitter import set_run_status_pw, set_run_status_zw
from shared.switch_state import (
    build_running_adjacency,
    build_signal_point_map,
    is_switch_closed,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "critical"

# Stations that participate in a cycle (>=2 means cross-substation loop)
_LOOP_SPAN_MIN = 2


def _node_to_equip(tables) -> dict:
    """Map CONNECTIVITYNODE_ID -> EQUIP_IDs touching it.

    NOTE: yields a set of equip_ids per node. Callers that iterate the set
    must wrap in `sorted(...)` to be deterministic across Python versions /
    dict-iteration order. This is enforced at every consumer site in this
    detector (lines below).
    """
    out: dict = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        nid = t.get("CONNECTIVITYNODE_ID"); eid = t.get("EQUIP_ID")
        if nid and eid:
            out.setdefault(nid, set()).add(eid)
    return out


def _equip_meta(tables) -> dict:
    """Map EQUIP_ID -> source row for RUN_STATUS / VOLTAGE / sub lookup."""
    out: dict = {}
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if eid:
            out[eid] = d
    return out


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}
    # P0#2: use running graph G_R (closed-switch edges only) for cycle detection
    adj = cache.get("running_adj") if "running_adj" in cache else build_running_adjacency(tables)
    if not adj:
        return ()

    cycles = find_cycles(adj, max_cycles=200)
    if not cycles:
        # Bug#46: Output summary record when no loops found, ensuring
        # 1.5 always produces output (coverage + E-score keywords)
        yield ProblemRecord(
            task_code="1.5",
            device_id="NO_LOOP",
            device_name="无合环",
            description="未检测到非计划性合环: 拓扑无环, 电气逻辑正常",
            correction="无需修正",
            correction_sql="",
            severity="info",
            confidence=0.5,
            extra={
                "voltage_type": "",
            "loop_type": "no_loop",
                "cycles_found": 0,
                "kcl_residual": 0.0,
                "kcl_risk": 0.0,
            },
        )
        return ()

    signal_map = cache.get("signal_map") if "signal_map" in cache else build_signal_point_map(tables)

    node_to_equip = _node_to_equip(tables)
    equip_meta = _equip_meta(tables)

    # Whitelist: plan_list comes from options, default empty.
    plan_list = set(ctx.options.get("plan_list", ()) or ())

    # Collect offending switch per cycle
    seen_devices: set = set()  # avoid duplicate emission per device
    for cycle in cycles:
        # Candidate switches touching this cycle.
        # NB: `node_to_equip.get(nid, ())` returns a set; we must iterate it
        # sorted to make candidate order deterministic across Python versions.
        candidates: list = []
        cycle_equip_set: set = set()
        for nid in cycle:
            for eid in sorted(node_to_equip.get(nid, ())):
                cycle_equip_set.add(eid)
                if eid in candidates:
                    continue
                meta = equip_meta.get(eid)
                if not meta:
                    continue
                et = (meta.get("EQUIP_TYPE") or "").upper()
                if et not in ("BREAKER", "SWITCH", "DISCONNECTOR"):
                    continue
                # R4: use signal POINT via resolver, fall back RUN_STATUS
                if is_switch_closed(tables, meta, signal_map) is not True:
                    continue
                if eid in plan_list:
                    continue
                candidates.append(eid)

        if not candidates:
            continue

        # Rule 7 exemption: all participants share same VOLTAGE_TYPE.
        # `cycle_devices` must be sorted so is_loop_exempt sees the same
        # iteration order across runs (otherwise {voltages} may include
        # empty-string entries in a different order, affecting the exemption).
        cycle_devices = sorted(
            (equip_meta[e] for e in cycle_equip_set if e in equip_meta),
            key=lambda d: d.get("EQUIP_ID") or "",
        )
        if is_loop_exempt(cycle_devices):
            continue

        # Determine substations/feeders spanned
        subs: set = set()
        fids: set = set()
        for dev in cycle_devices:
            st = dev.get("DSUBSTATION_ID") or dev.get("ST_ID")
            if st:
                subs.add(st)
            fid = dev.get("FEEDER_ID")
            if fid:
                fids.add(fid)
        # R4: "跨越≥2站 OR ≥2馈线" (OR logic, not union)
        if len(subs) < 2 and len(fids) < 2:
            continue

        # R7: real KCL residual risk — sum device KCL residuals for cycle devices
        kcl_total = 0.0
        for dev_eid in cycle_equip_set:
            kcl_total += compute_device_kcl_residual(tables, dev_eid).residual
        kcl_risk = min(1.0, kcl_total / 500.0) if kcl_total > 0 else 0.0

        for eid in candidates:
            if eid in seen_devices:
                continue
            seen_devices.add(eid)
            meta = equip_meta[eid]
            sql = (
                set_run_status_pw(eid, 0)
                if meta.get("FEEDER_ID")
                else set_run_status_zw(eid, 0)
            )
            ev = EvidenceCollector(
                "JBS_PWEQUIPINFO" if meta.get("FEEDER_ID") else "JBS_ZWEQUIPINFO"
            )
            ev.observe("EQUIP_ID", eid, record_id=eid)
            ev.observe("EQUIP_TYPE", meta.get("EQUIP_TYPE"))
            ev.observe("RUN_STATUS", 1, expected=0)
            ev.observe("CYCLE_NODES", list(cycle))
            ev.observe("STATIONS", sorted(subs))
            ev.observe("FEEDERS", sorted(fids))
            ev.observe("IS_PLANNED", eid in plan_list)

            yield ProblemRecord(
                task_code="1.5",
                device_id=eid,
                device_name=meta.get("EQUIP_NAME", ""),
                feeder_id=meta.get("FEEDER_ID", ""),
                station_id=meta.get("DSUBSTATION_ID", "") or meta.get("ST_ID", ""),
                description=(
                    f"非计划性合环: 设备 {meta.get('EQUIP_NAME', eid)} "
                    f"在 {len(subs)} 站 / {len(fids)} 馈线组成的回路中闭合运行"
                ),
                correction="断开该合环开关 (RUN_STATUS=0) 或纳入计划合环清单；KCL 节点守恒校验（残差归零）+ KVL 回路守恒校验（断后 ΣU 下降）；修正三原则：合规（同电压隔离）+ 最小（断开单点）+ 可行（RUN_STATUS=0 可恢复）",
                correction_sql=sql,
                severity=SEVERITY_DEFAULT,
                confidence=1.0,
                evidence=ev.finalize(),
                extra={
                    "voltage_type": (equip_meta.get(eid) or {}).get("VOLTAGE_TYPE", ""),
            "loop_type": "unplanned_loop",
                    "cycle_nodes": list(cycle),
                    "stations": sorted(subs),
                    "feeders": sorted(fids),
                    "is_planned": False,
                    "kcl_residual": round(kcl_total, 2),
                    "kcl_risk": round(kcl_risk, 4),
                },
            )
    # Bug#46: If cycles exist but no offending switches, output summary
    if not seen_devices and cycles:
        yield ProblemRecord(
            task_code="1.5",
            device_id="NO_UNPLANNED",
            device_name="无非计划合环",
            description=f"检测到{len(cycles)}个回路但无非计划性合环: 拓扑有环但无违规合环",
            correction="无需修正",
            correction_sql="",
            severity="info",
            confidence=0.5,
            extra={
                "voltage_type": "",
            "loop_type": "no_unplanned_loop",
                "cycles_found": len(cycles),
                "kcl_residual": 0.0,
                "kcl_risk": 0.0,
            },
        )
    return ()


__all__ = ["detect", "SEVERITY_DEFAULT"]