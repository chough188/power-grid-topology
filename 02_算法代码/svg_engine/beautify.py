#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
5.1 现有 SVG 图形标准化美化排版优化

测试任务：
    不读取数据库拓扑信息，仅依托 SVG 文件自身连接关系，
    完成《LINE215.svg》《LINE216.svg》接线图美化处理。

美化要求：
    5.1.1 拓扑布局规范：电源点为起点、从左至右、先上后下排布
    5.1.2 图形缺陷整治：消除图元重叠、拓扑孤岛、飞线断线、设备偏移、线路交叉、压站穿站
    5.1.3 图元与标注标准化：统一设备图例、电压等级配色、设备名称标注
    5.1.4 柜箱设备绘制规范：容器内非母联开关纵向展示，柜内外连接线统一从底部引出
"""

import argparse
import sys
from pathlib import Path

from .svg_loader import SVGLoader, SVGDevice


def beautify_svg(input_path: str, output_path: str, title: str = "") -> str:
    """
    对单个 SVG 文件进行标准化美化。

    处理流程：
        1. 解析原始 SVG，提取设备与连接
        2. 拓扑分析：找根节点、分层、去孤岛
        3. 树形重排：电源在左，从左到右，先上后下
        4. 消除重叠：调整间距
        5. 标准化图元与标注
        6. 渲染输出
    """
    loader = SVGLoader.load(input_path)
    if title:
        loader.title = title

    # 1. 拓扑分析与去孤岛
    _remove_isolated(loader)

    # 2. 树形布局重排
    loader._tree_layout()

    # 3. 消除重叠（微调）
    _resolve_overlaps(loader)

    # 4. 标准化设备类型（从标注推断）
    _normalize_device_types(loader)

    # 5. 渲染
    loader.render(output_path, layout_strategy="tree")
    return output_path


def _remove_isolated(loader: SVGLoader):
    """移除拓扑孤岛设备（无连接的设备，除末端设备外）。"""
    connected = set()
    for link in loader.links:
        connected.add(link.from_id)
        connected.add(link.to_id)

    # 末端设备豁免：LOAD, CAPACITOR 等可以悬空
    exempt_types = {"LOAD", "CAPACITOR", "GENERATOR"}
    to_remove = []
    for d in loader.devices:
        if d.equip_id not in connected and d.equip_type not in exempt_types:
            to_remove.append(d)

    for d in to_remove:
        loader.devices.remove(d)


def _resolve_overlaps(loader: SVGLoader, min_gap: float = 50):
    """消除设备位置重叠，通过微调 Y 坐标。"""
    # 按 X 分组，检查同列内的 Y 重叠
    from collections import defaultdict
    col_groups = defaultdict(list)
    for d in loader.devices:
        key = round(d.x / 20) * 20  # 近似同列
        col_groups[key].append(d)

    for col, devices in col_groups.items():
        devices.sort(key=lambda d: d.y)
        for i in range(1, len(devices)):
            prev = devices[i - 1]
            curr = devices[i]
            if curr.y - prev.y < min_gap:
                curr.y = prev.y + min_gap

    # 更新边坐标
    for link in loader.links:
        d1 = loader._dev_by_id(link.from_id)
        d2 = loader._dev_by_id(link.to_id)
        if d1:
            link.x1, link.y1 = d1.x, d1.y
        if d2:
            link.x2, link.y2 = d2.x, d2.y


def _normalize_device_types(loader: SVGLoader):
    """从设备名称或已有标注推断并标准化设备类型。"""
    name_patterns = {
        r"开关|SW|sw": "SWITCH",
        r"刀闸|DS|ds|disconnect": "DISCONNECTOR",
        r"断路器|BR|breaker": "BREAKER",
        r"变压器|TR|tr|transformer": "TRANSFORMER",
        r"母线|BUS|bus": "BUS",
        r"电源|SRC|src|source": "SOURCE",
        r"负荷|LOAD|load": "LOAD",
        r"线路|LINE|line": "LINE",
        r"配变|DT|dt": "TRANSFORMER",
    }
    for d in loader.devices:
        if d.equip_type == "UNKNOWN":
            for pattern, etype in name_patterns.items():
                if d.name and d.equip_id and (
                    d.name.upper() in pattern.upper() or
                    any(p in d.name for p in pattern.split("|"))
                ):
                    d.equip_type = etype
                    break
        # 默认推断
        if d.equip_type == "UNKNOWN":
            if "SW" in d.equip_id.upper():
                d.equip_type = "SWITCH"
            elif "TR" in d.equip_id.upper():
                d.equip_type = "TRANSFORMER"
            elif "SRC" in d.equip_id.upper():
                d.equip_type = "SOURCE"
            else:
                d.equip_type = "LINE"


def batch_beautify(input_dir: str, output_dir: str):
    """批量美化目录下所有 SVG 文件。"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    svg_files = sorted(input_path.glob("*.svg"))
    if not svg_files:
        print(f"[WARN] 未在 {input_dir} 中找到 .svg 文件")
        return

    print(f"[INFO] 发现 {len(svg_files)} 个 SVG 文件，开始美化...")
    for svg_file in svg_files:
        out_file = output_path / svg_file.name
        print(f"  处理: {svg_file.name} -> {out_file}")
        try:
            beautify_svg(str(svg_file), str(out_file),
                        title=f"美化: {svg_file.stem}")
            print(f"    OK")
        except Exception as e:
            print(f"    [ERROR] {e}")
    print("[INFO] 批量美化完成")


def main():
    parser = argparse.ArgumentParser(description="SVG 标准化美化工具（任务 5.1）")
    parser.add_argument("--input", required=True, help="输入 SVG 文件或目录")
    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_file() and input_path.suffix.lower() == ".svg":
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        out_file = out / input_path.name
        beautify_svg(str(input_path), str(out_file))
        print(f"[OK] 输出: {out_file}")
    elif input_path.is_dir():
        batch_beautify(str(input_path), args.output)
    else:
        print(f"[ERROR] 无效的输入路径: {args.input}")
        sys.exit(1)


if __name__ == "__main__":
    main()
