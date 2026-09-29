# -*- coding: utf-8 -*-
"""Task 2.4: 图形物理断开、拓扑逻辑误连通校验 — 单元测试.

验证逻辑：
  - 闭合设备A（RUN_STATUS=1, POINT=1）挂在节点N上
  - 分位开关B（RUN_STATUS=0, POINT=0）也挂在同一节点N
  - B 分位但仍通过N连接到A -> 拓扑逻辑误连通（false_link）
  - detector 应输出 correction_sql 包含 DELETE TERMINAL
"""
from __future__ import annotations

import unittest

from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.group_02_graph_model.task_2_4_phys_break_logi_connect.detector import (
    detect,
    SEVERITY_DEFAULT,
)


def _make_tables(equip_rows, terminal_rows, signal_rows=None):
    signal_rows = signal_rows or []
    return {
        "JBS_PWEQUIPINFO": [e for e in equip_rows if e.get("FEEDER_ID")],
        "JBS_ZWEQUIPINFO": [e for e in equip_rows if not e.get("FEEDER_ID")],
        "JBS_PWTERMINAL": [t for t in terminal_rows if t.get("TABLE") == "PW"],
        "JBS_ZWTERMINAL": [t for t in terminal_rows if t.get("TABLE") == "ZW"],
        # JBS_PWREAL: key is TRAN_ID (maps to EQUIP_ID), POINT=1=closed, 0=open
        "JBS_PWREAL": [
            s for s in signal_rows if s.get("table") == "PW"
        ],
        # JBS_ZWSIGNAL: key is EQUIP_ID or ID
        "JBS_ZWSIGNAL": [
            s for s in signal_rows if s.get("table") == "ZW"
        ],
    }


