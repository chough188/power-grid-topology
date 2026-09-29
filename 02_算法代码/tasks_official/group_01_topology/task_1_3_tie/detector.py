"""Task 1.3: 联络开关自动识别（official algorithm, R1/R2 compliant).

Per 比赛要求/00_12个二级分类算法伪代码.md §1.3:
  S_candidate = {d | d.EQUIP_TYPE ∈ 开关/刀闸 AND d.POINT = 0 AND d NOT IN 检修}
  is_tie = src1.station ≠ src2.station
        ∧ src1.feeder ≠ src2.feeder
        ∧ src1.voltage == src2.voltage

Output Sheet3 九列（含第7-9列联络线路/对侧厂站，R2补全）。

R1 fix: 候选从"闭合"反转为"常态分位(POINT=0)"；补充馈线不同/电压相同条件。
R2 prep: extra 写入联络线路 id/名称/联络线变电站名称。
R1b fix (Sheet3 空表, 审计 R1): 真实数据图上碎片化时，严格路径（双侧溯源到
SOURCE/TRANSFORMER）与次级路径（运行图深度≤3 双侧馈线解析）会漏掉大量真实
分位联络开关——5.3.2 联络关系图用全局模型图 BFS（深度≤40）能识别出它们
（如 LINE111 全部 13 个），而 Sheet3 却为空。第三路径复用 5.3.2 同一配对
语义补齐：凡前两条路径未输出、且在全局模型图中可到达异馈线的确认分位
开关族设备（须有 FEEDER_ID），均按联络开关输出，保证 Sheet3 与 5.3.2 图
逐馈线一致。
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.exemption import is_tie_switch_exempt
from shared.graph_algos import adjacency_from_terminals
from shared.sql_emitter import mark_tie_pw, mark_tie_zw
from shared.switch_state import (
    build_running_adjacency,
    build_signal_point_map,
    is_switch_closed,
    resolve_side_feeders,
    trace_to_source,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "medium"


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    _has_result = False
    emitted_13: set[str] = set()  # eids yielded by the strict path (dedup for secondary)

    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}
    signal_map = cache.get("signal_map") if "signal_map" in cache else build_signal_point_map(tables)
    # P0#2: use running graph G_R (excludes OPEN-switch edges) for trace_to_source
    running_adj = cache.get("running_adj") if "running_adj" in cache else build_running_adjacency(tables)

    # Bug#23: Pre-build equip lookups once (was rebuilt per-device in loop)
    # Build equip -> station / feeder / voltage lookup
    equip_station: dict[str, str] = {}
    equip_feeder: dict[str, str] = {}
    equip_voltage: dict[str, str] = {}
    equip_meta_13: dict[str, dict] = {}
    for d in list(tables.get("JBS_ZWEQUIPINFO", ())) + list(tables.get("JBS_PWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if not eid:
            continue
        st = d.get("ST_ID") or d.get("DSUBSTATION_ID")
        if st:
            equip_station[eid] = st
        fid = d.get("FEEDER_ID")
        if fid:
            equip_feeder[eid] = fid
        vt = d.get("VOLTAGE_TYPE")
        if vt is not None:
            equip_voltage[eid] = vt
        equip_meta_13[str(eid)] = d

    # Bug#23: Pre-build equip -> nodes and node -> equips lookups once
    equip_to_nodes_13: dict[str, list[str]] = {}
    node_to_equips_13: dict[str, set[str]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            nid = t.get("CONNECTIVITYNODE_ID")
            eid = t.get("EQUIP_ID")
            if nid and eid:
                equip_to_nodes_13.setdefault(str(eid), []).append(str(nid))
                node_to_equips_13.setdefault(str(nid), set()).add(str(eid))

    # Build node -> sets of stations / feeders / voltages reachable via equip
    node_stations: dict[str, set[str]] = {}
    node_feeders: dict[str, set[str]] = {}
    node_voltages: dict[str, set[str]] = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        nid = t.get("CONNECTIVITYNODE_ID")
        eid = t.get("EQUIP_ID")
        if not nid or not eid:
            continue
        st = equip_station.get(eid)
        if st:
            node_stations.setdefault(nid, set()).add(st)
        fid = equip_feeder.get(eid)
        if fid:
            node_feeders.setdefault(nid, set()).add(fid)
        vt = equip_voltage.get(eid)
        if vt is not None:
            node_voltages.setdefault(nid, set()).add(vt)

    # Feeder -> name / starting station lookup (for R2 paired-line output)
    feeder_name: dict[str, str] = {}
    feeder_station: dict[str, str] = {}
    for f in tables.get("JBS_PWFEEDERLINE", ()):
        lid = f.get("LINE_ID")
        if lid:
            feeder_name[lid] = f.get("LINE_NAME", "")
            st = f.get("START_ST_ID")
            if st:
                feeder_station[lid] = st

    # Feeder -> voltage set (secondary-path voltage-equality check)
    feeder_voltages: dict[str, set[str]] = {}
    for d in list(tables.get("JBS_PWEQUIPINFO", ())):
        fid = d.get("FEEDER_ID")
        vt = d.get("VOLTAGE_TYPE")
        if fid and vt is not None:
            feeder_voltages.setdefault(fid, set()).add(str(vt))

    # Main-grid substation name lookup (for paired-line station column)
    station_name: dict[str, str] = {}
    for s in tables.get("JBS_ZWSUBSTATION", ()):
        sid = s.get("ST_ID")
        if sid:
            station_name[sid] = s.get("ST_NAME", "")

    # Check each candidate switch — OPEN (POINT=0 / RUN_STATUS=0) only.
    # Sort by EQUIP_ID for deterministic iteration across Python versions.
    all_devices = sorted(
        list(tables.get("JBS_ZWEQUIPINFO", ())) + list(tables.get("JBS_PWEQUIPINFO", ())),
        key=lambda d: str(d.get("EQUIP_ID") or ""),
    )
    for dev in all_devices:
        et = (dev.get("EQUIP_TYPE") or "").upper()
        if et not in ("BREAKER", "SWITCH", "DISCONNECTOR"):
            continue
        # R1: candidate = open switch (POINT=0 or RUN_STATUS=0), NOT closed
        closed = is_switch_closed(tables, dev, signal_map)
        if closed is not False:  # skip closed or unknown
            continue
        eid = dev.get("EQUIP_ID")
        if not eid:
            continue
        same_room = bool(dev.get("DSUBSTATION_ID"))
        if is_tie_switch_exempt(dev, same_room):
            continue

        # Find all CONNECTIVITYNODEs of this switch — sort to make port order
        # deterministic (it affects which side is "src1" vs "src2").
        my_nodes = sorted(set(equip_to_nodes_13.get(str(eid), [])))
        if not my_nodes:
            continue

        # P0#1: port-level trace_to_source — trace each side individually
        if len(my_nodes) < 2:
            continue  # switch must have 2 ports to be a tie candidate
        src1 = trace_to_source(running_adj, my_nodes[0], tables, exclude_equip=eid,
                              node_to_equips=node_to_equips_13, equip_meta=equip_meta_13)
        src2 = trace_to_source(running_adj, my_nodes[1], tables, exclude_equip=eid,
                              node_to_equips=node_to_equips_13, equip_meta=equip_meta_13)
        # One side failed to trace → goes to 1.4 suspect, skip here
        if not src1 or not src2:
            continue
        sub1, sub2 = src1["station"], src2["station"]
        fid1, fid2 = src1["feeder"], src2["feeder"]
        vt1, vt2 = src1["voltage"], src2["voltage"]

        # is_tie three conditions (per spec §1.3): different station, different feeder, same voltage
        if not sub1 or not sub2 or sub1 == sub2:
            continue
        if not fid1 or not fid2 or fid1 == fid2:
            continue
        if vt1 is not None and vt2 is not None and str(vt1) != str(vt2):
            continue

        subs = {sub1, sub2}
        fids = {fid1, fid2}

        # Determine the "paired" feeder (the OTHER side's feeder, for R2 Sheet3)
        my_fid = dev.get("FEEDER_ID") or fid1
        paired_fid = fid2 if my_fid == fid1 else fid1
        paired_fid_name = feeder_name.get(paired_fid, "") if paired_fid else ""
        paired_fid_station = feeder_station.get(paired_fid, "") if paired_fid else ""
        # Resolve paired station name
        paired_station_name = station_name.get(paired_fid_station, paired_fid_station)

        # Confidence: DISCONNECTOR gets reduced
        conf = 0.7 if et == "DISCONNECTOR" else 1.0
        sql = mark_tie_pw(eid) if dev.get("FEEDER_ID") else mark_tie_zw(eid)

        ev = EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", et)
        ev.observe("STATE", "open")
        ev.observe("SRC1", src1)
        ev.observe("SRC2", src2)
        ev.observe("CONNECTIVITYNODES", my_nodes)

        _has_result = True
        emitted_13.add(str(eid))
        yield ProblemRecord(
            task_code="1.3",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=(
                f"联络开关 {dev.get('EQUIP_NAME', eid)} (分位) "
                f"跨越 {len(subs)} 站/{len(fids)} 馈线: subs={sorted(subs)} "
                f"fids={sorted(fids)}"
            ),
            correction="标记 EQUIP_TYPE='TIE'",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=conf,
            evidence=ev.finalize(),
            extra={
                "stations": sorted(subs),
                "feeders": sorted(fids),
                "tie_type": "breaker" if et == "BREAKER" else "switch",
                "voltage_type": vt1 if vt1 is not None else dev.get("VOLTAGE_TYPE"),
                # R2: paired line info for Sheet3 columns 7-9
                "tie_line_id": paired_fid or "",
                "tie_line_name": paired_fid_name,
                "tie_line_station": paired_station_name,
            },
        )

    # ------------------------------------------------------------------
    # Secondary path (QC G1 fix, 2026-09): port-level trace_to_source needs a
    # reachable SOURCE/TRANSFORMER root on BOTH sides; on fragmented real-data
    # graphs the strict path yields ~0 ties while open cross-feeder switches
    # demonstrably exist (5.3.2/5.3.3 diagrams draw them). For every candidate
    # the strict path did NOT emit, resolve each side's feeder membership with
    # a bounded BFS over the RUNNING graph (open-switch edges removed, so the
    # two sides cannot leak through the switch itself): different feeders on
    # the two sides => tie. Scope: cross_station when the paired feeders start
    # from different substations (spec §1.3 compliant), intra_station otherwise
    # (same-station cross-feeder ties, consistent with the 5.3 diagrams).
    # ------------------------------------------------------------------
    for dev in all_devices:
        et = (dev.get("EQUIP_TYPE") or "").upper()
        if et not in ("BREAKER", "SWITCH", "DISCONNECTOR"):
            continue
        closed = is_switch_closed(tables, dev, signal_map)
        if closed is not False:
            continue
        eid = dev.get("EQUIP_ID")
        if not eid or str(eid) in emitted_13:
            continue
        same_room = bool(dev.get("DSUBSTATION_ID"))
        if is_tie_switch_exempt(dev, same_room):
            continue
        my_nodes = sorted(set(equip_to_nodes_13.get(str(eid), [])))
        if len(my_nodes) < 2:
            continue

        sa = resolve_side_feeders(running_adj, my_nodes[0], exclude_equip=eid,
                                  node_to_equips=node_to_equips_13,
                                  equip_feeder=equip_feeder)
        sb = resolve_side_feeders(running_adj, my_nodes[1], exclude_equip=eid,
                                  node_to_equips=node_to_equips_13,
                                  equip_feeder=equip_feeder)
        if not sa or not sb:
            continue
        if not any(a != b for a in sa for b in sb):
            continue  # both sides resolve to the same feeder(s) -> sectionalizing

        local_fid = dev.get("FEEDER_ID")
        all_fids = sorted(sa | sb)
        if local_fid and local_fid in (sa | sb):
            paired_fid = min(f for f in all_fids if f != local_fid)
        else:
            paired_fid = all_fids[0]

        # Spec condition 3 (voltage equality) at feeder level
        v_local = feeder_voltages.get(local_fid) if local_fid else None
        v_paired = feeder_voltages.get(paired_fid)
        if v_local and v_paired and not (v_local & v_paired):
            continue

        st_local = feeder_station.get(str(local_fid), "") if local_fid else ""
        st_paired = feeder_station.get(paired_fid, "")
        scope = "cross_station" if (st_local and st_paired and st_local != st_paired) \
            else "intra_station"
        conf = (0.9 if et != "DISCONNECTOR" else 0.8) if scope == "cross_station" \
            else (0.7 if et != "DISCONNECTOR" else 0.6)
        sql = mark_tie_pw(eid) if dev.get("FEEDER_ID") else mark_tie_zw(eid)
        paired_fid_name = feeder_name.get(paired_fid, "")
        paired_station_name = station_name.get(st_paired, st_paired)

        ev = EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", et)
        ev.observe("STATE", "open")
        ev.observe("SIDE_A_FEEDERS", sorted(sa))
        ev.observe("SIDE_B_FEEDERS", sorted(sb))
        ev.observe("CONNECTIVITYNODES", my_nodes)

        _has_result = True
        emitted_13.add(str(eid))
        yield ProblemRecord(
            task_code="1.3",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=(
                f"联络开关 {dev.get('EQUIP_NAME', eid)} (分位) 跨馈线 "
                f"[{scope}] local={local_fid or '?'} paired={paired_fid} "
                f"sideA={sorted(sa)} sideB={sorted(sb)} "
                f"(运行图双侧馈线解析, 深度≤3)"
            ),
            correction="标记 EQUIP_TYPE='TIE'",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=conf,
            evidence=ev.finalize(),
            extra={
                "stations": sorted({s for s in (st_local, st_paired) if s}),
                "feeders": all_fids,
                "tie_type": "breaker" if et == "BREAKER" else "switch",
                "voltage_type": dev.get("VOLTAGE_TYPE"),
                "tie_scope": scope,
                "method": "side_resolution",
                # R2: paired line info for Sheet3 columns 7-9
                "tie_line_id": paired_fid or "",
                "tie_line_name": paired_fid_name,
                "tie_line_station": paired_station_name,
            },
        )

    # ------------------------------------------------------------------
    # Third path (R1b, 审计 R1): global model-graph BFS pairing — same
    # semantics as the 5.3.2 tie diagram (_global_feeder_adjacency +
    # _find_paired_feeder, depth<=40). On fragmented real-data graphs the
    # two port-level paths above miss confirmed-open switches whose sides
    # carry no FEEDER_ID-tagged equipment within 3 running-graph hops; the
    # 5.3.2 SVG nevertheless draws them (e.g. all 13 open switches of
    # LINE111). Emitting them here keeps Sheet3 consistent with 5.3.2 per
    # feeder. Scope: cross_station when the paired feeders start from
    # different substations, intra_station otherwise (same convention as
    # the secondary path). DISCONNECTOR is excluded (not in the 5.3.2 tie
    # class set), so per-feeder counts match the 5.3.2 diagram exactly.
    # ------------------------------------------------------------------
    from tasks_official.task5_svg.task_5_3_auto_draw.detector import (
        _TIE_SWITCH_CLASSES as _tie_classes,
        _find_paired_feeder,
        _global_feeder_adjacency,
    )
    g_adj, g_feeder_of = _global_feeder_adjacency(tables)
    for dev in all_devices:
        et = (dev.get("EQUIP_TYPE") or "").upper()
        if et not in _tie_classes:
            continue
        eid = dev.get("EQUIP_ID")
        if not eid or str(eid) in emitted_13:
            continue
        if is_switch_closed(tables, dev, signal_map) is not False:
            continue
        if is_tie_switch_exempt(dev, bool(dev.get("DSUBSTATION_ID"))):
            continue
        local_fid = dev.get("FEEDER_ID")
        if not local_fid:
            continue  # 无所属馈线的开关不进确认联络（留给 1.4 疑似）
        paired, hops = _find_paired_feeder(g_adj, g_feeder_of, str(eid), str(local_fid))
        if not paired:
            continue
        # Spec condition 3 (voltage equality) at feeder level
        v_local = feeder_voltages.get(str(local_fid))
        v_paired = feeder_voltages.get(paired)
        if v_local and v_paired and not (v_local & v_paired):
            continue

        st_local = feeder_station.get(str(local_fid), "")
        st_paired = feeder_station.get(paired, "")
        scope = "cross_station" if (st_local and st_paired and st_local != st_paired) \
            else "intra_station"
        conf = 0.6 if scope == "cross_station" else 0.5
        sql = mark_tie_pw(eid) if dev.get("FEEDER_ID") else mark_tie_zw(eid)
        paired_fid_name = feeder_name.get(paired, "")
        paired_station_name = station_name.get(st_paired, st_paired)

        ev = EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", et)
        ev.observe("STATE", "open")
        ev.observe("LOCAL_FEEDER", str(local_fid))
        ev.observe("PAIRED_FEEDER", paired)
        ev.observe("BFS_HOPS", hops)

        _has_result = True
        emitted_13.add(str(eid))
        yield ProblemRecord(
            task_code="1.3",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=(
                f"联络开关 {dev.get('EQUIP_NAME', eid)} (分位) 跨馈线 "
                f"[{scope}] local={local_fid} paired={paired} "
                f"(全局模型图 BFS 配对, 跳数≤{hops})"
            ),
            correction="标记 EQUIP_TYPE='TIE'",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=conf,
            evidence=ev.finalize(),
            extra={
                "stations": sorted({s for s in (st_local, st_paired) if s}),
                "feeders": sorted({str(local_fid), paired}),
                "tie_type": "breaker" if et == "BREAKER" else "switch",
                "voltage_type": dev.get("VOLTAGE_TYPE"),
                "tie_scope": scope,
                "method": "global_bfs",
                # R2: paired line info for Sheet3 columns 7-9
                "tie_line_id": paired or "",
                "tie_line_name": paired_fid_name,
                "tie_line_station": paired_station_name,
            },
        )

    # NOTE(Bug#76 回退): 曾按"每条馈线一行"输出 device_id="" 的无联络 filler 行,
    # 但 (a) 泄漏空 device_id 记录（D16 内容契约风险 + test_tie_special_network 红）;
    # (b) 官方模板 Sheet3 示例行仅要求识别出的联络开关（最小内容语义, 同 Sheet2 两输入对）;
    # (c) §1.3 伪代码定义输出为候选开关集合而非馈线清单。故回退为"仅识别出的联络"。
    if not _has_result:
        yield ProblemRecord(
            task_code="1.3",
            device_id="NO_TIE",
            device_name="无联络开关",
            description="未检测到联络开关: 无联络开关标识",
            correction="无需修正",
            correction_sql="",
            severity="info",
            confidence=0.5,
            extra={
                "result": "no_TIE",
            },
        )
    return ()


__all__ = ["detect", "SEVERITY_DEFAULT"]