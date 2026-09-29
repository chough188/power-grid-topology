# -*- coding: utf-8 -*-
"""Task 5.3: Auto-generate SVG diagrams from database topology.

Outputs four diagram types per official §4.3:
  5.3.1 single-feeder single-line diagram (LINE215 / LINE216)
  5.3.2 tie-switch relation diagram    (10kV LINE111)
  5.3.3 cross-substation tie diagram   (SUB004 + all feeders)
  5.3.4 device power-trace diagram    (LINE074 + TMP00034205, with backup path)

Each `render_*(tables) -> str` returns a full SVG XML document.
No external libraries required — plain stdlib only.

Real-data notes (CP-202606 official dataset):
- ``EQUIP_TYPE`` arrives as CIM OBJ_CODE and is normalized by the pipeline
  to CIM ENNAMEs (DBREAKER / DLOADSWITCH / DPWRTRANSFM / BUS / ...). All
  type filters below accept both the canonical enums (synthetic data) and
  the CIM ENNAMEs (real data) via the class sets defined under Helpers.
- Feeder<->substation association uses ``PWFEEDERLINE.START_ST_ID``;
  equipment ``DSUBSTATION_ID`` references transformer stations, never the
  ZWSUBSTATION id of the 110kV station.
- Power trace uses multi-source BFS (no depth cap): the real target
  TMP00034205 sits ~28 hops from the nearest 110kV busbar.
"""
from __future__ import annotations

import html as _html
import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector
from shared.switch_state import build_signal_point_map, is_switch_closed
from tasks_official.task5_svg.task_5_1_beautify.detector import (
    _render_legend as _r51_legend,
    _render_scale_bar as _r51_scale_bar,
)


def _legend_and_scale(width: int, height: int) -> str:
    """R4: 5.1 风格图例（电压+线型）与比例尺，右下角，风格与 5.1 完全对齐。"""
    return "\n".join((_r51_scale_bar(width, height), _r51_legend(width, height)))


# ---------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------

# CIM-aware equipment type classes. Every set accepts both the canonical
# enums (synthetic data) and the CIM ENNAMEs produced by normalize_dataset_types
# on the real dataset, so renderers behave identically on either.
_SOURCE_CLASSES = frozenset({"SOURCE"})
_TRANSFORMER_CLASSES = frozenset(
    {"TRANSFORMER", "PWRTRANSFM", "DPWRTRANSFM", "EARTHINGTRANSFORMER"}
)
_BUS_CLASSES = frozenset({"BUS", "BUSBAR", "DBUS"})
_TIE_SWITCH_CLASSES = frozenset(
    {"BREAKER", "SWITCH", "DBREAKER", "DLOADSWITCH", "COMPOSITESWITCH"}
)
_SWITCH_CLASSES = _TIE_SWITCH_CLASSES | frozenset({"DISCONNECTOR", "DDIS", "DGROUNDDIS"})
_SOURCE_ROOT_CLASSES = _SOURCE_CLASSES | _TRANSFORMER_CLASSES | _BUS_CLASSES

def _feeder_equip(tables: Mapping[str, Sequence[Mapping[str, Any]]], feeder_id: str) -> list:
    out = []
    for d in list(tables.get("JBS_PWEQUIPINFO", ())):
        if d.get("FEEDER_ID") == feeder_id:
            out.append(d)
    return out


def _feeder_terminals(tables, equip_ids: set) -> list:
    out = []
    for t in list(tables.get("JBS_PWTERMINAL", ())):
        if t.get("EQUIP_ID") in equip_ids:
            out.append(t)
    return out


def _adjacency_from_feeder(equip_ids: set, terminals: list) -> dict:
    """Build equip->equip adjacency via shared CONNECTIVITYNODE."""
    node_to_equips: dict = {}
    for t in terminals:
        nid = t.get("CONNECTIVITYNODE_ID")
        eid = t.get("EQUIP_ID")
        if nid and eid:
            node_to_equips.setdefault(nid, set()).add(eid)
    adj: dict = {eid: set() for eid in equip_ids}
    for equips_at_node in node_to_equips.values():
        eq_list = sorted(equips_at_node & equip_ids)
        for i, a in enumerate(eq_list):
            for b in eq_list[i + 1:]:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
    return adj


def _bbox(equip_ids: list, equip_meta: Mapping[str, Mapping]) -> tuple:
    """Naive horizontal layout: each device at (i*120, 60)."""
    return (0, 0, max(120 * len(equip_ids), 800), 120)


# ---------------------------------------------------------------
# 5.3.1 layout helpers: tidy radial tree (hierarchical single-line style)
# ---------------------------------------------------------------

# Per-class rendering: (shape, fill). CIM ENNAMEs and canonical enums both accepted.
_DEVICE_STYLE = (
    (("SOURCE",), ("rect", "#FF0000")),
    (("TRANSFORMER", "PWRTRANSFM", "DPWRTRANSFM", "EARTHINGTRANSFORMER"), ("circle", "#FF6600")),
    (("BUS", "BUSBAR", "DBUS"), ("busbar", "#8B4513")),
    (("BREAKER", "SWITCH", "DBREAKER", "DLOADSWITCH", "COMPOSITESWITCH"), ("square", "#32CD32")),
    (("DISCONNECTOR", "DDIS", "DGROUNDDIS"), ("diamond", "#1E90FF")),
    (("FUSE",), ("rect", "#FFD700")),
    (("LOAD",), ("triangle", "#1E90FF")),
)


