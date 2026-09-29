# -*- coding: utf-8 -*-
"""LLM SVG 读图解题工具：inspect/beautify/add_room/remove_dev/render/verify/reconnect/batch_inspect/batch_beautify/batch_fix/render_png 十一合一。

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_svg_tools.py inspect <svg路径> [--full]
    python -X utf8 scripts/llm_svg_tools.py beautify <svg路径> <输出路径>
    python -X utf8 scripts/llm_svg_tools.py add_room <svg路径> <输出路径> --room 000300 --left 00104 --right 00102 --switches 00301,00302,00303
    python -X utf8 scripts/llm_svg_tools.py remove_dev <svg路径> <输出路径> --id "00024"   # ID 必须存在于该图
    python -X utf8 scripts/llm_svg_tools.py reconnect <svg路径> <输出路径> --from "00301" --to "TMP00000003"
    python -X utf8 scripts/llm_svg_tools.py render <输出目录> [snapshot路径，默认 data/snapshot.json]
    python -X utf8 scripts/llm_svg_tools.py verify <svg路径> [--required ID1,ID2] [--exempt ID1,ID2]
    python -X utf8 scripts/llm_svg_tools.py batch_inspect <svg目录> [--csv 输出CSV]
    python -X utf8 scripts/llm_svg_tools.py batch_beautify <svg目录> <输出目录>
    python -X utf8 scripts/llm_svg_tools.py batch_fix <svg目录> [--csv 输出CSV]
    python -X utf8 scripts/llm_svg_tools.py render_png <svg路径或目录> --out <PNG输出目录> [--scale 2] [--max-w 2000] [--diagnose]

设计原则：inspect 默认只输出"问题行 + 计数"，避免大 SVG 内容撑爆 27B 上下文；
verify 输出固定 KEY=VALUE 行，供逐行对比；
batch_fix 对 ISSUE 图自动完成"首末端豁免判定 + 候选端点"，只有它标 view=Y 的图才需要看图；
render_png 用 Edge headless 把 SVG 渲染成 PNG 供 27B 视觉模块看图（PNG 输出到外部目录，项目目录不留图）；
render_png --diagnose 生成"诊断标注图"：装饰线弱化、拓扑线加粗、设备标 ID、
孤岛红框 / 悬空橙框 / 重叠黄圈标注 + 顶部信息条，27B 只需核对标注位置而非自行数数。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from svg_engine.svg_loader import SVGLoader  # noqa: E402

SWITCH_TYPES = {"SWITCH", "BREAKER", "DISCONNECTOR", "LOAD_BREAK_SWITCH", "FUSE", "刀闸", "负荷开关", "断路器"}

# Bug#63: 站房设备类型 — 这些是空间容器(建筑), 不是电力设备
# 在孤岛判定中自动豁免(legitimately disconnected)
STATION_BUILDING_TYPES = {
    "zf01", "zf04", "zf06", "zf07", "zf08", "zf09", "0323", "0324",
    "ZF01", "ZF04", "ZF06", "ZF07", "ZF08", "ZF09",
    "substation", "STATION", "BUILDING", "ROOM",
    "zf", "ZF", "站房", "配电房", "环网柜", "箱变",
}


def _load(svg_path: str) -> SVGLoader:
    loader = SVGLoader(svg_path).parse()
    return loader


def _device_map(loader: SVGLoader) -> dict:
    return {d.equip_id: d for d in loader.devices}


def _degree(loader: SVGLoader) -> dict:
    deg = {d.equip_id: 0 for d in loader.devices}
    for ln in loader.links:
        deg[ln.from_id] = deg.get(ln.from_id, 0) + 1
        deg[ln.to_id] = deg.get(ln.to_id, 0) + 1
    return deg


def cmd_inspect(args: argparse.Namespace) -> int:
    loader = _load(args.svg)
    devs = {d.equip_id: d for d in loader.devices}
    deg = _degree(loader)
    lines = []
    lines.append("FILE = %s" % args.svg)
    lines.append("CANVAS = %.0fx%.0f" % (loader.width, loader.height))
    lines.append("DEVICES = %d" % len(loader.devices))
    lines.append("LINKS = %d" % len(loader.links))
    if args.full:
        lines.append("--- DEVICE LIST ---")
        for d in loader.devices:
            lines.append("DEV %s | %s | %.0f,%.0f | deg=%d" % (d.equip_id, d.equip_type or "?", d.x, d.y, deg.get(d.equip_id, 0)))
        lines.append("--- LINK LIST ---")
        for ln in loader.links:
            lines.append("LINK %s -> %s" % (ln.from_id, ln.to_id))
    # 缺陷检查
    dangling = []
    for d in loader.devices:
        if d.equip_type in SWITCH_TYPES:
            if deg.get(d.equip_id, 0) < 2:
                dangling.append("%s(%s,deg=%d)" % (d.equip_id, d.equip_type, deg.get(d.equip_id, 0)))
    islands = [d.equip_id for d in loader.devices if deg.get(d.equip_id, 0) == 0 and d.equip_type not in STATION_BUILDING_TYPES]
    lines.append("ISLAND_DEVICE = %d" % len(islands))
    if islands:
        lines.append("ISLAND_DEVICE_LIST = %s" % " ".join(islands))
    lines.append("DANGLING_SWITCH = %d" % len(dangling))
    if dangling:
        lines.append("DANGLING_SWITCH_LIST = %s" % " ".join(dangling))
    lines.append("NOTE = 首端/末端设备(deg=1)可能是合法线路端头,需按官方规则豁免")
    unref = []
    for ln in loader.links:
        if ln.from_id not in devs:
            unref.append(ln.from_id)
        if ln.to_id not in devs:
            unref.append(ln.to_id)
    lines.append("UNREFERENCED_LINK_ID = %d" % len(set(unref)))
    overlap = []
    # Bug#68: Spatial grid O(N) overlap detection (tolerance=6)
    _cell = 25
    _grid = {}
    for _d in loader.devices:
        _cx, _cy = int(_d.x // _cell), int(_d.y // _cell)
        _grid.setdefault((_cx, _cy), []).append(_d)
    _seen = set()
    for (_cx, _cy), _cd in _grid.items():
        _nb = []
        for _dx in range(-1, 2):
            for _dy in range(-1, 2):
                _nb.extend(_grid.get((_cx + _dx, _cy + _dy), []))
        for _a in _cd:
            for _b in _nb:
                if _a is _b: continue
                _pair = tuple(sorted([_a.equip_id, _b.equip_id]))
                if _pair in _seen: continue
                _seen.add(_pair)
                _dist = math.hypot(_a.x - _b.x, _a.y - _b.y)
                if _dist < 6:
                    overlap.append("%s~%s(d=%.0f)" % (_a.equip_id, _b.equip_id, _dist))
    lines.append("OVERLAP_DEVICES = %d" % len(overlap))
    if overlap:
        lines.append("OVERLAP_LIST = %s" % " ".join(overlap[:20]))
    print("\n".join(lines))
    return 0


def cmd_beautify(args: argparse.Namespace) -> int:
    from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
    svg = Path(args.svg).read_text(encoding="utf-8")
    out = beautify(svg)
    Path(args.out).write_text(out, encoding="utf-8")
    print("BEAUTIFY_IN = %d" % len(svg))
    print("BEAUTIFY_OUT = %d" % len(out))
    print("BEAUTIFY_SAVED = %s" % args.out)
    return 0


def cmd_add_room(args: argparse.Namespace) -> int:
    from tasks_official.task5_svg.task_5_2_modify.detector import add_room_with_switches
    svg = Path(args.svg).read_text(encoding="utf-8")
    switches = [s for s in args.switches.split(",") if s]
    out = add_room_with_switches(
        svg,
        room_id=args.room,
        room_name="站房%s" % args.room,
        left_switch_id=args.left,
        right_switch_id=args.right,
        inner_switch_ids=switches,
    )
    Path(args.out).write_text(out, encoding="utf-8")
    ok = args.room in out and all(s in out for s in switches)
    print("ADD_ROOM_OK = %s" % ok)
    print("ADD_ROOM_SAVED = %s" % args.out)
    return 0


def cmd_remove_dev(args: argparse.Namespace) -> int:
    from tasks_official.task5_svg.task_5_2_modify.detector import remove_device
    svg = Path(args.svg).read_text(encoding="utf-8")
    out = remove_device(svg, args.id)
    Path(args.out).write_text(out, encoding="utf-8")
    print("REMOVE_OK = %s" % (args.id not in out))
    print("REMOVE_SAVED = %s" % args.out)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from data_loader.universal import load_dataset
    from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_all
    ds = load_dataset(args.snapshot)
    feeds = [r["LINE_ID"] for r in ds.tables.get("JBS_PWFEEDERLINE", [])]
    line_a = feeds[0] if len(feeds) > 0 else "F101"
    line_b = feeds[1] if len(feeds) > 1 else "F102"
    res = render_all(ds.tables, line215=line_a, line216=line_b, line111=line_a,
                     sub004="SUB004", target_id="TMP00013138")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, svg in res.items():
        name = "%s.svg" % key
        (out_dir / name).write_text(svg, encoding="utf-8")
        print("RENDER %s = %d chars -> %s" % (key, len(svg), out_dir / name))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    loader = _load(args.svg)
    devs = {d.equip_id for d in loader.devices}
    deg = _degree(loader)
    missing = sorted({ln.from_id for ln in loader.links if ln.from_id not in devs} |
                     {ln.to_id for ln in loader.links if ln.to_id not in devs})
    dup_ids = []
    seen = set()
    for d in loader.devices:
        if d.equip_id in seen:
            dup_ids.append(d.equip_id)
        seen.add(d.equip_id)
    dangling = []
    islands = []
    for d in loader.devices:
        dg = deg.get(d.equip_id, 0)
        if dg == 0:
            islands.append(d.equip_id)
        elif d.equip_type in SWITCH_TYPES and dg < 2:
            dangling.append(d.equip_id)
    exempt = set(x for x in (args.exempt or "").split(",") if x)
    islands = [i for i in islands if i not in exempt]
    dangling = [d for d in dangling if d not in exempt]
    required = [r for r in (args.required or "").split(",") if r]
    missing_required = [r for r in required if r not in devs]
    print("VERIFY_FILE = %s" % args.svg)
    print("LINK_ENDPOINT_MISSING = %d" % len(missing))
    print("DUPLICATE_DEVICE_ID = %d" % len(dup_ids))
    print("ISLAND_DEVICE = %d" % len(islands))
    print("ISLAND_DEVICE_LIST = %s" % (" ".join(islands) if islands else "-"))
    print("DANGLING_SWITCH = %d" % len(dangling))
    print("DANGLING_SWITCH_LIST = %s" % (" ".join(dangling) if dangling else "-"))
    print("REQUIRED_MISSING = %d" % len(missing_required))
    print("VERIFY_OK = %s" % (not missing and not dup_ids and not islands and not dangling and not missing_required))
    return 0


def cmd_reconnect(args: argparse.Namespace) -> int:
    """删除设备后把两侧设备直接连通（官方 5.2 T6 要求）。"""
    loader = _load(args.svg)
    devs = {d.equip_id: d for d in loader.devices}
    if args.from_id not in devs or args.to_id not in devs:
        print("RECONNECT_FAIL = unknown id (from=%s to=%s)" % (args.from_id, args.to_id))
        return 1
    for ln in loader.links:
        if {ln.from_id, ln.to_id} == {args.from_id, args.to_id}:
            print("RECONNECT_SKIP = already connected")
            Path(args.out).write_text(Path(args.svg).read_text(encoding="utf-8"), encoding="utf-8")
            return 0
    a, b = devs[args.from_id], devs[args.to_id]
    block = '<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#2CA02C" stroke-width="2.5" data-from="%s" data-to="%s"/>' % (
        a.x, a.y, b.x, b.y, args.from_id, args.to_id)
    svg_text = Path(args.svg).read_text(encoding="utf-8")
    new_text = svg_text.rstrip()
    if new_text.endswith("</svg>"):
        new_text = new_text[: -len("</svg>")] + block + "\n</svg>"
    Path(args.out).write_text(new_text, encoding="utf-8")
    print("RECONNECT_OK = %s -> %s" % (args.from_id, args.to_id))
    print("RECONNECT_SAVED = %s" % args.out)
    return 0


def _find_edge() -> str | None:
    """探测 Edge 可执行文件路径（headless 渲染用）。"""
    import os
    import shutil
    cands = [
        os.environ.get("ProgramFiles(x86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("ProgramFiles", "") + r"\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    return shutil.which("msedge")


def _overlap_groups(devs: list, dist_thresh: float = 12.0) -> list:
    """把距离 < dist_thresh 的设备聚成重叠组，返回 [(cx, cy, [ids...]), ...]。"""
    groups: list = []
    used = set()
    for i, a in enumerate(devs):
        if i in used:
            continue
        members = [i]
        changed = True
        while changed:
            changed = False
            for j, b in enumerate(devs):
                if j in used or j in members:
                    continue
                for m in members:
                    if math.hypot(devs[m].x - b.x, devs[m].y - b.y) < dist_thresh:
                        members.append(j)
                        changed = True
                        break
        if len(members) > 1:
            for m in members:
                used.add(m)
            cx = sum(devs[m].x for m in members) / len(members)
            cy = sum(devs[m].y for m in members) / len(members)
            groups.append((cx, cy, [devs[m].equip_id for m in members]))
    return groups


def _build_diagnose_svg(loader, svg_path: Path, svg_text: str) -> str:
    """生成诊断标注版 SVG：装饰弱化 + 拓扑加粗 + ID 标注 + 孤岛红框/悬空橙框/重叠黄圈 + 顶部信息条。

    纯文本处理（不序列化 XML，避免命名空间丢失）。拓扑线判定：
    1. 有 data-from 的 line → 拓扑线
    2. 无 data-from 的 line → 端点落在 loader.links 端点集合（坐标匹配，容差 0.6）→ 拓扑线
    3. 其余 → 装饰线，弱化为浅灰 0.12 透明度
    """
    import re
    devs = loader.devices
    deg = _degree(loader)
    islands = [d for d in devs if deg.get(d.equip_id, 0) == 0]
    dangling = [d for d in devs if d.equip_type in SWITCH_TYPES and deg.get(d.equip_id, 0) < 2]
    groups = _overlap_groups(devs)
    link_ends = set()
    for ln in loader.links:
        link_ends.add((round(float(ln.x1)), round(float(ln.y1))))
        link_ends.add((round(float(ln.x2)), round(float(ln.y2))))
    w, h = loader.width, loader.height

    def _repl_line(m):
        tag = m.group(0)
        if 'data-from' in tag:
            tag = re.sub(r'stroke="[^"]*"', 'stroke="#2CA02C"', tag)
            tag = re.sub(r'stroke-width="[^"]*"', 'stroke-width="4.5"', tag)
            tag = re.sub(r'stroke-dasharray="[^"]*"', '', tag)
            return tag
        x1 = float(re.search(r'x1="([\d.\-]+)"', tag).group(1))
        y1 = float(re.search(r'y1="([\d.\-]+)"', tag).group(1))
        x2 = float(re.search(r'x2="([\d.\-]+)"', tag).group(1))
        y2 = float(re.search(r'y2="([\d.\-]+)"', tag).group(1))
        if (round(x1), round(y1)) in link_ends and (round(x2), round(y2)) in link_ends:
            tag = re.sub(r'stroke="[^"]*"', 'stroke="#2CA02C"', tag)
            tag = re.sub(r'stroke-width="[^"]*"', 'stroke-width="4.5"', tag)
            tag = re.sub(r'stroke-dasharray="[^"]*"', '', tag)
            return tag
        tag = re.sub(r'stroke="[^"]*"', 'stroke="#CCCCCC"', tag)
        tag = re.sub(r'stroke-width="[^"]*"', 'stroke-width="1"', tag)
        return tag.replace('/>', ' opacity="0.15"/>')

    svg_text = re.sub(r'<line\b[^>]*/>', _repl_line, svg_text)
    svg_text = re.sub(r'<path\b[^>]*/>', lambda m: m.group(0).replace('/>', ' opacity="0.15"/>'), svg_text)

    ann = ['<g id="diag-annot" font-family="sans-serif">']
    ann.append('<rect x="0" y="0" width="%.0f" height="30" fill="#222222"/>' % w)
    ann.append('<text x="12" y="20" font-size="16" fill="#FFFFFF">FILE=%s | DEVICES=%d | LINKS=%d | ISLAND=%d | OVERLAP_GROUPS=%d | DANGLING=%d</text>'
               % (svg_path.name, len(devs), len(loader.links), len(islands), len(groups), len(dangling)))
    island_ids = {d.equip_id for d in islands}
    dang_ids = {d.equip_id for d in dangling}
    for d in devs:
        x, y = d.x, d.y
        if d.equip_id in island_ids:
            ann.append('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" fill="none" stroke="#D62728" stroke-width="3" stroke-dasharray="6 4"/>'
                       % (x - 45, y - 38, 90, 76))
            ann.append('<text x="%.0f" y="%.0f" font-size="13" fill="#D62728" font-weight="bold">%s ISLAND</text>'
                       % (x - 44, y - 44, d.equip_id))
        elif d.equip_id in dang_ids:
            ann.append('<text x="%.0f" y="%.0f" font-size="12" fill="#FF7F0E">%s</text>' % (x - 40, y - 30, d.equip_id))
        else:
            ann.append('<text x="%.0f" y="%.0f" font-size="11" fill="#666666">%s</text>' % (x - 36, y - 28, d.equip_id))
    for gi, (gx, gy, ids) in enumerate(groups):
        ann.append('<ellipse cx="%.0f" cy="%.0f" rx="65" ry="45" fill="none" stroke="#FFD700" stroke-width="3" stroke-dasharray="8 4"/>' % (gx, gy))
        ann.append('<text x="%.0f" y="%.0f" font-size="12" fill="#B8860B" font-weight="bold">OVERLAP%d: %s</text>'
                   % (gx + 70, gy - 20, gi + 1, " ".join(ids)))
    ann.append('<rect x="%.0f" y="36" width="260" height="86" fill="#FFFFFF" fill-opacity="0.85" stroke="#CCC"/>' % (w - 270))
    ann.append('<text x="%.0f" y="54" font-size="12" fill="#333">图例</text>' % (w - 262))
    ann.append('<text x="%.0f" y="72" font-size="11" fill="#D62728">红框=孤岛(无连线)</text>' % (w - 262))
    ann.append('<text x="%.0f" y="88" font-size="11" fill="#FF7F0E">橙字=悬空开关</text>' % (w - 262))
    ann.append('<text x="%.0f" y="104" font-size="11" fill="#B8860B">黄圈=设备重叠组</text>' % (w - 262))
    ann.append('<text x="%.0f" y="120" font-size="11" fill="#666">绿粗线=拓扑连线</text>' % (w - 262))
    ann.append('</g>')
    new_svg = svg_text.rstrip()
    if new_svg.endswith("</svg>"):
        new_svg = new_svg[: -len("</svg>")] + "".join(ann) + "\n</svg>"
    return new_svg


def cmd_render_png(args: argparse.Namespace) -> int:
    """SVG → PNG（Edge headless 截图），供 27B 视觉模块看图。

    PNG 是 SVG 的渲染衍生物，默认输出到外部目录（如 $env:TEMP\svg_png），
    项目目录内不留 PNG（数据隔离）。
    --diagnose 生成诊断标注图（弱化装饰/加粗拓扑/孤岛红框/重叠黄圈/顶部信息条）。
    """
    import subprocess
    import time
    src = Path(args.in_path)
    if src.is_dir():
        files = sorted(src.glob("*.svg"))
    elif src.is_file():
        files = [src]
    else:
        print("PNG_INPUT_NOT_FOUND = %s" % args.in_path)
        return 1
    edge = args.edge or _find_edge()
    if not edge:
        print("PNG_EDGE_NOT_FOUND = 未找到 msedge.exe, 请用 --edge 指定完整路径")
        return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for f in files:
        try:
            loader = _load(str(f))
            w, h = float(loader.width), float(loader.height)
            scale = float(args.scale)
            if w * scale > args.max_w:
                scale = max(1.0, float(args.max_w) / w)
            ww, hh = int(round(w * scale)), int(round(h * scale))
            if args.diagnose:
                svg_text = f.read_text(encoding="utf-8")
                diag_svg = _build_diagnose_svg(loader, f, svg_text)
                work = out_dir / (f.stem + "_diag.svg")
                work.write_text(diag_svg, encoding="utf-8")
                png = out_dir / (f.stem + "_diag.png")
                deg = _degree(loader)
                n_island = sum(1 for d in loader.devices if deg.get(d.equip_id, 0) == 0)
                n_dang = sum(1 for d in loader.devices if d.equip_type in SWITCH_TYPES and deg.get(d.equip_id, 0) < 2)
                n_grp = len(_overlap_groups(loader.devices))
                url = work.resolve().as_uri()
            else:
                work = f
                png = out_dir / (f.stem + ".png")
                url = f.resolve().as_uri()
            subprocess.run([
                edge, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--default-background-color=FFFFFFFF",
                "--window-size=%d,%d" % (ww, hh),
                "--screenshot=%s" % png, url,
            ], capture_output=True, timeout=args.timeout)
            t0 = time.time()
            while (not png.exists() or png.stat().st_size == 0) and time.time() - t0 < 15:
                time.sleep(0.5)
            if png.exists() and png.stat().st_size > 0:
                if args.diagnose:
                    print("PNG_DIAG %s = %dx%d devices=%d links=%d island=%d overlap_groups=%d dangling=%d -> %s"
                          % (f.name, ww, hh, len(loader.devices), len(loader.links), n_island, n_grp, n_dang, png))
                else:
                    print("PNG %s = %dx%d -> %s" % (f.name, ww, hh, png))
                ok += 1
            else:
                print("PNG %s = ERROR 渲染超时或无输出" % f.name)
                fail += 1
        except Exception as e:
            print("PNG %s = ERROR %s" % (f.name, e))
            fail += 1
    print("PNG_RENDERED = %d" % ok)
    print("PNG_FAIL = %d" % fail)
    print("PNG_OUT_DIR = %s" % out_dir)
    return 0 if fail == 0 else 1


def _batch_load(svg_path: str) -> tuple:
    """加载并返回 (loader, errors)。错误时返回 (None, 错误字符串)。"""
    try:
        return _load(svg_path), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def cmd_batch_inspect(args: argparse.Namespace) -> int:
    """批量体检一个 SVG 目录，输出汇总 CSV + 问题计数（供 27B 逐图判断）。"""
    in_dir = Path(args.in_dir)
    if not in_dir.is_dir():
        print("BATCH_DIR_NOT_FOUND = %s" % args.in_dir)
        return 1
    files = sorted(in_dir.glob("*.svg"))
    rows = []
    for f in files:
        loader, err = _batch_load(str(f))
        if err:
            rows.append((f.name, "PARSE_ERROR", err[:40]))
            continue
        devs = {d.equip_id for d in loader.devices}
        deg = _degree(loader)
        islands = [d.equip_id for d in loader.devices if deg.get(d.equip_id, 0) == 0 and d.equip_type not in STATION_BUILDING_TYPES]
        dangling = [d.equip_id for d in loader.devices
                    if d.equip_type in SWITCH_TYPES and deg.get(d.equip_id, 0) < 2]
        dup = len(loader.devices) - len(devs)
        unref = len({ln.from_id for ln in loader.links if ln.from_id not in devs} |
                    {ln.to_id for ln in loader.links if ln.to_id not in devs})
        if islands or dangling or dup or unref or err:
            rows.append((f.name, "ISSUE", "islands=%d dangling=%d dup=%d unref=%d" % (
                len(islands), len(dangling), dup, unref)))
        else:
            rows.append((f.name, "OK", "devices=%d links=%d" % (len(loader.devices), len(loader.links))))
    print("BATCH_SCANNED = %d" % len(rows))
    print("BATCH_OK = %d" % sum(1 for _, st, _ in rows if st == "OK"))
    print("BATCH_ISSUE = %d" % sum(1 for _, st, _ in rows if st == "ISSUE"))
    print("BATCH_PARSE_ERROR = %d" % sum(1 for _, st, _ in rows if st == "PARSE_ERROR"))
    print("--- ISSUE FILES (逐图处理清单) ---")
    for name, st, detail in rows:
        if st != "OK":
            print("%s | %s | %s" % (name, st, detail))
    if args.csv:
        import csv
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file", "status", "detail"])
            w.writerows(rows)
        print("BATCH_CSV = %s" % out)
    return 0


def cmd_batch_beautify(args: argparse.Namespace) -> int:
    """批量美化一个 SVG 目录（官方 5.1：必须程序自动化，不允许手动改）。"""
    from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
    in_dir, out_dir = Path(args.in_dir), Path(args.out_dir)
    if not in_dir.is_dir():
        print("BATCH_DIR_NOT_FOUND = %s" % args.in_dir)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for f in sorted(in_dir.glob("*.svg")):
        try:
            svg = f.read_text(encoding="utf-8")
            out = beautify(svg)
            (out_dir / f.name).write_text(out, encoding="utf-8")
            print("BEAUTIFY %s = %d -> %d" % (f.name, len(svg), len(out)))
            ok += 1
        except Exception as e:
            print("BEAUTIFY %s = ERROR %s" % (f.name, e))
            fail += 1
    print("BATCH_BEAUTIFY_OK = %d" % ok)
    print("BATCH_BEAUTIFY_FAIL = %d" % fail)
    print("BATCH_BEAUTIFY_OUT = %s" % out_dir)
    return 0 if fail == 0 else 1


def cmd_batch_fix(args: argparse.Namespace) -> int:
    """批量自动修正建议：完整检测 + 首末端自动豁免 + 候选端点 + 待看图清单。

    对目录内每张 SVG：
      1. 完整检测（一项不跳）：ISLAND / DANGLING / DUPLICATE / UNREFERENCED / OVERLAP
      2. 自动豁免（100% 可靠规则）：dangling 开关 deg=1 且位于图元 x/y 极值 = 线路首端/末端
      3. 豁免后 verify 计算（不改文件；豁免只影响 verify 参数）
      4. 其余孤岛/悬空：输出最近 3 个非问题设备的距离候选（仅候选，接线逻辑由人确认）
      5. 仍需人看的图标记 view=Y → 只对这些图渲染诊断图 + 看图
    """
    in_dir = Path(args.in_dir)
    if not in_dir.is_dir():
        print("BATCH_DIR_NOT_FOUND = %s" % args.in_dir)
        return 1
    rows = []
    for f in sorted(in_dir.glob("*.svg")):
        loader, err = _batch_load(str(f))
        if err:
            rows.append((f.name, "PARSE_ERROR", 0, 0, 0, 0, 0, "", "Y", ""))
            continue
        devs = {d.equip_id: d for d in loader.devices}
        deg = _degree(loader)
        islands = [d.equip_id for d in loader.devices if deg.get(d.equip_id, 0) == 0 and d.equip_type not in STATION_BUILDING_TYPES]
        dangling = [d for d in loader.devices
                    if d.equip_type in SWITCH_TYPES and deg.get(d.equip_id, 0) < 2]
        dup = len(loader.devices) - len(devs)
        unref = len({ln.from_id for ln in loader.links if ln.from_id not in devs} |
                    {ln.to_id for ln in loader.links if ln.to_id not in devs})
        # Bug#68: Spatial grid for O(N) overlap detection (tolerance=6)
        _cell = 25
        _grid = {}
        for _d in loader.devices:
            _cx, _cy = int(_d.x // _cell), int(_d.y // _cell)
            _grid.setdefault((_cx, _cy), []).append(_d)
        overlap = 0
        _seen = set()
        for (_cx, _cy), _cd in _grid.items():
            _nb = []
            for _dx in range(-1, 2):
                for _dy in range(-1, 2):
                    _nb.extend(_grid.get((_cx + _dx, _cy + _dy), []))
            for _a in _cd:
                for _b in _nb:
                    if _a is _b: continue
                    _pair = tuple(sorted([_a.equip_id, _b.equip_id]))
                    if _pair in _seen: continue
                    _seen.add(_pair)
                    if math.hypot(_a.x - _b.x, _a.y - _b.y) < 6:
                        overlap += 1
        xs = [d.x for d in loader.devices]
        ys = [d.y for d in loader.devices]
        exempt = sorted({d.equip_id for d in dangling
                         if deg.get(d.equip_id, 0) == 1
                         and (d.x == min(xs) or d.x == max(xs) or d.y == min(ys) or d.y == max(ys))})
        left_islands = [i for i in islands if i not in exempt]
        left_dangling = [d.equip_id for d in dangling if d.equip_id not in exempt]
        # Bug#67: overlap is visual quality, not topology — do not block verify_ok
        verify_ok = not left_islands and not left_dangling and not dup and not unref
        if not islands and not left_dangling and not dup and not unref:
            status = "OK"
        elif verify_ok:
            status = "EXEMPT_OK"
        else:
            status = "PENDING"
        view = "N" if status in ("OK", "EXEMPT_OK") else "Y"
        cands = {}
        for did in left_islands + left_dangling:
            near = []
            for d in loader.devices:
                if d.equip_id in left_islands + left_dangling:
                    continue
                near.append((d.equip_id, math.hypot(d.x - _byid(loader, did).x, d.y - _byid(loader, did).y)))
            cands[did] = " ".join("%s(%.0f)" % (i, dist) for i, dist in sorted(near, key=lambda t: t[1])[:3])
        print("BATCHFIX %s = %s islands=%d dangling=%d exempt=%s dup=%d unref=%d overlap=%d verify_ok=%s view=%s" % (
            f.name, status, len(islands), len(dangling),
            ",".join(exempt) if exempt else "-", dup, unref, overlap, verify_ok, view))
        for did, cs in cands.items():
            print("CAND %s -> %s" % (did, cs))
        rows.append((f.name, status, len(islands), len(dangling), dup, unref, overlap,
                     ",".join(exempt), view, "; ".join("%s: %s" % (k, v) for k, v in cands.items())))
    print("BATCHFIX_SCANNED = %d" % len(rows))
    print("BATCHFIX_OK = %d" % sum(1 for _, st, *_ in rows if st == "OK"))
    print("BATCHFIX_EXEMPT_OK = %d" % sum(1 for _, st, *_ in rows if st == "EXEMPT_OK"))
    print("BATCHFIX_PENDING = %d" % sum(1 for _, st, *_ in rows if st == "PENDING"))
    print("BATCHFIX_PARSE_ERROR = %d" % sum(1 for _, st, *_ in rows if st == "PARSE_ERROR"))
    print("BATCHFIX_NEED_VIEW = %d" % sum(1 for r in rows if r[8] == "Y"))
    print("BATCHFIX_NEED_VIEW_LIST = %s" % (" ".join(r[0] for r in rows if r[8] == "Y") or "-"))
    if args.csv:
        import csv
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file", "status", "islands", "dangling", "dup", "unref", "overlap",
                        "exempt", "view", "candidates"])
            w.writerows(rows)
        print("BATCHFIX_CSV = %s" % out)
    return 0


def _byid(loader, equip_id: str):
    for d in loader.devices:
        if d.equip_id == equip_id:
            return d
    raise KeyError(equip_id)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description="LLM SVG tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("svg")
    p_inspect.add_argument("--full", action="store_true")
    p_inspect.set_defaults(func=cmd_inspect)

    p_beau = sub.add_parser("beautify")
    p_beau.add_argument("svg")
    p_beau.add_argument("out")
    p_beau.set_defaults(func=cmd_beautify)

    p_room = sub.add_parser("add_room")
    p_room.add_argument("svg")
    p_room.add_argument("out")
    p_room.add_argument("--room", required=True)
    p_room.add_argument("--left", required=True)
    p_room.add_argument("--right", required=True)
    p_room.add_argument("--switches", required=True)
    p_room.set_defaults(func=cmd_add_room)

    p_rm = sub.add_parser("remove_dev")
    p_rm.add_argument("svg")
    p_rm.add_argument("out")
    p_rm.add_argument("--id", required=True)
    p_rm.set_defaults(func=cmd_remove_dev)

    p_render = sub.add_parser("render")
    p_render.add_argument("out_dir")
    p_render.add_argument("snapshot", nargs="?", default="data/snapshot.json",
                          help="数据源: data/snapshot.json 或 date.sql 或含 *.sql 的目录")
    p_render.set_defaults(func=cmd_render)

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("svg")
    p_ver.add_argument("--required", default="")
    p_ver.add_argument("--exempt", default="", help="豁免ID(逗号分隔):备用间隔/合法线路端头,如 00302,TMP00000001")
    p_ver.set_defaults(func=cmd_verify)

    p_rec = sub.add_parser("reconnect")
    p_rec.add_argument("svg")
    p_rec.add_argument("out")
    p_rec.add_argument("--from", dest="from_id", required=True)
    p_rec.add_argument("--to", dest="to_id", required=True)
    p_rec.set_defaults(func=cmd_reconnect)

    p_bi = sub.add_parser("batch_inspect")
    p_bi.add_argument("in_dir")
    p_bi.add_argument("--csv", default="")
    p_bi.set_defaults(func=cmd_batch_inspect)

    p_bb = sub.add_parser("batch_beautify")
    p_bb.add_argument("in_dir")
    p_bb.add_argument("out_dir")
    p_bb.set_defaults(func=cmd_batch_beautify)

    p_bf = sub.add_parser("batch_fix")
    p_bf.add_argument("in_dir")
    p_bf.add_argument("--csv", default="")
    p_bf.set_defaults(func=cmd_batch_fix)

    p_png = sub.add_parser("render_png")
    p_png.add_argument("in_path")
    p_png.add_argument("--out", dest="out_dir", required=True)
    p_png.add_argument("--scale", type=float, default=2.0, help="放大倍率(默认2, SVG尺寸通常偏小)")
    p_png.add_argument("--max-w", dest="max_w", type=float, default=2000, help="输出宽度上限(默认2000)")
    p_png.add_argument("--edge", default="", help="msedge.exe 完整路径(自动探测不到时指定)")
    p_png.add_argument("--timeout", type=int, default=60)
    p_png.add_argument("--diagnose", action="store_true", help="诊断标注模式: 弱化装饰线/加粗拓扑线/设备ID/孤岛红框/重叠黄圈/顶部信息条")
    p_png.set_defaults(func=cmd_render_png)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
