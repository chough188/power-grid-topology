# -*- coding: utf-8 -*-
"""Task 1.1: 设备拓扑悬空检测 (official algorithm).

Per 比赛要求/00_12个二级分类算法伪代码.md + 00_官方要求权威整合清单.md §3.1 + 评审手册 §4.2:

  1) 三类异常:
      - single_dangle    (非末端设备仅有一侧连接)
      - contiguous_dangle (局部连通分量内多设备彼此相连, 但与上下游主共断开)
      - island           (设备完全无任何端子)

  2) 豁免 (8 项 + 末端站房 IS_END_DEVICE=1 + COMPOSITESWITCH):
      - 电力用户 / 配变 / 电缆终端头 / 备用间隔 / 末端站房
      - DISCONNECTOR 允许单侧 (Rule 6)
      - COMPOSITESWITCH != null 组合开关 按复合规则独立判定
      - 配电站 + 箱变 站内所有设备不参与悬空判定

  3) 不同异常产生不同 SQL 修正 (契约: 每行单条可直接执行语句):
      - single_dangle     -> INSERT TERMINAL (补齐缺失端子)
      - contiguous_dangle -> INSERT new CN (新建连接节点, 改挂步骤见修正方案)
      - island            -> INSERT TERMINAL (主语句; 前置"新建主网侧 CN"
                             步骤保留在修正方案文本中, 官方 §1.1 Sheet1 列示例形态)

  4) degree vs expected_degree:
      SWITCH/DISCONNECTOR=2, BUS>=2, LINE=2, SOURCE/TRANSFORMER=1
"""
from __future__ import annotations

from collections.abc import Sequence

from shared.exemption import (
    is_dangle_exempt,
    is_single_side_allowed,
)
from shared.graph_algos import (
    adjacency_from_terminals,
    connected_components,
)
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "critical"


def _expected_degree(equip_type: str) -> int:
    t = (equip_type or "").upper()
    if t in ("SWITCH", "DISCONNECTOR", "BREAKER", "断路器", "开关", "刀闸", "隔离开关"):
        return 2
    if t in ("BUS", "母线"):
        return 2
    if t in ("LINE", "线路", "CABLE"):
        return 2
    if t in ("SOURCE", "电源", "TRANSFORMER", "变压器"):
        return 1
    return 2


def _is_end_room(tables, room_id: str) -> bool:
    """检查 JBS_PWROOM.IS_END_DEVICE=1. Schema 字段缺失时回退到名称启发式."""
    if not room_id:
        return False
    for r in list(tables.get("JBS_PWROOM", ())):
        if r.get("ROOM_ID") == room_id:
            val = r.get("IS_END_DEVICE")
            if val is None:
                name = (r.get("ROOM_NAME") or "").strip()
                return name.startswith("末端") or "末端站房" in name or "末端配电站" in name
            return str(val) in ("1", "true", "TRUE", "True", "yes", "Y")
    return False


def _is_end_station_room(tables, dsub_id: str) -> bool:
    """配电站房豁免 (官方 §8.4 强制): 站内所有设备不参与悬空判定."""
    return _is_end_room(tables, dsub_id)


def _is_composite_switch(dev: dict) -> bool:
    """COMPOSITESWITCH != null -> 组合开关, 按复合规则独立判定 (官方 §1.1 边界)."""
    val = dev.get("COMPOSITESWITCH")
    if val is None or val == "":
        return False
    return str(val).strip().upper() not in ("", "NONE", "NULL", "0")


def _device_kind_table(dev: dict) -> str:
    return "JBS_PWEQUIPINFO" if dev.get("FEEDER_ID") else "JBS_ZWEQUIPINFO"


def _sql_add_terminal_pw() -> str:
    # 列集与提供数据集的 JBS_PWTERMINAL(ID, EQUIP_ID, CONNECTIVITYNODE_ID)
    # 一致 — 可直接执行; 与 1.2/2.3/4.1 的端子 INSERT 形态保持统一。
    # (官方 §1.1 菜单形式含 PORT_NO/VALID_FLAG, 该两列不在提供的 14 表 dump 中。)
    return (
        "INSERT INTO JBS_PWTERMINAL "
        "(ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
        "VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)"
    )


def _sql_add_terminal_zw() -> str:
    return (
        "INSERT INTO JBS_ZWTERMINAL "
        "(ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
        "VALUES (SEQ_ZWTERMINAL.NEXTVAL, :device_id, :new_node_id)"
    )