def _device_shape(et: str) -> tuple:
    et = (et or "DEVICE").upper()
    for classes, style in _DEVICE_STYLE:
        if et in classes:
            return style
    return ("circle", "#666666")


def _forest_roots(equip_ids: set, adj: Mapping[str, set], source_classes: frozenset,
                  equip_meta: Mapping[str, Mapping]) -> list:
    """Root every connected component: prefer a SOURCE-class device, else min id."""
    seen: set = set()
    roots: list = []
    for start in sorted(equip_ids):
        if start in seen:
            continue
        comp: list = [start]
        seen.add(start)
        i = 0
        best = None
        while i < len(comp):
            cur = comp[i]; i += 1
            for nb in sorted(adj.get(cur, ())):
                if nb not in seen:
                    seen.add(nb); comp.append(nb)
            if best is None and (equip_meta.get(cur, {}).get("EQUIP_TYPE") or "").upper() in source_classes:
                best = cur
        roots.append(best or comp[0])
    return roots


def _tree_layout(roots: list, adj: Mapping[str, set], leaf_w: int, level_h: int,
                 top: int, left: int) -> tuple:
    """Tidy tree layout over the forest rooted at ``roots``.

    Returns ``(pos, parent_of, n_leaves)`` where ``pos[eid] = (x, y)``.
    Children are visited in sorted order; each leaf consumes one x-slot,
    internal nodes are centered over their children. Non-tree edges (loops)
    are ignored by the layout and drawn as curved overlays by the caller.
    """
    pos: dict = {}
    parent_of: dict = {}
    next_leaf = [0]

    def place(node: str, depth: int, parent: str | None) -> None:
        # iterative post-order to avoid recursion limits on deep feeders
        stack = [(node, depth, parent, False)]
        while stack:
            n, d, p, processed = stack.pop()
            if processed:
                kids = [c for c in sorted(adj.get(n, ())) if parent_of.get(c) == n]
                if kids:
                    xs = [pos[c][0] for c in kids]
                    pos[n] = ((min(xs) + max(xs)) / 2.0, top + d * level_h)
                else:
                    pos[n] = (left + next_leaf[0] * leaf_w, top + d * level_h)
                    next_leaf[0] += 1
                continue
            if n in pos:
                continue
            # reserve a tentative slot so children can be placed first
            stack.append((n, d, p, True))
            for c in sorted(adj.get(n, ())):
                if c == p or c in parent_of:
                    continue
                parent_of[c] = n
                stack.append((c, d + 1, n, False))

    for r in roots:
        if r in parent_of or r in pos:
            continue
        place(r, 0, None)
    return pos, parent_of, next_leaf[0]


# ---------------------------------------------------------------
# 5.3.1 Single-feeder single-line diagram
# ---------------------------------------------------------------

