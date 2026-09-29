#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
5.2 SVG 图形交互式增删设备

测试任务 1：
    基于 5.1 美化后的 LINE215.svg，在开关 00104 与开关 00102 之间新增站房（编号站房 000300）
    站内配置 3 台负荷开关：00301、00302、00303
    拓扑连接：00301 对接 00104，00302 备用间隔，00303 对接 00102

测试任务 2：
    针对 5.1 美化后的 LINE216.svg，删除开关 00024 图元及文字标注，左右两侧设备直接连通

注意：
    增删设备后需自动同步更新图形节点坐标、线路连接关系，
    保证修改后图形拓扑与后台模型逻辑完全一致。
"""

import argparse
import sys
from pathlib import Path

from .svg_loader import SVGLoader, SVGDevice


def add_station_between(
    svg_path: str,
    output_path: str,
    switch_a: str,
    switch_b: str,
    station_id: str,
    station_name: str = "",
    internal_switches: list = None,
    connections: list = None,
) -> str:
    """
    在两个开关之间新增站房及内部开关。

    Args:
        svg_path: 输入 SVG 路径
        output_path: 输出路径
        switch_a, switch_b: 两侧开关 equip_id
        station_id: 站房编号
        station_name: 站房名称
        internal_switches: [(switch_id, switch_name), ...]
        connections: [连接目标, 备用, 连接目标] 与 internal_switches 一一对应
    """
    loader = SVGLoader.load(svg_path)

    dev_a = loader._dev_by_id(switch_a)
    dev_b = loader._dev_by_id(switch_b)
    if not dev_a or not dev_b:
        raise ValueError(f"找不到开关: {switch_a} 或 {switch_b}")

    # 计算站房位置（两开关中间偏下）
    mid_x = (dev_a.x + dev_b.x) / 2
    mid_y = max(dev_a.y, dev_b.y) + 80

    # 1. 添加站房容器（用 BUS 类型表示站房母线/容器）
    room = SVGDevice(
        equip_id=station_id,
        name=station_name or station_id,
        equip_type="BUS",
        x=mid_x,
        y=mid_y,
        attrs={"is_room": True, "width": 120, "height": 100},
    )
    loader.devices.append(room)

    # 2. 添加内部开关
    if internal_switches is None:
        internal_switches = []
    if connections is None:
        connections = []

    n = len(internal_switches)
    for idx, (sw_id, sw_name) in enumerate(internal_switches):
        # 纵向排列
        sw_x = mid_x + (idx - (n - 1) / 2) * 40
        sw_y = mid_y + 30

        sw = SVGDevice(
            equip_id=sw_id,
            name=sw_name or sw_id,
            equip_type="SWITCH",
            x=sw_x,
            y=sw_y,
            attrs={"parent_room": station_id},
        )
        loader.devices.append(sw)

        # 开关到站房的连接线（统一从底部引出）
        loader.links.append(SVGLink(
            from_id=sw_id, to_id=station_id,
            x1=sw_x, y1=sw_y - 6,
            x2=mid_x, y2=mid_y,
        ))

        # 按 connections 规则连接
        conn_target = connections[idx] if idx < len(connections) else ""
        if conn_target and conn_target not in ("备用", "standby", "none", ""):
            # 连接到外部设备
            target_dev = loader._dev_by_id(conn_target)
            if target_dev:
                loader.links.append(SVGLink(
                    from_id=sw_id, to_id=conn_target,
                    x1=sw_x, y1=sw_y,
                    x2=target_dev.x, y2=target_dev.y,
                ))

    # 3. 断开原开关之间的直接连接（如果存在）
    loader.links = [ln for ln in loader.links
                    if not (ln.from_id == switch_a and ln.to_id == switch_b)
                    and not (ln.from_id == switch_b and ln.to_id == switch_a)]

    # 4. 站房与两侧开关连接（通过对应内部开关已连）
    # 按测试任务规则：switch_a 接第一个开关，switch_b 接最后一个开关
    if internal_switches:
        first_sw = internal_switches[0][0]
        last_sw = internal_switches[-1][0]

        # 第一个开关接 switch_a
        if not any(ln.from_id == first_sw and ln.to_id == switch_a for ln in loader.links):
            loader.links.append(SVGLink(
                from_id=first_sw, to_id=switch_a,
                x1=mid_x - 40, y1=mid_y + 30,
                x2=dev_a.x, y2=dev_a.y,
            ))
        # 最后一个开关接 switch_b
        if not any(ln.from_id == last_sw and ln.to_id == switch_b for ln in loader.links):
            loader.links.append(SVGLink(
                from_id=last_sw, to_id=switch_b,
                x1=mid_x + 40, y1=mid_y + 30,
                x2=dev_b.x, y2=dev_b.y,
            ))

    # 5. 重新布局并渲染
    loader.title = f"{loader.title} (新增站房 {station_id})"
    loader._tree_layout()
    loader.render(output_path)
    return output_path


def delete_switch_and_connect(svg_path: str, output_path: str, switch_id: str) -> str:
    """
    从 SVG 中删除指定开关图元及标注，将其左右两侧原有设备直接连通。
    """
    loader = SVGLoader.load(svg_path)

    if not loader._dev_by_id(switch_id):
        raise ValueError(f"找不到开关: {switch_id}")

    # 使用 loader.remove_device 并 connect_neighbors=True
    loader.remove_device(switch_id, connect_neighbors=True)

    # 重新布局
    loader.title = f"{loader.title} (删除 {switch_id})"
    loader._tree_layout()
    loader.render(output_path)
    return output_path


# ── 测试任务预设 ──────────────────────────────────────────

def run_test_task1(input_svg: str, output_dir: str):
    """
    测试任务1：
    基于美化后的 LINE215.svg，在开关 00104 与开关 00102 之间新增站房。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output = out / "LINE215_add_station.svg"

    add_station_between(
        svg_path=input_svg,
        output_path=str(output),
        switch_a="00104",
        switch_b="00102",
        station_id="000300",
        station_name="站房 000300",
        internal_switches=[
            ("00301", "开关 00301"),
            ("00302", "开关 00302"),
            ("00303", "开关 00303"),
        ],
        connections=["00104", "备用", "00102"],
    )
    print(f"[OK] 测试任务1完成: {output}")
    return str(output)