def _sql_add_cn_and_relink() -> str:
    return (
        "INSERT INTO JBS_PWCNODE_DICT "
        "(CN_ID, VOLTAGE_TYPE, ST_ID, CREATE_DATE) "
        "VALUES (:new_cn_id, :voltage_type, :station_id, SYSDATE)"
    )


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    cache = (ctx.options or {}).get("_shared_cache") or {}

    # Bug#39: Pre-build end_room_id set once (was scanning JBS_PWROOM per device = O(N×M))
    end_room_ids: set[str] = set()
    for r in tables.get("JBS_PWROOM", ()):
        rid = r.get("ROOM_ID")
        if not rid:
            continue
        val = r.get("IS_END_DEVICE")
        if val is None:
            name = (r.get("ROOM_NAME") or "").strip()
            if name.startswith("末端") or "末端站房" in name or "末端配电站" in name:
                end_room_ids.add(str(rid))
        elif str(val) in ("1", "true", "TRUE", "True", "yes", "Y"):
            end_room_ids.add(str(rid))

    equip_nodes: dict = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = t.get("EQUIP_ID"); nid = t.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            equip_nodes.setdefault(str(eid), set()).add(str(nid))

    adj = cache.get("adjacency") if "adjacency" in cache else adjacency_from_terminals(tables)
    comps = connected_components(adj)
    equip_to_comp: dict = {}
    for comp in comps:
        for node in comp:
            equip_to_comp[node] = comp
    source_set = {
        str(d.get("EQUIP_ID")) for d in (
            list(tables.get("JBS_ZWEQUIPINFO", ())) + list(tables.get("JBS_PWEQUIPINFO", ()))
        )
        if str(d.get("EQUIP_TYPE") or "").upper() in ("SOURCE", "TRANSFORMER", "电源", "变压器")
    }
    has_main_source_comp: dict = {}
    for comp in comps:
        has_main_source_comp[id(comp)] = bool(comp & source_set)

    all_equips = list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ()))
    for dev in all_equips:
        eid = dev.get("EQUIP_ID")
        if not eid:
            continue

        # Exemption rules (priority order)
        if is_dangle_exempt(dev):
            continue
        # Bug#39: Use pre-built set instead of _is_end_station_room() scan
        if str(dev.get("DSUBSTATION_ID") or "") in end_room_ids:
            continue
        if _is_composite_switch(dev):
            continue

        nodes = equip_nodes.get(str(eid), set())
        deg = len(nodes)
        equip_type = dev.get("EQUIP_TYPE", "")
        expected = _expected_degree(equip_type)
        if deg == 1 and is_single_side_allowed(dev):
            continue
        if deg >= expected:
            continue

        # Classify 3 types
        if deg == 0:
            emit_type = "island"
            desc_kind = "无任何端子 (拓扑孤岛)"
            recommend = "add_main_connection"
            confidence=0.9
        else:
            comp = None
            for nid in nodes:
                if nid in equip_to_comp:
                    comp = equip_to_comp[nid]
                    break
            comp_has_source = bool(comp and has_main_source_comp.get(id(comp), False))
            if not comp_has_source:
                emit_type = "contiguous_dangle"
                comp_size = len(comp) if comp else 1
                desc_kind = f"局部连通分量内 {comp_size} 个设备彼此相连, 但与上游主电源断开"
                recommend = "add_path_to_main"
                confidence=0.9
            else:
                emit_type = "single_dangle"
                desc_kind = f"仅 {deg} 个连接节点 (期望 {expected})"
                recommend = "add_terminal"
                confidence=0.9 if deg == 0 else 1.0

        # Evidence
        ev = EvidenceCollector(_device_kind_table(dev))
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", equip_type)
        ev.observe("VOLTAGE_TYPE", dev.get("VOLTAGE_TYPE"))
        ev.observe("DEGREE", deg)
        ev.observe("EXPECTED_DEGREE", expected)
        ev.observe("CONNECTIVITYNODES", sorted(nodes))
        ev.observe("COMPOSITESWITCH", dev.get("COMPOSITESWITCH") or "")
        ev.observe("IS_END_ROOM", _is_end_station_room(tables, dev.get("DSUBSTATION_ID") or ""))

        # SQL per emit_type — contract: ONE executable statement per row.
        if emit_type == "contiguous_dangle":
            sql = _sql_add_cn_and_relink()
        else:
            # single_dangle (deg=1) and island (deg=0): primary action is the
            # missing TERMINAL row (official §1.1 Sheet1 column example form).
            # For islands the prerequisite "create new main-grid CN" step stays
            # in the correction text (see desc_kind / correction mapping above).
            sql = _sql_add_terminal_pw() if dev.get("FEEDER_ID") else _sql_add_terminal_zw()

        yield ProblemRecord(
            task_code="1.1",
            device_id=eid,
            device_name=dev.get("EQUIP_NAME", ""),
            feeder_id=dev.get("FEEDER_ID", "") or dev.get("START_ST_ID", ""),
            station_id=dev.get("DSUBSTATION_ID", "") or dev.get("ST_ID", ""),
            description=f"设备 {dev.get('EQUIP_NAME', eid)} ({equip_type}) {desc_kind}",
            correction={
                "single_dangle": "补齐缺失的 TERMINAL 端子记录 (ID/EQUIP_ID/CONNECTIVITYNODE_ID)",
                "contiguous_dangle": "新建连接节点 CN, 把现有 Terminal 改挂到新 CN, 建立与主干的连接路径",
                "island": "新建主网侧连接节点 CN, 再新建 TERMINAL 指向新 CN, 建立与上游主电源的连接",
            }[emit_type],
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=confidence,
            evidence=ev.finalize(),
            extra={
                "emit_type": emit_type,
                "degree": deg,
                "expected_degree": expected,
                "current_nodes": sorted(nodes),
                "voltage_type": dev.get("VOLTAGE_TYPE"),
                "recommend": recommend,
                "comp_size": len(comp) if comp else 0,
                "composite_switch": dev.get("COMPOSITESWITCH") or "",
            },
        )

    return ()


__all__ = ["detect"]
