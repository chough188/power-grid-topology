# -*- coding: utf-8 -*-
"""合成 SVG 样本生成器 (比赛官方 SVG 还未下发时,用于测试美化功能)。

按 detector._parse_devices 期望的格式生成:
  <g data-equip-id="TMP00000001" data-equip-type="..." data-voltage="...">
    <rect x=".." y=".." width=".." height=".." fill=".."/>
  </g>
  <line x1=".." y1=".." x2=".." y2=".." data-from="TMP..." data-to="TMP..." />

设计原则:
- 仅使用 Python 标准库 + 字符串拼接,不依赖任何项目模块
  (保持 data_loader 作为 common 层,不引入反向依赖)
- 颜色/尺寸与 5.1 detector 默认值保持一致(评审手册 §5.3)
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any


# 评审手册 §5.3 电压等级配色
VOLTAGE_COLORS = {
    1000: "#D62728", 500: "#D62728", 220: "#D62728",
    110:  "#1F77B4", 35:  "#1F77B4",
    10:   "#2CA02C",
    0.4:  "#9467BD",
}

# 评审手册 §5.3 设备图元尺寸
DEVICE_DIMENSIONS = {
    "BREAKER":      (40, 24),
    "SWITCH":       (40, 24),
    "DISCONNECTOR": (24, 24),
    "TRANSFORMER":  (48, 48),
    "BUS":          (60, 8),
    "LINE":         (16, 4),
    "XF":           (48, 48),
}

DEVICE_COL_GAP = 80
DEVICE_ROW_GAP = 60

LINE_COLOR = "#2CA02C"
LINE_WIDTH = 2.5


def make_synthetic_svg(
    n_devices: int = 8,
    seed: int = 42,
    width: int | None = None,
    height: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """生成简单链式 + 一个支线的合成 SVG。"""
    rng = random.Random(seed)
    types = ["BREAKER", "SWITCH", "TRANSFORMER", "DISCONNECTOR"]
    voltages = [10, 35, 110, 220]

    devices: list[dict[str, Any]] = []
    x = 60
    y = 220
    for i in range(1, n_devices + 1):
        equip_id = f"TMP{i:08d}"
        et = types[i % len(types)]
        v = voltages[i % len(voltages)]
        w, h = DEVICE_DIMENSIONS.get(et, (32, 24))
        devices.append({
            "equip_id": equip_id,
            "equip_type": et,
            "voltage": v,
            "x": x, "y": y, "w": w, "h": h,
        })
        x += DEVICE_COL_GAP + w

    edges: list[tuple[str, str]] = []
    for i in range(len(devices) - 1):
        edges.append((devices[i]["equip_id"], devices[i + 1]["equip_id"]))
    if len(devices) >= 5:
        edges.append((devices[1]["equip_id"], devices[4]["equip_id"]))

    if width is None:
        width = devices[-1]["x"] + devices[-1]["w"] + 80
    if height is None:
        height = 480

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    parts.append(f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" fill="#FAFAFA"/>')

    for a, b in edges:
        da = next(d for d in devices if d["equip_id"] == a)
        db = next(d for d in devices if d["equip_id"] == b)
        x1 = da["x"] + da["w"]
        y1 = da["y"] + da["h"] / 2
        x2 = db["x"]
        y2 = db["y"] + db["h"] / 2
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{LINE_COLOR}" stroke-width="{LINE_WIDTH}" '
            f'data-from="{a}" data-to="{b}"/>'
        )

    for d in devices:
        color = VOLTAGE_COLORS.get(d["voltage"], "#888888")
        parts.append(
            f'<g data-equip-id="{d["equip_id"]}" '
            f'data-equip-type="{d["equip_type"]}" '
            f'data-voltage="{d["voltage"]}">'
        )
        parts.append(
            f'<rect x="{d["x"]}" y="{d["y"]}" width="{d["w"]}" height="{d["h"]}" '
            f'fill="{color}" stroke="#333" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{d["x"] + d["w"] / 2}" y="{d["y"] - 4}" '
            f'font-size="9" text-anchor="middle" fill="#333">'
            f'{d["equip_id"][-3:]}</text>'
        )
        parts.append('</g>')

    parts.append('</svg>')

    svg = "".join(parts)
    lookups = {
        "voltage_lookup": {d["equip_id"]: d["voltage"] for d in devices},
        "equip_type_lookup": {d["equip_id"]: d["equip_type"] for d in devices},
        "edges": edges,
    }
    return svg, lookups


def write_synthetic_svg(out_path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """生成 SVG 并写到文件,返回 lookups。"""
    svg, lookups = make_synthetic_svg(**kwargs)
    Path(out_path).write_text(svg, encoding="utf-8")
    return lookups


__all__ = ["make_synthetic_svg", "write_synthetic_svg"]
