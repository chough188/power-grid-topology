"""Task 1.2: 拓扑连通性异常诊断与断点定位（official 6 break types).

Per 比赛要求/00_12个二级分类算法伪代码.md §1.2:

    break_type = classify(path_M, path_R):
      - 开关分断: path_M 存在 ∧ path_R 不存在 ∧ 路径含分位开关
      - 状态未知: path_M 存在 ∧ path_R 不存在 ∧ 关键开关无遥信
      - 终端缺失: 邻接 TERMINAL 不存在
      - 节点缺失: TERMINAL.CONNECTIVITYNODE_ID 为空
      - 错误跨接: 路径经过非预期厂站/馈线
      - 起终点无效: 设备 ID 不存在

官方固定测试:
- T1: TMP00013138 → TMP00047197   (必杀断点对)
- T2: TMP00007913 → TMP00007907   (必杀断点对)
- T3: TMP00012903 → TMP00047124   (0821 更新: 官方标准输出模板 Sheet2 新增"输入："行)

T3 说明（Round 3.7 核查）: official_pairs 保留 T3 以保障"若评分数据中该对
断开则必须报告"。但真实数据中 T3 两设备真正连通 —— 存在 148 节点全闭合路径
（经 DPWRTRANSFM/LOWVOLLINE 跨 3 馈线, 无分位开关; 0821 更新前后状态一致）,
按 Q&A2/Q16 "路径内无分位开关 = 真正连通" 语义正确不报告, 属负对照输入对,
不计入 self_grade BISHA_PAIRS 分母。
"""
import random
from collections.abc import Sequence

from shared.exemption import is_single_side_allowed
from shared.graph_algos import (
    adjacency_from_terminals,
    shortest_path,
    shortest_path_excluding,
    terminal_ids_in_end_rooms,
    connected_components,
)
from shared.sql_emitter import insert_pw_terminal, update_pw_terminal_node, delete_pw_terminal
from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "high"


def _first_model_path(base_adj, s_node, t_node, forbidden):
    """返回模型图中 s_node→t_node 的任意一条路径（用于跨接判定），无则 None。"""
    return shortest_path_excluding(base_adj, s_node, t_node, forbidden)


def _open_switches_on_path(path, open_device_edges):
    """按路径顺序返回被遍历的分位设备 ID（去重）。

    ``open_device_edges`` 由调用方预建：{frozenset({端子a, 端子b}): [设备ID...]}，
    仅收录分位(POINT==0)设备自身端子对贡献的边（与 _build_running_graph 同口径）。
    """
    out = []
    seen = set()
    for i in range(len(path) - 1):
        devs = open_device_edges.get(frozenset((path[i], path[i + 1])))
        if not devs:
            continue
        for d in devs:
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out


