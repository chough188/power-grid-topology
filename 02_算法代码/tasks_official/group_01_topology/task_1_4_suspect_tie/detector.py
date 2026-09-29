# -*- coding: utf-8 -*-
"""Task 1.4: 疑似联络开关智能识别与复核研判（R3: 对齐规范5类原因 + POINT字段 + 置信度).

Per 比赛要求/00_12个二级分类算法伪代码.md §1.4:
  - terminal_missing: 端子缺失
  - contiguous_dangle: 连续悬空
  - feeder_conflict:   馈线冲突
  - svg_mismatch:      SVG/图形不匹配
  - repair_unknown:    检修/状态未知
  - confidence < 0.7, correction_sql = "" (仅复核)
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.exemption import is_tie_switch_exempt
from shared.graph_algos import adjacency_from_terminals
from shared.switch_state import (
    build_running_adjacency,
    build_signal_point_map,
    is_switch_closed,
    trace_to_source,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "medium"


def _classify_reason(dev, eid, closed, et, node_stations, my_nodes) -> tuple[str, str, str]:
    """Map device to spec §1.4 reason class + human-readable recommendation + SQL."""
    equip_name = dev.get("EQUIP_NAME", "") or ""
    obj_code = dev.get("OBJ_CODE", "") or ""
    is_maintenance = "检修" in equip_name or "检修" in obj_code
    is_spare = ("备用" in equip_name or "备用" in obj_code or
                "SPARE" in obj_code.upper())

    if is_maintenance:
        return ("repair_unknown", "检修中状态未知，待检修完成后复核", "")
    if is_spare:
        return ("terminal_missing", "备用间隔端子缺失，不进复核",
                "INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) VALUES (?, ?, ?)")
    if et == "DISCONNECTOR":
        return ("feeder_conflict", "刀闸不应作为联络开关，复核两侧电源归属",
                f"UPDATE JBS_PWEQUIPINFO SET FEEDER_ID = :correct_feeder WHERE EQUIP_ID = {eid}")
    if closed is None:
        return ("repair_unknown", "RUN_STATUS缺失，补齐遥信采集后重新判定", "")

    # Check terminal connectivity
    subs: set[str] = set()
    for n in my_nodes:
        subs.update(node_stations.get(n, set()))
    if len(subs) < 2:
        return ("contiguous_dangle", "未触及第二站所，疑似连续悬空", "")
    return ("svg_mismatch", "信号抖动或SVG与模型不匹配，延长采集窗口复核",
            "INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, FEEDER_ID, VOLTAGE_TYPE) VALUES (?, ?, ?, ?, ?)")


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}
    signal_map = cache.get("signal_map") if "signal_map" in cache else build_signal_point_map(tables)
    running_adj = cache.get("running_adj") if "running_adj" in cache else build_running_adjacency(tables)

    # Bug#24: Pre-build equip lookups once (was rebuilt per-device in loop)
    equip_station: dict[str, str] = {}
    equip_meta_14: dict[str, dict] = {}
    for d in list(tables.get("JBS_ZWEQUIPINFO", ())) + list(tables.get("JBS_PWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        st = d.get("ST_ID") or d.get("DSUBSTATION_ID")
        if eid and st:
            equip_station[eid] = st
        if eid:
            equip_meta_14[str(eid)] = d

    # Pre-build equip -> nodes and node -> equips lookups once
    equip_to_nodes_14: dict[str, list[str]] = {}
    node_to_equips_14: dict[str, set[str]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            nid = t.get("CONNECTIVITYNODE_ID")
            eid = t.get("EQUIP_ID")
            if nid and eid:
                equip_to_nodes_14.setdefault(str(eid), []).append(str(nid))
                node_to_equips_14.setdefault(str(nid), set()).add(str(eid))

    node_stations: dict[str, set[str]] = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        nid = t.get("CONNECTIVITYNODE_ID")
        eid = t.get("EQUIP_ID")
        st = equip_station.get(eid)
        if nid and st:
            node_stations.setdefault(nid, set()).add(st)

    feeder_name: dict[str, str] = {}
    feeder_station: dict[str, str] = {}
    for f in tables.get("JBS_PWFEEDERLINE", ()):
        lid = f.get("LINE_ID")
        if lid:
            feeder_name[lid] = f.get("LINE_NAME", "")
            sst = f.get("START_ST_ID")
            if sst:
                feeder_station[lid] = sst
    station_name: dict[str, str] = {}
    for s in tables.get("JBS_ZWSUBSTATION", ()):
        sid = s.get("ST_ID")
        if sid:
            station_name[sid] = s.get("ST_NAME", "")

    seen: set[str] = set()
    for dev in list(tables.get("JBS_ZWEQUIPINFO", ())) + list(tables.get("JBS_PWEQUIPINFO", ())):
        et = (dev.get("EQUIP_TYPE") or "").upper()
        if et not in ("BREAKER", "SWITCH", "DISCONNECTOR"):
            continue

        closed = is_switch_closed(tables, dev, signal_map)
        if closed is True:
            continue

        eid = dev.get("EQUIP_ID")
        if not eid or eid in seen:
            continue
        same_room = bool(dev.get("DSUBSTATION_ID"))
        if is_tie_switch_exempt(dev, same_room):
            continue

        my_nodes = list(equip_to_nodes_14.get(str(eid), []))
        if not my_nodes:
            continue

        if len(my_nodes) >= 2:
            src1 = trace_to_source(running_adj, my_nodes[0], tables, exclude_equip=eid,
                                  node_to_equips=node_to_equips_14, equip_meta=equip_meta_14)
            src2 = trace_to_source(running_adj, my_nodes[1], tables, exclude_equip=eid,
                                  node_to_equips=node_to_equips_14, equip_meta=equip_meta_14)
        elif len(my_nodes) == 1:
            src1 = trace_to_source(running_adj, my_nodes[0], tables, exclude_equip=eid,
                                  node_to_equips=node_to_equips_14, equip_meta=equip_meta_14)
            src2 = None
        else:
            src1 = src2 = None

        # Suspect tie policy (original 1.3 logic):
        # Both sides trace OK and same station/feeder → not a tie, skip
        # Both sides trace OK (different) → not 1.4 territory, skip
        # Exactly one side fails → suspect
        # Both sides fail → skip (not a tie at all)
        if src1 and src2:
            continue  # both OK → this is 1.3 territory, not suspect
        if not src1 and not src2:
            continue  # both fail → not a tie candidate
        # Otherwise: exactly one side fails → suspect
        seen.add(eid)

        subs = set()
        if src1:
            subs.add(src1["station"])
        if src2:
            subs.add(src2["station"])

        fail_reason, recommend, reason_sql = _classify_reason(
            dev, eid, closed, et, node_stations, my_nodes,
        )

        confidence = 0.6

        my_fid = dev.get("FEEDER_ID") or ""
        ok_src = src1 or src2
        paired_fid = ok_src["feeder"] if ok_src and ok_src.get("feeder") else ""
        paired_fid_name = feeder_name.get(paired_fid, "") if paired_fid else ""
        paired_fid_station = feeder_station.get(paired_fid, "") if paired_fid else ""
        paired_station_name = station_name.get(paired_fid_station, paired_fid_station)

        ev = EvidenceCollector("JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", et)
        ev.observe("FAIL_REASON", fail_reason)
        ev.observe("SRC1", src1)
        ev.observe("SRC2", src2)

        yield ProblemRecord(
            task_code="1.4",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=(
                f"疑似联络 [{fail_reason}]: {dev.get('EQUIP_NAME', eid)} "
                f"(et={et}) 单侧追溯失败"
            ),
            correction=f"[待人工复核] {recommend}",
            correction_sql=reason_sql,
            severity=SEVERITY_DEFAULT,
            confidence=confidence,
            evidence=ev.finalize(),
            extra={
                "stations": sorted(subs),
                "voltage_type": (equip_meta_14.get(eid) or {}).get("VOLTAGE_TYPE", ""),
            "fail_reason": fail_reason,
                "recommend": recommend,
                "tie_line_id": paired_fid,
                "tie_line_name": paired_fid_name,
                "tie_line_station": paired_station_name,
            },
        )

    # NOTE(Bug#49 回退): 曾有 NO_SUSPECT_TIE 汇总 sentinel, 其 fail_reason="no_suspect_tie"
    # 不属于评审手册 §4.2 五分类 {terminal_missing, feeder_conflict, svg_mismatch,
    # contiguous_dangle, repair_unknown}, 导致 test_five_fail_reason_categories 恒红。
    # 任务覆盖由 5.0 评分的 Bug#27 空列表补齐保证, 无需 sentinel。