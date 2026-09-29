# -*- coding: utf-8 -*-
"""Task 4.2: 主配接口错拼接（official algorithm).

Per 比赛要求/00_12个二级分类算法伪代码.md §4.2:

    wrong(m, p) = voltage(m) != voltage(p)
                 OR substation(m) != substation(p)
                 OR multiple_p_share_node(m)        # 同一节点被多进线占用
                 OR trace_to_source(p) != substation(m)

主配接口 = 同时被主网 (JBS_ZWTERMINAL) 与配网 (JBS_PWTERMINAL) 设备共享的
CONNECTIVITYNODE_ID。对每个 (主网设备 m, 配网设备 p) 配对判定 wrong，
错拼必须"先验正确候选，再断旧"（高风险，默认至少一次人工确认）。

修正 SQL（建议但不直接执行）:
  -- 步骤 2: 断开旧
  UPDATE JBS_PWTERMINAL SET VALID_FLAG=0 WHERE ID=<old_term>;
  -- 步骤 3: 建立新（最佳候选节点）
  UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID=<new_cn> WHERE ID=<new_term>;
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.sql_emitter import (
    multi_step,
    set_pw_terminal_valid_flag,
    update_pw_terminal_node,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector
from shared.graph_algos import adjacency_from_terminals, bfs

SEVERITY_DEFAULT = "critical"


def _build_node_terms(tables: dict) -> dict:
    """Map CONNECTIVITYNODE_ID -> list[(eid, term_id, table)]."""
    out: dict[str, list[tuple]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            nid = t.get("CONNECTIVITYNODE_ID")
            eid = t.get("EQUIP_ID")
            tid = t.get("ID")
            if nid and eid:
                out.setdefault(str(nid), []).append(
                    (str(eid), str(tid) if tid is not None else None, tbl)
                )
    return out


def _best_match_node(
    m_meta: dict,
    pw_meta: dict,
    node_terms: dict,
    exclude_node: str,
    excluded_p: str,
    *,
    vs_index: dict[tuple[str, str], list[tuple[str, str]]] | None = None,
) -> str | None:
    """找与主网设备 m 电压/厂站一致、且位于不同节点的配网设备，返回其节点作候选。

    Bug#34: Accepts pre-built (voltage, station) -> [(nid, eid)] index
    to avoid O(N_nodes) scan per call. Falls back to scan if no index.
    """
    vm = m_meta.get("VOLTAGE_TYPE")
    sm = m_meta.get("ST_ID")
    if vs_index is not None:
        candidates = vs_index.get((str(vm), str(sm)), [])
        for (nid2, eid) in candidates:
            if nid2 == exclude_node or eid == excluded_p:
                continue
            return nid2
        return None
    # Fallback: scan node_terms
    for nid2, terms2 in node_terms.items():
        if nid2 == exclude_node:
            continue
        for (eid, _tid, tbl) in terms2:
            if tbl != "JBS_PWTERMINAL" or eid == excluded_p:
                continue
            d = pw_meta.get(eid)
            if not d:
                continue
            sv = d.get("DSUBSTATION_ID") or d.get("ST_ID")
            if d.get("VOLTAGE_TYPE") == vm and sv == sm:
                return nid2
    return None


def _bfs_find_nearest(adj: dict, start: str, targets: set[str]) -> str | None:
    """Bug#31: Early-exit BFS — find nearest target node, return immediately."""
    from collections import deque
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        if node in targets:
            return node
        for nb in adj.get(node, ()):
            if nb not in seen:
                queue.append(str(nb))
    return None


