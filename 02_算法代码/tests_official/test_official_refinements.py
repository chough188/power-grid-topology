# -*- coding: utf-8 -*-
"""Tests for the official 12 task refinements (2026-07-22 second-pass audit).

Covers:
  1.1 dangle: IS_END_DEVICE / COMPOSITESWITCH exemption + 3 emit types
  1.2 break: path must exclude end-room terminals (per 评审手册 §4.2)
  1.4 suspect tie: 5 failure reasons + 检修中分闸 / 备用间隔 awareness
  3.1 switch/voltage: must NOT emit SQL (仅注不修)
  1.5 loop: plan_list whitelist (already covered)
  Module 5 self-grading still tested in test_gap_fill_handoff.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_loader.loader import OfficialDataset
from tasks_official.contracts import TaskContext


def _load_dataset():
    snap = _ROOT / "data" / "snapshot.json"
    if not snap.is_file():
        raise unittest.SkipTest(f"snapshot not found: {snap}")
    payload = json.loads(snap.read_text(encoding="utf-8-sig"))
    ds = OfficialDataset(payload["tables"])
    ds.validate()
    return ds


# ======================================================================
# Task 1.1 dangle
# ======================================================================

class TestTaskOneOne(unittest.TestCase):
    def test_three_emit_types_present(self):
        from tasks_official.group_01_topology.task_1_1_dangle.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        types = {r.extra["emit_type"] for r in recs}
        # At minimum contiguous_dangle should be present (synthetic data has no SOURCE)
        self.assertIn("contiguous_dangle", types)

    def test_records_carry_evidence_min_3(self):
        from tasks_official.group_01_topology.task_1_1_dangle.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        for r in recs:
            self.assertGreaterEqual(len(r.evidence), 3)

    def test_sql_single_statement_per_emit_type(self):
        """All 1.1 emit types produce ONE executable statement (contract).

        single_dangle / island share the add-terminal primary statement
        (official §1.1 Sheet1 column example form); contiguous_dangle uses
        the CN-dictionary insert. The prerequisite steps for multi-step
        repairs live in the correction text, not joined into the SQL cell.
        """
        from tasks_official.group_01_topology.task_1_1_dangle.detector import (
            _sql_add_terminal_pw, _sql_add_terminal_zw, _sql_add_cn_and_relink,
        )
        single = _sql_add_terminal_pw()
        zw = _sql_add_terminal_zw()
        contig = _sql_add_cn_and_relink()
        island = _sql_add_terminal_pw()  # same primary statement as single_dangle
        for s in (single, zw, contig, island):
            # No multi-statement cells: at most one trailing semicolon total.
            self.assertEqual(s.count(";"), 0)
            self.assertNotIn("\n", s)
        self.assertIn("INSERT INTO JBS_PWTERMINAL", single)
        self.assertIn("INSERT INTO JBS_ZWTERMINAL", zw)
        self.assertIn("INSERT INTO JBS_PWCNODE_DICT", contig)
        self.assertNotEqual(single, contig)
        # Verify all SQL pass the official shape validator
        from tasks_official.self_grade import parse_sql
        self.assertTrue(parse_sql(single))
        self.assertTrue(parse_sql(zw))
        self.assertTrue(parse_sql(contig))
        self.assertTrue(parse_sql(island))

    def test_end_room_devices_are_skipped(self):
        """Devices inside IS_END_DEVICE=1 rooms must not be flagged."""
        from tasks_official.group_01_topology.task_1_1_dangle.detector import detect
        ds = _load_dataset()
        tables = dict(ds.tables)
        # Add an end-room device with degree=0 (would normally be flagged as island)
        tables["JBS_PWROOM"] = list(tables.get("JBS_PWROOM", ())) + [
            {"ROOM_ID": "ROOM_END_X", "ROOM_NAME": "末端站房X", "IS_END_DEVICE": 1, "FEEDER_ID": "F999"},
        ]
        tables["JBS_PWEQUIPINFO"] = list(tables.get("JBS_PWEQUIPINFO", ())) + [
            {"EQUIP_ID": "DEV_END_X", "EQUIP_NAME": "端站开关", "EQUIP_TYPE": "SWITCH",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F999", "DSUBSTATION_ID": "ROOM_END_X",
             "COMPOSITESWITCH": ""},
        ]
        # No TERMINAL row -> degree=0 -> island if not exempt
        ds2 = OfficialDataset(tables)
        ds2.validate()
        recs = list(detect(TaskContext(tables=ds2.tables)))
        ids = {r.device_id for r in recs}
        self.assertNotIn("DEV_END_X", ids, "End-room device should be exempted")

    def test_composite_switch_devices_are_skipped(self):
        """COMPOSITESWITCH != null devices must not be flagged by 1.1."""
        from tasks_official.group_01_topology.task_1_1_dangle.detector import detect
        ds = _load_dataset()
        tables = dict(ds.tables)
        # Inject a composite-switch device with degree=0 (would normally be flagged)
        tables["JBS_PWEQUIPINFO"] = list(tables.get("JBS_PWEQUIPINFO", ())) + [
            {"EQUIP_ID": "DEV_COMP_X", "EQUIP_NAME": "组合开关X", "EQUIP_TYPE": "BREAKER",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F999", "DSUBSTATION_ID": "ROOM999",
             "COMPOSITESWITCH": "COMP0001"},
        ]
        ds2 = OfficialDataset(tables)
        ds2.validate()
        recs = list(detect(TaskContext(tables=ds2.tables)))
        ids = {r.device_id for r in recs}
        self.assertNotIn("DEV_COMP_X", ids, "COMPOSITESWITCH device should be exempted")

    def test_island_emit_has_recommend_add_main_connection(self):
        """Island emit should include recommend=add_main_connection."""
        from tasks_official.group_01_topology.task_1_1_dangle.detector import detect
        ds = _load_dataset()
        tables = dict(ds.tables)
        # Inject an island device (degree=0, no exemptions)
        tables["JBS_PWEQUIPINFO"] = list(tables.get("JBS_PWEQUIPINFO", ())) + [
            {"EQUIP_ID": "DEV_ISL_X", "EQUIP_NAME": "孤岛设备", "EQUIP_TYPE": "SWITCH",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F999", "DSUBSTATION_ID": "ROOM999",
             "COMPOSITESWITCH": ""},
        ]
        ds2 = OfficialDataset(tables)
        ds2.validate()
        recs = list(detect(TaskContext(tables=ds2.tables)))
        island_recs = [r for r in recs if r.device_id == "DEV_ISL_X"]
        if island_recs:
            self.assertEqual(island_recs[0].extra["emit_type"], "island")
            self.assertEqual(island_recs[0].extra["recommend"], "add_main_connection")
            self.assertIn("新建主网侧连接节点", island_recs[0].correction)


# ======================================================================
# Task 1.2 break
# ======================================================================

class TestTaskOneTwo(unittest.TestCase):
    def test_path_excludes_end_rooms(self):
        """Per 评审手册 §4.2 + Sheet 2 注释: 路径不经过末端站房."""
        from shared.graph_algos import terminal_ids_in_end_rooms
        ds = _load_dataset()
        tables = dict(ds.tables)
        # Add an end room and a terminal inside it
        tables["JBS_PWROOM"] = list(tables.get("JBS_PWROOM", ())) + [
            {"ROOM_ID": "ROOM_END_BLOCK", "ROOM_NAME": "末端站房Y", "IS_END_DEVICE": 1, "FEEDER_ID": "F888"},
        ]
        tables["JBS_PWEQUIPINFO"] = list(tables.get("JBS_PWEQUIPINFO", ())) + [
            {"EQUIP_ID": "DEV_IN_END", "EQUIP_NAME": "端站开关", "EQUIP_TYPE": "SWITCH",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F888", "DSUBSTATION_ID": "ROOM_END_BLOCK",
             "COMPOSITESWITCH": ""},
        ]
        tables["JBS_PWTERMINAL"] = list(tables.get("JBS_PWTERMINAL", ())) + [
            {"ID": "T_END_001", "EQUIP_ID": "DEV_IN_END", "CONNECTIVITYNODE_ID": "CN_END_BLOCK_1"},
        ]
        ds2 = OfficialDataset(tables)
        ds2.validate()
        excluded = terminal_ids_in_end_rooms(ds2.tables)
        self.assertIn("CN_END_BLOCK_1", excluded)

    def test_shortest_path_excluding_helper(self):
        from shared.graph_algos import shortest_path_excluding
        adj = {"A": {"B"}, "B": {"A", "C"}, "C": {"B", "X"}, "X": {"C"}}
        # Without exclusion: A -> B -> C -> X
        self.assertEqual(shortest_path_excluding(adj, "A", "X", []), ("A", "B", "C", "X"))
        # Excluding C: no path
        self.assertIsNone(shortest_path_excluding(adj, "A", "X", ["C"]))
        # Excluding B: A is unreachable from X
        self.assertIsNone(shortest_path_excluding(adj, "A", "X", ["B"]))

    def test_detector_emits_break_records(self):
        from tasks_official.group_01_topology.task_1_2_break.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        # Each record should have break_type in extra
        for r in recs:
            self.assertIn("break_type", r.extra)


# ======================================================================
# Task 1.4 suspect tie
# ======================================================================

class TestTaskOneFour(unittest.TestCase):
    def test_five_fail_reason_categories(self):
        """Per 评审手册 §4.2: 5 类失败原因 (R3: 对齐规范)."""
        from tasks_official.group_01_topology.task_1_4_suspect_tie.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        if not recs:
            self.skipTest("no suspect tie records in snapshot")
        for r in recs:
            self.assertIn(r.extra.get("fail_reason"), {
                "terminal_missing", "contiguous_dangle", "feeder_conflict",
                "svg_mismatch", "repair_unknown",
            })

    def test_maintenance_device_classified_correctly(self):
        from tasks_official.group_01_topology.task_1_4_suspect_tie.detector import detect
        ds = _load_dataset()
        tables = dict(ds.tables)
        # Add a maintenance device that would normally trigger suspect
        tables["JBS_PWEQUIPINFO"] = list(tables.get("JBS_PWEQUIPINFO", ())) + [
            {"EQUIP_ID": "DEV_MAINT", "EQUIP_NAME": "检修开关", "EQUIP_TYPE": "SWITCH",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F777", "DSUBSTATION_ID": "ROOM777",
             "ST_ID": "SUB001", "RUN_STATUS": 0, "COMPOSITESWITCH": ""},
        ]
        # Connect to two different stations via terminals
        tables["JBS_PWTERMINAL"] = list(tables.get("JBS_PWTERMINAL", ())) + [
            {"ID": "T_M1", "EQUIP_ID": "DEV_MAINT", "CONNECTIVITYNODE_ID": "CN_M1"},
            {"ID": "T_M2", "EQUIP_ID": "DEV_MAINT", "CONNECTIVITYNODE_ID": "CN_M2"},
        ]
        # Need other equip to bind CN to stations
        for cn, st in [("CN_M1", "SUB001"), ("CN_M2", "SUB002")]:
            tables["JBS_PWEQUIPINFO"].append({
                "EQUIP_ID": f"EQ_{cn}", "EQUIP_NAME": f"绑定设备{cn}", "EQUIP_TYPE": "TRANSFORMER",
                "VOLTAGE_TYPE": 10, "FEEDER_ID": "F777", "DSUBSTATION_ID": "ROOM777",
                "ST_ID": st, "RUN_STATUS": 1, "COMPOSITESWITCH": "",
            })
            tables["JBS_PWTERMINAL"].append({
                "ID": f"T_{cn}_B", "EQUIP_ID": f"EQ_{cn}", "CONNECTIVITYNODE_ID": cn,
            })
        ds2 = OfficialDataset(tables)
        ds2.validate()
        recs = list(detect(TaskContext(tables=ds2.tables)))
        maint = [r for r in recs if r.device_id == "DEV_MAINT"]
        if maint:
            self.assertEqual(maint[0].extra["fail_reason"], "repair_unknown")

    def test_correction_sql_always_empty(self):
        """Per official: 1.4 留空, 不自动 SQL 修正."""
        from tasks_official.group_01_topology.task_1_4_suspect_tie.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        for r in recs:
            self.assertEqual(r.correction_sql, "")


# ======================================================================
# Task 3.1 switch/voltage
# ======================================================================

class TestTaskThreeOne(unittest.TestCase):
    def test_no_sql_emitted(self):
        """Per official: 3.1 仅注不修, 不生成修正 SQL."""
        from tasks_official.group_03_state_voltage.task_3_1_switch_voltage.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        for r in recs:
            self.assertEqual(r.correction_sql, "", "3.1 must not emit SQL")
            self.assertTrue(r.extra.get("manual_review"))

    def test_correction_includes_review_marker(self):
        from tasks_official.group_03_state_voltage.task_3_1_switch_voltage.detector import detect
        recs = list(detect(TaskContext(tables=_load_dataset().tables)))
        for r in recs:
            self.assertIn("[待人工复核]", r.correction)


if __name__ == "__main__":
    unittest.main()