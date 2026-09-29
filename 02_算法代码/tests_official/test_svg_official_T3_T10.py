# -*- coding: utf-8 -*-
"""官方固定测试 T3–T10 专用单元测试（SVG 美化/增删/自动出图）。"""
from __future__ import annotations

import unittest
from pathlib import Path

from data_loader.svg_synth import make_synthetic_svg
from tasks_official.task5_svg.task_5_1_beautify.detector import (
    beautify,
    verify_topological_equivalence,
    _parse_devices,
    _parse_edges,
)
from tasks_official.task5_svg.task_5_2_modify.detector import (
    add_room_with_switches,
    remove_device,
)
from tasks_official.task5_svg.task_5_3_auto_draw.detector import (
    render_5_3_1_single_feeder,
    render_5_3_2_tie_diagram,
    render_5_3_3_substation_diagram,
    render_5_3_4_power_trace,
)


SAMPLE_SVG_LIKE_LINE215 = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400">\n'
    '  <g data-equip-id="00104" data-equip-type="BREAKER" data-voltage="10"><circle cx="50" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00102" data-equip-type="SWITCH" data-voltage="10"><circle cx="200" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00101" data-equip-type="DISCONNECTOR" data-voltage="10"><circle cx="350" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00103" data-equip-type="TRANSFORMER" data-voltage="0.4"><circle cx="500" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00024" data-equip-type="BREAKER" data-voltage="10"><circle cx="650" cy="100" r="12"/></g>\n'
    '  <line x1="62" y1="100" x2="188" y2="100" data-from="00104" data-to="00102"/>\n'
    '  <line x1="212" y1="100" x2="338" y2="100" data-from="00102" data-to="00101"/>\n'
    '  <line x1="362" y1="100" x2="488" y2="100" data-from="00101" data-to="00103"/>\n'
    '  <line x1="512" y1="100" x2="638" y2="100" data-from="00103" data-to="00024"/>\n'
    '</svg>'
)

SAMPLE_SVG_LIKE_LINE216 = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200">\n'
    '  <g data-equip-id="00021" data-equip-type="BREAKER"><circle cx="50" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00022" data-equip-type="SWITCH"><circle cx="150" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00023" data-equip-type="DISCONNECTOR"><circle cx="250" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00024" data-equip-type="BREAKER"><circle cx="350" cy="100" r="12"/></g>\n'
    '  <g data-equip-id="00025" data-equip-type="TRANSFORMER"><circle cx="450" cy="100" r="12"/></g>\n'
    '  <line x1="62" y1="100" x2="138" y2="100" data-from="00021" data-to="00022"/>\n'
    '  <line x1="162" y1="100" x2="238" y2="100" data-from="00022" data-to="00023"/>\n'
    '  <line x1="262" y1="100" x2="338" y2="100" data-from="00023" data-to="00024"/>\n'
    '  <line x1="362" y1="100" x2="438" y2="100" data-from="00024" data-to="00025"/>\n'
    '</svg>'
)


class T3_T4_BeautifyTests(unittest.TestCase):
    """T3 (LINE215.svg 美化) / T4 (LINE216.svg 美化)"""

    def setUp(self):
        self.voltage_lookup = {"00104": 10, "00102": 10, "00101": 10, "00103": 0.4, "00024": 10}
        self.type_lookup = {"00104": "BREAKER", "00102": "SWITCH",
                            "00101": "DISCONNECTOR", "00103": "TRANSFORMER", "00024": "BREAKER"}
        self.edges = [("00104", "00102"), ("00102", "00101"), ("00101", "00103"), ("00103", "00024")]

    def test_T3_official_LINE215_beautify(self):
        out = beautify(SAMPLE_SVG_LIKE_LINE215, voltage_lookup=self.voltage_lookup,
                       equip_type_lookup=self.type_lookup, edge_lookup=self.edges)
        self.assertTrue(out.startswith("<svg"))
        for eid in ["00104", "00102", "00101", "00103", "00024"]:
            self.assertIn(eid, out)
        self.assertIn("kV", out)
        self.assertGreater(len(out), 800)

    def test_T4_official_LINE216_beautify(self):
        edges = [("00021", "00022"), ("00022", "00023"), ("00023", "00024"), ("00024", "00025")]
        vl = {"00021": 10, "00022": 10, "00023": 10, "00024": 10, "00025": 0.4}
        tl = {"00021": "BREAKER", "00022": "SWITCH", "00023": "DISCONNECTOR",
              "00024": "BREAKER", "00025": "TRANSFORMER"}
        out = beautify(SAMPLE_SVG_LIKE_LINE216, voltage_lookup=vl,
                       equip_type_lookup=tl, edge_lookup=edges)
        self.assertTrue(out.startswith("<svg"))
        for eid in ["00021", "00022", "00023", "00024", "00025"]:
            self.assertIn(eid, out)
        self.assertIn("kV", out)

    def test_beautify_topology_preserved(self):
        svg, lookups = make_synthetic_svg(n_devices=8, seed=42)
        devices = _parse_devices(svg)
        edges = _parse_edges(svg)
        out = beautify(svg, voltage_lookup=lookups["voltage_lookup"],
                       equip_type_lookup=lookups["equip_type_lookup"],
                       edge_lookup=edges)
        res = verify_topological_equivalence(svg, out, edges_before=edges, edges_after=edges)
        self.assertTrue(res["ok"], f"topology not preserved: {res['summary']}")

    def test_beautify_handles_empty_svg(self):
        with self.assertRaises((ValueError, RuntimeError)):
            beautify("", voltage_lookup={}, equip_type_lookup={})