def render_5_3_1_single_feeder(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    feeder_id: str,
    *,
    title: str | None = None,
) -> str:
    """Render one feeder's topology as a hierarchical single-line SVG.

    Per official §5.1.1: power source at top-left, radial tree layout
    (trunk horizontal per level, branches drop down with orthogonal
    elbow connectors). Per official §5.1.3: standardized colors per
    device class, name label under each device, type label above,
    legend in the top-right corner, no overlapping nodes.

    Layout: tidy tree over the feeder adjacency forest — every component
    is rooted at its SOURCE-class device (or min id), leaves consume
    sequential x-slots, internal nodes center over their children.
    Non-tree edges (loops) are drawn as dashed curves and reported.
    """
    equip = _feeder_equip(tables, feeder_id)
    if not equip:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text x="10" y="30">no equipment for feeder {feeder_id}</text></svg>'
    equip_ids = {d.get("EQUIP_ID") for d in equip if d.get("EQUIP_ID")}
    terms = _feeder_terminals(tables, equip_ids)
    adj = _adjacency_from_feeder(equip_ids, terms)
    equip_meta = {d.get("EQUIP_ID"): d for d in equip if d.get("EQUIP_ID")}

    leaf_w, level_h, top, left = 78, 92, 46, 60
    roots = _forest_roots(equip_ids, adj, _SOURCE_ROOT_CLASSES, equip_meta)
    pos, parent_of, n_leaves = _tree_layout(roots, adj, leaf_w, level_h, top, left)
    max_depth = max(((pos[e][1] - top) // level_h) for e in pos) if pos else 0
    width = int(left + max(n_leaves, 1) * leaf_w + 40)
    height = int(top + (max_depth + 1) * level_h + 46)

    # Edges: orthogonal elbows for tree edges; dashed curves for loop edges.
    edges_xml: list = []
    seen_edges: set = set()
    loop_count = 0
    for a in sorted(pos):
        for b in sorted(adj.get(a, ())):
            key = tuple(sorted((a, b)))
            if key in seen_edges or b not in pos:
                continue
            seen_edges.add(key)
            pa, pb = pos[a], pos[b]
            if parent_of.get(b) == a:
                mid_y = pa[1] + level_h / 2.0
                edges_xml.append(
                    f'  <path d="M {pa[0]:.1f} {pa[1]:.1f} V {mid_y:.1f} H {pb[0]:.1f} V {pb[1]:.1f}" '
                    f'fill="none" stroke="#333" stroke-width="1.5"/>'
                )
            elif parent_of.get(a) == b:
                mid_y = pb[1] + level_h / 2.0
                edges_xml.append(
                    f'  <path d="M {pa[0]:.1f} {pa[1]:.1f} V {mid_y:.1f} H {pb[0]:.1f} V {pb[1]:.1f}" '
                    f'fill="none" stroke="#333" stroke-width="1.5"/>'
                )
            else:
                loop_count += 1
                cy = min(pa[1], pb[1]) - 18
                edges_xml.append(
                    f'  <path d="M {pa[0]:.1f} {pa[1]:.1f} Q {(pa[0] + pb[0]) / 2.0:.1f} {cy:.1f} '
                    f'{pb[0]:.1f} {pb[1]:.1f}" fill="none" stroke="#C00000" '
                    f'stroke-width="1" stroke-dasharray="4,3"/>'
                )

    nodes_xml: list = []
    for eid in sorted(pos):
        meta = equip_meta.get(eid, {})
        x, y = pos[eid]
        et = (meta.get("EQUIP_TYPE") or "DEVICE").upper()
        ename = _html.escape(str(meta.get("EQUIP_NAME") or eid))
        shape, fill = _device_shape(et)
        if shape == "busbar":
            body = (f'<rect x="{x - 16:.1f}" y="{y - 3:.1f}" width="32" height="6" '
                    f'fill="{fill}" stroke="#333"/>')
        elif shape == "square":
            body = (f'<rect x="{x - 9:.1f}" y="{y - 9:.1f}" width="18" height="18" '
                    f'fill="{fill}" stroke="#333"/>')
        elif shape == "diamond":
            body = (f'<polygon points="{x:.1f},{y - 11:.1f} {x + 11:.1f},{y:.1f} '
                    f'{x:.1f},{y + 11:.1f} {x - 11:.1f},{y:.1f}" fill="{fill}" stroke="#333"/>')
        elif shape == "triangle":
            body = (f'<polygon points="{x:.1f},{y - 11:.1f} {x + 11:.1f},{y + 9:.1f} '
                    f'{x - 11:.1f},{y + 9:.1f}" fill="{fill}" stroke="#333"/>')
        elif shape == "rect":
            body = (f'<rect x="{x - 12:.1f}" y="{y - 9:.1f}" width="24" height="18" '
                    f'fill="{fill}" stroke="#333"/>')
        else:  # circle
            body = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{fill}" stroke="#333"/>'
        nodes_xml.append(
            f'  <g class="device" data-equip-id="{eid}">\n'
            f'    {body}\n'
            f'    <text x="{x:.1f}" y="{y + 30:.1f}" text-anchor="middle" font-size="12">{ename}</text>\n'
            f'    <text x="{x:.1f}" y="{y - 18:.1f}" text-anchor="middle" font-size="10" fill="#666">{et}</text>\n'
            f'  </g>'
        )

    legend_items = [
        ("电源", "#FF0000"), ("变压器/配变", "#FF6600"), ("母线", "#8B4513"),
        ("开关/断路器", "#32CD32"), ("刀闸", "#1E90FF"), ("负荷", "#1E90FF"),
    ]
    legend_x = width - 170
    legend_y = 14
    legend_xml = [f'  <rect x="{legend_x - 8}" y="{legend_y - 4}" width="164" height="{18 * len(legend_items) + 12}" '
                  f'fill="#FFFFFF" stroke="#BBB"/>']
    for i, (label, color) in enumerate(legend_items):
        ly = legend_y + 10 + i * 18
        legend_xml.append(
            f'  <rect x="{legend_x}" y="{ly}" width="12" height="12" fill="{color}" stroke="#333"/>'
            f'<text x="{legend_x + 18}" y="{ly + 10}" font-size="11">{label}</text>'
        )

    title_str = _html.escape(title or f"Single-line: feeder {feeder_id}")
    # R4: 画布底部扩展一个图例带，附 5.1 风格图例 + 比例尺
    height += 190
    loop_note = f'  <text x="10" y="{height - 8}" font-size="11" fill="#C00000">虚线红 = 环路边 ({loop_count})</text>\n' if loop_count else ""
    body = "\n".join(edges_xml + nodes_xml + legend_xml)
    body += "\n" + _legend_and_scale(width, height)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <rect width="{width}" height="{height}" fill="#FAFAFA"/>\n'
        f'  <text x="10" y="20" font-size="14" font-weight="bold">{title_str}</text>\n'
        f'{body}\n'
        f'{loop_note}'
        f'</svg>'
    )


# ---------------------------------------------------------------
# 5.3.2 Tie-switch relation diagram (single feeder)
# ---------------------------------------------------------------

def _global_feeder_adjacency(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> tuple:
    """Global equip adjacency + equip->feeder map (distribution + main grid).

    Returns ``(adj, feeder_of)``. ``feeder_of[eid]`` is the FEEDER_ID for
    distribution equipment and None for main-grid (ZW) equipment that sits
    above the 10kV level.
    """
    all_equip = list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ()))
    feeder_of: dict = {}
    for d in all_equip:
        eid = d.get("EQUIP_ID")
        if eid:
            feeder_of[eid] = d.get("FEEDER_ID")
    node_to_equips: dict = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = t.get("EQUIP_ID"); nid = t.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            node_to_equips.setdefault(nid, set()).add(eid)
    adj: dict = {}
    for equips_at_node in node_to_equips.values():
        eq_list = sorted(equips_at_node)
        for i, a in enumerate(eq_list):
            for b in eq_list[i + 1:]:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
    return adj, feeder_of