class TestTask24PhysBreakLogiConnect(unittest.TestCase):

    def test_false_link_detected_between_open_and_closed(self):
        """闭合母联与分位开关共享同一节点 -> false_link."""
        tables = _make_tables(
            equip_rows=[
                {
                    "EQUIP_ID": "A", "EQUIP_TYPE": "BREAKER",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 1, "VOLTAGE_TYPE": 10,
                },
                {
                    "EQUIP_ID": "B", "EQUIP_TYPE": "SWITCH",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 10,
                },
            ],
            terminal_rows=[
                {"ID": "TA", "EQUIP_ID": "A", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
                {"ID": "TB", "EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
            ],
            signal_rows=[
                {"TRAN_ID": "A", "POINT": 1.0, "table": "PW"},
                {"TRAN_ID": "B", "POINT": 0.0, "table": "PW"},
            ],
        )
        ctx = TaskContext(tables=tables, options={})
        recs = list(detect(ctx))
        self.assertTrue(
            any(r.extra.get("status") == "false_link" for r in recs),
            f"Expected false_link record, got: {[(r.device_id, r.extra) for r in recs]}",
        )

    def test_no_false_link_when_neighbour_is_also_open(self):
        """两相邻分位开关之间无误报：均分位时拓扑自然断开."""
        # Provide signal_map entries so is_switch_closed has definite results
        tables = _make_tables(
            equip_rows=[
                {
                    "EQUIP_ID": "B1", "EQUIP_TYPE": "SWITCH",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 10,
                },
                {
                    "EQUIP_ID": "B2", "EQUIP_TYPE": "SWITCH",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 10,
                },
            ],
            terminal_rows=[
                {"ID": "TB1", "EQUIP_ID": "B1", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
                {"ID": "TB2", "EQUIP_ID": "B2", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
            ],
            # Explicit signal entries for both: both open (POINT=0)
            signal_rows=[
                {"TRAN_ID": "B1", "POINT": 0.0, "table": "PW"},
                {"TRAN_ID": "B2", "POINT": 0.0, "table": "PW"},
            ],
        )
        ctx = TaskContext(tables=tables, options={})
        recs = list(detect(ctx))
        false_links = [r for r in recs if r.extra.get("status") == "false_link"]
        self.assertEqual(
            0, len(false_links),
            f"Both switches open (POINT=0) — should have no false_link: {false_links}",
        )

    def test_correction_sql_present(self):
        """检测到的 false_link 必须包含 correction_sql."""
        tables = _make_tables(
            equip_rows=[
                {
                    "EQUIP_ID": "A", "EQUIP_TYPE": "BREAKER",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 1, "VOLTAGE_TYPE": 10,
                },
                {
                    "EQUIP_ID": "B", "EQUIP_TYPE": "SWITCH",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 10,
                },
            ],
            terminal_rows=[
                {"ID": "TA", "EQUIP_ID": "A", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
                {"ID": "TB", "EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
            ],
            signal_rows=[
                {"TRAN_ID": "A", "POINT": 1.0, "table": "PW"},
                {"TRAN_ID": "B", "POINT": 0.0, "table": "PW"},
            ],
        )
        ctx = TaskContext(tables=tables, options={})
        recs = list(detect(ctx))
        fl_recs = [r for r in recs if r.extra.get("status") == "false_link"]
        self.assertTrue(fl_recs, "Should have at least one false_link record")
        for r in fl_recs:
            self.assertTrue(
                r.correction_sql,
                f"Record {r.device_id} has empty correction_sql",
            )
            # 官方交付约束: 修正 SQL 仅允许 UPDATE (禁 DELETE)。
            # 误连通的修正语义 = 软删除端子行 (VALID_FLAG=0), 见 contract.validate_sql_preview。
            upper_sql = r.correction_sql.upper()
            self.assertTrue(
                upper_sql.startswith("UPDATE"),
                f"correction_sql must be UPDATE-only (official constraint): {r.correction_sql}",
            )
            self.assertIn(
                "VALID_FLAG", upper_sql,
                f"false_link correction should soft-delete terminal via VALID_FLAG: {r.correction_sql}",
            )

    def test_severity_is_medium(self):
        """SEVERITY_DEFAULT 应为 medium（与算法注释一致）。"""
        self.assertEqual(SEVERITY_DEFAULT, "medium")

    def test_record_task_code_is_2_4(self):
        """ProblemRecord.task_code 必须为 '2.4'."""
        tables = _make_tables(
            equip_rows=[
                {
                    "EQUIP_ID": "A", "EQUIP_TYPE": "BREAKER",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 1, "VOLTAGE_TYPE": 10,
                },
                {
                    "EQUIP_ID": "B", "EQUIP_TYPE": "SWITCH",
                    "FEEDER_ID": "F1", "DSUBSTATION_ID": "RM1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 10,
                },
            ],
            terminal_rows=[
                {"ID": "TA", "EQUIP_ID": "A", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
                {"ID": "TB", "EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "N1", "TABLE": "PW"},
            ],
            signal_rows=[
                {"TRAN_ID": "A", "POINT": 1.0, "table": "PW"},
                {"TRAN_ID": "B", "POINT": 0.0, "table": "PW"},
            ],
        )
        ctx = TaskContext(tables=tables, options={})
        recs = list(detect(ctx))
        fl_recs = [r for r in recs if r.extra.get("status") == "false_link"]
        self.assertTrue(fl_recs)
        for r in fl_recs:
            self.assertEqual(r.task_code, "2.4")

    def test_zw_equipment_false_link(self):
        """ZW设备（无FEEDER_ID）分位但连到合位设备 -> 也应检测。"""
        tables = _make_tables(
            equip_rows=[
                {
                    "EQUIP_ID": "ZA", "EQUIP_TYPE": "BREAKER",
                    "ST_ID": "ST1", "DSUBSTATION_ID": "ST1",
                    "RUN_STATUS": 1, "VOLTAGE_TYPE": 110,
                },
                {
                    "EQUIP_ID": "ZB", "EQUIP_TYPE": "SWITCH",
                    "ST_ID": "ST1", "DSUBSTATION_ID": "ST1",
                    "RUN_STATUS": 0, "VOLTAGE_TYPE": 110,
                },
            ],
            terminal_rows=[
                {"ID": "TZA", "EQUIP_ID": "ZA", "CONNECTIVITYNODE_ID": "N1", "TABLE": "ZW"},
                {"ID": "TZB", "EQUIP_ID": "ZB", "CONNECTIVITYNODE_ID": "N1", "TABLE": "ZW"},
            ],
            signal_rows=[
                {"ID": "ZA", "POINT": 1.0, "table": "ZW"},
                {"ID": "ZB", "POINT": 0.0, "table": "ZW"},
            ],
        )
        ctx = TaskContext(tables=tables, options={})
        recs = list(detect(ctx))
        fl_recs = [r for r in recs if r.extra.get("status") == "false_link"]
        self.assertTrue(
            fl_recs,
            f"ZW equipment false_link should be detected: {[(r.device_id, r.extra) for r in recs]}",
        )
        # ZW 用原始 SQL 而非函数; 官方约束仅允许 UPDATE (禁 DELETE),
        # 误连通修正语义 = 软删除端子行 (VALID_FLAG=0)。
        for r in fl_recs:
            upper_sql = r.correction_sql.upper()
            self.assertTrue(
                upper_sql.startswith("UPDATE"),
                f"ZW correction_sql must be UPDATE-only (official constraint): {r.correction_sql}",
            )
            self.assertIn("VALID_FLAG", upper_sql)


if __name__ == "__main__":
    unittest.main()
