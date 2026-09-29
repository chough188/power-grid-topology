#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SVG Engine 综合测试脚本"""

import sys
from pathlib import Path

# 将 svg_engine 加入路径
sys.path.insert(0, str(Path(__file__).parent))

from svg_engine.svg_loader import SVGLoader, build_graph_from_json, load_snapshot
from svg_engine import beautify
from svg_engine import auto_generate

print("=" * 60)
print("SVG 引擎综合测试")
print("=" * 60)

# ── 测试 1: 解析现有 SVG ────────────────────────────────
svg_path = r"E:/dianli/xiangmu/dianli/电力拓扑图修正/03_数据集/official_base_networks_opendss_v1/IEEE13Nodeckt_official_snapshot.svg"
print(f"\n[TEST 1] 解析 SVG: {svg_path}")
try:
    loader = SVGLoader.load(svg_path)
    print(f"  设备数: {len(loader.devices)}")
    print(f"  连接数: {len(loader.links)}")
    print(f"  标题: {loader.title}")
    if loader.devices:
        d = loader.devices[0]
        print(f"  首个设备: {d.equip_id} ({d.equip_type}) @ ({d.x:.0f}, {d.y:.0f})")
    print("  [PASS]")
except Exception as e:
    print(f"  [FAIL] {e}")

# ── 测试 2: 美化 SVG ────────────────────────────────────
print(f"\n[TEST 2] 美化 SVG")
out_dir = r"E:/dianli/xiangmu/dianli/电力拓扑图修正/04_SVG输出/5.1_原始美化图"
try:
    output = f"{out_dir}/IEEE13Nodeckt_beautified.svg"
    beautify.beautify_svg(svg_path, output, title="美化: IEEE13Nodeckt")
    print(f"  输出: {output}")
    # 验证输出文件
    out_path = Path(output)
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  文件大小: {out_path.stat().st_size} bytes")
        print("  [PASS]")
    else:
        print("  [FAIL] 输出文件无效")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── 测试 3: 从 JSON 生成单线图 ──────────────────────────
print(f"\n[TEST 3] 自动生成单线图")
json_path = r"E:/dianli/xiangmu/dianli/电力拓扑图修正/03_数据集/official_base_networks_v1/example_simple_official_snapshot.json"
try:
    output = f"{out_dir}/example_simple_single.svg"
    auto_generate.generate_single_line(json_path, "FD_example_simple", output)
    print(f"  输出: {output}")
    out_path = Path(output)
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  文件大小: {out_path.stat().st_size} bytes")
        print("  [PASS]")
    else:
        print("  [FAIL] 输出文件无效")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── 测试 4: 从 JSON 生成电源追溯图 ──────────────────────
print(f"\n[TEST 4] 生成电源追溯路径图")
try:
    snapshot = load_snapshot(json_path)
    graph = build_graph_from_json(snapshot)
    # 找一个非电源设备
    target = None
    for nid, data in graph["nodes"].items():
        if data.get("type") not in ("SOURCE", "SUBSTATION"):
            target = nid
            break
    if target:
        output = f"{out_dir}/example_simple_trace.svg"
        auto_generate.generate_trace_path(json_path, target, output)
        print(f"  目标设备: {target}")
        print(f"  输出: {output}")
        out_path = Path(output)
        if out_path.exists() and out_path.stat().st_size > 100:
            print(f"  文件大小: {out_path.stat().st_size} bytes")
            print("  [PASS]")
        else:
            print("  [FAIL] 输出文件无效")
    else:
        print("  [SKIP] 无合适目标设备")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