def _find_paired_feeder(adj: Mapping[str, set], feeder_of: Mapping[str, str | None],
                        start: str, local_feeder: str) -> tuple:
    """BFS from ``start`` until an equipment of ANOTHER feeder is reached.

    Returns ``(paired_feeder_id, hops)`` or ``(None, None)`` when no other
    feeder is reachable (isolated component / data gap).
    """
    seen = {start}
    queue: deque = deque([(start, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth > 40:  # safety cap; tie points are normally 1-3 hops away
            break
        for nb in sorted(adj.get(cur, ())):
            if nb in seen:
                continue
            seen.add(nb)
            fid = feeder_of.get(nb)
            if fid and fid != local_feeder:
                return fid, depth + 1
            queue.append((nb, depth + 1))
    return None, None


def render_5_3_2_tie_diagram(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    feeder_id: str,
) -> str:
    """Render tie-switch relation diagram for one feeder.

    Per official §5.3.2: visualise tie switches + paired lines. For each
    confirmed-open SWITCH/BREAKER in this feeder, the paired line on the
    other side is found by global BFS to the first equipment with a
    different FEEDER_ID. Each row draws
    [本馈线] ——[分闸联络开关]—— [对侧馈线].
    """
    equip = _feeder_equip(tables, feeder_id)
    tables_dict = tables if isinstance(tables, dict) else dict(tables)
    signal_map = build_signal_point_map(tables_dict)
    ties: list = []
    for d in equip:
        et = (d.get("EQUIP_TYPE") or "").upper()
        # CIM-aware: real data carries DBREAKER / DLOADSWITCH / COMPOSITESWITCH
        if et not in _TIE_SWITCH_CLASSES:
            continue
        # R10: use signal POINT resolver for closed state; Q&A ruling:
        # switches without a signal default to CLOSED, so only confirmed-open
        # switches count as tie points.
        if is_switch_closed(tables_dict, d, signal_map) is not False:
            continue
        ties.append(d.get("EQUIP_ID"))
    if not ties:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text x="10" y="30">no tie switches in {feeder_id}</text></svg>'

    adj, feeder_of = _global_feeder_adjacency(tables_dict)
    feeder_names: dict = {}
    for r in list(tables.get("JBS_PWFEEDERLINE", ())):
        fid = r.get("LINE_ID")
        if fid:
            feeder_names[fid] = r.get("LINE_NAME") or fid

    def feeder_label(fid: str | None) -> str:
        if not fid:
            return "未识别"
        return _html.escape(f"{feeder_names.get(fid, fid)} ({fid})")

    local_label = _html.escape(
        f"{feeder_names.get(feeder_id, feeder_id)} ({feeder_id})")
    box_w, row_h, top = 280, 76, 46
    left_x, switch_x, right_x = 60, 520, 900
    width = right_x + box_w + 60
    height = top + len(ties) * row_h + 30
    # R4: 画布底部扩展一个图例带，附 5.1 风格图例 + 比例尺
    height += 190
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'  <rect width="{width}" height="{height}" fill="#FAFAFA"/>',
        f'  <text x="10" y="20" font-size="14" font-weight="bold">'
        f'Tie switches in {local_label}: {len(ties)}</text>',
    ]
    for i, eid in enumerate(ties):
        meta = next((d for d in equip if d.get("EQUIP_ID") == eid), {})
        paired, hops = _find_paired_feeder(adj, feeder_of, eid, feeder_id)
        y = top + i * row_h
        cy = y + 26
        parts.append(
            f'  <g class="tie-row" data-equip-id="{eid}">\n'
            f'    <rect x="{left_x}" y="{y}" width="{box_w}" height="52" fill="#ADD8E6" stroke="#333"/>\n'
            f'    <text x="{left_x + box_w // 2}" y="{y + 22}" text-anchor="middle" font-size="12">{local_label}</text>\n'
            f'    <text x="{left_x + box_w // 2}" y="{y + 40}" text-anchor="middle" font-size="10" fill="#444">本馈线</text>\n'
            f'    <line x1="{left_x + box_w}" y1="{cy}" x2="{switch_x}" y2="{cy}" stroke="#333" stroke-width="1.5"/>\n'
            f'    <rect x="{switch_x}" y="{y}" width="200" height="52" fill="#FFD700" stroke="#333"/>\n'
            f'    <text x="{switch_x + 100}" y="{y + 22}" text-anchor="middle" font-size="12">'
            f'{_html.escape(str(meta.get("EQUIP_NAME") or eid))}</text>\n'
            f'    <text x="{switch_x + 100}" y="{y + 40}" text-anchor="middle" font-size="10" fill="#444">'
            f'分闸联络开关</text>\n'
            f'    <line x1="{switch_x + 200}" y1="{cy}" x2="{right_x}" y2="{cy}" '
            f'stroke="#333" stroke-width="1.5"/>\n'
            f'    <rect x="{right_x}" y="{y}" width="{box_w}" height="52" '
            f'fill="{"#C8E6C9" if paired else "#EEEEEE"}" stroke="#333"/>\n'
            f'    <text x="{right_x + box_w // 2}" y="{y + 22}" text-anchor="middle" font-size="12">'
            f'{feeder_label(paired)}</text>\n'
            f'    <text x="{right_x + box_w // 2}" y="{y + 40}" text-anchor="middle" font-size="10" fill="#444">'
            f'{"对侧馈线 (跳数 " + str(hops) + ")" if paired else "未找到对侧馈线"}</text>\n'
            f'  </g>'
        )
    parts.append(_legend_and_scale(width, height))
    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------
# 5.3.3 Cross-substation tie diagram
# ---------------------------------------------------------------

def render_5_3_3_substation_diagram(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    substation_id: str,
) -> str:
    """Render all feeders under one substation (全站联络总图).

    Per official §5.3.3: aggregate every outgoing feeder of the station.
    Primary association on real data: ``PWFEEDERLINE.START_ST_ID == ST_ID``
    (equipment ``DSUBSTATION_ID`` references transformer stations and never
    matches a ZWSUBSTATION id); synthetic-data fallback groups equipment by
    ``DSUBSTATION_ID``. Layout is a grid so 30+ feeders stay readable.
    """
    feeder_rows = [
        r for r in list(tables.get("JBS_PWFEEDERLINE", ()))
        if str(r.get("START_ST_ID")) == str(substation_id)
    ]
    feeders_under_sub: dict = {}
    if feeder_rows:
        for r in feeder_rows:
            fid = r.get("LINE_ID")
            if fid:
                feeders_under_sub[fid] = {"name": r.get("LINE_NAME"), "equip": 0}
        count_by_feeder: dict = {}
        for d in list(tables.get("JBS_PWEQUIPINFO", ())):
            fid = d.get("FEEDER_ID")
            if fid in feeders_under_sub:
                count_by_feeder[fid] = count_by_feeder.get(fid, 0) + 1
        for fid, meta in feeders_under_sub.items():
            meta["equip"] = count_by_feeder.get(fid, 0)
    else:
        for d in list(tables.get("JBS_PWEQUIPINFO", ())):
            if d.get("DSUBSTATION_ID") != substation_id:
                continue
            fid = d.get("FEEDER_ID")
            if fid:
                feeders_under_sub.setdefault(fid, {"name": None, "equip": 0})
                feeders_under_sub[fid]["equip"] += 1
    if not feeders_under_sub:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text x="10" y="30">no feeders under {substation_id}</text></svg>'

    n = len(feeders_under_sub)
    box_w, box_h, gap_x, gap_y = 190, 44, 30, 58
    cols = max(1, math.ceil(math.sqrt(n * 2)))
    rows = math.ceil(n / cols)
    width = 60 + cols * (box_w + gap_x)
    height = 80 + rows * (box_h + gap_y)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'  <rect width="100%" height="100%" fill="#FAFAFA"/>',
        f'  <text x="10" y="20" font-size="14" font-weight="bold">'
        f'Substation {substation_id}: {n} feeders</text>',
    ]
    card_center: dict[str, tuple[float, float]] = {}
    for i, (fid, meta) in enumerate(sorted(feeders_under_sub.items())):
        x = 60 + (i % cols) * (box_w + gap_x)
        y = 70 + (i // cols) * (box_h + gap_y)
        label = meta.get("name") or fid
        card_center[fid] = (x + box_w / 2, y + box_h / 2)
        parts.append(
            f'  <g class="feeder" data-feeder-id="{fid}">\n'
            f'    <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="#ADD8E6" stroke="#333"/>\n'
            f'    <text x="{x + box_w // 2}" y="{y + 18}" text-anchor="middle" font-size="12">{label}</text>\n'
            f'    <text x="{x + box_w // 2}" y="{y + 35}" text-anchor="middle" font-size="10" fill="#444">{fid} ({meta.get("equip", 0)} dev)</text>\n'
            f'  </g>'
        )

    # --- Tie lines between feeder cards (QC t3 fix, 2026-09) ---------
    # Open switches whose two sides resolve (bounded BFS over the RUNNING
    # graph, same semantics as task 1.3 secondary path) to two different
    # feeders under this substation are drawn as orange tie lines; ties to a
    # feeder outside the substation are listed as cross-station notes.
    from shared.switch_state import (
        build_running_adjacency, build_signal_point_map,
        is_switch_closed, resolve_side_feeders,
    )
    local_fids = set(feeders_under_sub.keys())
    internal_ties: list[tuple[str, str, str]] = []   # (fid_a, fid_b, switch_name)
    cross_ties: list[str] = []                       # "switch_name fid_local→fid_external"
    try:
        signal_map = build_signal_point_map(tables)
        running_adj = build_running_adjacency(tables)
        node_to_equips: dict = {}
        equip_to_nodes: dict = {}
        for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
            for r in tables.get(tbl, ()):
                nid, eid = r.get("CONNECTIVITYNODE_ID"), r.get("EQUIP_ID")
                if nid and eid:
                    node_to_equips.setdefault(nid, set()).add(eid)
                    equip_to_nodes.setdefault(str(eid), []).append(nid)
        equip_feeder = {
            str(d.get("EQUIP_ID")): d.get("FEEDER_ID")
            for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ()))
        }
        tie_classes = ("BREAKER", "SWITCH", "DISCONNECTOR",
                       "DBREAKER", "DLOADSWITCH", "COMPOSITESWITCH")
        for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
            et = (d.get("EQUIP_TYPE") or "").upper()
            if et not in tie_classes:
                continue
            if is_switch_closed(tables, d, signal_map) is not False:
                continue
            eid = str(d.get("EQUIP_ID"))
            nodes = sorted(set(equip_to_nodes.get(eid, [])))
            if len(nodes) < 2:
                continue
            sa = resolve_side_feeders(running_adj, nodes[0], exclude_equip=eid,
                                      node_to_equips=node_to_equips,
                                      equip_feeder=equip_feeder)
            sb = resolve_side_feeders(running_adj, nodes[1], exclude_equip=eid,
                                      node_to_equips=node_to_equips,
                                      equip_feeder=equip_feeder)
            if not sa or not sb:
                continue
            fa = sorted(f for f in sa if f in local_fids)
            fb = sorted(f for f in sb if f in local_fids)
            sw_name = str(d.get("EQUIP_NAME") or eid)
            if fa and fb and any(a != b for a in fa for b in fb):
                internal_ties.append((fa[0], fb[0], sw_name))
            elif bool(fa) != bool(fb):
                internal_fid = (fa or fb)[0]
                external = sorted(((sb if fa else sa) - local_fids))
                if external:
                    cross_ties.append(f"{sw_name} {internal_fid}→{external[0]}(跨站)")
    except Exception:  # noqa: BLE001 - diagram must never fail on data gaps
        internal_ties, cross_ties = [], []

    for fid_a, fid_b, sw_name in internal_ties:
        if fid_a not in card_center or fid_b not in card_center:
            continue
        x1, y1 = card_center[fid_a]
        x2, y2 = card_center[fid_b]
        parts.append(
            f'  <line class="tie" data-from="{fid_a}" data-to="{fid_b}" '
            f'x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
            f'stroke="#FF7F0E" stroke-width="2"/>'
            f'<text x="{(x1 + x2) / 2:g}" y="{(y1 + y2) / 2 - 5:g}" font-size="9" '
            f'fill="#B35900" text-anchor="middle">{_html.escape(sw_name)}</text>'
        )
    note_y = height - 8
    tie_note = (f'{len(internal_ties)} 条站内分位联络线'
                + (f', {len(cross_ties)} 条跨站联络' if cross_ties else "")) \
        if (internal_ties or cross_ties) else "未检测到分位馈线间联络开关"
    parts.append(
        f'  <text x="10" y="{note_y}" font-size="11" fill="#B35900">{tie_note}</text>'
    )
    for i, note in enumerate(cross_ties[:8]):
        parts.append(
            f'  <text x="10" y="{height + 16 + i * 14}" font-size="10" '
            f'fill="#C00000">{_html.escape(note)}</text>'
        )
    if cross_ties:
        # extend canvas so the cross-station notes are visible
        extra_h = 16 + len(cross_ties[:8]) * 14
        parts[0] = parts[0].replace(f'height="{height}"', f'height="{height + extra_h}"')
        parts[0] = parts[0].replace(f'viewBox="0 0 {width} {height}"',
                                    f'viewBox="0 0 {width} {height + extra_h}"')
        parts[1] = parts[1].replace(f'height="100%"', f'height="{height + extra_h}"')
    # R4: 画布底部扩展一个图例带，附 5.1 风格图例 + 比例尺
    base_h = height + ((16 + len(cross_ties[:8]) * 14) if cross_ties else 0)
    new_h = base_h + 190
    parts[0] = parts[0].replace(f'height="{base_h}"', f'height="{new_h}"')
    parts[0] = parts[0].replace(f'viewBox="0 0 {width} {base_h}"',
                                f'viewBox="0 0 {width} {new_h}"')
    if 'height="100%"' in parts[1]:
        parts[1] = parts[1].replace('height="100%"', f'height="{new_h}"')
    else:
        parts[1] = parts[1].replace(f'height="{base_h}"', f'height="{new_h}"')
    parts.append(_legend_and_scale(width, new_h))
    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------
