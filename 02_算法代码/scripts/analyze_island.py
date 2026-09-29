# -*- coding: utf-8 -*-
"""分析 CIM SVG 孤岛设备：真实坐标(从 transform/polyline 提取)、GLink_Ref 图、孤岛周边物理接线。

用法:
    python -X utf8 scripts/analyze_island.py <svg路径> [--island TMPxxxx] [--radius 30]
"""
from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_NS = "{http://www.w3.org/2000/svg}"
NS2 = "{http://iec.ch/TC57/2005/SVG-schema#}"


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def extract_center(el) -> tuple[float, float] | None:
    """从图形元素提取中心坐标。"""
    tag = el.tag.replace(ROOT_NS, "")
    if tag == "use":
        x, y = el.get("x"), el.get("y")
        if x is not None and y is not None:
            return _f(x), _f(y)
        tr = el.get("transform", "")
        m = re.search(r"translate\(\s*([-\d.eE]+)\s*,\s*([-\d.eE]+)", tr)
        if m:
            return _f(m.group(1)), _f(m.group(2))
        return None
    if tag == "polyline":
        pts = [p.split(",") for p in el.get("points", "").split()]
        pts = [(_f(p[0]), _f(p[1])) for p in pts if len(p) >= 2]
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return None
    if tag == "polygon":
        pts = [p.split(",") for p in el.get("points", "").split()]
        pts = [(_f(p[0]), _f(p[1])) for p in pts if len(p) >= 2]
        if pts:
            return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        return None
    if tag == "rect":
        return _f(el.get("x")) + _f(el.get("width")) / 2, _f(el.get("y")) + _f(el.get("height")) / 2
    if tag == "circle":
        return _f(el.get("cx")), _f(el.get("cy"))
    return None


def polyline_endpoints(el) -> list[tuple[float, float]]:
    pts = [p.split(",") for p in el.get("points", "").split()]
    out = []
    for p in pts:
        if len(p) >= 2:
            try:
                out.append((_f(p[0]), _f(p[1])))
            except Exception:
                pass
    return out