def _trace_to_source_station(
    p_eid: str,
    tables: dict,
    node_terms: dict,
    pw_meta: dict,
    adj: dict | None = None,
    *,
    equip_to_nodes_map: dict[str, set[str]] | None = None,
    source_node_set: set[str] | None = None,
    source_node_station: dict[str, str] | None = None,
) -> str | None:
    """Trace from distribution device p to the nearest source, return its station.

    R7: per spec §4.2, if trace_to_source(p) != substation(m), the
    interface is wrongly spliced.

    Bug#25: equip_to_nodes_map, source_node_set, source_node_station can be
    pre-built by caller to avoid O(N_nodes × N_terms) rebuild per call.
    """
    if adj is None:
        adj = adjacency_from_terminals(tables)
    if not adj:
        return None
    # Find a terminal node of device p (use pre-built map if available)
    if equip_to_nodes_map is not None:
        p_nodes = equip_to_nodes_map.get(p_eid, set())
    else:
        p_nodes: set[str] = set()
        for tid, terms in node_terms.items():
            for (eid, _tid, _tbl) in terms:
                if eid == p_eid:
                    p_nodes.add(tid)
    if not p_nodes:
        return None
    # Use pre-built source lookups if available
    if source_node_set is not None and source_node_station is not None:
        source_nodes = source_node_set
        if not source_nodes:
            return None
        # Bug#31: Early-exit BFS — stop as soon as a source node is found,
        # instead of traversing the entire connected component.
        # Also cache results by start_node to avoid redundant BFS.
        if not hasattr(_trace_to_source_station, "_bfs_cache"):
            _trace_to_source_station._bfs_cache = {}
        cache = _trace_to_source_station._bfs_cache
        for pn in p_nodes:
            if pn not in adj:
                continue
            if pn in cache:
                sn = cache[pn]
            else:
                sn = _bfs_find_nearest(adj, pn, source_nodes)
                cache[pn] = sn
            if sn is not None:
                return source_node_station.get(sn)
        return None
    # Fall back to original logic (no pre-built lookups)
    source_ids: set[str] = set()
    for eid, d in pw_meta.items():
        et = (d.get("EQUIP_TYPE") or "").upper()
        if et in ("SOURCE", "TRANSFORMER", "MAIN"):
            source_ids.add(eid)
    zw_devs = list(tables.get("JBS_ZWEQUIPINFO", ()))
    for d in zw_devs:
        et = (d.get("EQUIP_TYPE") or "").upper()
        if et in ("SOURCE", "TRANSFORMER", "MAIN"):
            source_ids.add(d.get("EQUIP_ID"))
    if not source_ids:
        return None
    source_nodes: set[str] = set()
    for tid, terms in node_terms.items():
        for (eid, _tid, _tbl) in terms:
            if eid in source_ids:
                source_nodes.add(tid)
    if not source_nodes:
        return None
    for pn in p_nodes:
        if pn in adj:
            visited = bfs(adj, pn)
            for sn in source_nodes:
                if sn in visited:
                    for (seid, _tid, _tbl) in node_terms.get(sn, []):
                        if seid in source_ids:
                            src_meta = pw_meta.get(seid) or next(
                                (d for d in zw_devs if d.get("EQUIP_ID") == seid), None
                            )
                            if src_meta:
                                return str(src_meta.get("ST_ID") or src_meta.get("DSUBSTATION_ID") or "")
    return None


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}
    adj_cache = cache.get("adjacency") if "adjacency" in cache else None
    node_terms = _build_node_terms(tables)

    pw_meta: dict = {}
    for d in tables.get("JBS_PWEQUIPINFO", ()):
        eid = d.get("EQUIP_ID")
        if eid:
            pw_meta[str(eid)] = d
    zw_meta: dict = {}
    for d in tables.get("JBS_ZWEQUIPINFO", ()):
        eid = d.get("EQUIP_ID")
        if eid:
            zw_meta[str(eid)] = d
    # 配网馈线 -> 起始厂站
    feeder_sub: dict = {}
    for f in tables.get("JBS_PWFEEDERLINE", ()):
        lid = f.get("LINE_ID")
        if lid:
            feeder_sub[str(lid)] = str(f.get("START_ST_ID") or "")

    # Bug#25: Pre-build equip->nodes, source nodes, and source station map once
    equip_to_nodes_42: dict[str, set[str]] = {}
    for nid, terms in node_terms.items():
        for (eid, _tid, _tbl) in terms:
            equip_to_nodes_42.setdefault(eid, set()).add(nid)
    source_types_42 = {"SOURCE", "TRANSFORMER", "MAIN"}
    source_ids_42: set[str] = set()
    for eid, d in pw_meta.items():
        if (d.get("EQUIP_TYPE") or "").upper() in source_types_42:
            source_ids_42.add(eid)
    for d in tables.get("JBS_ZWEQUIPINFO", ()):
        if (d.get("EQUIP_TYPE") or "").upper() in source_types_42:
            eid = d.get("EQUIP_ID")
            if eid:
                source_ids_42.add(eid)
    source_node_set_42: set[str] = set()
    source_node_station_42: dict[str, str] = {}
    for nid, terms in node_terms.items():
        for (eid, _tid, _tbl) in terms:
            if eid in source_ids_42:
                source_node_set_42.add(nid)
                src_meta = pw_meta.get(eid) or next(
                    (d for d in tables.get("JBS_ZWEQUIPINFO", ()) if d.get("EQUIP_ID") == eid), None
                )
                if src_meta:
                    source_node_station_42[nid] = str(
                        src_meta.get("ST_ID") or src_meta.get("DSUBSTATION_ID") or ""
                    )

    # Bug#34: Pre-build (voltage, station) -> [(nid, eid)] index for _best_match_node
    vs_index_42: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for nid, terms in node_terms.items():
        for (eid, _tid, tbl) in terms:
            if tbl != "JBS_PWTERMINAL":
                continue
            d = pw_meta.get(eid)
            if not d:
                continue
            sv = d.get("DSUBSTATION_ID") or d.get("ST_ID")
            vt = d.get("VOLTAGE_TYPE")
            if vt is not None and sv is not None:
                vs_index_42.setdefault((str(vt), str(sv)), []).append((nid, eid))

    seen_pairs: set[tuple[str, str]] = set()
    wrong_yielded = 0  # P2-7: track yielded records (not inspected pairs) for the sentinel

    for nid, terms in node_terms.items():
        pw_here = [(eid, tid, tbl) for (eid, tid, tbl) in terms if tbl == "JBS_PWTERMINAL"]
        zw_here = [(eid, tid, tbl) for (eid, tid, tbl) in terms if tbl == "JBS_ZWTERMINAL"]
        if not pw_here or not zw_here:
            continue  # 仅主网或仅配网，非主配接口

        for (m, _m_tid, _m_tbl) in zw_here:
            for (p, p_tid, p_tbl) in pw_here:
                if (m, p) in seen_pairs:
                    continue
                seen_pairs.add((m, p))
                m_meta = zw_meta.get(m)
                p_meta = pw_meta.get(p)
                if not m_meta or not p_meta:
                    continue

                voltage_m = m_meta.get("VOLTAGE_TYPE")
                voltage_p = p_meta.get("VOLTAGE_TYPE")
                sub_m = m_meta.get("ST_ID")
                sub_p = p_meta.get("DSUBSTATION_ID") or p_meta.get("ST_ID")
                if not sub_p and p_meta.get("FEEDER_ID"):
                    sub_p = feeder_sub.get(str(p_meta.get("FEEDER_ID")), "")
                multiple_p = len(pw_here) > 1

                reasons: list[str] = []
                if voltage_m != voltage_p:
                    reasons.append("电压不一致")
                if sub_m != sub_p:
                    reasons.append("厂站不一致")
                if multiple_p:
                    reasons.append("同一节点被多进线占用")
                # R7: trace_to_source(p) != substation(m)
                trace_st = _trace_to_source_station(
                    p, tables, node_terms, pw_meta, adj=adj_cache,
                    equip_to_nodes_map=equip_to_nodes_42,
                    source_node_set=source_node_set_42,
                    source_node_station=source_node_station_42,
                )
                if trace_st is not None and sub_m is not None and str(trace_st) != str(sub_m):
                    reasons.append("电源追溯厂站不一致")

                if not reasons:
                    continue  # 正确拼接

                correct_node = _best_match_node(
                    m_meta, pw_meta, node_terms, nid, excluded_p=p,
                    vs_index=vs_index_42,
                )
                correct_p = None
                if correct_node:
                    for (eid, _tid, tbl) in node_terms.get(correct_node, ()):
                        if tbl == "JBS_PWTERMINAL" and eid != p:
                            correct_p = eid
                            break

                # 高风险修正 SQL：先断旧，再建新（若有最佳候选）
                stmts = [set_pw_terminal_valid_flag(p_tid or ":terminal_id", 0)]
                if correct_node and p_tid:
                    stmts.append(update_pw_terminal_node(p_tid, correct_node))
                sql = multi_step(*stmts)

                ev = EvidenceCollector("JBS_ZWEQUIPINFO")
                ev.observe("MAIN_ID", m, record_id=m)
                ev.observe("WRONG_DIST_ID", p, record_id=p)
                ev.observe("SHARED_NODE", nid)
                ev.observe("VOLTAGE_MAIN", voltage_m)
                ev.observe("VOLTAGE_DIST", voltage_p)
                ev.observe("SUBSTATION_MAIN", sub_m)
                ev.observe("SUBSTATION_DIST", sub_p)
                ev.observe("MULTIPLE_P_SHARE_NODE", multiple_p)
                ev.observe("CORRECT_DIST_ID", correct_p)
                ev.observe("CORRECT_NODE", correct_node)

                wrong_yielded += 1
                yield ProblemRecord(
                    task_code="4.2",
                    device_id=f"{m}|{p}",
                    device_name=p_meta.get("EQUIP_NAME", ""),
                    feeder_id=p_meta.get("FEEDER_ID", ""),
                    station_id=sub_p or "",
                    description=(
                        f"主配接口错拼接: 主网 {m}({sub_m}/{voltage_m}kV) 与配网 "
                        f"{p}({sub_p}/{voltage_p}kV) 共享节点 {nid} -> "
                        f"{'、'.join(reasons)}"
                    ),
                    correction=(
                        "高风险：先验正确候选再断旧。建议将配网侧端子改挂至正确节点"
                        + (f" {correct_node}（候选设备 {correct_p}）" if correct_node else "，无正确候选 -> 转人工复核")
                    ),
                    correction_sql=sql,
                    severity=SEVERITY_DEFAULT,
                    confidence=1.0,
                    evidence=ev.finalize(),
                    extra={
                        "voltage_type": (pw_meta.get(p) or {}).get("VOLTAGE_TYPE", ""),
            "high_risk": True,
                        "main_id": m,
                        "wrong_dist_id": p,
                        "correct_dist_id": correct_p,
                        "correct_node": correct_node,
                        "reasons": reasons,
                        "shared_node": nid,
                    },
                )
    # Bug#50 / P2-7: If no WRONG record was produced, output the summary sentinel.
    # Track yielded records (not inspected pairs): a shared node with all-correct
    # interfaces must still emit NO_WRONG_IF.
    if not wrong_yielded:
        yield ProblemRecord(
            task_code="4.2",
            device_id="NO_WRONG_IF",
            device_name="无错拼接口",
            description="未检测到错拼接口: 主配接口匹配正常",
            correction="无需修正",
            correction_sql="",
            severity="info",
            confidence=1.0,
            extra={
                "voltage_type": "",
            "result": "no_WRONG_IF",
            },
        )
    return ()


__all__ = ["detect", "SEVERITY_DEFAULT"]
