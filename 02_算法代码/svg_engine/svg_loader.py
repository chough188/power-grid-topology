#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SVG 解析与拓扑提取工具

支持：
    1. 解析 SVG XML 结构，提取设备图元（开关、刀闸、配变、母线等）
    2. 提取 SVG 内嵌的连接关系（线路、端点连接）
    3. 将 SVG 拓扑转换为内部图模型
    4. 将内部图模型渲染为标准化 SVG
"""

from __future__ import annotations

import json
import math
import re
import random
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 颜色规范（国网图元配色参考） ────────────────────────────
VOLTAGE_COLORS = {
    500: "#FF0000",    # 500kV 红
    220: "#FF7F00",    # 220kV 橙
    110: "#FF6600",    # 110kV 深橙
    35:  "#FFA500",    # 35kV 黄
    20:  "#FFD700",    # 20kV 金
    10:  "#32CD32",    # 10kV 绿
    6:   "#00CED1",    # 6kV 青
    0.4: "#1E90FF",    # 0.4kV 蓝
}

EQUIP_TYPE_COLORS = {
    "SOURCE":       "#FF0000",
    "TRANSFORMER":  "#FF6600",
    "SWITCH":       "#32CD32",
    "BREAKER":      "#FF4500",
    "DISCONNECTOR": "#1E90FF",
    "FUSE":         "#FFD700",
    "LINE":         "#666666",
    "LOAD":         "#1E90FF",
    "CAPACITOR":    "#FF69B4",
    "GENERATOR":    "#00FF00",
    "BUS":          "#8B4513",
    "SUBSTATION":   "#FF0000",
}

EQUIP_TYPE_SHORT = {
    "SOURCE":       "电源",
    "TRANSFORMER":  "变压器",
    "SWITCH":       "开关",
    "BREAKER":      "断路器",
    "DISCONNECTOR": "刀闸",
    "FUSE":         "熔断器",
    "LINE":         "线路",
    "LOAD":         "负荷",
    "CAPACITOR":    "电容",
    "GENERATOR":    "发电机",
    "BUS":          "母线",
    "SUBSTATION":   "变电站",
}


@dataclass
class SVGDevice:
    """SVG 中的设备图元。"""
    equip_id: str
    name: str
    equip_type: str
    x: float = 0.0
    y: float = 0.0
    voltage_type: int = 10
    run_status: int = 1
    feeder_id: str = ""
    substation_id: str = ""
    attrs: Dict = field(default_factory=dict)

    def color(self) -> str:
        return EQUIP_TYPE_COLORS.get(self.equip_type,
                                     VOLTAGE_COLORS.get(self.voltage_type, "#333333"))


@dataclass
class SVGLink:
    """SVG 中的连接关系（边）。"""
    from_id: str
    to_id: str
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    attrs: Dict = field(default_factory=dict)


@dataclass
class SVGLinkNode:
    """内部拓扑节点（连通性节点）。"""
    node_id: str
    equip_ids: List[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0


class SVGLoader:
    """SVG 文件加载器、拓扑提取器与渲染器。"""

    def __init__(self, svg_path: Optional[str] = None):
        self.svg_path = Path(svg_path) if svg_path else None
        self.devices: List[SVGDevice] = []
        self.links: List[SVGLink] = []
        self.nodes: Dict[str, SVGLinkNode] = {}
        self.width: float = 1200
        self.height: float = 800
        self.title: str = ""
        self._tree: Optional[ET.ElementTree] = None
        self._root: Optional[ET.Element] = None

    # ── 解析 ─────────────────────────────────────────────────

    def parse(self, svg_path: Optional[str] = None) -> SVGLoader:
        path = Path(svg_path) if svg_path else self.svg_path
        if not path:
            raise ValueError("svg_path required")

        self._tree = ET.parse(path)
        self._root = self._tree.getroot()
        root = self._root

        # 尺寸
        self.width = float(root.get("width", "1200").replace("px", ""))
        self.height = float(root.get("height", "800").replace("px", ""))
        vb = root.get("viewBox")
        if vb:
            parts = vb.split()
            if len(parts) == 4:
                self.width = float(parts[2])
                self.height = float(parts[3])

        # 提取标题
        title_el = root.find(".//{http://www.w3.org/2000/svg}text")
        if title_el is None:
            title_el = root.find(".//text")
        if title_el is not None and title_el.text:
            self.title = title_el.text

        self._parse_devices(root)
        self._parse_links(root)
        self._build_topology_nodes()
        return self

    def _parse_devices(self, root: ET.Element):
        """解析 <g> 元素中的设备，支持多种属性格式。"""
        groups: List[ET.Element] = []

        # 策略 1: 带 class="device" 的 <g>
        for tag in ("{http://www.w3.org/2000/svg}g", "g"):
            groups.extend(root.findall(f".//{tag}[@class='device']"))

        # 策略 2: 任何带 data-equip-id 的 <g>
        if not groups:
            for tag in ("{http://www.w3.org/2000/svg}g", "g"):
                for g in root.iter(tag):
                    if g.get("data-equip-id"):
                        groups.append(g)

        # 策略 3: CIM IEC SVG — <g id="TMP_..."> with <metadata><PSR_Ref ObjectID="..." PSRType="..."/>
        if not groups:
            for tag in ("{http://www.w3.org/2000/svg}g", "g"):
                for g in root.iter(tag):
                    gid = g.get("id", "")
                    if not gid.startswith("TMP_"):
                        continue
                    # Check for metadata > PSR_Ref child
                    for md in g.iter():
                        mtag = md.tag.split("}")[-1] if "}" in md.tag else md.tag
                        if mtag == "metadata":
                            for mc in md:
                                mctag = mc.tag.split("}")[-1] if "}" in mc.tag else mc.tag
                                if mctag == "PSR_Ref":
                                    groups.append(g)
                                    break
                            break

        seen_ids = set()
        for g in groups:
            # 优先 data-equip-id，回退到 CIM IEC PSR_Ref.ObjectID
            equip_id = g.get("data-equip-id", "")
            if not equip_id:
                for md in g.iter():
                    mtag = md.tag.split("}")[-1] if "}" in md.tag else md.tag
                    if mtag == "metadata":
                        for mc in md:
                            mctag = mc.tag.split("}")[-1] if "}" in mc.tag else mc.tag
                            if mctag == "PSR_Ref":
                                equip_id = mc.get("ObjectID", "")
                                break
                        if equip_id:
                            break
            if not equip_id or equip_id in seen_ids:
                continue
            seen_ids.add(equip_id)

            # 优先 data-equip-type，回退到 CIM IEC PSR_Ref.PSRType
            equip_type = g.get("data-equip-type", "")
            if not equip_type:
                for md in g.iter():
                    mtag = md.tag.split("}")[-1] if "}" in md.tag else md.tag
                    if mtag == "metadata":
                        for mc in md:
                            mctag = mc.tag.split("}")[-1] if "}" in mc.tag else mc.tag
                            if mctag == "PSR_Ref":
                                equip_type = mc.get("PSRType", "UNKNOWN")
                                break
                        if equip_type:
                            break
            if not equip_type:
                equip_type = "UNKNOWN"

            voltage_type = 10
            vt_str = g.get("data-voltage", "")
            if vt_str:
                try:
                    voltage_type = int(float(vt_str))
                except ValueError:
                    pass

            name = equip_id
            cx, cy = 0.0, 0.0

            for child in g:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "circle":
                    cx = float(child.get("cx", "0"))
                    cy = float(child.get("cy", "0"))
                elif tag == "rect":
                    x = float(child.get("x", "0"))
                    y = float(child.get("y", "0"))
                    w = float(child.get("width", "0"))
                    h = float(child.get("height", "0"))
                    cx, cy = x + w / 2, y + h / 2
                elif tag == "text":
                    txt = (child.text or "").strip()
                    if txt and txt.upper() in EQUIP_TYPE_COLORS and equip_type == "UNKNOWN":
                        equip_type = txt.upper()
                    elif txt and len(txt) < 30:
                        name = txt
                elif tag == "polygon":
                    pts = (child.get("points") or "").split()
                    xs = [float(p.split(",")[0]) for p in pts if "," in p]
                    ys = [float(p.split(",")[1]) for p in pts if "," in p]
                    if xs and ys:
                        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                elif tag == "polyline":
                    pts = (child.get("points") or "").split()
                    xs = [float(p.split(",")[0]) for p in pts if "," in p]
                    ys = [float(p.split(",")[1]) for p in pts if "," in p]
                    if xs and ys:
                        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                elif tag == "path":
                    m = re.search(r"[Mm]\s*([\d.\-eE]+)[,\s]+([\d.\-eE]+)", child.get("d", "") or "")
                    if m:
                        cx, cy = float(m.group(1)), float(m.group(2))

            self.devices.append(SVGDevice(
                equip_id=equip_id,
                name=name,
                equip_type=equip_type,
                x=cx, y=cy,
                voltage_type=voltage_type,
            ))

    def _parse_links(self, root: ET.Element):
        """解析 <line> 元素为连接关系，支持 data-from/data-to 和坐标匹配。"""
        lines: List[ET.Element] = []
        for tag in ("{http://www.w3.org/2000/svg}line", "line"):
            lines.extend(root.findall(f".//{tag}"))

        # 策略 A: data-from / data-to 属性（比赛 SVG 格式）
        for ln in lines:
            from_id = ln.get("data-from", "")
            to_id = ln.get("data-to", "")
            if from_id and to_id and from_id != to_id:
                x1 = float(ln.get("x1", "0"))
                y1 = float(ln.get("y1", "0"))
                x2 = float(ln.get("x2", "0"))
                y2 = float(ln.get("y2", "0"))
                self.links.append(SVGLink(
                    from_id=from_id, to_id=to_id,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))

        # 如果没有 data-from，策略 B: 坐标容差匹配
        if not self.links:
            pos_map: Dict[Tuple[int, int], str] = {}
            TOLERANCE = 5
            for d in self.devices:
                for dx in range(-TOLERANCE, TOLERANCE + 1):
                    for dy in range(-TOLERANCE, TOLERANCE + 1):
                        pos_map[(int(d.x) + dx, int(d.y) + dy)] = d.equip_id

            for ln in lines:
                x1 = float(ln.get("x1", "0"))
                y1 = float(ln.get("y1", "0"))
                x2 = float(ln.get("x2", "0"))
                y2 = float(ln.get("y2", "0"))

                from_id = pos_map.get((int(x1), int(y1)), "")
                to_id = pos_map.get((int(x2), int(y2)), "")

                if from_id and to_id and from_id != to_id:
                    self.links.append(SVGLink(
                        from_id=from_id, to_id=to_id,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                    ))

        # 策略 C: CIM IEC SVG — GLink_Ref inside device metadata provides connections
        if not self.links:
            dev_map = {d.equip_id: d for d in self.devices}
            for tag in ("{http://www.w3.org/2000/svg}g", "g"):
                for g in root.iter(tag):
                    gid = g.get("id", "")
                    if not gid.startswith("TMP_"):
                        continue
                    src_id = None
                    glinks = []
                    for md in g.iter():
                        mtag = md.tag.split("}")[-1] if "}" in md.tag else md.tag
                        if mtag == "metadata":
                            for mc in md:
                                mctag = mc.tag.split("}")[-1] if "}" in mc.tag else mc.tag
                                if mctag == "PSR_Ref":
                                    src_id = mc.get("ObjectID", "")
                                elif mctag == "GLink_Ref":
                                    glinks.append(mc.get("ObjectID", ""))
                    if src_id and glinks:
                        for tgt_id in glinks:
                            if tgt_id != src_id and tgt_id in dev_map:
                                sd = dev_map[src_id]
                                td = dev_map[tgt_id]
                                self.links.append(SVGLink(
                                    from_id=src_id, to_id=tgt_id,
                                    x1=sd.x, y1=sd.y, x2=td.x, y2=td.y,
                                ))

    def _build_topology_nodes(self):
        """基于连接关系构建连通性节点。"""
        pos_groups: Dict[Tuple[int, int], List[str]] = {}
        TOL = 8
        for d in self.devices:
            key = (round(d.x / TOL) * TOL, round(d.y / TOL) * TOL)
            pos_groups.setdefault(key, []).append(d.equip_id)

        self.nodes.clear()
        for idx, (pos, eqs) in enumerate(pos_groups.items()):
            nid = f"CN_{idx}"
            self.nodes[nid] = SVGLinkNode(
                node_id=nid, equip_ids=eqs,
                x=pos[0], y=pos[1],
            )

    # ── 图模型转换 ──────────────────────────────────────────

    def to_graph(self) -> Dict:
        nodes = {}
        edges = []
        for d in self.devices:
            nodes[d.equip_id] = {
                "name": d.name, "type": d.equip_type,
                "x": d.x, "y": d.y, "voltage": d.voltage_type,
            }
        for link in self.links:
            edges.append((link.from_id, link.to_id, {
                "x1": link.x1, "y1": link.y1,
                "x2": link.x2, "y2": link.y2,
            }))
        return {"nodes": nodes, "edges": edges}

    def from_graph(self, graph: Dict) -> SVGLoader:
        self.devices.clear()
        self.links.clear()
        for node_id, data in graph.get("nodes", {}).items():
            self.devices.append(SVGDevice(
                equip_id=node_id,
                name=data.get("name", node_id),
                equip_type=data.get("type", "UNKNOWN"),
                x=data.get("x", 0), y=data.get("y", 0),
                voltage_type=data.get("voltage", 10),
            ))
        for u, v, data in graph.get("edges", []):
            self.links.append(SVGLink(
                from_id=u, to_id=v,
                x1=data.get("x1", 0), y1=data.get("y1", 0),
                x2=data.get("x2", 0), y2=data.get("y2", 0),
            ))
        return self

    # ── 渲染 ─────────────────────────────────────────────────

    def render(self, output_path: str, layout_strategy: str = "tree"):
        if layout_strategy == "tree":
            self._tree_layout()
        elif layout_strategy == "force":
            self._force_layout()

        svg_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(self.width)}" height="{int(self.height)}" '
            f'viewBox="0 0 {int(self.width)} {int(self.height)}">',
            '  <rect width="100%" height="100%" fill="#FAFAFA"/>',
        ]

        if self.title:
            svg_parts.append(
                f'  <text x="20" y="30" font-size="16" font-weight="bold" fill="#333">{self.title}</text>'
            )

        for link in self.links:
            svg_parts.append(
                f'  <line x1="{link.x1:.1f}" y1="{link.y1:.1f}" x2="{link.x2:.1f}" y2="{link.y2:.1f}" '
                f'stroke="#555" stroke-width="1.5"/>'
            )

        for dev in self.devices:
            color = dev.color()
            if dev.equip_type in ("SOURCE", "SUBSTATION", "TRANSFORMER"):
                shape = (
                    f'    <circle cx="{dev.x:.1f}" cy="{dev.y:.1f}" r="12" fill="{color}" stroke="#333" stroke-width="1.5"/>'
                )
            elif dev.equip_type in ("SWITCH", "BREAKER", "DISCONNECTOR", "FUSE"):
                shape = (
                    f'    <rect x="{dev.x - 10:.1f}" y="{dev.y - 6:.1f}" width="20" height="12" '
                    f'fill="{color}" stroke="#333" stroke-width="1.5"/>'
                )
            elif dev.equip_type == "BUS":
                shape = (
                    f'    <rect x="{dev.x - 8:.1f}" y="{dev.y - 4:.1f}" width="16" height="8" '
                    f'fill="{color}" stroke="#333" stroke-width="1.5"/>'
                )
            else:
                shape = (
                    f'    <circle cx="{dev.x:.1f}" cy="{dev.y:.1f}" r="8" fill="{color}" stroke="#333" stroke-width="1"/>'
                )

            short = EQUIP_TYPE_SHORT.get(dev.equip_type, dev.equip_type)
            svg_parts.append(f'  <g class="device" data-equip-id="{dev.equip_id}" data-equip-type="{dev.equip_type}">')
            svg_parts.append(shape)
            svg_parts.append(
                f'    <text x="{dev.x:.1f}" y="{dev.y + 22:.1f}" text-anchor="middle" '
                f'font-size="11" fill="#333">{dev.name}</text>'
            )
            svg_parts.append(
                f'    <text x="{dev.x:.1f}" y="{dev.y - 16:.1f}" text-anchor="middle" '
                f'font-size="9" fill="#666">{short}</text>'
            )
            svg_parts.append('  </g>')

        svg_parts.append('</svg>')

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(svg_parts), encoding="utf-8")
        return output_path

    def _tree_layout(self):
        """树形布局：从左到右，电源在左。"""
        degree: Dict[str, int] = {}
        adj: Dict[str, List[str]] = {d.equip_id: [] for d in self.devices}
        for link in self.links:
            adj[link.from_id].append(link.to_id)
            adj[link.to_id].append(link.from_id)
            degree[link.from_id] = degree.get(link.from_id, 0) + 1
            degree[link.to_id] = degree.get(link.to_id, 0) + 1

        root = None
        for d in self.devices:
            if d.equip_type in ("SOURCE", "SUBSTATION", "GENERATOR"):
                root = d.equip_id
                break
        if not root:
            for d in self.devices:
                if degree.get(d.equip_id, 0) <= 1:
                    root = d.equip_id
                    break
        if not root and self.devices:
            root = self.devices[0].equip_id

        visited = {root}
        queue = deque([(root, 0)])
        levels: Dict[int, List[str]] = {}

        while queue:
            node, lvl = queue.popleft()
            levels.setdefault(lvl, []).append(node)
            for nb in adj.get(node, []):
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, lvl + 1))

        max_lvl = max(levels.keys()) if levels else 0
        for d in self.devices:
            if d.equip_id not in visited:
                levels.setdefault(max_lvl + 1, []).append(d.equip_id)

        PADDING_X, PADDING_Y = 80, 100
        NODE_DX, NODE_DY = 140, 70

        pos: Dict[str, Tuple[float, float]] = {}
        for lvl, nodes in levels.items():
            n = len(nodes)
            total_height = (n - 1) * NODE_DY
            start_y = PADDING_Y + max(0, (self.height - 2 * PADDING_Y - total_height) / 2)
            x = PADDING_X + lvl * NODE_DX
            for i, nid in enumerate(nodes):
                y = start_y + i * NODE_DY
                pos[nid] = (x, y)

        min_y = min((p[1] for p in pos.values()), default=0)
        if min_y < 50:
            offset = 50 - min_y
            for nid in pos:
                px, py = pos[nid]
                pos[nid] = (px, py + offset)

        for d in self.devices:
            if d.equip_id in pos:
                d.x, d.y = pos[d.equip_id]

        for link in self.links:
            if link.from_id in pos:
                link.x1, link.y1 = pos[link.from_id]
            if link.to_id in pos:
                link.x2, link.y2 = pos[link.to_id]

        max_x = max((p[0] for p in pos.values()), default=PADDING_X) + PADDING_X
        max_y = max((p[1] for p in pos.values()), default=PADDING_Y) + PADDING_Y
        self.width = max(self.width, max_x)
        self.height = max(self.height, max_y)

    def _force_layout(self, iterations: int = 100):
        for d in self.devices:
            if d.x == 0 and d.y == 0:
                d.x = random.uniform(100, self.width - 100)
                d.y = random.uniform(100, self.height - 100)

        for _ in range(iterations):
            forces: Dict[str, List[float]] = {d.equip_id: [0.0, 0.0] for d in self.devices}

            for i, d1 in enumerate(self.devices):
                for d2 in self.devices[i + 1:]:
                    dx = d1.x - d2.x
                    dy = d1.y - d2.y
                    dist = math.hypot(dx, dy) or 0.001
                    if dist < 200:
                        f = 5000 / (dist * dist)
                        fx, fy = f * dx / dist, f * dy / dist
                        forces[d1.equip_id][0] += fx
                        forces[d1.equip_id][1] += fy
                        forces[d2.equip_id][0] -= fx
                        forces[d2.equip_id][1] -= fy

            for link in self.links:
                d1 = self._dev_by_id(link.from_id)
                d2 = self._dev_by_id(link.to_id)
                if not d1 or not d2:
                    continue
                dx = d2.x - d1.x
                dy = d2.y - d1.y
                dist = math.hypot(dx, dy) or 0.001
                f = dist / 50
                fx, fy = f * dx / dist, f * dy / dist
                forces[d1.equip_id][0] += fx
                forces[d1.equip_id][1] += fy
                forces[d2.equip_id][0] -= fx
                forces[d2.equip_id][1] -= fy

            for d in self.devices:
                d.x += forces[d.equip_id][0] * 0.05
                d.y += forces[d.equip_id][1] * 0.05
                d.x = max(40, min(self.width - 40, d.x))
                d.y = max(40, min(self.height - 40, d.y))

        for link in self.links:
            d1 = self._dev_by_id(link.from_id)
            d2 = self._dev_by_id(link.to_id)
            if d1 and d2:
                link.x1, link.y1 = d1.x, d1.y
                link.x2, link.y2 = d2.x, d2.y

    def _dev_by_id(self, equip_id: str) -> Optional[SVGDevice]:
        for d in self.devices:
            if d.equip_id == equip_id:
                return d
        return None

    def add_device(self, dev: SVGDevice, connect_to: List[str]) -> SVGLoader:
        self.devices.append(dev)
        for target_id in connect_to:
            self.links.append(SVGLink(
                from_id=dev.equip_id, to_id=target_id,
                x1=dev.x, y1=dev.y,
            ))
        return self

    def remove_device(self, equip_id: str, connect_neighbors: bool = False) -> SVGLoader:
        self.devices = [d for d in self.devices if d.equip_id != equip_id]

        related = [ln for ln in self.links if ln.from_id == equip_id or ln.to_id == equip_id]
        neighbors = []
        for ln in related:
            nid = ln.to_id if ln.from_id == equip_id else ln.from_id
            if nid != equip_id:
                neighbors.append(nid)

        self.links = [ln for ln in self.links
                      if ln.from_id != equip_id and ln.to_id != equip_id]

        if connect_neighbors and len(neighbors) >= 2:
            for i in range(len(neighbors) - 1):
                self.links.append(SVGLink(
                    from_id=neighbors[i], to_id=neighbors[i + 1],
                ))
        return self

    def save(self, output_path: str) -> str:
        return self.render(output_path, layout_strategy="tree")

    @classmethod
    def load(cls, svg_path: str) -> SVGLoader:
        return cls(svg_path).parse()


# ── 从 JSON Snapshot 构建图 ───────────────────────────────

def build_graph_from_json(snapshot: Dict) -> Dict:
    tables = snapshot.get("tables", snapshot)
    equip_table = tables.get("JBS_PWEQUIPINFO", [])
    terminal_table = tables.get("JBS_PWTERMINAL", [])
    room_table = tables.get("JBS_PWROOM", [])
    feeder_table = tables.get("JBS_PWFEEDERLINE", [])

    nodes = {}
    for eq in equip_table:
        eid = eq.get("EQUIP_ID", "")
        nodes[eid] = {
            "name": eq.get("EQUIP_NAME", eid),
            "type": eq.get("EQUIP_TYPE", "UNKNOWN"),
            "voltage": eq.get("VOLTAGE_TYPE", 10),
            "feeder": eq.get("FEEDER_ID", ""),
            "substation": eq.get("DSUBSTATION_ID", ""),
            "run_status": eq.get("RUN_STATUS", 1),
        }

    cn_to_equips: Dict[str, List[str]] = {}
    for t in terminal_table:
        eid = t.get("EQUIP_ID", "")
        cn = t.get("CONNECTIVITYNODE_ID", "")
        if eid and cn:
            cn_to_equips.setdefault(cn, []).append(eid)

    edges = []
    seen = set()
    for cn, eqs in cn_to_equips.items():
        for i in range(len(eqs)):
            for j in range(i + 1, len(eqs)):
                a, b = eqs[i], eqs[j]
                if (a, b) not in seen and (b, a) not in seen:
                    seen.add((a, b))
                    edges.append((a, b, {"connectivity_node": cn}))

    return {"nodes": nodes, "edges": edges, "feeders": feeder_table, "rooms": room_table}


def load_snapshot(path: str) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
