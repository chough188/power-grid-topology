#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SVG Engine 扩展测试：edit_device + 大数据集 + 端到端验证"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from svg_engine.svg_loader import SVGLoader, SVGDevice
from svg_engine import beautify
from svg_engine import auto_generate
from svg_engine import edit_device

out_dir = Path(r"E:/dianli/xiangmu/dianli/电力拓扑图修正/04_SVG输出")
input_dir = Path(r"E:/dianli/xiangmu/dianli/电力拓扑图修正/03_数据集/svg_input")
json_dir = Path(r"E:/dianli/xiangmu/dianli/电力拓扑图修正/03_数据集")

print("=" * 60)
print("SVG 引擎扩展测试")
print("=" * 60)

# ── TEST 5: edit_device 删除开关 ─────────────────────────
print("\n[TEST 5] 删除开关测试")
try:
    # 先用一个已有的 beautified svg
    src = out_dir / "5.1_原始美化图" / "IEEE13Nodeckt_beautified.svg"
    if src.exists():
        output = out_dir / "5.2_设备增删修正图" / "IEEE13Nodeckt_del_test.svg"
        # 找一个开关来删除
        loader = SVGLoader.load(str(src))
        sw_to_del = None
        for d in loader.devices:
            if d.equip_type in ("SWITCH", "BREAKER"):
                sw_to_del = d.equip_id
                break
        if sw_to_del:
            edit_device.delete_switch_and_connect(str(src), str(output), sw_to_del)
            print(f"  删除开关: {sw_to_del}")
            print(f"  输出: {output} ({output.stat().st_size} bytes)")
            print("  [PASS]")
        else:
            print("  [SKIP] 无开关可删除")
    else:
        print(f"  [SKIP] 源文件不存在: {src}")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── TEST 6: 用 IEEE123 大数据集生成单线图 ───────────────
print("\n[TEST 6] IEEE123 大数据集单线图")
try:
    ieee123_json = json_dir / "official_base_networks_opendss_v1" / "IEEE123Master_official_snapshot.json"
    if ieee123_json.exists():
        output = out_dir / "5.3_自动生成图" / "单线图" / "IEEE123Master_single.svg"
        auto_generate.generate_single_line(str(ieee123_json), "FD_IEEE123Master", str(output))
        print(f"  输出: {output} ({output.stat().st_size} bytes)")
        print("  [PASS]")
    else:
        print(f"  [SKIP] 数据集不存在: {ieee123_json}")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── TEST 7: 用 LINE215.svg 测试美化 ──────────────────────
print("\n[TEST 7] LINE215.svg 美化")
try:
    line215 = input_dir / "LINE215.svg"
    if line215.exists():
        output = out_dir / "5.1_原始美化图" / "LINE215_beautified.svg"
        beautify.beautify_svg(str(line215), str(output), title="美化: LINE215")
        print(f"  输出: {output} ({output.stat().st_size} bytes)")
        print("  [PASS]")
    else:
        print(f"  [SKIP] 输入文件不存在: {line215}")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── TEST 8: 批量美化目录 ─────────────────────────────────
print("\n[TEST 8] 批量美化 svg_input 目录")
try:
    if input_dir.exists() and list(input_dir.glob("*.svg")):
        output = out_dir / "5.1_原始美化图"
        beautify.batch_beautify(str(input_dir), str(output))
        print("  [PASS]")
    else:
        print(f"  [SKIP] 输入目录为空: {input_dir}")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()

# ── 汇总 ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("输出文件汇总")
print("=" * 60)

for subdir in ["5.1_原始美化图", "5.2_设备增删修正图", "5.3_自动生成图"]:
    d = out_dir / subdir
    if d.exists():
        files = list(d.rglob("*.svg"))
        print(f"\n{subdir}/: {len(files)} 个 SVG 文件")
        for f in sorted(files)[:5]:
            print(f"  - {f.name} ({f.stat().st_size} bytes)")
        if len(files) > 5:
            print(f"  ... 共 {len(files)} 个")

print("\n" + "=" * 60)
print("扩展测试完成")
print("=" * 60)
