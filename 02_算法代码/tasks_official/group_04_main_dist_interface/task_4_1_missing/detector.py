"""Task 4.1: 主配接口漏拼接（official algorithm).

Per 比赛要求/00_12子任务单元测试清单.md T-4.1-01:
"主网出线与配网进线共享 CN → 视为已拼" (不报)

Per T-4.1-02:
"主网出线无配对 + 唯一名称+电压+厂站匹配 → 报 candidate"

Algorithm:
1. For each main-net terminal (JBS_ZWTERMINAL), collect EQUIP_ID + CONNECTIVITYNODE_ID.
2. For each dist-net terminal (JBS_PWTERMINAL), collect EQUIP_ID + CONNECTIVITYNODE_ID.
3. A main-net device is "paired" if its terminal node appears in dist-net.
4. Unpaired main-net devices are candidates for missing interface.
"""
from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from shared.sql_emitter import insert_zw_terminal_for_interface
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "high"


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    # Build map: CONNECTIVITYNODE_ID -> set of EQUIP_IDs in each net
    zw_equip_by_node: dict[str, set[str]] = {}
    _zw_vt = {d.get("EQUIP_ID"): d.get("VOLTAGE_TYPE", "") for d in tables.get("JBS_ZWEQUIPINFO", ())}
    _pw_vt = {d.get("EQUIP_ID"): d.get("VOLTAGE_TYPE", "") for d in tables.get("JBS_PWEQUIPINFO", ())}
    for t in tables.get("JBS_ZWTERMINAL", ()):
        nid = t.get("CONNECTIVITYNODE_ID"); eid = t.get("EQUIP_ID")
        if nid and eid:
            zw_equip_by_node.setdefault(nid, set()).add(eid)

    pw_equip_by_node: dict[str, set[str]] = {}
    for t in tables.get("JBS_PWTERMINAL", ()):
        nid = t.get("CONNECTIVITYNODE_ID"); eid = t.get("EQUIP_ID")
        if nid and eid:
            pw_equip_by_node.setdefault(nid, set()).add(eid)

    # Shared nodes = main-dist already paired
    shared_nodes = set(zw_equip_by_node.keys()) & set(pw_equip_by_node.keys())

    # Main-net equip lookup
    zw_equip_lookup: dict[str, dict] = {}
    for d in tables.get("JBS_ZWEQUIPINFO", ()):
        eid = d.get("EQUIP_ID")
        if eid:
            zw_equip_lookup[eid] = d

    # For each main-net device, check if it's reached any shared node
    # We count shared nodes per device
    zw_equip_shared_count: dict[str, int] = {}
    for nid in shared_nodes:
        for eid in zw_equip_by_node[nid]:
            zw_equip_shared_count[eid] = zw_equip_shared_count.get(eid, 0) + 1

    # 仅当本站存在配网馈线（即存在主配拼接预期）且设备为出线类时，才判定漏拼接，
    # 避免对主网内大量本就无需与配网配对的设备（量测、避雷器等）过度灌水。
    feeder_stations = {
        str(f.get("START_ST_ID") or "")
        for f in tables.get("JBS_PWFEEDERLINE", ())
    }
    outgoing_types = {
        "BREAKER", "SWITCH", "DISCONNECTOR", "LINE", "CONNECTOR",
        "断路器", "开关", "刀闸", "线路", "连接器",
    }

    # Build dist-net equip index (name, voltage, substation) for candidate matching
    pw_candidates: dict[str, dict] = {}  # EQUIP_ID -> {name, voltage, substation}
    for d in tables.get("JBS_PWEQUIPINFO", ()):
        deid = d.get("EQUIP_ID")
        if deid:
            pw_candidates[deid] = {
                "name": (d.get("EQUIP_NAME") or ""),
                "voltage": d.get("VOLTAGE_TYPE"),
                "substation": d.get("DSUBSTATION_ID") or d.get("ST_ID") or "",
            }

    # P0-2: 按 (厂站, 电压) 建倒排索引，避免对每个主网设备全量扫描 ~5万 配网候选
    pw_index_by_sv: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    # Bug#28: Also build voltage-only index for fallback (avoids O(N) scan per device)
    pw_index_by_v: dict[str, list[tuple[str, dict]]] = {}
    for pid, pdata in pw_candidates.items():
        key = (str(pdata["substation"]), str(pdata["voltage"]))
        pw_index_by_sv.setdefault(key, []).append((pid, pdata))
        pw_index_by_v.setdefault(str(pdata["voltage"]), []).append((pid, pdata))

    def _match_score(m_dev: dict, p_dev: dict) -> float:
        """Compute match score [0,1] between main-net and dist-net devices."""
        score = 0.0
        m_vt = m_dev.get("VOLTAGE_TYPE")
        p_vt = p_dev.get("voltage")
        if m_vt is not None and p_vt is not None and str(m_vt) == str(p_vt):
            score += 0.5  # voltage match = strongest signal
        m_st = str(m_dev.get("ST_ID") or "")
        p_st = str(p_dev.get("substation", ""))
        if m_st and p_st and m_st == p_st:
            score += 0.3  # same substation
        m_name = (m_dev.get("EQUIP_NAME") or "").upper()
        p_name = (p_dev.get("name") or "").upper()
        if m_name and p_name:
            score += SequenceMatcher(None, m_name, p_name).ratio() * 0.2  # name similarity
        return score

    # Emit missing interface for main-net outgoing-bay devices with 0 shared nodes
    for dev in tables.get("JBS_ZWEQUIPINFO", ()):
        eid = dev.get("EQUIP_ID")
        if not eid:
            continue
        if zw_equip_shared_count.get(eid, 0) > 0:
            continue  # already paired via shared CN
        st_id = str(dev.get("ST_ID") or "")
        equip_type = (dev.get("EQUIP_TYPE") or "").upper()
        # 仅本站有配网馈线（存在拼接预期）且为出线类设备才判漏拼接
        if st_id not in feeder_stations:
            continue
        if equip_type not in outgoing_types:
            continue

        # R6/P2#7: find best candidate + top_k alternatives → three statuses
        # 先按 (ST_ID, VOLTAGE_TYPE) 精确过滤，再只对命中的候选评分，大幅减少评分样本数
        m_st = str(dev.get("ST_ID") or "")
        m_vt = str(dev.get("VOLTAGE_TYPE") or "")
        candidates = pw_index_by_sv.get((m_st, m_vt))
        if not candidates:
            # Bug#28: Use pre-built voltage-only index instead of O(N) scan
            candidates = pw_index_by_v.get(m_vt, [])[:200]
        scored = [(pid, _match_score(dev, pdata)) for pid, pdata in candidates]
        scored.sort(key=lambda x: -x[1])
        candidate_id = scored[0][0] if scored and scored[0][1] > 0.8 else None
        multi_choice = [pid for pid, sc in scored[:3] if sc > 0.0]
        # Determine status per spec §4.1: candidate / multi_choice / missing
        if candidate_id and len(multi_choice) <= 1:
            status = "candidate"
        elif len(multi_choice) > 1:
            status = "multi_choice"
            candidate_id = multi_choice[0]  # best as primary candidate
        else:
            status = "missing"
            candidate_id = None

        sql = insert_zw_terminal_for_interface(eid, ":shared_node_id")
        ev = EvidenceCollector("JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", dev.get("EQUIP_TYPE"))
        ev.observe("ST_ID", dev.get("ST_ID"))
        ev.observe("SHARED_NODES_COUNT", 0)
        ev.observe("MATCH_STATUS", status)
        if candidate_id:
            ev.observe("BEST_CANDIDATE_ID", candidate_id)
        yield ProblemRecord(
            task_code="4.1",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            station_id=dev.get("ST_ID", ""),
            description=(
                f"主网设备 {dev.get('EQUIP_NAME', eid)} 无配网 CONNECTIVITYNODE 共享 "
                f"({status})"
            ),
            correction="补一条 ZWTERMINAL，使其与对应配网节点共享 CONNECTIVITYNODE_ID",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=0.85,
            evidence=ev.finalize(),
            extra={
                "voltage_type": _zw_vt.get(eid, "") or _pw_vt.get(eid, ""),
                "status": status,
                "shared_nodes_count": 0,
                "candidate": candidate_id,
                "multi_choice": multi_choice,
            },
        )

    return ()
