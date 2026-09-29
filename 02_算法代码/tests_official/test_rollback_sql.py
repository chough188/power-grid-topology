# -*- coding: utf-8 -*-
"""Tests for shared.rollback_sql — reverse SQL generation (评审手册: 所有修正有反向SQL).

Covers the full Run-10 statement inventory (9 shapes): literal/placeholder
INSERTs, IN-list UPDATEs, bind-scoped flag UPDATEs, equipment-scoped flag
UPDATEs, and no-op forward statements whose targets are absent from the
pre-correction snapshot.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openpyxl import Workbook

from shared.rollback_sql import RollbackContext, generate_rollback_sql, invert_statement

SNAP = {
    "tables": {
        "JBS_PWEQUIPINFO": [
            {"EQUIP_ID": "TMP00000100", "EQUIP_NAME": "开关00100", "EQUIP_TYPE": "1705",
             "VOLTAGE_TYPE": "1010", "FEEDER_ID": "TMP00000160"},
        ],
        "JBS_PWTERMINAL": [
            {"ID": "T1", "EQUIP_ID": "TMP00000100", "CONNECTIVITYNODE_ID": "CN_A"},
            {"ID": "T2", "EQUIP_ID": "TMP00000100", "CONNECTIVITYNODE_ID": "CN_B"},
            {"ID": "T3", "EQUIP_ID": "TMP00000200", "CONNECTIVITYNODE_ID": "CN_C"},
        ],
        "JBS_ZWTERMINAL": [
            {"ID": "Z1", "EQUIP_ID": "TMP00000300", "CONNECTIVITYNODE_ID": "CN_Z"},
        ],
    }
}

S1_HEADER = ["序号", "一级分类", "二级分类", "问题设备id", "问题设备名称",
             "所属馈线", "所属厂站", "问题说明", "修正方案", "修正sql"]


def _make_xlsx(path: Path) -> None:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "拓扑校验问题清单"
    ws1.append(S1_HEADER)
    rows = [
        # 2.1 literal PWEQUIPINFO insert
        [1, "2", "2.1 图上有、模型无校验任务", "TMP00000100", "开关00100", "F1", "ST1",
         "x", "y",
         "INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, FEEDER_ID, VOLTAGE_TYPE) "
         "VALUES ('TMP00000100', '开关00100', '1705', 'TMP00000160', :voltage_type)"],
        # 1.4 all-placeholder PWEQUIPINFO insert (ctx device id in col 3)
        [2, "1", "1.4 疑似联络开关智能识别与复核研判任务", "TMP00000999", "开关00999", "F2", "ST1",
         "x", "y",
         "INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, FEEDER_ID, VOLTAGE_TYPE) "
         "VALUES (?, ?, ?, ?, ?)"],
        # 1.1 PW terminal insert (binds)
        [3, "1", "1.1 设备拓扑悬空检测任务", "TMP00000200", "开关00200", "F3", "ST1",
         "x", "y",
         "INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
         "VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)"],
        # 1.1 ZW terminal insert (binds)
        [4, "1", "1.1 设备拓扑悬空检测任务", "TMP00000300", "刀闸00300", "F4", "ST1",
         "x", "y",
         "INSERT INTO JBS_ZWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
         "VALUES (SEQ_ZWTERMINAL.NEXTVAL, :device_id, :new_node_id)"],
        # 1.1 CN dict insert
        [5, "1", "1.1 设备拓扑悬空检测任务", "TMP00000200", "开关00200", "F3", "ST1",
         "x", "y",
         "INSERT INTO JBS_PWCNODE_DICT (CN_ID, VOLTAGE_TYPE, ST_ID, CREATE_DATE) "
         "VALUES (:new_cn_id, :voltage_type, :station_id, SYSDATE)"],
        # 1.4 feeder UPDATE — target present in snapshot
        [6, "1", "1.4 疑似联络开关智能识别与复核研判任务", "TMP00000100", "开关00100", "F1", "ST1",
         "x", "y",
         "UPDATE JBS_PWEQUIPINFO SET FEEDER_ID = :correct_feeder WHERE EQUIP_ID = TMP00000100"],
        # 1.4 feeder UPDATE — target absent (ZW-only device)
        [7, "1", "1.4 疑似联络开关智能识别与复核研判任务", "TMP00000998", "刀闸00998", "F5", "ST1",
         "x", "y",
         "UPDATE JBS_PWEQUIPINFO SET FEEDER_ID = :correct_feeder WHERE EQUIP_ID = TMP00000998"],
        # 2.3 IN-list UPDATE (one hit + one missing)
        [8, "2", "2.3 图形物理连通、拓扑逻辑断开校验任务", "TMP00000200", "开关00200", "F3", "ST1",
         "x", "y",
         "UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node WHERE ID IN ('T3', 'TX')"],
        # 2.4 bind-scoped flag UPDATE
        [9, "2", "2.4 图形物理断开、拓扑逻辑误连通校验任务", "TMP00000200", "开关00200", "F3", "ST1",
         "x", "y",
         "UPDATE JBS_PWTERMINAL SET VALID_FLAG = :flag WHERE ID = :terminal_id"],
        # 2.2 equipment-scoped flag UPDATE
        [10, "2", "2.2 模型有、图上无校验任务", "TMP00000100", "开关00100", "F1", "ST1",
         "x", "y",
         "UPDATE JBS_PWTERMINAL SET VALID_FLAG=0 WHERE EQUIP_ID='TMP00000100';"],
    ]
    for r in rows:
        ws1.append(r)
    ws2 = wb.create_sheet("拓扑连通性异常诊断与断点定位结果")
    ws2.append(["序号", "馈线", "断点A", "断点B", "说明", "方案", "备注1", "备注2", "备注3", "sql"])
    ws2.append([1, "F1", "T1", "T2", "x", "y", "", "", "",
                "INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) "
                "VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)"])
    wb.save(path)


class TestRollbackSql(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.xlsx = root / "official_result.xlsx"
        self.snap = root / "snapshot.json"
        self.out = root / "runout"
        _make_xlsx(self.xlsx)
        self.snap.write_text(json.dumps(SNAP), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_full_generation_coverage(self) -> None:
        summary = generate_rollback_sql(self.xlsx, self.snap, self.out)
        self.assertTrue(summary["coverage_ok"])
        self.assertEqual(summary["unparsed"], 0)
        self.assertEqual(summary["cells"], 11)  # 10 Sheet1 + 1 Sheet2
        text = (self.out / "rollback.sql").read_text(encoding="utf-8")
        report = (self.out / "rollback_report.md").read_text(encoding="utf-8")
        self.assertIn("literal_restore", report)

        # 1) literal PWEQUIPINFO insert -> DELETE by literal equip id
        self.assertIn(
            "DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = 'TMP00000100'", text)
        # 2) all-placeholder insert -> ctx device id from row context
        self.assertIn(
            "DELETE FROM JBS_PWEQUIPINFO WHERE EQUIP_ID = 'TMP00000999'", text)
        # 3/4) terminal inserts -> bind-scoped DELETE reusing forward binds
        self.assertIn(
            "DELETE FROM JBS_PWTERMINAL WHERE EQUIP_ID = :device_id "
            "AND CONNECTIVITYNODE_ID = :new_node_id", text)
        self.assertIn(
            "DELETE FROM JBS_ZWTERMINAL WHERE EQUIP_ID = :device_id "
            "AND CONNECTIVITYNODE_ID = :new_node_id", text)
        # 5) CN dict insert
        self.assertIn("DELETE FROM JBS_PWCNODE_DICT WHERE CN_ID = :new_cn_id", text)
        # 6) feeder UPDATE present -> literal restore of snapshot value
        self.assertIn(
            "UPDATE JBS_PWEQUIPINFO SET FEEDER_ID = 'TMP00000160' "
            "WHERE EQUIP_ID = 'TMP00000100'", text)
        # 7) feeder UPDATE absent -> NO-OP
        self.assertIn("NO-OP: TMP00000998 absent from JBS_PWEQUIPINFO", text)
        # 8) IN-list -> per-id restore + NO-OP for missing
        self.assertIn("UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = 'CN_C' WHERE ID = 'T3'", text)
        self.assertIn("NO-OP: terminal TX absent pre-correction", text)
        # 9) bind flag UPDATE -> capture+restore pair
        self.assertIn("SELECT VALID_FLAG INTO :prev_valid_flag FROM JBS_PWTERMINAL WHERE ID = :terminal_id", text)
        self.assertIn("UPDATE JBS_PWTERMINAL SET VALID_FLAG = :prev_valid_flag WHERE ID = :terminal_id", text)
        # 10) equipment-scoped flag UPDATE -> per-terminal capture pairs
        self.assertIn("UPDATE JBS_PWTERMINAL SET VALID_FLAG = :prev_flag_T1 WHERE ID = 'T1'", text)
        self.assertIn("UPDATE JBS_PWTERMINAL SET VALID_FLAG = :prev_flag_T2 WHERE ID = 'T2'", text)

    def test_unparsed_statement_flagged(self) -> None:
        rc = RollbackContext(SNAP)
        lines = invert_statement("MERGE INTO foo USING bar ON (1)", rc, None)
        self.assertTrue(lines[0].startswith("-- UNPARSED"))
        self.assertEqual(rc.counts["unparsed"], 1)


if __name__ == "__main__":
    unittest.main()