def run_test_task2(input_svg: str, output_dir: str):
    """
    测试任务2：
    针对美化后的 LINE216.svg，删除开关 00024。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output = out / "LINE216_del_switch.svg"

    delete_switch_and_connect(
        svg_path=input_svg,
        output_path=str(output),
        switch_id="00024",
    )
    print(f"[OK] 测试任务2完成: {output}")
    return str(output)


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SVG 增删设备工具（任务 5.2）")
    parser.add_argument("--input", required=True, help="5.1 美化后的 SVG 文件或目录")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--mode", choices=["add_station", "del_switch", "test1", "test2"],
                        default="test1", help="操作模式")
    parser.add_argument("--switch-a", default="", help="左侧开关 ID")
    parser.add_argument("--switch-b", default="", help="右侧开关 ID")
    parser.add_argument("--station-id", default="", help="站房 ID")
    parser.add_argument("--station-name", default="", help="站房名称")
    parser.add_argument("--del-id", default="", help="要删除的开关 ID")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "test1":
        run_test_task1(str(input_path), str(output_dir))
    elif args.mode == "test2":
        run_test_task2(str(input_path), str(output_dir))
    elif args.mode == "add_station":
        if not all([args.switch_a, args.switch_b, args.station_id]):
            print("[ERROR] --switch-a, --switch-b, --station-id 必填")
            sys.exit(1)
        output = output_dir / f"add_station_{args.station_id}.svg"
        add_station_between(
            str(input_path), str(output),
            args.switch_a, args.switch_b,
            args.station_id, args.station_name,
        )
        print(f"[OK] 新增站房: {output}")
    elif args.mode == "del_switch":
        if not args.del_id:
            print("[ERROR] --del-id 必填")
            sys.exit(1)
        output = output_dir / f"del_switch_{args.del_id}.svg"
        delete_switch_and_connect(
            str(input_path), str(output), args.del_id,
        )
        print(f"[OK] 删除开关: {output}")


if __name__ == "__main__":
    main()