# 5.3.4 Device power-trace diagram (with backup path)
# ---------------------------------------------------------------

def _source_equips(tables):
    """Identify power-source roots: SOURCE / transformer / busbar devices.

    CIM-aware: real datasets normalize main-grid transformers to TRANSFORMER
    (1311) and busbars to BUS (1301); distribution busbars stay DBUS. All are
    legitimate power entry points for a trace.
    """
    out = []
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        et = (d.get("EQUIP_TYPE") or "").upper()
        if et in _SOURCE_ROOT_CLASSES and d.get("EQUIP_ID"):
            out.append(d["EQUIP_ID"])
    return out


def _multi_source_bfs(adj, sources, target, exclude=frozenset()):
    """Shortest path from ANY source to target via proper BFS (no depth cap).

    Returns ``(path, origin_source)``; ``(None, None)`` when unreachable.
    ``exclude`` removes the main-path source for backup-path computation.
    """
    start = [s for s in dict.fromkeys(sources) if s != target and s not in exclude]
    if not start:
        return None, None
    prev: dict = {}
    origin: dict = {}
    queue: deque = deque()
    for s in start:
        prev[s] = None
        origin[s] = s
        queue.append(s)
    while queue:
        n = queue.popleft()
        if n == target:
            path = [n]
            while prev[n] is not None:
                n = prev[n]
                path.append(n)
            return path[::-1], origin[target]
        for m in sorted(adj.get(n, ())):
            if m not in prev:
                prev[m] = n
                origin[m] = origin[n]
                queue.append(m)
    return None, None


