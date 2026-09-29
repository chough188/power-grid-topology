# -*- coding: utf-8 -*-
"""SVG synth 与 5.1 美化 单元测试。"""
import unittest
from pathlib import Path

from data_loader.svg_synth import make_synthetic_svg, write_synthetic_svg
from tasks_official.task5_svg.task_5_1_beautify.detector import (
    beautify,
    verify_topological_equivalence,
    _parse_devices,
    _parse_edges,
)


class SvgSynthTests(unittest.TestCase):
    def test_make_synthetic_svg_basic(self):
        svg, lookups = make_synthetic_svg(n_devices=8, seed=42)
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertEqual(len(lookups["voltage_lookup"]), 8)
        self.assertEqual(len(lookups["equip_type_lookup"]), 8)
        self.assertGreater(len(lookups["edges"]), 0)

    def test_make_synthetic_svg_uses_required_attrs(self):
        svg, _ = make_synthetic_svg(n_devices=5)
        # 必须包含 data-equip-id, data-equip-type, data-voltage
        self.assertIn('data-equip-id="TMP00000001"', svg)
        self.assertIn('data-equip-type=', svg)
        self.assertIn('data-voltage=', svg)
        # 必须包含 data-from / data-to (边)
        self.assertIn('data-from=', svg)
        self.assertIn('data-to=', svg)


class SvgBeautifyIntegrationTests(unittest.TestCase):
    def test_beautify_preserves_topology(self):
        svg, lookups = make_synthetic_svg(n_devices=10, seed=42)
        devices = _parse_devices(svg)
        edges = _parse_edges(svg)
        self.assertEqual(len(devices), 10)
        self.assertEqual(len(edges), 10)

        out = beautify(
            svg,
            voltage_lookup=lookups["voltage_lookup"],
            equip_type_lookup=lookups["equip_type_lookup"],
            edge_lookup=edges,
        )
        # 输出必须比输入更"美化"(至少包含图例/标题/规范化样式)
        self.assertGreater(len(out), len(svg) * 0.9)

        res = verify_topological_equivalence(
            svg, out, edges_before=edges, edges_after=edges
        )
        self.assertTrue(res["ok"], f"美化后拓扑必须等价: {res['summary']}")
        self.assertEqual(res["type_changed"], [])

    def test_beautify_handles_small_svg(self):
        svg, lookups = make_synthetic_svg(n_devices=3, seed=7)
        edges = _parse_edges(svg)
        out = beautify(
            svg,
            voltage_lookup=lookups["voltage_lookup"],
            equip_type_lookup=lookups["equip_type_lookup"],
            edge_lookup=edges,
        )
        res = verify_topological_equivalence(svg, out, edges_before=edges, edges_after=edges)
        self.assertTrue(res["ok"])


if __name__ == "__main__":
    unittest.main()
