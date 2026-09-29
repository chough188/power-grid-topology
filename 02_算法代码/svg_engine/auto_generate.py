#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
5.3 自动生成 SVG 接线图

基于完整电网模型数据库，按统一制图规则自动生成：
    5.3.1 单馈线完整单线图
    5.3.2 馈线联络关系图
    5.3.3 全站间馈线联络总图
    5.3.4 指定设备电源追溯路径图（含备供路径）

测试任务：
    1. 生成 LINE215、LINE216 单线图
    2. 生成 10kV LINE111 联络关系图
    3. 生成 SUB004 变电站下所有线路联络关系图
    4. 生成 LINE074 配变 0486 (id=TMP00034205) 电源追溯路径图
"""

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .svg_loader import (
    SVGLoader, SVGDevice, SVGLink,
    build_graph_from_json, load_snapshot,
)


def generate_single_line(db_path: str, feeder_id: str, output_path: str) -> str:
    """
    5.3.1 生成单馈线完整单线图。
    """
    snapshot = _load_db(db_path)
    graph = build_graph_from_json(snapshot)

    # 筛选指定馈线的设备
    nodes = {}
    edges = []
    for nid, data in graph["nodes"].items():
        if data.get("feeder") == feeder_id:
            nodes[nid] = data

    for a, b, data in graph["edges"]:
        if a in nodes and b in nodes:
            edges.append((a, b, data))

    sub_graph = {"nodes": nodes, "edges": edges}
    loader = SVGLoader()
    loader.from_graph(sub_graph)
    loader.title = f"单线图: {feeder_id}"
    loader._tree_layout()
    loader.render(output_path)
    return output_path


def generate_tie_diagram(db_path: str, feeder_id: str, output_path: str) -> str:
    """
    5.3.2 生成馈线联络关系图。
    显示馈线间的联络开关、联络线路配对关系。
    """
    snapshot = _load_db(db_path)
    graph = build_graph_from_json(snapshot)

    # 找联络开关：属于两个不同馈线的连通节点上的 SWITCH/BREAKER
    tie_switches = _find_tie_switches(graph)

    # 只保留与指定 feeder 相关的联络
    related = [ts for ts in tie_switches
               if feeder_id in (ts.get("feeder_a"), ts.get("feeder_b"))]

    # 构建简化图：馈线为节点，联络为边
    nodes = {}
    edges = []
    seen_feeders = set()
    for ts in related:
        fa, fb = ts.get("feeder_a", ""), ts.get("feeder_b", "")
        if fa and fa not in seen_feeders:
            seen_feeders.add(fa)
            nodes[fa] = {"name": fa, "type": "FEEDER"}
        if fb and fb not in seen_feeders:
            seen_feeders.add(fb)
            nodes[fb] = {"name": fb, "type": "FEEDER"}
        if fa and fb:
            edges.append((fa, fb, {"switch": ts.get("switch_id", "")}))

    loader = SVGLoader()
    loader.from_graph({"nodes": nodes, "edges": edges})
    loader.title = f"联络关系图: {feeder_id}"
    loader._force_layout(iterations=80)
    loader.render(output_path, layout_strategy="force")
    return output_path


def generate_station_tie_map(db_path: str, station_id: str, output_path: str) -> str:
    """
    5.3.3 生成全站间馈线联络总图。
    汇总多变电站之间全部联络拓扑。
    """
    snapshot = _load_db(db_path)
    graph = build_graph_from_json(snapshot)
    feeders = graph.get("feeders", [])

    # 筛选该变电站下的馈线
    station_feeders = [f for f in feeders
                       if f.get("START_ST_ID") == station_id]
    feeder_ids = {f["LINE_ID"] for f in station_feeders}

    # 找这些馈线与其他馈线的联络
    tie_switches = _find_tie_switches(graph)
    related = [ts for ts in tie_switches
               if ts.get("feeder_a") in feeder_ids or ts.get("feeder_b") in feeder_ids]

    # 构建图：变电站为节点，联络为边
    stations = set()
    for f in station_feeders:
        stations.add(f.get("START_ST_ID", station_id))

    for ts in related:
        # 获取联络对端变电站
        fa, fb = ts.get("feeder_a", ""), ts.get("feeder_b", "")
        # 从 graph nodes 查找
        for nid, data in graph["nodes"].items():
            if data.get("feeder") == fa and data.get("substation"):
                stations.add(data["substation"])
            if data.get("feeder") == fb and data.get("substation"):
                stations.add(data["substation"])

    nodes = {st: {"name": st, "type": "SUBSTATION"} for st in stations}
    edges = []
    seen = set()
    for ts in related:
        # 简化为站-站边
        fa, fb = ts.get("feeder_a", ""), ts.get("feeder_b", "")
        sa = _get_station_for_feeder(graph, fa)
        sb = _get_station_for_feeder(graph, fb)
        if sa and sb and sa != sb and (sa, sb) not in seen:
            seen.add((sa, sb))
            edges.append((sa, sb, {"switch": ts.get("switch_id", "")}))

    loader = SVGLoader()
    loader.from_graph({"nodes": nodes, "edges": edges})
    loader.title = f"全站联络总图: {station_id}"
    loader._force_layout(iterations=60)
    loader.render(output_path, layout_strategy="force")
    return output_path


def generate_trace_path(db_path: str, device_id: str, output_path: str) -> str:
    """
    5.3.4 生成指定设备电源追溯路径图（含备供路径）。
    """
    snapshot = _load_db(db_path)
    graph = build_graph_from_json(snapshot)

    # BFS 找从电源到设备的全部路径
    all_paths = _find_power_paths(graph, device_id)

    # 收集路径上的所有节点和边
    path_nodes = set()
    path_edges = set()
    for path in all_paths:
        for nid in path:
            path_nodes.add(nid)
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            path_edges.add(tuple(sorted((a, b))))

    nodes = {nid: graph["nodes"][nid] for nid in path_nodes if nid in graph["nodes"]}
    edges = []
    for a, b, data in graph["edges"]:
        if tuple(sorted((a, b))) in path_edges:
            edges.append((a, b, data))

    loader = SVGLoader()
    loader.from_graph({"nodes": nodes, "edges": edges})
    loader.title = f"电源追溯: {device_id}"
    loader._tree_layout()
    loader.render(output_path)
    return output_path


# ── 辅助函数 ──────────────────────────────────────────────

def _load_db(db_path: str) -> Dict:
    """加载数据库（JSON snapshot 或包含 snapshot 的目录）。"""
    p = Path(db_path)
    if p.is_file() and p.suffix == ".json":
        return load_snapshot(str(p))
    elif p.is_file() and p.suffix == ".sql":
        # 尝试找同名的 json
        json_file = p.with_suffix(".json")
        if json_file.exists():
            return load_snapshot(str(json_file))
        raise ValueError(f"SQL 文件需要对应 JSON snapshot: {db_path}")
    elif p.is_dir():
        # 找目录下的第一个 json
        jsons = list(p.glob("*.json"))
        if jsons:
            return load_snapshot(str(jsons[0]))
        sqls = list(p.glob("*.sql"))
        if sqls:
            j = sqls[0].with_suffix(".json")
            if j.exists():
                return load_snapshot(str(j))
        raise ValueError(f"目录中未找到有效的数据库文件: {db_path}")
    else:
        raise ValueError(f"无效的数据库路径: {db_path}")


def _find_tie_switches(graph: Dict) -> List[Dict]:
    """
    识别联络开关：
    - 开关/断路器类型
    - 两侧属于不同馈线
    """
    nodes = graph["nodes"]
    edges = graph["edges"]

    # 建立 equip_id -> feeder_id 映射
    equip_feeder = {}
    for nid, data in nodes.items():
        equip_feeder[nid] = data.get("feeder", "")

    # 构建邻接
    adj = defaultdict(list)
    for a, b, _ in edges:
        adj[a].append(b)
        adj[b].append(a)

    tie_switches = []
    for nid, data in nodes.items():
        if data.get("type") not in ("SWITCH", "BREAKER", "DISCONNECTOR"):
            continue
        neighbors = adj.get(nid, [])
        feeders = set()
        feeder_map = {}
        for nb in neighbors:
            f = equip_feeder.get(nb, "")
            if f:
                feeders.add(f)
                feeder_map[f] = nb
        if len(feeders) >= 2:
            flist = list(feeders)
            tie_switches.append({
                "switch_id": nid,
                "feeder_a": flist[0],
                "feeder_b": flist[1] if len(flist) > 1 else "",
            })
    return tie_switches


def _get_station_for_feeder(graph: Dict, feeder_id: str) -> str:
    """根据馈线 ID 获取所属变电站。"""
    for nid, data in graph["nodes"].items():
        if data.get("feeder") == feeder_id and data.get("substation"):
            return data["substation"]
    for f in graph.get("feeders", []):
        if f.get("LINE_ID") == feeder_id:
            return f.get("START_ST_ID", "")
    return ""


def _find_power_paths(graph: Dict, target_id: str) -> List[List[str]]:
    """
    从所有电源节点到目标设备的所有路径。
    使用 BFS/DFS 找全部简单路径。
    """
    nodes = graph["nodes"]
    edges = graph["edges"]

    # 找电源节点
    sources = [nid for nid, data in nodes.items()
               if data.get("type") in ("SOURCE", "SUBSTATION", "GENERATOR")]

    if not sources:
        # 没有明确电源，找度数最小的节点作为候选
        degree = defaultdict(int)
        for a, b, _ in edges:
            degree[a] += 1
            degree[b] += 1
        sources = [min(nodes.keys(), key=lambda k: degree.get(k, 0))]

    # 构建邻接表
    adj = defaultdict(list)
    for a, b, _ in edges:
        adj[a].append(b)
        adj[b].append(a)

    all_paths = []
    max_paths_per_source = 5  # 限制路径数量

    for src in sources:
        paths = _dfs_paths(adj, src, target_id, max_paths=max_paths_per_source)
        all_paths.extend(paths)

    return all_paths


def _dfs_paths(adj, start, end, max_paths=5, max_depth=50) -> List[List[str]]:
    """DFS 找从 start 到 end 的简单路径。"""
    paths = []
    stack = [(start, [start])]
    while stack and len(paths) < max_paths:
        node, path = stack.pop()
        if node == end:
            paths.append(path)
            continue
        if len(path) >= max_depth:
            continue
        for nb in adj.get(node, []):
            if nb not in path:
                stack.append((nb, path + [nb]))
    return paths


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="自动生成 SVG 接线图（任务 5.3）")
    parser.add_argument("--db", required=True, help="数据库目录或 JSON snapshot 文件")
    parser.add_argument("--output", required=True, help="SVG 输出目录")
    parser.add_argument("--type", choices=["single", "tie", "station", "trace"],
                        default="single", help="生成类型")
    parser.add_argument("--feeder", default="", help="馈线 ID（单线图/联络图）")
    parser.add_argument("--station", default="", help="变电站 ID（全站联络图）")
    parser.add_argument("--device", default="", help="设备 ID（电源追溯图）")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if args.type == "single":
        if not args.feeder:
            print("[ERROR] --feeder 参数必填")
            sys.exit(1)
        output = out / f"single_{args.feeder}.svg"
        generate_single_line(args.db, args.feeder, str(output))
        print(f"[OK] 单线图: {output}")

    elif args.type == "tie":
        if not args.feeder:
            print("[ERROR] --feeder 参数必填")
            sys.exit(1)
        output = out / f"tie_{args.feeder}.svg"
        generate_tie_diagram(args.db, args.feeder, str(output))
        print(f"[OK] 联络关系图: {output}")

    elif args.type == "station":
        if not args.station:
            print("[ERROR] --station 参数必填")
            sys.exit(1)
        output = out / f"station_{args.station}.svg"
        generate_station_tie_map(args.db, args.station, str(output))
        print(f"[OK] 全站联络总图: {output}")

    elif args.type == "trace":
        if not args.device:
            print("[ERROR] --device 参数必填")
            sys.exit(1)
        output = out / f"trace_{args.device}.svg"
        generate_trace_path(args.db, args.device, str(output))
        print(f"[OK] 电源追溯路径图: {output}")


if __name__ == "__main__":
    main()