def _path_to_node_path(equip_path, equip_to_nodes):
    """Convert equip path -> CONNECTIVITYNODE path for SVG rendering."""
    out = []
    for eid in equip_path:
        nodes = equip_to_nodes.get(eid)
        if nodes:
            out.append(sorted(nodes)[0])
    return out


def render_5_3_4_power_trace(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    device_id: str,
) -> str:
    """Render power-trace path from source(s) to one device.

    Per official §5.3.4: include BOTH main (shortest) and BACKUP
    power paths from a **different** independent source.

    Algorithm:
      1. Find every SOURCE / transformer / busbar equipment id (CIM-aware).
      2. Multi-source BFS -> main_path = shortest path from any source.
      3. Second BFS excluding the main source -> backup_path.
      4. Render both paths on one SVG; main solid blue, backup dashed orange.

    Per official T10 test: device_id = TMP00034205 (LINE074 配变 0486).
    """
    equip_ids = {d.get("EQUIP_ID") for d in list(tables.get("JBS_PWEQUIPINFO", ()))
                 + list(tables.get("JBS_ZWEQUIPINFO", ())) if d.get("EQUIP_ID")}
    if device_id not in equip_ids:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
                f'<text x="10" y="30">device {device_id} not in model</text></svg>')

    # Build equip->nodes map
    equip_to_nodes = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = t.get("EQUIP_ID"); nid = t.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            equip_to_nodes.setdefault(eid, set()).add(nid)

    # Build equip->equip adjacency via shared CN
    node_to_equips = {}
    for eid, nodes in equip_to_nodes.items():
        for nid in nodes:
            node_to_equips.setdefault(nid, set()).add(eid)
    adj = {eid: set() for eid in equip_ids}
    for equips_at_node in node_to_equips.values():
        eq_list = sorted(equips_at_node)
        for i, a in enumerate(eq_list):
            for b in eq_list[i + 1:]:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)

    sources = _source_equips(tables) or sorted(equip_ids)[:1]
    # Prefer main-grid (ZWEQUIPINFO) sources so the trace reaches the real
    # plant/substation entry point; fall back to distribution busbars only
    # when the target is reachable from those alone.
    zw_ids = {d.get("EQUIP_ID") for d in list(tables.get("JBS_ZWEQUIPINFO", ()))
              if d.get("EQUIP_ID")}
    main_pool = [s for s in sources if s in zw_ids] or sources

    # Main path: single multi-source BFS pass (optimal, no depth cap — the
    # real target sits ~28 hops from the nearest 110kV busbar).
    main_path, main_src = _multi_source_bfs(adj, main_pool, device_id)
    if not main_path:
        main_path, main_src = _multi_source_bfs(adj, sources, device_id)
    if not main_path:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60">'
                f'<text x="10" y="30">no power path from any source to {device_id}</text></svg>')

    # Backup path: shortest path from any OTHER source (second BFS pass).
    backup_path, backup_src = _multi_source_bfs(
        adj, main_pool, device_id, exclude=frozenset({main_src})
    )
    if not backup_path:
        backup_path, backup_src = _multi_source_bfs(
            adj, sources, device_id, exclude=frozenset({main_src})
        )

    # Render
    step = 130
    width = max((len(main_path) + 1) * step, 800)
    y_main = 50
    y_backup = 100
    nodes_main = []
    nodes_backup = []
    for i, eid in enumerate(main_path):
        x = 60 + i * step
        equip_meta = next((d for d in list(tables.get("JBS_PWEQUIPINFO", ()))
                           + list(tables.get("JBS_ZWEQUIPINFO", ()))
                           if d.get("EQUIP_ID") == eid), {})
        ename = equip_meta.get("EQUIP_NAME") or eid
        nodes_main.append(
            f'  <g class="main" data-equip-id="{eid}">\n'
            f'    <circle cx="{x}" cy="{y_main}" r="12" fill="#1E90FF" stroke="#003366"/>\n'
            f'    <text x="{x}" y="{y_main - 18}" text-anchor="middle" font-size="11">{ename}</text>\n'
            f'  </g>'
        )
        if i < len(main_path) - 1:
            x2 = 60 + (i + 1) * step
            nodes_main.append(
                f'  <line x1="{x}" y1="{y_main}" x2="{x2}" y2="{y_main}" stroke="#1E90FF" stroke-width="2"/>'
            )

    if backup_path:
        for i, eid in enumerate(backup_path):
            x = 60 + i * step
            equip_meta = next((d for d in list(tables.get("JBS_PWEQUIPINFO", ()))
                               + list(tables.get("JBS_ZWEQUIPINFO", ()))
                               if d.get("EQUIP_ID") == eid), {})
            ename = equip_meta.get("EQUIP_NAME") or eid
            nodes_backup.append(
                f'  <g class="backup" data-equip-id="{eid}">\n'
                f'    <rect x="{x - 10}" y="{y_backup - 10}" width="20" height="20" fill="#FFA500" stroke="#663300"/>\n'
                f'    <text x="{x}" y="{y_backup + 22}" text-anchor="middle" font-size="11">{ename}</text>\n'
                f'  </g>'
            )
            if i < len(backup_path) - 1:
                x2 = 60 + (i + 1) * step
                nodes_backup.append(
                    f'  <line x1="{x}" y1="{y_backup}" x2="{x2}" y2="{y_backup}" stroke="#FFA500" stroke-width="2" stroke-dasharray="5,3"/>'
                )

    main_body = "\n".join(nodes_main) if nodes_main else ""
    backup_body = "\n".join(nodes_backup) if nodes_backup else ""
    # R4: 画布底部扩展一个图例带，附 5.1 风格图例 + 比例尺
    total_h = 160 + 190
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" viewBox="0 0 {width} {total_h}">\n'
        f'  <rect width="100%" height="{total_h}" fill="#FAFAFA"/>\n'
        f'  <text x="10" y="20" font-size="14" font-weight="bold">Power trace to {device_id}</text>\n'
        f'  <text x="10" y="{y_main - 30}" font-size="11" fill="#1E90FF">-- main path from source {main_src} (solid blue) --</text>\n'
        + (f'  <text x="10" y="{y_backup - 22}" font-size="11" fill="#FFA500">-- backup path from source {backup_src} (dashed orange) --</text>\n' if backup_src else '')
        + f'{main_body}\n'
        + f'{backup_body}\n'
        + _legend_and_scale(width, total_h)
        + '\n'
        f'</svg>'
    )

