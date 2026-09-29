# -*- coding: utf-8 -*-
"""Graph algorithms used by the official 12 detectors.

All algorithms operate on plain Python data structures so that detectors
do not need networkx. Inputs are Mapping[str, Iterable[str]] adjacency
maps (node_id -> iterable of neighbour node_ids). Outputs are tuples
or frozensets for immutability and dataclass compatibility.

Index:
    adjacency_from_terminals(tables) -> dict[str, set[str]]
    bfs(adj, start) -> tuple[str, ...]
    connected_components(adj) -> tuple[frozenset[str], ...]
    has_cycle(adj) -> bool
    find_cycles(adj) -> tuple[tuple[str, ...], ...]
    articulation_points(adj) -> frozenset[str]
    shortest_path(adj, src, tgt) -> tuple[str, ...] | None
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def adjacency_from_terminals(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, set[str]]:
    """Build node-to-node adjacency from TERMINAL rows.

    Rows are JBS_PWTERMINAL / JBS_ZWTERMINAL with fields
    EQUIP_ID and CONNECTIVITYNODE_ID. Two nodes are adjacent when they
    share the same EQUIP_ID (an electrical device implicitly connects
    all of its terminal nodes).
    """
    equip_to_nodes: dict[str, set[str]] = {}
    for table_name in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(table_name, ()):
            eid = row.get("EQUIP_ID")
            nid = row.get("CONNECTIVITYNODE_ID")
            if eid and nid:
                equip_to_nodes.setdefault(str(eid), set()).add(str(nid))
    adj: dict[str, set[str]] = {}
    for eid, nodes in equip_to_nodes.items():
        node_list = sorted(nodes)
        if len(node_list) == 1:
            # 单端子设备（变压器/线路末端/电缆终端头）：注册为孤立节点，
            # 使其可作为路径端点被寻路命中，而非被整体丢弃导致 1.2 大量假阳性"拓扑断连"。
            adj.setdefault(node_list[0], set())
            continue
        for a, b in zip(node_list, node_list[1:]):
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return adj


def bfs(adj: Mapping[str, Iterable[str]], start: str) -> tuple[str, ...]:
    """Breadth-first traversal returning visited node_ids in order."""
    visited: list[str] = []
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        for nb in sorted(adj.get(node, ())):
            if nb not in seen:
                queue.append(str(nb))
    return tuple(visited)


def connected_components(adj: Mapping[str, Iterable[str]]) -> tuple[frozenset[str], ...]:
    """Return all connected components (as frozensets of node_ids).

    Components with a single node are returned too — these are the
    isolated islands that task 1.1 / 1.2 should flag.
    """
    seen: set[str] = set()
    components: list[frozenset[str]] = []
    nodes = set(adj.keys())
    for nb_set in adj.values():
        nodes.update(nb_set)
    for start in sorted(nodes):
        if start in seen:
            continue
        component = set(bfs(adj, start))
        seen.update(component)
        components.append(frozenset(component))
    return tuple(components)


def has_cycle(adj: Mapping[str, Iterable[str]]) -> bool:
    """Return True iff the undirected graph contains at least one cycle."""
    return any(len(c) >= 3 and any(len(adj.get(n, ())) >= 2 for n in c) for c in connected_components(adj))


def find_cycles(adj: Mapping[str, Iterable[str]], max_cycles: int = 100, max_path: int = 16) -> tuple[tuple[str, ...], ...]:
    """Find up to `max_cycles` elementary cycles (Johnson-style BFS, bounded).

    Returned tuples are simple cycles (no repeated interior nodes). Result
    is empty for forest graphs. Useful for tasks 1.5 / 2.3 / 2.4.
    """
    cycles: list[tuple[str, ...]] = []
    seen_edges: set[tuple[str, str]] = set()
    components = connected_components(adj)
    for component in components:
        if len(component) < 3:
            continue
        nodes = sorted(component)
        for i, src in enumerate(nodes):
            for tgt in nodes[i + 1:]:
                if tgt not in adj.get(src, ()):
                    continue
                edge = tuple(sorted((src, tgt)))
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                for path in _simple_paths_within(adj, src, tgt, component, max_path=max_path):
                    if len(path) >= 3 and path[0] == src and path[-1] == tgt:
                        cycles.append(path)
                        if len(cycles) >= max_cycles:
                            return tuple(cycles)
    return tuple(cycles)


def _simple_paths_within(
    adj: Mapping[str, Iterable[str]],
    src: str,
    tgt: str,
    component: frozenset[str],
    max_path: int,
) -> Iterable[tuple[str, ...]]:
    seen: set[str] = {src}
    stack: list[tuple[str, ...]] = [(src,)]
    while stack:
        path = stack.pop()
        last = path[-1]
        if last == tgt and len(path) >= 2:
            yield path
            continue
        if len(path) >= max_path:
            continue
        for nb in sorted(adj.get(last, ())):
            if nb not in component:
                continue
            if nb in seen and nb != tgt:
                continue
            seen.add(nb)
            stack.append(path + (nb,))


def shortest_path(adj: Mapping[str, Iterable[str]], src: str, tgt: str) -> tuple[str, ...] | None:
    """BFS shortest path between two nodes. Returns None if unreachable."""
    if src == tgt:
        return (src,)
    seen = {src}
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(src, (src,))])
    while queue:
        node, path = queue.popleft()
        for nb in sorted(adj.get(node, ())):
            if nb in seen:
                continue
            seen.add(nb)
            new_path = path + (str(nb),)
            if nb == tgt:
                return new_path
            queue.append((str(nb), new_path))
    return None


def articulation_points(adj: Mapping[str, Iterable[str]]) -> frozenset[str]:
    """Return articulation points (Tarjan).

    Useful for task 1.2: removing an articulation point disconnects a
    component, suggesting a single-point-of-failure topology issue.
    """
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap: set[str] = set()
    timer = [0]

    def dfs(u: str) -> None:
        children = 0
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in sorted(adj.get(u, ())):
            if v not in disc:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent[u] is None and children > 1:
                    ap.add(u)
                if parent[u] is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node in sorted(set(adj.keys()) | {n for s in adj.values() for n in s}):
        if node not in disc:
            parent[node] = None
            dfs(node)
    return frozenset(ap)





def shortest_path_excluding(
    adj: "Mapping[str, Iterable[str]]",
    src: str,
    tgt: str,
    excluded: "Iterable[str]",
) -> "tuple[str, ...] | None":
    """BFS shortest path that avoids a set of forbidden node IDs.

    Per 评审手册 §4.2 + 00_官方要求权威整合清单.md §8.4:
    `路径算法禁止绕道末端站房`. The caller is responsible for mapping
    end-room devices -> their CONNECTIVITYNODE_IDs and passing them in.
    Returns None if src == tgt or no path exists within the constraint.
    """
    if src == tgt:
        return (src,)
    excluded_set = set(excluded)
    if src in excluded_set or tgt in excluded_set:
        return None
    seen = {src}
    queue: "deque[tuple[str, tuple[str, ...]]]" = deque([(src, (src,))])
    while queue:
        node, path = queue.popleft()
        for nb in sorted(adj.get(node, ())):
            if nb in seen or nb in excluded_set:
                continue
            seen.add(nb)
            new_path = path + (str(nb),)
            if nb == tgt:
                return new_path
            queue.append((str(nb), new_path))
    return None


def terminal_ids_in_end_rooms(
    tables: "Mapping[str, Sequence[Mapping[str, Any]]]",
) -> "set[str]":
    """Return the set of CONNECTIVITYNODE_IDs that belong to devices inside an end-station room.

    Per 官方 §8.4 强制: 配电站 / 箱变 (IS_END_DEVICE=1) 站内所有设备不参与悬空判定.
    For path-finding we must also forbid routes that pass through these terminals.

    Real dataset (CP-202606 最终版) JBS_PWROOM has NO IS_END_DEVICE column; its
    TYPE field carries ZD_OBJECT OBJ_CODE: 1002=配电站, 1005=箱式变 (terminal
    equipment per 宣讲会/§8.4), 1006=高压用户站 (terminal-class customer station,
    0 rows in current dataset). Fall back to name heuristic for synthetic data.
    """
    END_ROOM_TYPES = {"1002", "1005", "1006"}
    end_room_ids: set[str] = set()
    for r in list(tables.get("JBS_PWROOM", ())):
        rid = r.get("ROOM_ID")
        if not rid:
            continue
        val = r.get("IS_END_DEVICE")
        if val is not None:
            is_end = str(val) in ("1", "true", "TRUE", "True", "yes", "Y")
        else:
            # No explicit flag: judge by TYPE code (real data), then name heuristic
            is_end = (
                str(r.get("TYPE") or "") in END_ROOM_TYPES
                or "末端" in (r.get("ROOM_NAME") or "")
            )
        if is_end:
            end_room_ids.add(str(rid))
    if not end_room_ids:
        return set()
    # Collect all device IDs inside end rooms
    end_devices: set[str] = set()
    for d in list(tables.get("JBS_PWEQUIPINFO", ())):
        if str(d.get("DSUBSTATION_ID") or "") in end_room_ids:
            eid = d.get("EQUIP_ID")
            if eid:
                end_devices.add(str(eid))
    if not end_devices:
        return set()
    # Map devices -> terminal CN IDs
    end_nodes: set[str] = set()
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(tbl, ()):
            if str(row.get("EQUIP_ID") or "") in end_devices:
                nid = row.get("CONNECTIVITYNODE_ID")
                if nid:
                    end_nodes.add(str(nid))
    return end_nodes


__all__ = [
    "adjacency_from_terminals",
    "articulation_points",
    "bfs",
    "connected_components",
    "find_cycles",
    "has_cycle",
    "shortest_path",
    "shortest_path_excluding",
    "terminal_ids_in_end_rooms",
]
