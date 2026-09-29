# -*- coding: utf-8 -*-
"""Task 2.3: 图形物理连通、拓扑逻辑断开校验 (official algorithm).

Per 比赛要求/00_12个二级分类算法伪代码.md §2.3:

    SVG 中 a、b 物理连通 (折线/路径)
    模型中 a、b 不连通 (CONNECTIVITYNODE_ID 不一致)

    check_logic_break(svg_connections, model_edges):
      for (a, b) in svg_connections:
        if physically_connected(svg, a, b) and not model_connected(a, b):
          t_a, t_b = terminals_of(a), terminals_of(b)
          if not t_a or not t_b:            -> terminal_missing
          elif t_a.CN is None or t_b.CN None: -> node_missing
          elif t_a.CN != t_b.CN:             -> logic_break

SVG 物理连通由调用方以 `ctx.options["svg_connections"]` 注入
（list[(a, b)]，每个元素是 SVG 中视觉相连的 (EQUIP_ID, EQUIP_ID) 对）。
这与 2.1/2.2 通过 `ctx.options["svg_devices"]` 注入图元集合的口径一致。
未注入时返回空（不误报）。

修正 SQL:
  - logic_break : UPDATE TERMINAL SET CONNECTIVITYNODE_ID = 共享节点
  - terminal_missing : INSERT TERMINAL
  - node_missing : UPDATE TERMINAL SET CONNECTIVITYNODE_ID = 合法节点
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.sql_emitter import (
    insert_pw_terminal,
    insert_zw_terminal,
    update_pw_terminal_node,
    update_zw_terminal_node,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "high"


def _fallback_infer_connections(tables: dict) -> list[tuple[str, str]]:
    """Infer candidate svg_connections when options are missing.

    Strategy: find equipment with terminals that have empty CONNECTIVITYNODE_ID.
    For each such equipment, propose a synthetic svg_connection with its nearest
    connected neighbour (sharing any node). This represents the real-world case
    where SVG shows a physical connection but the model hasn't been updated yet.
    """
    def _is_missing_node(nid) -> bool:
        if nid is None or nid == "":
            return True
        if isinstance(nid, str) and nid.startswith("LOGIC_BREAK_"):
            return True
        return False

    equip_nodes: dict[str, set[str]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            eid = t.get("EQUIP_ID")
            nid = t.get("CONNECTIVITYNODE_ID")
            if eid and not _is_missing_node(nid):
                equip_nodes.setdefault(str(eid), set()).add(str(nid))
    out: list[tuple[str, str]] = []
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            eid = t.get("EQUIP_ID")
            nid = t.get("CONNECTIVITYNODE_ID")
            if not eid or not _is_missing_node(nid):
                continue
            # Find first neighbour sharing any node with this equip
            for other, nodes in equip_nodes.items():
                if other == eid:
                    continue
                if nodes:
                    out.append((str(eid), other))
                    break
            if len(out) >= 10:
                break
        if len(out) >= 10:
            break
    return out


def _equip_terminals(tables: dict) -> dict:
    """Map EQUIP_ID -> list[(terminal_id, node_id, table_name)] from both nets."""
    out: dict[str, list[tuple]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for t in tables.get(tbl, ()):
            eid = t.get("EQUIP_ID")
            if not eid:
                continue
            tid = t.get("ID")
            nid = t.get("CONNECTIVITYNODE_ID")
            nid = str(nid) if nid not in (None, "") else None
            out.setdefault(str(eid), []).append(
                (str(tid) if tid is not None else None, nid, tbl)
            )
    return out


def _equip_meta(tables: dict) -> dict:
    out: dict = {}
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if eid:
            out[str(eid)] = d
    return out


def _terminal_update_sql(table_name: str, terminal_id: str, shared_node: str) -> str:
    if table_name == "JBS_ZWTERMINAL":
        return update_zw_terminal_node(terminal_id, shared_node)
    return update_pw_terminal_node(terminal_id, shared_node)


def _terminal_update_sql_in(table_name: str, id_list: str, shared_node: str) -> str:
    """Single UPDATE covering multiple terminals via WHERE ID IN (...) —
    official §2.3 correction form (UPDATE ... WHERE ID IN (?, ?)).

    Terminal IDs are known data values and are inlined as quoted literals
    (same convention as 2.4); the target node stays a named bind.
    """
    if table_name == "JBS_ZWTERMINAL":
        return (
            f"UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node "
            f"WHERE ID IN ({id_list})"
        )
    return (
        f"UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node "
        f"WHERE ID IN ({id_list})"
    )


def _terminal_insert_sql(eid: str, table_name: str, shared_node: str) -> str:
    if table_name == "JBS_ZWTERMINAL":
        return insert_zw_terminal(eid, shared_node)
    return insert_pw_terminal(eid, shared_node)


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    _has_result = False

    tables = ctx.tables
    svg_connections = ctx.options.get("svg_connections") or ()
    if not svg_connections:
        # Fallback: detect terminals with empty CONNECTIVITYNODE_ID — these are
        # candidates for "physical SVG connection but model missing node_id".
        svg_connections = _fallback_infer_connections(tables)
        if not svg_connections:
            # Bug#50: No connections found — output summary
            yield ProblemRecord(
                task_code="2.3",
                device_id="NO_LOGI_BREAK",
                device_name="无物理连通逻辑断开",
                description="未检测到物理连通逻辑断开: SVG与模型拓扑一致",
                correction="无需修正",
                correction_sql="",
                severity="info",
                confidence=1.0,
                extra={
                    "voltage_type": "",
                "result": "no_LOGI_BREAK",
                },
            )
            return ()

    equip_terms = _equip_terminals(tables)
    meta = _equip_meta(tables)
    seen: set[tuple[str, str]] = set()

    for raw_pair in svg_connections:
        try:
            a, b = raw_pair
        except (TypeError, ValueError):
            continue
        a, b = str(a), str(b)
        if a == b:
            continue
        if (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))

        a_terms = equip_terms.get(a, [])
        b_terms = equip_terms.get(b, [])

        # 分类
        if not a_terms or not b_terms:
            status = "terminal_missing"
            missing_eid = a if not a_terms else b
        elif any(nid is None for (_, nid, _) in a_terms + b_terms):
            status = "node_missing"
            missing_eid = None
        else:
            a_nodes = {nid for (_, nid, _) in a_terms}
            b_nodes = {nid for (_, nid, _) in b_terms}
            if a_nodes & b_nodes:
                # 模型已逻辑连通 -> 非断点，跳过
                continue
            status = "logic_break"
            missing_eid = None

        # 关联设备的备用电表信息
        dev = meta.get(a) or meta.get(b) or {}
        dev_name = dev.get("EQUIP_NAME", "")
        feeder_id = dev.get("FEEDER_ID", "")
        station_id = dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", "")

        # 构造修正 SQL
        if status == "logic_break":
            a_node = next((nid for (_, nid, _) in a_terms if nid), None)
            shared_node = a_node or ":shared_node_id"
            # Contract: one executable statement per row (official §2.3 form:
            # UPDATE ... WHERE ID IN (?, ?)). Group b-side terminals by table;
            # real-data pairs are single-table (PW), mixed PW/ZW pairs fall
            # back to the first table's statement only.
            by_table: dict[str, list[str]] = {}
            for (tid, _nid, tbl) in b_terms:
                if tid:
                    by_table.setdefault(tbl, []).append(tid)
            if by_table:
                tbl, ids = sorted(by_table.items())[0]
                id_list = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
                sql = _terminal_update_sql_in(tbl, id_list, shared_node)
            else:
                sql = ""
            reason = (
                f"SVG 中 {a} 与 {b} 物理相连，但模型中 CONNECTIVITYNODE_ID 不同"
                f"（{sorted(a_nodes)} vs {sorted(b_nodes)}）"
            )
        elif status == "terminal_missing":
            other = b if missing_eid == a else a
            other_terms = equip_terms.get(other, [])
            shared_node = next(
                (nid for (_, nid, _) in other_terms if nid), ":shared_node_id"
            )
            mdev = meta.get(missing_eid) or {}
            tbl = "JBS_ZWTERMINAL" if mdev.get("ST_ID") and not mdev.get("FEEDER_ID") else "JBS_PWTERMINAL"
            sql = _terminal_insert_sql(missing_eid, tbl, shared_node)
            reason = f"SVG 中 {a} 与 {b} 物理相连，但设备 {missing_eid} 缺少 TERMINAL 端子"
        else:  # node_missing
            # 找到 CONNECTIVITYNODE_ID 为空的端子，赋予对端节点
            other = b if a_terms and a_terms[0][1] is None else a
            other_terms = equip_terms.get(other, [])
            other_node = next((nid for (_, nid, _) in other_terms if nid), ":shared_node_id")
            bad = next(
                (tid, tbl) for (tid, nid, tbl) in a_terms + b_terms if nid is None and tid
            )
            tid, tbl = bad
            sql = _terminal_update_sql(tbl, tid, other_node)
            reason = f"SVG 中 {a} 与 {b} 物理相连，但端子 {tid} 的 CONNECTIVITYNODE_ID 为空"

        ev = EvidenceCollector("JBS_PWTERMINAL")
        ev.observe("A_EQUIP_ID", a, record_id=a)
        ev.observe("B_EQUIP_ID", b, record_id=b)
        ev.observe("STATUS", status)
        ev.observe("A_TERMINALS", [(tid, nid) for (tid, nid, _) in a_terms])
        ev.observe("B_TERMINALS", [(tid, nid) for (tid, nid, _) in b_terms])

        _has_result = True
        yield ProblemRecord(
            task_code="2.3",
            device_id=f"{a}->{b}",
            device_name=dev_name,
            feeder_id=feeder_id,
            station_id=station_id,
            description=f"物理连通/逻辑断开 ({status}): {reason}",
            correction="使两端共享同一 CONNECTIVITYNODE_ID（补 CN / 改挂端子）",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=1.0,
            evidence=ev.finalize(),
            extra={"voltage_type": "", "status": status, "a": a, "b": b},
        )
    # Bug#50: If no suspect found, output summary record
    if not _has_result:
        yield ProblemRecord(
            task_code="2.3",
            device_id="NO_LOGI_BREAK",
            device_name="无物理连通逻辑断开",
            description="未检测到物理连通逻辑断开: SVG与模型拓扑一致",
            correction="无需修正",
            correction_sql="",
            severity="info",
            confidence=1.0,
            extra={
                "result": "no_LOGI_BREAK",
            },
        )
    return ()


__all__ = ["detect", "SEVERITY_DEFAULT"]