def analyze(path: str, island_id: str | None = None, radius: float = 30.0):
    tree = ET.parse(path)
    root = tree.getroot()

    # ── 收集设备组 ──
    devs = {}       # ObjectID -> dict(layer, psr_type, name, center, group_id, refs)
    layers = {}     # layer name -> [ObjectID]
    for g in root.iter(ROOT_NS + "g"):
        gid = g.get("id", "")
        if not gid.startswith("TMP_"):
            continue
        psr = None
        refs = []
        layer = "?"
        for md in g.findall(ROOT_NS + "metadata"):
            for mc in md:
                t = mc.tag.replace(NS2, "")
                if t == "PSR_Ref":
                    psr = mc
                elif t == "GLink_Ref":
                    refs.append(mc.get("ObjectID", ""))
                elif t == "Layer_Ref":
                    layer = mc.get("ObjectName", "?")
        if psr is None:
            continue
        oid = psr.get("ObjectID", "")
        center = None
        shape = "?"
        for child in g:
            ct = child.tag.replace(ROOT_NS, "")
            c = extract_center(child)
            if c:
                center = c
                shape = ct
                break
        if not oid or oid in devs:
            continue
        devs[oid] = {
            "layer": layer,
            "psr_type": psr.get("PSRType", ""),
            "name": psr.get("ObjectName", ""),
            "center": center,
            "shape": shape,
            "group_id": gid,
            "refs": refs,
        }
        layers.setdefault(layer, []).append(oid)

    # ── 构图（与 SVGLoader 策略 C 一致：两端都是图形设备才计边）──
    deg = {oid: 0 for oid in devs}
    edges = set()
    for oid, d in devs.items():
        for r in d["refs"]:
            if r != oid and r in devs:
                if (oid, r) not in edges:
                    edges.add((oid, r))
                    deg[oid] += 1
                    deg[r] += 1

    islands = [o for o, d in devs.items() if deg[o] == 0]

    print(f"FILE = {path}")
    print(f"DEVICES(graphical) = {len(devs)}  EDGES = {len(edges)}  ISLANDS = {len(islands)}")
    print("LAYERS:")
    for ln, ids in sorted(layers.items()):
        print(f"  {ln}: {len(ids)}")
    print()

    # 类型分布
    types = {}
    for d in devs.values():
        key = f"{d['layer']}/{d['psr_type']}"
        types[key] = types.get(key, 0) + 1
    print("TYPE DISTRIBUTION (layer/psr_type):")
    for k, v in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print()

    target_islands = [island_id] if island_id else islands
    for iso in target_islands:
        d = devs.get(iso)
        if not d:
            print(f"ISLAND {iso}: NOT A GRAPHICAL DEVICE")
            continue
        cx, cy = d["center"] if d["center"] else (float("nan"), float("nan"))
        print(f"=== ISLAND {iso} ===")
        print(f"  layer={d['layer']} psr_type={d['psr_type']} name={d['name']} center=({cx:.1f},{cy:.1f}) shape={d['shape']}")
        print(f"  own refs: {d['refs']}  (existing: {[r for r in d['refs'] if r in devs]}, missing: {[r for r in d['refs'] if r not in devs]})")
        if not d["center"]:
            print("  !! no geometry")
            continue
        # 周边设备
        near = []
        for oid, dd in devs.items():
            if oid == iso or not dd["center"]:
                continue
            dx = dd["center"][0] - cx
            dy = dd["center"][1] - cy
            dist = math.hypot(dx, dy)
            if dist <= radius:
                near.append((dist, oid, dd))
        near.sort()
        print(f"  NEAR DEVICES (r<={radius}):")
        for dist, oid, dd in near[:15]:
            print(f"    {dist:7.2f}  {oid}  {dd['layer']}/{dd['psr_type']} deg={deg[oid]} name={dd['name']}")
        # 周边线段（点到折线最小距离）
        def seg_dist(px, py, ax, ay, bx, by):
            vx, vy = bx - ax, by - ay
            wx, wy = px - ax, py - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
            return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

        print(f"  WIRES near (min point-to-polyline dist <= 3.0):")
        wire_hits = []
        for oid, dd in devs.items():
            if dd["shape"] not in ("polyline", "polygon"):
                continue
            g = root.find(f".//{ROOT_NS}g[@id='{dd['group_id']}']")
            if g is None or len(list(g)) == 0:
                continue
            el = list(g)[0]
            tag = el.tag.replace(ROOT_NS, "")
            raw = el.get("points", "").split()
            pts = []
            for p in raw:
                parts = p.split(",")
                if len(parts) >= 2:
                    try:
                        pts.append((_f(parts[0]), _f(parts[1])))
                    except Exception:
                        pass
            if not pts:
                continue
            n = len(pts) + (1 if tag == "polygon" else 0)
            best = min(seg_dist(cx, cy, pts[i % len(pts)][0], pts[i % len(pts)][1],
                                pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1])
                       for i in range(n))
            if best <= 3.0:
                wire_hits.append((best, oid, dd, pts))
        wire_hits.sort()
        for best, oid, dd, pts in wire_hits[:12]:
            print(f"    {best:5.2f}  wire {oid} ({dd['psr_type']}) deg={deg[oid]} pts={[(round(a,1),round(b,1)) for a,b in pts[:4]]} refs={dd['refs']}")
        print()


if __name__ == "__main__":
    p = sys.argv[1]
    iso = None
    rad = 30.0
    if "--island" in sys.argv:
        iso = sys.argv[sys.argv.index("--island") + 1]
    if "--radius" in sys.argv:
        rad = float(sys.argv[sys.argv.index("--radius") + 1])
    analyze(p, iso, rad)
