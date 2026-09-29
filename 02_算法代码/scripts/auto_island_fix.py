# -*- coding: utf-8 -*-
"""CIM 配网 SVG 孤岛自动修复驱动（仅新增 GLink_Ref 连接引用，不改动其他任何字节）。

损坏模型（已验证）:
  孤岛设备 = 其 GLink_Ref 列表被整体替换为指向不存在 ID 的悬空引用
  （数值邻接的伪 ID，或被删共享节点的真实 ID）。
  文件内所有现存边均为完全对称引用（A ref B <=> B ref A）。

修复策略（按优先级）:
  P1 健康共引用者: 岛 I 的悬空引用 d 若同时被健康设备 S 引用（S 在 d 的另一侧），
     连 I-S（恢复被删节点两侧的原有电气连接）。取几何最近者。
  P2 共岛配对: 岛 I 与岛 J 共享同一悬空引用 d（原经 d 直连），连 I-J。取最近者。
  P3 几何回退: 岛 I 无任何共引用证据时，连到几何最近的、类型兼容的健康设备
     （馈线段/接头/连线/母线/开关 互补规则；站房类设备不作目标）。
  安全保证: 每个岛只加一条新边且岛原度数=0 => 不可能产生环（辐射网保持）。
  验证: 修改后立即重新解析，要求 非豁免孤岛=0、dup=0、unref=0、dangling 不增加。

用法:
  python -X utf8 scripts/auto_island_fix.py <svg文件或目录...> [--dry-run]
      [--log output/svg_fix_log.jsonl] [--radius 25]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_NS = "{http://www.w3.org/2000/svg}"
NS2 = "{http://iec.ch/TC57/2005/SVG-schema#}"
SVG_TAG = ROOT_NS + "svg"
G_TAG = ROOT_NS + "g"
META_TAG = ROOT_NS + "metadata"

# 与 llm_svg_tools.STATION_BUILDING_TYPES 完全一致（孤岛判定豁免）
STATION_BUILDING_TYPES = {
    "zf01", "zf04", "zf06", "zf07", "zf08", "zf09", "0323", "0324",
    "ZF01", "ZF04", "ZF06", "ZF07", "ZF08", "ZF09",
    "substation", "STATION", "BUILDING", "ROOM",
    "zf", "ZF", "站房", "配电房", "环网柜", "箱变",
}
SWITCH_TYPES = {"0301", "0305", "0306", "0307"}  # 与 llm_svg_tools 的 dangling 判定对齐

# 层名 -> 岛设备可连接的目标层（按偏好顺序）
TARGET_LAYER_PREF = {
    "Junction_Layer": ["ConnLine_Layer", "ACLineSegment_Layer", "Junction_Layer",
                       "BusbarSection_Layer", "CompositeSwitch_Layer", "Disconnector_Layer",
                       "Breaker_Layer"],
    "ACLineSegment_Layer": ["ACLineSegment_Layer", "Junction_Layer", "ConnLine_Layer",
                            "BusbarSection_Layer"],
    "ConnLine_Layer": ["Junction_Layer", "ACLineSegment_Layer", "ConnLine_Layer",
                       "BusbarSection_Layer"],
    "PowerTransformer_Layer": ["ConnLine_Layer", "ACLineSegment_Layer", "Junction_Layer",
                               "BusbarSection_Layer"],
    "CompositeSwitch_Layer": ["ConnLine_Layer", "Junction_Layer", "BusbarSection_Layer",
                              "ACLineSegment_Layer"],
    "Disconnector_Layer": ["ConnLine_Layer", "Junction_Layer", "BusbarSection_Layer",
                           "ACLineSegment_Layer"],
    "Breaker_Layer": ["ConnLine_Layer", "Junction_Layer", "BusbarSection_Layer",
                      "ACLineSegment_Layer"],
}
DEFAULT_PREF = ["Junction_Layer", "ConnLine_Layer", "ACLineSegment_Layer",
                "BusbarSection_Layer"]
NEVER_TARGET_LAYERS = {"Substation_Layer"}  # 站房不作为连接目标


def _num(oid: str) -> int | None:
    m = re.search(r"(\d+)$", oid)
    return int(m.group(1)) if m else None


def _center_of(el) -> tuple[float, float] | None:
    """从图形元素提取中心点（use 的 x/y 或 translate；polyline/polygon bbox 中点；
    rect/circle/ellipse 中心）。"""
    tag = el.tag.replace(ROOT_NS, "")
    if tag == "use":
        try:
            return (float(el.get("x") or 0), float(el.get("y") or 0))
        except ValueError:
            pass
        t = el.get("transform") or ""
        m = re.search(r"translate\(\s*([-\d.]+)[ ,]+([-\d.]+)", t)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        return None
    if tag in ("polyline", "polygon"):
        pts = []
        for pair in re.findall(r"([-\d.eE]+)[ ,]+([-\d.eE]+)", el.get("points") or ""):
            try:
                pts.append((float(pair[0]), float(pair[1])))
            except ValueError:
                pass
        if pts:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        return None
    if tag == "rect":
        try:
            return (float(el.get("x")) + float(el.get("width")) / 2,
                    float(el.get("y")) + float(el.get("height")) / 2)
        except (TypeError, ValueError):
            return None
    if tag in ("circle", "ellipse"):
        try:
            return (float(el.get("cx")), float(el.get("cy")))
        except (TypeError, ValueError):
            return None
    return None


class Device:
    __slots__ = ("oid", "gid", "layer", "psr", "name", "refs", "center")

    def __init__(self):
        self.oid = ""; self.gid = ""; self.layer = "?"; self.psr = ""
        self.name = ""; self.refs: list[str] = []; self.center = None


def parse_model(text: str) -> dict[str, Device]:
    root = ET.fromstring(text)
    devs: dict[str, Device] = {}
    for g in root.iter(G_TAG):
        gid = g.get("id", "")
        if not gid.startswith("TMP_"):
            continue
        d = Device()
        d.gid = gid
        center = None
        for child in g:
            if center is None:
                c = _center_of(child)
                if c:
                    center = c
        for md in g.findall(META_TAG):
            for mc in md:
                t = mc.tag.replace(NS2, "")
                if t == "PSR_Ref":
                    d.oid = mc.get("ObjectID", "")
                    d.psr = mc.get("PSRType", "")
                    d.name = mc.get("ObjectName", "")
                elif t == "GLink_Ref":
                    r = mc.get("ObjectID", "")
                    if r:
                        d.refs.append(r)
                elif t == "Layer_Ref":
                    d.layer = mc.get("ObjectName", "?")
        if d.oid and d.oid not in devs:
            d.center = center
            devs[d.oid] = d
    return devs


def compute_degrees(devs: dict[str, Device]) -> dict[str, int]:
    deg = {o: 0 for o in devs}
    for o, d in devs.items():
        for r in d.refs:
            if r != o and r in devs:
                deg[o] += 1
                deg[r] += 1
    return deg


def find_islands(devs: dict[str, Device], deg: dict[str, int]) -> list[str]:
    return [o for o, d in devs.items()
            if deg[o] == 0 and d.psr not in STATION_BUILDING_TYPES]


def dist(a: Device, b: Device) -> float | None:
    if a.center and b.center:
        return math.hypot(a.center[0] - b.center[0], a.center[1] - b.center[1])
    return None


def pick_target(island: Device, candidates: list[str], devs: dict[str, Device],
                pref_layers: list[str]) -> str | None:
    """按 (偏好层序, 几何距离, ID 邻接) 选目标。"""
    if not candidates:
        return None
    scored = []
    for i, oid in enumerate(candidates):
        t = devs[oid]
        try:
            tier = pref_layers.index(t.layer)
        except ValueError:
            tier = len(pref_layers)  # 非偏好层排最后
        dd = dist(island, t)
        idn = _num(oid); imn = _num(island.oid)
        id_delta = abs(idn - imn) if (idn is not None and imn is not None) else 10**9
        scored.append((tier, dd if dd is not None else 10**9, id_delta, i, oid))
    scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    best = scored[0]
    # 若最佳候选无几何证据且 ID 差巨大，仍接受（辐射网中任何同层连接都优于孤岛），
    # 但记录距离供审计。
    return best[4]


def plan_edges(devs: dict[str, Device], deg: dict[str, int], islands: list[str]):
    """返回 (edges, decisions)。edges: set[frozenset({a,b})]; decisions: 每岛说明。"""
    islands = list(islands)
    island_set = set(islands)
    dangling_of = {i: [r for r in devs[i].refs if r not in devs] for i in islands}
    # 悬空节点 -> 引用它的设备集合
    referrers: dict[str, list[str]] = {}
    for o, d in devs.items():
        for r in d.refs:
            if r not in devs:
                referrers.setdefault(r, []).append(o)

    edges: set[frozenset] = set()
    decisions: dict[str, dict] = {}
    pending = set(islands)

    # P1: 健康共引用者
    for i in sorted(pending):
        cands = []
        for dn in dangling_of[i]:
            for s in referrers.get(dn, []):
                if s != i and s not in island_set and s not in cands \
                        and devs[s].layer not in NEVER_TARGET_LAYERS:
                    cands.append(s)
        if cands:
            pref = TARGET_LAYER_PREF.get(devs[i].layer, DEFAULT_PREF)
            t = pick_target(devs[i], cands, devs, pref)
            if t:
                edges.add(frozenset((i, t)))
                pending.discard(i)
                decisions[i] = {"priority": "P1_co_referrer", "target": t,
                                "dangling_nodes": dangling_of[i]}
    # P2: 共岛配对（共享悬空节点）
    for i in sorted(pending):
        cands = []
        for dn in dangling_of[i]:
            for j in referrers.get(dn, []):
                if j != i and j in island_set and j not in cands:
                    cands.append(j)
        if cands:
            pref = TARGET_LAYER_PREF.get(devs[i].layer, DEFAULT_PREF)
            t = pick_target(devs[i], cands, devs, pref)
            if t:
                edges.add(frozenset((i, t)))
                pending.discard(i)
                decisions[i] = {"priority": "P2_co_island", "target": t,
                                "dangling_nodes": dangling_of[i]}
    # P3: 几何最近兼容健康设备
    healthy = [o for o in devs if o not in island_set and deg[o] > 0
               and devs[o].layer not in NEVER_TARGET_LAYERS]
    for i in sorted(pending):
        pref = TARGET_LAYER_PREF.get(devs[i].layer, DEFAULT_PREF)
        t = pick_target(devs[i], healthy, devs, pref)
        if t:
            edges.add(frozenset((i, t)))
            pending.discard(i)
            dd = dist(devs[i], devs[t])
            decisions[i] = {"priority": "P3_geometry", "target": t,
                            "distance": round(dd, 2) if dd is not None else None,
                            "target_layer": devs[t].layer}
        else:
            decisions[i] = {"priority": "SKIP", "target": None,
                            "reason": "no compatible healthy device"}
    return edges, decisions


def _locate_metadata(lines: list[str], group_start: int, window: int = 80) -> tuple[int, int] | None:
    """在 group 起始行后 window 行内定位 <ns0:metadata> ... </ns0:metadata>。"""
    meta_start = None
    for j in range(group_start, min(len(lines), group_start + window)):
        if "<ns0:metadata>" in lines[j]:
            meta_start = j
            break
    if meta_start is None:
        return None
    for j in range(meta_start, min(len(lines), meta_start + window)):
        if lines[j].strip() == "</ns0:metadata>":
            return (meta_start, j)
    return None


def apply_edges(text: str, edges: set[frozenset], devs: dict[str, Device]) -> tuple[str, list[dict]]:
    """字符串手术：在每个端点设备的 metadata 中新增 <ns2:GLink_Ref ObjectID=.../>。
    只增行，不改其他字节。返回 (new_text, applied)。"""
    lines = text.split("\n")
    # 只需定位边端点设备的 metadata 块
    endpoint_gids = {devs[o].gid for e in edges for o in e if o in devs}
    spans: dict[str, tuple[int, int]] = {}
    for oid, d in devs.items():
        if d.gid not in endpoint_gids:
            continue
        pat = re.compile(r'<ns\d+:g id="%s"[ >]' % re.escape(d.gid))
        found = False
        # 逐行扫描匹配（gid 理论上唯一；若重复则要求 metadata 内含该 ObjectID）
        for idx, ln in enumerate(lines):
            if not pat.search(ln):
                continue
            sp = _locate_metadata(lines, idx)
            if sp is None:
                continue
            ms, me = sp
            seg_text = "\n".join(lines[ms:me + 1])
            if ('ObjectID="%s"' % oid) in seg_text:
                spans[oid] = sp
                found = True
                break
        if not found:
            raise RuntimeError("cannot locate metadata block for %s (gid=%s)" % (oid, d.gid))
    insertions: list[tuple[int, str, str, str]] = []  # (line_idx, indent, other_oid, edge_key)
    missing: list[str] = []
    for e in sorted(edges, key=lambda f: sorted(f)):
        a, b = sorted(e)
        for oid, other in ((a, b), (b, a)):
            sp = spans.get(oid)
            if sp is None:
                missing.append(oid)
                continue
            ms, me = sp
            seg = lines[ms:me + 1]
            if any(('ObjectID="%s"' % other) in s for s in seg):
                continue  # 该端已存在引用
            anchor = None
            for j in range(me - ms, -1, -1):
                if "<ns2:GLink_Ref" in seg[j]:
                    anchor = ms + j
                    break
            if anchor is None:
                for j in range(ms, me + 1):
                    if "<ns2:Layer_Ref" in lines[j]:
                        anchor = j
                        break
            if anchor is None:
                anchor = me  # 插在 </ns0:metadata> 前
            indent = re.match(r'^(\s*)', lines[anchor]).group(1)
            insertions.append((anchor + 1, indent, other, "%s->%s" % (a, b)))
    if missing:
        raise RuntimeError("metadata block not found for: %s" % ",".join(sorted(set(missing))))
    # 自底向上插入，保持行号有效；同一行多个插入时按 edge_key 稳定排序
    insertions.sort(key=lambda x: (x[0], x[3]), reverse=True)
    for pos, indent, other, _key in insertions:
        lines.insert(pos, '%s<ns2:GLink_Ref ObjectID="%s"/>' % (indent, other))
    applied = [{"src": sorted(e)[0], "dst": sorted(e)[1], "type": "GLink_Ref_symmetric"}
               for e in sorted(edges, key=lambda f: sorted(f))]
    return "\n".join(lines), applied


def verify(text_before: str, text_after: str) -> dict:
    """修改前后对比：孤岛/dup/unref/dangling。"""
    def stats(text):
        devs = parse_model(text)
        deg = compute_degrees(devs)
        islands = find_islands(devs, deg)
        dangling = [o for o, d in devs.items() if d.psr in SWITCH_TYPES and deg[o] < 2]
        dup = len(devs) - len({d.oid for d in devs.values()})
        return devs, deg, islands, dangling, dup

    devs_b, deg_b, isl_b, dang_b, dup_b = stats(text_before)
    devs_a, deg_a, isl_a, dang_a, dup_a = stats(text_after)
    # unref: strategy C 下不可能出现（边要求两端都存在）
    return {
        "islands_before": len(isl_b), "islands_after": len(isl_a),
        "islands_left": isl_a,
        "dangling_before": len(dang_b), "dangling_after": len(dang_a),
        "dup_before": dup_b, "dup_after": dup_a,
        "devices_before": len(devs_b), "devices_after": len(devs_a),
    }


def process_file(path: Path, dry_run: bool, log_path: Path | None, radius_note: int) -> dict:
    t0 = time.time()
    rec = {"file": path.name, "status": "ERROR", "applied": []}
    try:
        text = path.read_text(encoding="utf-8")
        devs = parse_model(text)
        deg = compute_degrees(devs)
        islands = find_islands(devs, deg)
        rec["islands_before"] = len(islands)
        rec["cand_count"] = sum(1 for o, d in devs.items()
                                if deg[o] > 0 and d.layer not in NEVER_TARGET_LAYERS)
        if not islands:
            rec["status"] = "OK_NO_ISLANDS"
            rec["elapsed_sec"] = round(time.time() - t0, 3)
            return rec
        edges, decisions = plan_edges(devs, deg, islands)
        rec["decisions"] = {i: decisions[i] for i in islands}
        if not edges:
            rec["status"] = "SKIPPED"
            rec["elapsed_sec"] = round(time.time() - t0, 3)
            return rec
        new_text, applied = apply_edges(text, edges, devs)
        v = verify(text, new_text)
        rec.update(v)
        ok = (v["islands_after"] == 0 and v["dup_after"] == 0
              and v["dangling_after"] <= v["dangling_before"]
              and v["devices_after"] == v["devices_before"])
        # XML 可解析性
        ET.fromstring(new_text)
        if not ok:
            rec["status"] = "VERIFY_FAIL"
            return rec
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")
        rec["applied"] = applied
        rec["status"] = "FIXED_DRYRUN" if dry_run else "FIXED"
    except Exception as e:  # noqa: BLE001
        rec["status"] = "ERROR"
        rec["error"] = repr(e)
    finally:
        rec["elapsed_sec"] = round(time.time() - t0, 3)
        if log_path is not None:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--log", default="", help="JSONL 日志路径（默认不写）")
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        pp = Path(p)
        if pp.is_dir():
            files.extend(sorted(pp.glob("*.svg")))
        elif pp.is_file():
            files.append(pp)
    log_path = Path(args.log) if args.log else None
    results = []
    for f in files:
        r = process_file(f, args.dry_run, log_path, 25)
        results.append(r)
        print("%s status=%s islands %s->%s applied=%d" % (
            f.name, r["status"], r.get("islands_before", "?"),
            r.get("islands_after", "-"), len(r.get("applied", []))))
        if args.verbose and r.get("decisions"):
            for i, dec in sorted(r["decisions"].items()):
                print("    %s -> %s" % (i, json.dumps(dec, ensure_ascii=False)))
    from collections import Counter
    c = Counter(r["status"] for r in results)
    print("SUMMARY files=%d %s" % (len(files), dict(c)))


if __name__ == "__main__":
    main()
