# -*- coding: utf-8 -*-
"""SVG → Tkinter Canvas 渲染器

目标：把 SVG 中的 rect/circle/line/polygon/g 元素解析并绘制到 tk.Canvas，
无需第三方依赖（cairosvg/PIL/SVG 库都不用），仅 tkinter + 正则。

应用场景：
  - SvgPanel 真正"可视化"显示 SVG（不再只是 Text 源码）
  - 异常高亮：在 Canvas 上用红色圈出 device_id 对应的设备

设计原则：
  - 模块化：render_svg() 纯函数，输入 svg_text + canvas，返回绘制数量
  - 健壮性：解析失败时静默跳过该元素
  - 灵活性：viewBox/width/height 自适应缩放
"""
from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Sequence


# ---------------------------------------------------------------------------
# SVG 属性解析
# ---------------------------------------------------------------------------


_RE_RECT = re.compile(
    r'<rect\b([^/>]*)/?>', re.IGNORECASE | re.DOTALL,
)
_RE_CIRCLE = re.compile(
    r'<circle\b([^/>]*)/?>', re.IGNORECASE | re.DOTALL,
)
_RE_LINE = re.compile(
    r'<line\b([^/>]*)/?>', re.IGNORECASE | re.DOTALL,
)
_RE_POLYGON = re.compile(
    r'<polygon\b([^/>]*)/?>', re.IGNORECASE | re.DOTALL,
)
_RE_G_OPEN = re.compile(
    r'<g\b([^>]*)>', re.IGNORECASE | re.DOTALL,
)
_RE_DATA_EQUIP_ID = re.compile(r'data-equip-id="([^"]+)"')


def _attrs(blob: str) -> dict[str, str]:
    """从 <tag attr1="v1" attr2='v2'> 中解析键值对。"""
    out: dict[str, str] = {}
    for m in re.finditer(r'([a-zA-Z\-:]+)\s*=\s*"([^"]*)"', blob):
        out[m.group(1).lower()] = m.group(2)
    for m in re.finditer(r"([a-zA-Z\-:]+)\s*=\s*'([^']*)'", blob):
        key = m.group(1).lower()
        if key not in out:
            out[key] = m.group(2)
    return out