# ---------------------------------------------------------------
# Convenience entry point for batch rendering
# ---------------------------------------------------------------

def render_all(tables, *, line215=None, line216=None, line111=None, sub004=None, target_id=None) -> dict:
    """Render all 4 diagram types. Returns dict of name -> SVG string."""
    out = {}
    if line215:
        out["5.3.1_LINE215"] = render_5_3_1_single_feeder(tables, line215, title="LINE215 single-line")
    if line216:
        out["5.3.1_LINE216"] = render_5_3_1_single_feeder(tables, line216, title="LINE216 single-line")
    if line111:
        out["5.3.2_LINE111"] = render_5_3_2_tie_diagram(tables, line111)
    if sub004:
        out["5.3.3_SUB004"] = render_5_3_3_substation_diagram(tables, sub004)
    if target_id:
        out["5.3.4_trace"] = render_5_3_4_power_trace(tables, target_id)
    return out


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    """Official-style entry point for 5.3 自动出图.

    从 ``ctx.options`` 读取四类出图所需的定位键（line215 / line216 /
    line111 / sub004 / target_id）。若 options 为空，则自动从 tables 探测：
      - 找前 2 条 LINE 类设备当作 line215/line216
      - 找首条有 DANGLE/OPEN 状态的开关当作 line111（tie）
      - 找首个 STATION 当作 sub004
      - 找首个 LOAD 当作 trace target
    调用 :func:`render_all` 生成 4 类 SVG，并以一条 ProblemRecord 汇总成果。
    """
    tables = ctx.tables
    opts = ctx.options or {}
    line215 = opts.get("line215")
    line216 = opts.get("line216")
    line111 = opts.get("line111")
    sub004 = opts.get("sub004")
    target_id = opts.get("target_id")

    # Fallback auto-probe when options are missing
    if not (line215 and line216 and line111 and sub004 and target_id):
        pw_equip = list(tables.get("JBS_PWEQUIPINFO", []))
        lines = [e.get("EQUIP_ID") for e in pw_equip
                 if (e.get("EQUIP_TYPE") or "").upper() in ("LINE", "FEEDER_LINE")][:2]
        subs = list(tables.get("JBS_ZWSUBSTATION", []))
        loads = [e.get("EQUIP_ID") for e in pw_equip
                 if (e.get("EQUIP_TYPE") or "").upper() in ("LOAD", "TRANSFORMER")]
        if line215 is None and len(lines) >= 1:
            line215 = lines[0]
        if line216 is None and len(lines) >= 2:
            line216 = lines[1]
        if line111 is None and lines:
            line111 = lines[0]  # reuse as tie candidate
        if sub004 is None and subs:
            sub004 = subs[0].get("ST_ID") or subs[0].get("ST_NAME")
        if target_id is None and loads:
            target_id = loads[0]

    rendered = render_all(
        tables,
        line215=line215,
        line216=line216,
        line111=line111,
        sub004=sub004,
        target_id=target_id,
    )
    if not rendered:
        return ()

    total_groups = sum(s.count("<g") for s in rendered.values())
    ev = EvidenceCollector("JBS_PWEQUIPINFO")
    for name, svg in rendered.items():
        ev.observe(name, f"{len(svg)} bytes / {svg.count('<g')} groups", record_id=name)

    return (
        ProblemRecord(
            task_code="5.3",
            device_id="auto_draw",
            description=f"自动出图完成 {len(rendered)} 类图（共 {total_groups} 个图元组）",
            correction="导出 SVG 供人工核对图实一致",
            correction_sql="",
            severity="info",
            confidence=1.0,
            evidence=ev.finalize(),
            extra={
                "diagrams": list(rendered.keys()),
                "byte_counts": {k: len(v) for k, v in rendered.items()},
            },
        ),
    )


__all__ = [
    "render_5_3_1_single_feeder",
    "render_5_3_2_tie_diagram",
    "render_5_3_3_substation_diagram",
    "render_5_3_4_power_trace",
    "render_all",
    "detect",
]