def _build_running_graph(tables, base_adj):
    """Build G_R = G_M minus the edges contributed by split (分位) switches.

    模型图 G_M 把每个设备自身的 terminal 节点两两相连；当某设备是分位开关
    (POINT==0) 时，它在运行态下是断开的，因此必须从 G_R 中删除该设备贡献的
    连边，使运行态图能反映"开关打开后路径中断"。
    """
    split_equips = set()
    for sig in tables.get("JBS_ZWSIGNAL", ()):
        eid = sig.get("EQUIP_ID") or sig.get("ID")
        point = sig.get("POINT")
        if eid is not None and point in ("0", 0):
            split_equips.add(str(eid))
    for sig in tables.get("JBS_PWREAL", ()):
        eid = sig.get("EQUIP_ID") or sig.get("TRAN_ID")
        point = sig.get("POINT")
        if eid is not None and point in ("0", 0):
            split_equips.add(str(eid))

    # 收集每个设备贡献的 terminal 节点（与 adjacency_from_terminals 同口径）
    equip_nodes: dict[str, list[str]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(tbl, ()):
            eid = row.get("EQUIP_ID")
            nid = row.get("CONNECTIVITYNODE_ID")
            if eid and nid:
                equip_nodes.setdefault(str(eid), []).append(str(nid))

    running_adj = {n: set(neighbors) for n, neighbors in base_adj.items()}
    for eid, nodes in equip_nodes.items():
        if eid not in split_equips or len(nodes) < 2:
            continue
        # 删除该分位设备自身 terminal 节点之间的连边
        nl = list(dict.fromkeys(nodes))  # 去重保序
        for a, b in zip(nl, nl[1:]):
            running_adj.get(a, set()).discard(b)
            running_adj.get(b, set()).discard(a)
    return running_adj, split_equips


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    base_adj = adjacency_from_terminals(tables)
    if not base_adj:
        return ()

    equip_lookup = {}
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if eid:
            equip_lookup[eid] = d

    # Build device-id list, sorted for deterministic iteration
    devices = sorted(equip_lookup.keys())

    # Build running graph (G_R) by removing edges from split switches
    running_adj, split_equips = _build_running_graph(tables, base_adj)
    # PERFORMANCE: pre-compute connected components for O(1) connectivity checks
    base_comp_id = {}
    for idx, comp in enumerate(connected_components(base_adj)):
        for node in comp:
            base_comp_id[node] = idx
    running_comp_id = {}
    for idx, comp in enumerate(connected_components(running_adj)):
        for node in comp:
            running_comp_id[node] = idx
    forbidden = terminal_ids_in_end_rooms(tables)
    # 官方 §8.4: 末端站房(配电站/箱变)终端节点不参与电气连通 →
    # 预计算移除 forbidden 后的基础图连通分量，使「同组件」快捷判定也具备末端感知。
    if forbidden:
        noend_adj = {
            n: [nb for nb in nbrs if nb not in forbidden]
            for n, nbrs in base_adj.items()
            if n not in forbidden
        }
        noend_comp_id: dict = {}
        for idx, comp in enumerate(connected_components(noend_adj)):
            for node in comp:
                noend_comp_id[node] = idx
    else:
        noend_comp_id = base_comp_id

    # PERFORMANCE FIX: pre-index signals by EQUIP_ID for O(1) unknown_state check
    # Replaces O(n*m) per-pair scan of all ZWSIGNAL+PWREAL records
    _signals_by_equip: dict[str, list] = {}
    for sig in list(tables.get("JBS_ZWSIGNAL", ())) + list(tables.get("JBS_PWREAL", ())):
        eid = str(sig.get("EQUIP_ID") or sig.get("ID") or sig.get("TRAN_ID") or "")
        if eid:
            _signals_by_equip.setdefault(eid, []).append(sig)


    # Build node->station lookup (O(N) once, replaces O(N*M) per-call _node_owner_station)
    node_to_station: dict[str, str] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(tbl, ()):
            nid = row.get("CONNECTIVITYNODE_ID")
            eid = row.get("EQUIP_ID")
            if nid and eid and eid in equip_lookup:
                dev = equip_lookup[eid]
                st = str(dev.get("ST_ID") or dev.get("DSUBSTATION_ID") or "")
                if st:
                    node_to_station[str(nid)] = st

    # Official test pairs (always check)
    official_pairs = [
        ("TMP00013138", "TMP00047197"),  # T1 必杀
        ("TMP00007913", "TMP00007907"),  # T2 必杀
        ("TMP00012903", "TMP00047124"),  # T3 必杀（0821 官方模板 Sheet2 新增行）
    ]

    # Build equip->nodes mapping (needed for component lookup and path finding)
    equip_to_nodes = {}
    for row in tables.get("JBS_PWTERMINAL", ()) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = row.get("EQUIP_ID"); nid = row.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            equip_to_nodes.setdefault(eid, []).append(nid)

    # 官方 Q&A2/Q16: 静态路径存在但路径中含分位开关 → 必须输出为断点（开关分断）。
    # 预索引「分位设备自身端子对贡献的边」，路径扫描 O(path_len)。
    # 节点顺序与 _build_running_graph 完全一致（同表序 dict.fromkeys 去重）。
    open_device_edges: dict = {}
    for eid in sorted(split_equips):
        nodes = equip_to_nodes.get(eid) or []
        nl = list(dict.fromkeys(nodes))
        for x, y in zip(nl, nl[1:]):
            open_device_edges.setdefault(frozenset((x, y)), []).append(str(eid))

    # PERFORMANCE FIX: use component IDs to pre-filter pairs.
    # Only check pairs where devices are in DIFFERENT connected components
    # (same-component pairs are guaranteed connected -> skip BFS entirely).
    # This avoids O(N^2) pair explosion when FEEDER_ID is missing and falls back to ST_ID.
    equip_to_comp = {}
    for eid, nodes in equip_to_nodes.items():
        comps_for_equip = {base_comp_id.get(n) for n in nodes if base_comp_id.get(n) is not None}
        if comps_for_equip:
            equip_to_comp[eid] = next(iter(comps_for_equip))  # first component

    # Build device-to-comp mapping for quick lookup
    comp_groups = {}
    for eid, comp_id in equip_to_comp.items():
        comp_groups.setdefault(comp_id, []).append(eid)

    pairs_to_check = []
    # Only generate cross-component pairs within same feeder group (these are the disconnected ones)
    feeder_voltage_pairs = {}
    for eid, dev in equip_lookup.items():
        fid = dev.get("FEEDER_ID") or dev.get("ST_ID")
        if fid is None:
            continue
        feeder_voltage_pairs.setdefault((fid, dev.get("VOLTAGE_TYPE")), []).append(eid)

    random.seed(42)
    global_pair_cap = 5000  # v26: reduced from 50000 for real-data performance (5K sufficient for coverage)
    for key, devs in feeder_voltage_pairs.items():
        if len(pairs_to_check) >= global_pair_cap:
            break
        # Sample to keep per-group small
        if len(devs) > 10:
            devs = random.sample(devs, 10)  # v26: reduced from 50 for real-data performance
        # Group by component within this feeder
        comp_devs = {}
        for d in devs:
            c = equip_to_comp.get(d)
            if c is not None:
                comp_devs.setdefault(c, []).append(d)
        # Only check cross-component pairs (disconnected)
        comp_list = list(comp_devs.keys())
        for i in range(len(comp_list)):
            if len(pairs_to_check) >= global_pair_cap:
                break
            for j in range(i + 1, len(comp_list)):
                for a in comp_devs[comp_list[i]]:
                    for b in comp_devs[comp_list[j]]:
                        if len(pairs_to_check) < global_pair_cap:
                            pairs_to_check.append((a, b))
    # Add official test pairs (always)
    for a, b in official_pairs:
        if a in equip_lookup and b in equip_lookup:
            pairs_to_check.append((a, b))

    # Bug#80: Add running-state diff pairs (开关分断)
    # These are device pairs that are connected in model graph (same component)
    # but disconnected in running graph (switch open)
    _running_added = 0
    _pairs_seen_set = set(pairs_to_check)  # PERFORMANCE: O(1) lookup instead of set(list) every iteration
    for key, devs in feeder_voltage_pairs.items():
        if _running_added >= 500:
            break
        if len(devs) > 10:
            import random as _rng
            devs = _rng.sample(devs, 10)
        # Group by running component
        run_comp_devs = {}
        for d in devs:
            nodes = equip_to_nodes.get(d, [])
            if not nodes:
                continue
            r_comp = running_comp_id.get(str(nodes[0]))
            run_comp_devs.setdefault(r_comp, []).append(d)
        # Group by base component
        base_comp_devs = {}
        for d in devs:
            c_id = equip_to_comp.get(d)
            base_comp_devs.setdefault(c_id, []).append(d)
        # Find pairs in same base component but different running component
        for b_comp, b_devs in base_comp_devs.items():
            if len(b_devs) < 2:
                continue
            # Group these by running component
            sub_run = {}
            for d in b_devs:
                nodes = equip_to_nodes.get(d, [])
                r_c = running_comp_id.get(str(nodes[0])) if nodes else None
                sub_run.setdefault(r_c, []).append(d)
            r_ids = [k for k in sub_run if k is not None]
            for i in range(len(r_ids)):
                for j in range(i + 1, len(r_ids)):
                    for a in sub_run[r_ids[i]]:
                        for b in sub_run[r_ids[j]]:
                            if (a, b) not in _pairs_seen_set and (b, a) not in _pairs_seen_set:
                                pairs_to_check.append((a, b))
                                _pairs_seen_set.add((a, b))
                                _running_added += 1
                                if _running_added >= 500:
                                    break
                        if _running_added >= 500:
                            break
                    if _running_added >= 500:
                        break
                if _running_added >= 500:
                    break
            if _running_added >= 500:
                break

    def _switch_break_record(s, t, s_nodes, t_nodes, path):
        """官方 Q&A2/Q16: 静态路径存在但路径内含分位开关 → 断点（开关分断）记录。

        路径内无分位开关时返回 None（存在全闭合通路，真正连通）。
        Q43: 断点为分位开关时本侧填写、对侧留空。
        """
        open_on_path = _open_switches_on_path(path, open_device_edges)
        if not open_on_path:
            return None
        first_open = open_on_path[0]
        ev = EvidenceCollector("JBS_PWEQUIPINFO")
        ev.observe("SOURCE_ID", s, record_id=s)
        ev.observe("TARGET_ID", t)
        ev.observe("S_TERMINALS", s_nodes)
        ev.observe("T_TERMINALS", t_nodes)
        ev.observe("PATH_MODEL", "connected_with_open_switches")
        ev.observe("OPEN_SWITCHES_ON_PATH", open_on_path)
        sql = insert_pw_terminal(s, path[0]) if equip_lookup[s].get("FEEDER_ID") else "INSERT INTO JBS_ZWTERMINAL ..."
        return ProblemRecord(
            task_code="1.2",
            device_id=s,
            device_name=equip_lookup[s].get("EQUIP_NAME", ""),
            feeder_id=equip_lookup[s].get("FEEDER_ID", ""),
            station_id=equip_lookup[s].get("DSUBSTATION_ID", "") or equip_lookup[s].get("ST_ID", ""),
            description=(
                f"{s} -> {t} 静态路径存在(长{len(path)})但路径内含 {len(open_on_path)} 个分位开关"
                f"（首个: {first_open} {equip_lookup.get(first_open, {}).get('EQUIP_NAME', '')}）; "
                f"按官方规则输出为断点; KCL 校验会触发节点 Sigma I_in!=Sigma I_out"
            ),
            correction="核查路径内分位开关状态; KCL 节点守恒 + KVL 回路守恒校验; 修正三原则: 合规(不破坏现有连通) + 最小(最少改动) + 可行(保留 PK 可回滚)",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=0.9,
            evidence=ev.finalize(),
            extra={
                "break_type": "开关分断",
                "target_id": t,
                "target_name": equip_lookup.get(t, {}).get("EQUIP_NAME", ""),
                "source_node": path[0],
                "target_node": path[-1],
                # Q43: 断点为分位开关时本侧填写、对侧留空
                "suspect_switch_id": first_open,
                "suspect_switch_name": equip_lookup.get(first_open, {}).get("EQUIP_NAME", first_open),
                "peer_switch_id": "",
                "peer_switch_name": "",
                "open_switches_on_path": open_on_path,
                "path_len": len(path),
            },
        )

    seen_pairs = set()
    for s, t in pairs_to_check:
        if (s, t) in seen_pairs or (t, s) in seen_pairs:
            continue
        seen_pairs.add((s, t))

        # Step 1: input validation
        if s not in equip_lookup or t not in equip_lookup:
            yield ProblemRecord(
                task_code="1.2", device_id=s,
                description=f"起点设备 {s} 或终点 {t} ID 不存在",
                correction="检查输入 ID 是否在 JBS_PWEQUIPINFO / JBS_ZWEQUIPINFO",
                correction_sql="",
                severity="high", confidence=0.9,
                extra={"break_type": "起终点无效", "target_id": t,
                       "target_name": equip_lookup.get(t, {}).get("EQUIP_NAME", "")},
            )
            continue

        # Step 2: check path_M (model graph) and path_R (running graph)
        # equip_to_nodes already defined above (moved out of loop for performance)

        s_nodes = equip_to_nodes.get(s, [])
        t_nodes = equip_to_nodes.get(t, [])
        if not s_nodes or not t_nodes:
            yield ProblemRecord(
                task_code="1.2", device_id=s,
                description=f"设备 {s} 或 {t} 无 TERMINAL 记录",
                correction="补 TERMINAL 记录",
                correction_sql=insert_pw_terminal(s, ":new_node") if equip_lookup[s].get("FEEDER_ID") else "INSERT INTO JBS_ZWTERMINAL ...",
                severity="high", confidence=0.9,
                extra={"break_type": "终端缺失", "target_id": t,
                       "target_name": equip_lookup.get(t, {}).get("EQUIP_NAME", "")},
            )
            continue

        # Empty CONNECTIVITYNODE_ID check
        if any(n is None or n == "" for n in s_nodes + t_nodes):
            yield ProblemRecord(
                task_code="1.2", device_id=s,
                description=f"设备 {s} 或 {t} 的 CONNECTIVITYNODE_ID 为空",
                correction="修正 TERMINAL 的 CONNECTIVITYNODE_ID",
                correction_sql="",
                severity="high", confidence=0.9,
                extra={"break_type": "节点缺失", "target_id": t,
                       "target_name": equip_lookup.get(t, {}).get("EQUIP_NAME", "")},
            )
            continue

        # Find shortest path in model graph (path_M)
        s_node = s_nodes[0]
        t_node = t_nodes[0]
        # forbidden already computed once outside loop (performance fix)

        # PERFORMANCE: use component IDs for O(1) connectivity check
        s_comps = {base_comp_id.get(sn) for sn in s_nodes} - {None}
        t_comps = {base_comp_id.get(tn) for tn in t_nodes} - {None}
        common_comps = s_comps & t_comps if s_comps and t_comps else set()
        # 末端感知（官方 §8.4）：仅当存在不经过末端站房终端节点的路径时，
        # 才视为有效模型连通；否则落入下方 BFS/断点分支。
        s_noend = {noend_comp_id.get(sn) for sn in s_nodes} - {None}
        t_noend = {noend_comp_id.get(tn) for tn in t_nodes} - {None}
        end_aware_connected = bool(s_noend & t_noend)
        if common_comps and end_aware_connected:
            # 官方 Q&A2/Q16（标准输出模板 Sheet2 输入对注释）：静态拓扑存在路径时，
            # 若路径中有分闸开关 → 必须作为断点输出（开关分断），即使另存在全合环
            # 绕行路径（运行态同组件也不得跳过）；仅当路径内无分位开关（存在全闭合
            # 通路）才视为真正连通。官方测试对 T1/T2 即此语义。
            path_m0 = shortest_path_excluding(base_adj, s_node, t_node, forbidden)
            if path_m0 is not None:
                rec = _switch_break_record(s, t, s_nodes, t_nodes, path_m0)
                if rec is not None:
                    yield rec
                continue  # 路径内无分位开关 → 真正连通，跳过

        # Only do BFS when components differ or nodes missing from component map
        path_m = shortest_path_excluding(base_adj, s_node, t_node, forbidden)
        if path_m:
            rec = _switch_break_record(s, t, s_nodes, t_nodes, path_m)
            if rec is not None:
                yield rec
            continue  # connected in model (within end-room constraint)

        # Try alternate terminal pairs, still constrained
        found_path = None
        for sn in s_nodes:
            for tn in t_nodes:
                p = shortest_path_excluding(base_adj, sn, tn, forbidden)
                if p:
                    found_path = p
                    break
            if found_path:
                break
        if found_path:
            rec = _switch_break_record(s, t, s_nodes, t_nodes, found_path)
            if rec is not None:
                yield rec
            continue

        # 模型图不连通 → 断点。用运行态图(G_R)差分判定断点类型：
        #   path_R 通、path_M 不通 → 断点由分位开关造成 → 开关分断
        #   path_R 也不通         → 真实拓扑断连 / 状态未知 / 错误跨接
        ev = EvidenceCollector("JBS_PWEQUIPINFO")
        ev.observe("SOURCE_ID", s, record_id=s)
        ev.observe("TARGET_ID", t)
        ev.observe("S_TERMINALS", s_nodes)
        ev.observe("T_TERMINALS", t_nodes)
        ev.observe("PATH_MODEL", None)

        # PERFORMANCE: check running graph via component ID first
        s_rc = running_comp_id.get(s_node)
        t_rc = running_comp_id.get(t_node)
        path_r = None
        if s_rc is not None and t_rc is not None and s_rc == t_rc:
            path_r = shortest_path_excluding(running_adj, s_node, t_node, forbidden)
        # 沿模型图路径寻找"跨厂站/跨馈线"的异常跨接
        cross_station = False
        path_m_for_cross = _first_model_path(base_adj, s_node, t_node, forbidden)
        if path_m_for_cross:
            s_st = str(equip_lookup.get(s, {}).get("ST_ID") or equip_lookup.get(s, {}).get("DSUBSTATION_ID") or "")
            t_st = str(equip_lookup.get(t, {}).get("ST_ID") or equip_lookup.get(t, {}).get("DSUBSTATION_ID") or "")
            for node in path_m_for_cross:
                owner = node_to_station.get(node, "")
                if owner and owner not in (s_st, t_st):
                    cross_station = True
                    break

        if path_r is not None:
            break_type = "开关分断"
        elif cross_station:
            break_type = "错误跨接"
        else:
            # 运行态也不通：检查相关开关遥信是否缺失（状态未知）还是确实拓扑断连
            # PERFORMANCE: use pre-indexed _signals_by_equip for O(1) lookup
            unknown_state = False
            for check_id in (s, t):
                for sig in _signals_by_equip.get(check_id, []):
                    point = sig.get("POINT")
                    if point in (None, ""):
                        unknown_state = True
                        break
                if unknown_state:
                    break
            break_type = "状态未知" if unknown_state else "拓扑断连"

        # SQL
        sql = insert_pw_terminal(s, s_node) if equip_lookup[s].get("FEEDER_ID") else "INSERT INTO JBS_ZWTERMINAL ..."

        # R7: identify the specific open switch causing the break (for Sheet2 col 5-8)
        suspect_switch_id = ""
        suspect_switch_name = ""
        if break_type in ("开关分断", "状态未知"):
            # Find the first split equip adjacent to s's nodes.
            # P1-8: iterate SORTED — split_equips is a str-set whose iteration
            # order varies with PYTHONHASHSEED; sorted() pins the choice to the
            # lowest ID so Sheet2 suspect columns are reproducible across runs.
            for seid in sorted(split_equips):
                se_nodes = equip_to_nodes.get(seid, [])
                if any(sn in se_nodes for sn in s_nodes):
                    suspect_switch_id = seid
                    suspect_switch_name = equip_lookup.get(seid, {}).get("EQUIP_NAME", seid)
                    break
            # If not found near s, try near t
            if not suspect_switch_id:
                for seid in sorted(split_equips):
                    se_nodes = equip_to_nodes.get(seid, [])
                    if any(tn in se_nodes for tn in t_nodes):
                        suspect_switch_id = seid
                        suspect_switch_name = equip_lookup.get(seid, {}).get("EQUIP_NAME", seid)
                        break

        yield ProblemRecord(
            task_code="1.2",
            device_id=s,
            device_name=equip_lookup[s].get("EQUIP_NAME", ""),
            feeder_id=equip_lookup[s].get("FEEDER_ID", ""),
            station_id=equip_lookup[s].get("DSUBSTATION_ID", "") or equip_lookup[s].get("ST_ID", ""),
            description=f"{s} → {t} 不连通 ({break_type}); KCL 校验会触发节点 ΣI_in≠ΣI_out",
            correction="补 CONNECTIVITYNODE 或检查开关分位状态；KCL 节点守恒 + KVL 回路守恒校验；修正三原则：合规（不破坏现有连通）+ 最小（最少改动）+ 可行（保留 PK 可回滚）",
            correction_sql=sql,
            severity=SEVERITY_DEFAULT,
            confidence=0.9,
            evidence=ev.finalize(),
            extra={
                "break_type": break_type,
                "target_id": t,
                "target_name": equip_lookup.get(t, {}).get("EQUIP_NAME", ""),
                "source_node": s_node,
                "target_node": t_node,
                # R7: 疑似断点设备 (Sheet2 col 5-8)
                "suspect_switch_id": suspect_switch_id or s,
                "suspect_switch_name": suspect_switch_name or equip_lookup[s].get("EQUIP_NAME", ""),
                "peer_switch_id": t,
                "peer_switch_name": equip_lookup.get(t, {}).get("EQUIP_NAME", ""),
            },
        )

    # Bug#87: Ensure kill-pair output even if no records were produced
    for a, b in official_pairs:
        _kp_yielded = any((a, b) in seen_pairs or (b, a) in seen_pairs for _ in [0])
        if not _kp_yielded:
            yield ProblemRecord(
                task_code="1.2",
                device_id=a,
                device_name=equip_lookup.get(a, {}).get("EQUIP_NAME", "NOT_FOUND"),
                description=f"必杀对 {a} -> {b}: 设备ID在数据集中不存在",
                correction="核实设备ID是否正确",
                correction_sql="",
                severity="info",
                confidence=0.5,
                evidence=[],
                extra={
                    "break_type": "not_found",
                    "target_id": b,
                    "target_name": equip_lookup.get(b, {}).get("EQUIP_NAME", "NOT_FOUND"),
                    "suspect_switch_id": "",
                    "suspect_switch_name": "",
                    "peer_switch_id": b,
                    "peer_switch_name": equip_lookup.get(b, {}).get("EQUIP_NAME", ""),
                },
            )
    return ()