def _num(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_viewbox(svg: str) -> tuple[float, float, float, float]:
    """从 SVG 提取 viewBox 或 width/height。"""
    m = re.search(r'<svg\b[^>]*\bviewBox\s*=\s*"([^"]+)"', svg, re.IGNORECASE)
    if m:
        parts = m.group(1).split()
        if len(parts) == 4:
            return tuple(float(p) for p in parts)  # type: ignore[return-value]
    width_m = re.search(r'<svg\b[^>]*\bwidth\s*=\s*"(\d+(?:\.\d+)?)"', svg, re.IGNORECASE)
    height_m = re.search(r'<svg\b[^>]*\bheight\s*=\s*"(\d+(?:\.\d+)?)"', svg, re.IGNORECASE)
    w = float(width_m.group(1)) if width_m else 1600.0
    h = float(height_m.group(1)) if height_m else 600.0
    return (0.0, 0.0, w, h)


# ---------------------------------------------------------------------------
# 渲染入口
# ---------------------------------------------------------------------------


def render_svg(
    canvas: tk.Canvas,
    svg: str,
    *,
    highlight_ids: Sequence[str] | None = None,
    fit_to_canvas: bool = True,
    padding: int = 16,
) -> dict[str, int]:
    """把 SVG 绘制到 tk.Canvas 上。

    Args:
        canvas: 目标 Canvas。
        svg: SVG 源码字符串。
        highlight_ids: 需要红色高亮的设备 ID 列表。
        fit_to_canvas: 是否按比例缩放到 Canvas 大小。

    Returns:
        统计信息：{"shapes": N, "highlighted": M}
    """
    highlight_ids = set(highlight_ids or ())
    canvas.delete("all")

    # 计算 viewBox / 缩放比例
    vb_x, vb_y, vb_w, vb_h = _parse_viewbox(svg)
    if vb_w <= 0 or vb_h <= 0:
        vb_w, vb_h = 1600.0, 600.0
    canvas.update_idletasks()
    cw = max(canvas.winfo_width(), 320)
    ch = max(canvas.winfo_height(), 200)
    scale_x = (cw - 2 * padding) / vb_w if fit_to_canvas else 1.0
    scale_y = (ch - 2 * padding) / vb_h if fit_to_canvas else 1.0
    scale = min(scale_x, scale_y)
    ox = padding - vb_x * scale
    oy = padding - vb_y * scale

    shapes_drawn = 0
    highlighted = 0

    # 1. 矩形
    for m in _RE_RECT.finditer(svg):
        a = _attrs(m.group(1))
        x = _num(a.get("x")) * scale + ox
        y = _num(a.get("y")) * scale + oy
        w = _num(a.get("width"), 10) * scale
        h = _num(a.get("height"), 10) * scale
        if w <= 0 or h <= 0:
            continue
        fill = a.get("fill") or "#3B9CFF"
        outline = a.get("stroke") or "#1F2630"
        sw = _num(a.get("stroke-width"), 1) * scale
        canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline=outline, width=max(1, sw))
        shapes_drawn += 1

    # 2. 圆形
    for m in _RE_CIRCLE.finditer(svg):
        a = _attrs(m.group(1))
        cx = _num(a.get("cx")) * scale + ox
        cy = _num(a.get("cy")) * scale + oy
        r = _num(a.get("r"), 5) * scale
        fill = a.get("fill") or "#3B9CFF"
        outline = a.get("stroke") or "#1F2630"
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=outline)
        shapes_drawn += 1

    # 3. 线段
    for m in _RE_LINE.finditer(svg):
        a = _attrs(m.group(1))
        x1 = _num(a.get("x1")) * scale + ox
        y1 = _num(a.get("y1")) * scale + oy
        x2 = _num(a.get("x2")) * scale + ox
        y2 = _num(a.get("y2")) * scale + oy
        stroke = a.get("stroke") or "#888888"
        sw = _num(a.get("stroke-width"), 1) * scale
        canvas.create_line(x1, y1, x2, y2, fill=stroke, width=max(1, sw))
        shapes_drawn += 1

    # 4. 多边形
    for m in _RE_POLYGON.finditer(svg):
        a = _attrs(m.group(1))
        points_str = a.get("points", "")
        pts = []
        for token in re.split(r'[\s,]+', points_str.strip()):
            if not token:
                continue
            try:
                pts.append(float(token))
            except ValueError:
                pass
        if len(pts) < 4:
            continue
        coords = []
        for i in range(0, len(pts) - 1, 2):
            coords.extend([pts[i] * scale + ox, pts[i + 1] * scale + oy])
        fill = a.get("fill") or "#3B9CFF"
        outline = a.get("stroke") or "#1F2630"
        canvas.create_polygon(*coords, fill=fill, outline=outline)
        shapes_drawn += 1

    # 5. <g data-equip-id> 容器：画高亮圆圈
    for m in _RE_G_OPEN.finditer(svg):
        a = _attrs(m.group(1))
        eid = a.get("data-equip-id")
        if not eid or eid not in highlight_ids:
            continue
        # 在 <g> 容器内找首个 rect/circle 的位置画高亮
        inner_start = m.end()
        inner_end = svg.find("</g>", inner_start)
        if inner_end < 0:
            continue
        inner = svg[inner_start:inner_end]
        rect_m = _RE_RECT.search(inner) or _RE_CIRCLE.search(inner)
        if not rect_m:
            continue
        ia = _attrs(rect_m.group(1))
        if rect_m.group(0).startswith("<rect"):
            x = _num(ia.get("x")) * scale + ox
            y = _num(ia.get("y")) * scale + oy
            w = _num(ia.get("width"), 20) * scale
            h = _num(ia.get("height"), 20) * scale
            canvas.create_rectangle(
                x - 4, y - 4, x + w + 4, y + h + 4,
                outline="#E08400", width=3,
            )
        else:
            cx = _num(ia.get("cx")) * scale + ox
            cy = _num(ia.get("cy")) * scale + oy
            r = _num(ia.get("r"), 8) * scale
            canvas.create_oval(
                cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4,
                outline="#E08400", width=3,
            )
        highlighted += 1

    return {"shapes": shapes_drawn, "highlighted": highlighted}


__all__ = ["render_svg"]
