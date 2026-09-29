# -*- coding: utf-8 -*-
"""Smoke tests for the official SVG 5.x detectors.

Run:
    python -X utf8 -m unittest tests_official.test_svg_5x_smoke -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_loader.loader import OfficialDataset  # noqa: E402


class SvgFiveXSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        snap = _ROOT / "data" / "snapshot.json"
        if not snap.is_file():
            raise unittest.SkipTest(f"snapshot not found: {snap}")
        from collections import Counter
        from data_loader.object_dictionary import normalize_dataset_types
        payload = json.loads(snap.read_text(encoding="utf-8-sig"))
        ds = OfficialDataset(payload["tables"])
        ds.validate()
        # 与 gui/auto_pipeline 一致:渲染前做 EQUIP_TYPE 归一(真实数据 OBJ_CODE)
        cls.tables = normalize_dataset_types(ds.tables)
        pw = list(cls.tables.get("JBS_PWEQUIPINFO", ()))
        feeder_count = Counter(d.get("FEEDER_ID") for d in pw if d.get("FEEDER_ID"))
        cls.top_feeder, _ = feeder_count.most_common(1)[0]
        st_count = Counter(r.get("START_ST_ID") for r in cls.tables.get("JBS_PWFEEDERLINE", ())
                           if r.get("START_ST_ID"))
        cls.top_station = st_count.most_common(1)[0][0] if st_count else None
        term_eids = {r.get("EQUIP_ID") for r in cls.tables.get("JBS_PWTERMINAL", ())}
        cls.trace_device = next(
            (d.get("EQUIP_ID") for d in pw
             if d.get("FEEDER_ID") == cls.top_feeder and d.get("EQUIP_ID") in term_eids),
            None,
        )
        # 该馈线第一个设备 ID,用于断言"馈线设备确实被渲染"
        cls.first_dev = next((d.get("EQUIP_ID") for d in pw
                              if d.get("FEEDER_ID") == cls.top_feeder), None)

    def test_5_3_1_single_feeder_renders(self) -> None:
        from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_5_3_1_single_feeder
        out = render_5_3_1_single_feeder(dict(self.tables), self.top_feeder, title="smoke")
        self.assertTrue(out.startswith("<svg"))
        # Verify top-feeder devices are rendered
        if self.first_dev:
            self.assertIn(self.first_dev, out)
        self.assertGreater(len(out), 500)

    def test_5_3_2_tie_diagram_renders(self) -> None:
        from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_5_3_2_tie_diagram
        out = render_5_3_2_tie_diagram(dict(self.tables), self.top_feeder)
        self.assertTrue(out.startswith("<svg"))

    def test_5_3_3_substation_diagram_renders(self) -> None:
        from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_5_3_3_substation_diagram
        out = render_5_3_3_substation_diagram(dict(self.tables), self.top_station)
        self.assertTrue(out.startswith("<svg"))

    def test_5_3_4_power_trace_renders_with_main_and_backup(self) -> None:
        from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_5_3_4_power_trace
        out = render_5_3_4_power_trace(dict(self.tables), self.trace_device)
        self.assertTrue(out.startswith("<svg"))
        self.assertIn("main", out)

    def test_5_2_add_room_with_switches(self) -> None:
        from tasks_official.task5_svg.task_5_2_modify.detector import add_room_with_switches
        sample_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200">\n'
            '  <g data-equip-id="00104"><circle cx="50" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00102"><circle cx="600" cy="100" r="12"/></g>\n'
            '</svg>'
        )
        out = add_room_with_switches(
            sample_svg,
            room_id="ROOM000300",
            room_name="新增站房",
            left_switch_id="00104",
            right_switch_id="00102",
            inner_switch_ids=["00301", "00302", "00303"],
            inner_switch_names=["负荷开关00301", "负荷开关00302(备用)", "负荷开关00303"],
        )
        self.assertIn("ROOM000300", out)
        self.assertIn("00301", out)
        self.assertIn("备用间隔", out)

    def test_5_2_remove_device(self) -> None:
        from tasks_official.task5_svg.task_5_2_modify.detector import remove_device
        sample_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200">\n'
            '  <g data-equip-id="00024"><circle cx="100" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00025"><circle cx="200" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00023"><circle cx="50"  cy="100" r="12"/></g>\n'
            '</svg>'
        )
        out = remove_device(sample_svg, "00024")
        self.assertNotIn("00024", out)
        self.assertIn("00025", out)
        self.assertIn("00023", out)



    def test_5_1_beautify_renders(self) -> None:
        """T3/T4 (LINE215/LINE216): 5.1 beautify re-layouts devices on a grid."""
        from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
        sample_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200">\n'
            '  <g data-equip-id="00104"><circle cx="50" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00102"><circle cx="300" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00101"><circle cx="200" cy="50" r="12"/></g>\n'
            '  <g data-equip-id="00103"><circle cx="500" cy="100" r="12"/></g>\n'
            '  <g data-equip-id="00024"><circle cx="400" cy="50" r="12"/></g>\n'
            '</svg>'
        )
        out = beautify(
            sample_svg,
            voltage_lookup={"00104": 10, "00102": 10, "00101": 10, "00103": 0.4, "00024": 110},
            equip_type_lookup={"00104": "BREAKER", "00102": "SWITCH",
                               "00101": "DISCONNECTOR", "00103": "TRANSFORMER",
                               "00024": "BUS"},
        )
        self.assertTrue(out.startswith("<svg"))
        for eid in ["00104", "00102", "00101", "00103", "00024"]:
            self.assertIn(eid, out)
        self.assertIn("kV", out)  # voltage legend
        self.assertGreater(out.count("font-weight=" + chr(34) + "bold" + chr(34)), 0)


if __name__ == "__main__":
    unittest.main()