class T5_T6_ModifyTests(unittest.TestCase):
    """T5 (LINE215 加站房) / T6 (LINE216 删开关)"""

    def test_T5_official_LINE215_add_room_with_switches(self):
        out = add_room_with_switches(
            SAMPLE_SVG_LIKE_LINE215,
            room_id="ROOM_TEST_001",
            room_name="新增站房",
            left_switch_id="00104",
            right_switch_id="00102",
            inner_switch_ids=["SW001", "SW002"],
            inner_switch_names={"SW001": "负荷开关SW001", "SW002": "负荷开关SW002(备用)"},
        )
        self.assertIn("ROOM_TEST_001", out)
        self.assertIn("SW001", out)
        self.assertIn("备用", out)

    def test_T6_official_LINE216_delete_switch(self):
        out = remove_device(SAMPLE_SVG_LIKE_LINE216, "00024")
        self.assertNotIn("00024", out)
        self.assertIn("00021", out)
        self.assertIn("00025", out)

    def test_remove_nonexistent_device_returns_unchanged(self):
        result = remove_device(SAMPLE_SVG_LIKE_LINE216, "NONEXIST")
        self.assertEqual(result, SAMPLE_SVG_LIKE_LINE216)

    def test_add_room_preserves_existing_devices(self):
        before_count = SAMPLE_SVG_LIKE_LINE215.count("data-equip-id")
        out = add_room_with_switches(
            SAMPLE_SVG_LIKE_LINE215,
            room_id="ROOM_X",
            room_name="测试站房",
            left_switch_id="00104",
            right_switch_id="00102",
            inner_switch_ids=["S1"],
            inner_switch_names={"S1": "S1"},
        )
        after_count = out.count("data-equip-id")
        self.assertGreater(after_count, before_count)


class T7_T10_AutoDrawTests(unittest.TestCase):
    """T7 (单线图) / T8 (联络图) / T9 (全站图) / T10 (电源追溯)。

    数据驱动:从快照动态选取设备最多的馈线/变电站与可追溯设备
    (真实数据下旧合成 ID F101/ST001/TMP00000007-as-device 不存在;
    渲染前按流水线口径做 EQUIP_TYPE 归一,与 gui/auto_pipeline 一致)。
    """

    @classmethod
    def setUpClass(cls):
        snap = Path(__file__).resolve().parents[1] / "data" / "snapshot.json"
        if not snap.is_file():
            raise unittest.SkipTest(f"snapshot not found, T7-T10 depend on 14-table data")
        import json
        from collections import Counter
        from data_loader.loader import OfficialDataset
        from data_loader.object_dictionary import normalize_dataset_types
        payload = json.loads(snap.read_text(encoding="utf-8-sig"))
        ds = OfficialDataset(payload["tables"])
        ds.validate()
        cls.tables = normalize_dataset_types(ds.tables)
        pw = list(cls.tables.get("JBS_PWEQUIPINFO", ()))
        feeder_count = Counter(d.get("FEEDER_ID") for d in pw if d.get("FEEDER_ID"))
        cls.top_feeder = feeder_count.most_common(1)[0][0]
        st_count = Counter(r.get("START_ST_ID") for r in cls.tables.get("JBS_PWFEEDERLINE", ())
                           if r.get("START_ST_ID"))
        cls.top_station = st_count.most_common(1)[0][0] if st_count else None
        term_eids = {r.get("EQUIP_ID") for r in cls.tables.get("JBS_PWTERMINAL", ())}
        cls.trace_device = next(
            (d.get("EQUIP_ID") for d in pw
             if d.get("FEEDER_ID") == cls.top_feeder and d.get("EQUIP_ID") in term_eids),
            None,
        )

    def test_T7_official_single_feeder_diagram(self):
        out = render_5_3_1_single_feeder(self.tables, self.top_feeder, title="T7单线图")
        self.assertTrue(out.startswith("<svg"))
        self.assertGreater(len(out), 500)
        self.assertIn("T7", out)

    def test_T8_official_tie_diagram(self):
        out = render_5_3_2_tie_diagram(self.tables, self.top_feeder)
        self.assertTrue(out.startswith("<svg"))

    def test_T9_official_substation_diagram(self):
        out = render_5_3_3_substation_diagram(self.tables, self.top_station)
        self.assertTrue(out.startswith("<svg"))
        self.assertGreater(len(out), 500)

    def test_T10_official_power_trace(self):
        out = render_5_3_4_power_trace(self.tables, self.trace_device)
        self.assertTrue(out.startswith("<svg"))
        self.assertIn("main", out)

    def test_all_renderings_have_unique_content(self):
        import hashlib
        outs = {}
        for name, fn, arg in [
            ("T7", render_5_3_1_single_feeder, ("F101",)),
            ("T8", render_5_3_2_tie_diagram, ("F101",)),
            ("T9", render_5_3_3_substation_diagram, ("ST001",)),
            ("T10", render_5_3_4_power_trace, ("TMP00000007",)),
        ]:
            out = fn(self.tables, *arg) if len(arg) == 1 else fn(self.tables, arg[0])
            h = hashlib.md5(out.encode()).hexdigest()
            outs[name] = h
        self.assertEqual(len(set(outs.values())), 4,
                         msg="Each T7-T10 rendering should produce distinct SVG content")


if __name__ == "__main__":
    unittest.main()
