"""Task 2.4: 图形物理断开、拓扑逻辑误连通校验 (R8: 校验对端合位 + 修正迭代).

Algorithm:
- For devices that are OPEN (POINT=0 / RUN_STATUS=0), find terminals shared
  with OTHER CLOSED devices via CONNECTIVITYNODE
- Only flag as false_link when the other device is CLOSED (POINT=1 / RUN_STATUS=1)
- If all neighbours are also open, no false_link — correct topology.
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.exemption import is_measurement_exempt
from shared.graph_algos import adjacency_from_terminals
from shared.sql_emitter import set_pw_terminal_valid_flag
from shared.switch_state import build_signal_point_map, is_switch_closed
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "medium"


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}
    adj = cache.get("adjacency") if "adjacency" in cache else adjacency_from_terminals(tables)
    if not adj:
        return ()
    signal_map = cache.get("signal_map") if "signal_map" in cache else build_signal_point_map(tables)

    # Build set of OPEN devices (R8: use resolver)
    open_devices = set()
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        if is_switch_closed(tables, d, signal_map) is False:
            eid = d.get("EQUIP_ID")
            if eid:
                open_devices.add(eid)

    # Pre-build: equip -> [(terminal_id, node_id)] and node -> [equip_id] indexes
    # (original code did O(N) scan per open device per terminal = O(open * terminals^2))
    equip_terminals: dict[str, list[tuple]] = {}
    node_equips: dict[str, list[str]] = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = t.get("EQUIP_ID")
        nid = t.get("CONNECTIVITYNODE_ID")
        tid = t.get("ID")
        if eid and nid:
            equip_terminals.setdefault(eid, []).append((tid, nid))
            node_equips.setdefault(nid, []).append(eid)

    # Pre-compute closed status for all devices (avoid repeated is_switch_closed calls)
    all_equips = list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ()))
    closed_status: dict[str, bool] = {}
    for dev in all_equips:
        eid = dev.get("EQUIP_ID")
        if eid:
            result = is_switch_closed(tables, dev, signal_map)
            closed_status[eid] = result is not False  # True if closed or unknown

    # For each open device, find terminals shared with CLOSED devices
    seen_terminals: set[str] = set()
    for dev in all_equips:
        eid = dev.get("EQUIP_ID")
        if eid not in open_devices:
            continue
        my_terminals = []
        for tid, nid in equip_terminals.get(eid, []):
            if nid in adj:
                # R8: only flag if neighbour is CLOSED (use pre-computed index)
                closed_neighbours = [
                    neid for neid in node_equips.get(nid, [])
                    if neid != eid and closed_status.get(neid, True)
                ]
                if closed_neighbours:
                    my_terminals.append((tid, nid, closed_neighbours))

        for terminal_id, nid, closed_neighbours in my_terminals:
            if terminal_id in seen_terminals:
                continue
            seen_terminals.add(terminal_id)
            # Bug#41: 答疑明确禁止DELETE（可能影响拓扑连接关系），改为 UPDATE VALID_FLAG=0
            sql = set_pw_terminal_valid_flag(terminal_id, 0) if dev.get("FEEDER_ID") else "UPDATE JBS_ZWTERMINAL SET VALID_FLAG = 0 WHERE ID = :terminal_id"
            ev = EvidenceCollector("JBS_PWTERMINAL")
            ev.observe("TERMINAL_ID", terminal_id, record_id=terminal_id)
            ev.observe("EQUIP_ID", eid)
            ev.observe("CONNECTIVITYNODE_ID", nid)
            ev.observe("CLOSED_NEIGHBOURS", closed_neighbours)
            yield ProblemRecord(
                task_code="2.4",
                device_id=eid,
                device_name=dev.get("EQUIP_NAME", ""),
                feeder_id=dev.get("FEEDER_ID", ""),
                station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
                description=f"设备 {dev.get('EQUIP_NAME', eid)} 分位但端子 {terminal_id} 仍连到合位设备 {closed_neighbours}",
                correction=f"置无效 TERMINAL {terminal_id} (VALID_FLAG=0)",
                correction_sql=sql,
                severity=SEVERITY_DEFAULT,
                confidence=0.85,
                evidence=ev.finalize(),
                extra={"voltage_type": dev.get("VOLTAGE_TYPE", ""), "status": "false_link", "terminal_id": terminal_id, "closed_neighbours": closed_neighbours},
            )

    return ()
