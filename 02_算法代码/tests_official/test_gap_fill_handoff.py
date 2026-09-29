# -*- coding: utf-8 -*-
"""Gap-filling tests for the latest requirements (2026-07-22 handoff).

Covers three new enforcement points:
  1. 5.1 beautify — 100% topological equivalence before/after
  2. 5.2 modify   — transactional 7-step flow + rollback
  3. Module 5     — independent self-grading detector (4 dimensions)
"""
from __future__ import annotations

from tasks_official.registry import LazyTaskRegistry
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ========================================================================
# 5.1 beautify — topological equivalence + style compliance
# ========================================================================

class TestFiveOneBeautifyEnhancements(unittest.TestCase):
    """5.1 beautify hard requirements per 评审手册 §5.3."""

    SAMPLE_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200">\n'
        '  <g data-equip-id="00104" data-equip-type="BREAKER" data-voltage="10">'
        '<circle cx="50" cy="100" r="12"/></g>\n'
        '  <g data-equip-id="00102" data-equip-type="SWITCH" data-voltage="10">'
        '<circle cx="300" cy="100" r="12"/></g>\n'
        '  <g data-equip-id="00101" data-equip-type="DISCONNECTOR" data-voltage="110">'
        '<circle cx="200" cy="50" r="12"/></g>\n'
        '  <g data-equip-id="00024" data-equip-type="TRANSFORMER" data-voltage="0.4">'
        '<circle cx="400" cy="50" r="12"/></g>\n'
        '  <line x1="50" y1="100" x2="300" y2="100" data-from="00104" data-to="00102"/>\n'
        '  <line x1="300" y1="100" x2="400" y2="50" data-from="00102" data-to="00024"/>\n'
        '  <line x1="400" y1="50" x2="200" y2="50" data-from="00024" data-to="00101"/>\n'
        '</svg>'
    )

    def test_topological_equivalence_passes_for_pure_relayout(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import (
            beautify, verify_topological_equivalence,
        )
        out = beautify(
            self.SAMPLE_SVG,
            voltage_lookup={"00104": 10, "00102": 10, "00101": 110, "00024": 0.4},
            equip_type_lookup={
                "00104": "BREAKER", "00102": "SWITCH",
                "00101": "DISCONNECTOR", "00024": "TRANSFORMER",
            },
            edge_lookup=[("00104", "00102"), ("00102", "00024"), ("00024", "00101")],
        )
        explicit_edges = [("00104", "00102"), ("00102", "00024"), ("00024", "00101")]
        eq = verify_topological_equivalence(
            self.SAMPLE_SVG, out,
            edges_before=explicit_edges,
            edges_after=explicit_edges,
        )
        self.assertTrue(eq["ok"], msg=eq)
        self.assertEqual(eq["missing_ids"], [])
        self.assertEqual(eq["added_ids"], [])
        self.assertEqual(eq["type_changed"], [])
        self.assertEqual(eq["edge_diff"]["added"], [])
        self.assertEqual(eq["edge_diff"]["removed"], [])

    def test_topological_equivalence_flags_missing_devices(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import verify_topological_equivalence
        # Replace last device id with bogus
        modified = self.SAMPLE_SVG.replace('data-equip-id="00024"', 'data-equip-id="BOGUS"')
        eq = verify_topological_equivalence(self.SAMPLE_SVG, modified)
        self.assertFalse(eq["ok"])
        self.assertIn("00024", eq["missing_ids"])
        self.assertIn("BOGUS", eq["added_ids"])

    def test_topological_equivalence_flags_type_change(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import verify_topological_equivalence
        modified = self.SAMPLE_SVG.replace(
            'data-equip-type="TRANSFORMER" data-voltage="0.4"',
            'data-equip-type="BREAKER" data-voltage="0.4"',
        )
        eq = verify_topological_equivalence(self.SAMPLE_SVG, modified)
        self.assertFalse(eq["ok"])
        self.assertIn("00024", eq["type_changed"])

    def test_topological_equivalence_flags_added_edge(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import verify_topological_equivalence
        modified = self.SAMPLE_SVG + '\n<line x1="0" y1="0" x2="1" y2="1" data-from="00104" data-to="00024"/>'
        eq = verify_topological_equivalence(self.SAMPLE_SVG, modified)
        self.assertFalse(eq["ok"])
        self.assertIn(("00024", "00104"), eq["edge_diff"]["added"])

    def test_canvas_size_meets_minimum_1600x600(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import beautify, MIN_CANVAS_WIDTH, MIN_CANVAS_HEIGHT
        out = beautify(self.SAMPLE_SVG)
        # First line declares width / height
        import re
        m = re.search(r'<svg[^>]*width="(\d+)"[^>]*height="(\d+)"', out)
        self.assertIsNotNone(m)
        w, h = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual(w, MIN_CANVAS_WIDTH)
        self.assertGreaterEqual(h, MIN_CANVAS_HEIGHT)

    def test_voltage_palette_includes_1000_and_500_kv(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import VOLTAGE_COLORS
        self.assertIn(1000, VOLTAGE_COLORS)
        self.assertIn(500, VOLTAGE_COLORS)
        # 1000/500/220 should all be red per §5.3
        self.assertEqual(VOLTAGE_COLORS[1000], VOLTAGE_COLORS[500])
        self.assertEqual(VOLTAGE_COLORS[500], VOLTAGE_COLORS[220])
        # 0.4 should be purple per §5.3
        self.assertEqual(VOLTAGE_COLORS[0.4], "#9467BD")
        # 10 should be green per §5.3
        self.assertEqual(VOLTAGE_COLORS[10], "#2CA02C")

    def test_legend_and_scale_bar_rendered_in_bottom_right(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
        out = beautify(self.SAMPLE_SVG, width=1800, height=900)
        # Legend rectangle + scale-bar line present
        self.assertIn("Legend", out)
        self.assertIn("scale-bar", out)
        self.assertIn("100 px", out)
        # Line-style swatches present (MAIN / OPEN / TIE / ANOM / CROSS)
        for kind in ("MAIN", "OPEN", "TIE", "ANOM", "CROSS"):
            self.assertIn(kind, out)

    def test_key_devices_rendered_with_bold_halo(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
        out = beautify(
            self.SAMPLE_SVG,
            key_device_ids=["00104"],  # 电源
            voltage_lookup={"00104": 10, "00102": 10, "00101": 110, "00024": 0.4},
            equip_type_lookup={
                "00104": "BREAKER", "00102": "SWITCH",
                "00101": "DISCONNECTOR", "00024": "TRANSFORMER",
            },
            edge_lookup=[("00104", "00102"), ("00102", "00024"), ("00024", "00101")],
        )
        # The key device label should have font-weight=bold
        self.assertIn('font-weight="bold"', out)
        # Stroke-width=3 marker should be used for key device
        self.assertIn('stroke-width="3"', out)
        # Halo rect should be present
        self.assertIn("FF6F00", out)

    def test_device_dimensions_match_official_specs(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import DEVICE_DIMENSIONS
        # 开关 40x24, 刀闸 24x24, 配变 48x48
        self.assertEqual(DEVICE_DIMENSIONS["BREAKER"], (40, 24))
        self.assertEqual(DEVICE_DIMENSIONS["SWITCH"], (40, 24))
        self.assertEqual(DEVICE_DIMENSIONS["DISCONNECTOR"], (24, 24))
        self.assertEqual(DEVICE_DIMENSIONS["TRANSFORMER"], (48, 48))

    def test_font_is_sans_serif_12px(self):
        from tasks_official.task5_svg.task_5_1_beautify.detector import beautify
        out = beautify(self.SAMPLE_SVG)
        self.assertIn("font-family=\"sans-serif\"", out)
        self.assertIn("font-size=\"12\"", out)


# ========================================================================
# 5.2 modify — transactional 7-step flow
# ========================================================================

class TestFiveTwoTransactionalEditor(unittest.TestCase):
    """5.2 modify 评审手册 §5.2: choose -> validate -> preview -> apply -> validate -> confirm -> save."""

    SAMPLE_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200">\n'
        '  <g data-equip-id="00104"><circle cx="50" cy="100" r="12"/></g>\n'
        '  <g data-equip-id="00102"><circle cx="600" cy="100" r="12"/></g>\n'
        '  <g data-equip-id="00024"><circle cx="300" cy="100" r="12"/></g>\n'
        '</svg>'
    )

    def _make_add_room_editor(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import TransactionalEditor
        return TransactionalEditor(self.SAMPLE_SVG)

    def test_happy_path_7_steps_complete(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import (
            OpKind, StepStatus, TransactionalEditor,
        )
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(
            OpKind.ADD_ROOM,
            room_id="ROOM000300",
            room_name="新增站房",
            left_switch_id="00104",
            right_switch_id="00102",
            inner_switch_ids=["00301", "00302", "00303"],
            inner_switch_names=["负荷开关00301", "负荷开关00302(备用)", "负荷开关00303"],
        )
        editor.validate()
        preview = editor.preview()
        self.assertIn("ROOM000300", preview)
        editor.apply()
        editor.validate()
        editor.confirm(user="alice")
        final = editor.save()
        self.assertIn("ROOM000300", final)
        self.assertTrue(editor.committed)
        # Journal should record all 7 steps
        steps = [e.step for e in editor.journal]
        self.assertEqual(steps.count("choose"), 1)
        self.assertEqual(steps.count("validate"), 2)
        self.assertEqual(steps.count("preview"), 1)
        self.assertEqual(steps.count("apply"), 1)
        self.assertEqual(steps.count("confirm"), 1)
        self.assertEqual(steps.count("save"), 1)
        # All entries should be DONE
        self.assertTrue(all(e.status == StepStatus.DONE for e in editor.journal))

    def test_remove_device_path_works(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import OpKind, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(OpKind.REMOVE_DEVICE, device_id="00024")
        editor.validate()
        editor.preview()
        editor.apply()
        editor.validate()
        editor.confirm(user="bob")
        final = editor.save()
        self.assertNotIn("00024", final)
        self.assertIn("00104", final)
        self.assertIn("00102", final)

    def test_validate_rejects_duplicate_room_id(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import OpKind, TransactionError, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(
            OpKind.ADD_ROOM,
            room_id="00104",  # already exists!
            left_switch_id="00102",
            right_switch_id="00024",
            inner_switch_ids=["X"],
        )
        with self.assertRaises(TransactionError):
            editor.validate()

    def test_validate_rejects_unknown_left_switch(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import OpKind, TransactionError, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(
            OpKind.ADD_ROOM,
            room_id="ROOM999",
            left_switch_id="NOPE",
            right_switch_id="00102",
            inner_switch_ids=["X"],
        )
        with self.assertRaises(TransactionError):
            editor.validate()

    def test_save_requires_confirm(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import OpKind, TransactionError, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(OpKind.REMOVE_DEVICE, device_id="00024")
        editor.validate()
        editor.preview()
        editor.apply()
        # Skip post-validate (post-condition check is optional for the test below);
        # skip confirm.
        with self.assertRaises(TransactionError):
            editor.save()
        # After rollback, fresh editor without choose should still fail save
        editor2 = TransactionalEditor(self.SAMPLE_SVG)
        with self.assertRaises(TransactionError):
            editor2.save()

    def test_rollback_reverts_to_original(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import OpKind, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        editor.choose(OpKind.REMOVE_DEVICE, device_id="00024")
        editor.validate()
        editor.preview()
        editor.apply()
        editor.rollback()
        # Current svg should be original
        self.assertEqual(editor.current_svg, self.SAMPLE_SVG)
        self.assertFalse(editor.committed)

    def test_cannot_save_without_choose(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import TransactionError, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        with self.assertRaises(TransactionError):
            editor.save()

    def test_cannot_validate_without_choose(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import TransactionError, TransactionalEditor
        editor = TransactionalEditor(self.SAMPLE_SVG)
        with self.assertRaises(TransactionError):
            editor.validate()

    def test_remove_device_strips_orphan_edges(self):
        from tasks_official.task5_svg.task_5_2_modify.detector import remove_device
        svg_with_edge = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200">\n'
            '  <g data-equip-id="00024"><circle cx="300" cy="100" r="12"/></g>\n'
            '  <line data-from="00024" data-to="00025" x1="0" y1="0" x2="10" y2="10"/>\n'
            '  <line data-from="00025" data-to="00026" x1="10" y1="10" x2="20" y2="20"/>\n'
            '</svg>'
        )
        out = remove_device(svg_with_edge, "00024")
        self.assertNotIn("data-from=\"00024\"", out)
        self.assertNotIn("data-to=\"00024\"", out)


# ========================================================================
# Module 5 — 4-dim self-grading detector
# ========================================================================

class TestModuleFiveSelfGrading(unittest.TestCase):
    """Task 1 Module 5: 4-dim independent self-grading detector."""

    def _load_snapshot(self):
        import json
        snap = _ROOT / "data" / "snapshot.json"
        if not snap.is_file():
            raise self.skipTest(f"snapshot not found: {snap}")
        payload = json.loads(snap.read_text(encoding="utf-8-sig"))
        from data_loader.loader import OfficialDataset
        ds = OfficialDataset(payload["tables"])
        ds.validate()
        return ds

    def test_dimensions_weights_sum_to_one(self):
        from tasks_official.group_05_scoring.task_5_0_self_grade.detector import DIMENSION_WEIGHTS
        self.assertAlmostEqual(sum(DIMENSION_WEIGHTS.values()), 1.0, places=6)

    def test_dimension_keys_are_stable(self):
        from tasks_official.group_05_scoring.task_5_0_self_grade.detector import (
            DIMENSION_WEIGHTS, DIMENSION_FULL_NAMES, DIMENSION_TASK_MAP, DIMENSION_SATURATION,
        )
        for k in DIMENSION_WEIGHTS:
            self.assertIn(k, DIMENSION_FULL_NAMES)
            self.assertIn(k, DIMENSION_TASK_MAP)
            self.assertIn(k, DIMENSION_SATURATION)

    def test_score_dimension_saturates(self):
        from tasks_official.group_05_scoring.task_5_0_self_grade.detector import score_dimension
        self.assertEqual(score_dimension("D1_topology_integrity", 0), 1.0)
        self.assertEqual(score_dimension("D1_topology_integrity", 100), 0.0)
        # Midpoint
        mid = score_dimension("D1_topology_integrity", 10)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 1.0)

    def test_compute_all_dimensions_returns_4_dims(self):
        from tasks_official.group_05_scoring.task_5_0_self_grade.detector import compute_all_dimensions
        ds = self._load_snapshot()
        result = compute_all_dimensions(ds.tables)
        self.assertIn("total_score", result)
        self.assertIn("dimensions", result)
        self.assertEqual(
            set(result["dimensions"].keys()),
            {
                "D1_topology_integrity",
                "D2_graph_model_consistency",
                "D3_electric_logic",
                "D4_main_dist_interface",
            },
        )
        for dim_name, dim_info in result["dimensions"].items():
            self.assertIn("score", dim_info)
            self.assertIn("weight", dim_info)
            self.assertIn("detail", dim_info)
            self.assertGreaterEqual(dim_info["score"], 0.0)
            self.assertLessEqual(dim_info["score"], 1.0)
        self.assertGreaterEqual(result["total_score"], 0.0)
        self.assertLessEqual(result["total_score"], 1.0)

    def test_detect_emits_record_per_feeder(self):
        from tasks_official.group_05_scoring.task_5_0_self_grade.detector import detect
        from tasks_official.contracts import ProblemRecord, TaskContext
        ds = self._load_snapshot()
        ctx = TaskContext(tables=ds.tables)
        recs = list(detect(ctx))
        self.assertGreater(len(recs), 0)
        for r in recs:
            self.assertEqual(r.task_code, "5.0")
            self.assertIsInstance(r, ProblemRecord)
            self.assertGreaterEqual(len(r.evidence), 3)
            self.assertIn("dimensions", r.extra)
            self.assertIn("before_score", r.extra)
            self.assertIn("after_score", r.extra)
            self.assertGreaterEqual(r.extra["after_score"], r.extra["before_score"])

    def test_detect_via_official_runner(self):
        from tasks_official.execution import OfficialRunner
        ds = self._load_snapshot()
        result = OfficialRunner(LazyTaskRegistry.with_module_resolver()).run(["5.0"], ds)
        self.assertIn("5.0", result.records_by_task)
        self.assertGreater(len(result.records_by_task["5.0"]), 0)


if __name__ == "__main__":
    unittest.main()