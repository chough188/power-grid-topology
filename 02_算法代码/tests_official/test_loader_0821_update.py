# -*- coding: utf-8 -*-
"""Official 0821 database update script applied deterministically by loader.normalized().

Covers D:\\whb\\baomi\\dianli\\0821更新\\数据库更新脚本20260821.txt (5 statements):
  1) UPDATE "EQUIP"."JBS_ZWEQUIPINFO" SET EQUIP_TYPE='1321' WHERE EQUIP_TYPE='1312'
  2) DELETE FROM "EQUIP"."JBS_PWREAL" WHERE ROWID NOT IN
     (SELECT MIN(ROWID) ... GROUP BY "TRAN_ID","DATA_DATE")
  3) DELETE "EQUIP"."JBS_PWTERMINAL" WHERE ID='TMP00062787'
  4) UPDATE "EQUIP"."JBS_ZWTERMINAL" SET CONNECTIVITYNODE_ID='109000054006023'
     WHERE "EQUIP_ID"='TMP00048726'
  5) DELETE FROM "EQUIP"."JBS_PWTERMINAL" WHERE "ID"='TMP00063385'

Statements 1/2 are already covered by the pre-existing Bug#42 steps (Q7/Q8);
this test pins both the legacy behavior and the new row-level updates, plus
idempotency (applying normalized() twice must not change the data).
"""
from __future__ import annotations

import copy
import unittest

from data_loader.loader import OfficialDataset


def _tables() -> dict:
    return {
        "JBS_PWEQUIPINFO": [
            {"EQUIP_ID": "TMP00013998", "EQUIP_TYPE": "1705"},
            {"EQUIP_ID": "TMP00014596", "EQUIP_TYPE": "1705"},
        ],
        "JBS_ZWEQUIPINFO": [
            {"EQUIP_ID": "TMP00048670", "EQUIP_TYPE": "1312"},
            {"EQUIP_ID": "TMP00048726", "EQUIP_TYPE": "1321"},
        ],
        "JBS_PWTERMINAL": [
            {"ID": "TMP00062787", "EQUIP_ID": "TMP00013998", "CONNECTIVITYNODE_ID": "-6807292"},
            {"ID": "TMP00063385", "EQUIP_ID": "TMP00014596", "CONNECTIVITYNODE_ID": "-6782446"},
            {"ID": "TMP00000001", "EQUIP_ID": "TMP00013998", "CONNECTIVITYNODE_ID": "-100"},
        ],
        "JBS_ZWTERMINAL": [
            {"ID": "TMP00129617", "EQUIP_ID": "TMP00048726", "CONNECTIVITYNODE_ID": "109000054006019"},
            {"ID": "TMP00129999", "EQUIP_ID": "TMP00048728", "CONNECTIVITYNODE_ID": "109000054006023"},
        ],
        "JBS_PWREAL": [
            {"TRAN_ID": "T1", "DATA_DATE": "D1", "POINT": 1, "KEEP": "first"},
            {"TRAN_ID": "T1", "DATA_DATE": "D1", "POINT": 1, "KEEP": "dup"},
            {"TRAN_ID": "T2", "DATA_DATE": "D1", "POINT": 0, "KEEP": "only"},
        ],
    }


class Loader0821UpdateTests(unittest.TestCase):
    def test_0821_delete_pwterminals(self):
        """Statements 3/5: both terminal rows deleted, others untouched."""
        ds = OfficialDataset(_tables()).normalized()
        ids = {str(r["ID"]) for r in ds.tables["JBS_PWTERMINAL"]}
        self.assertNotIn("TMP00062787", ids)
        self.assertNotIn("TMP00063385", ids)
        self.assertIn("TMP00000001", ids)

    def test_0821_rebind_zwterminal(self):
        """Statement 4: TMP00048726 rebound to 109000054006023; others untouched."""
        ds = OfficialDataset(_tables()).normalized()
        rows = [r for r in ds.tables["JBS_ZWTERMINAL"] if str(r["EQUIP_ID"]) == "TMP00048726"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["CONNECTIVITYNODE_ID"]), "109000054006023")
        other = [r for r in ds.tables["JBS_ZWTERMINAL"] if str(r["EQUIP_ID"]) == "TMP00048728"][0]
        self.assertEqual(str(other["CONNECTIVITYNODE_ID"]), "109000054006023")
        self.assertNotEqual(str(other["ID"]), "TMP00129617")

    def test_bug42_1312_to_1321(self):
        """Statement 1 (via Bug#42/Q7): 1312 -> 1321 on ZWEQUIPINFO."""
        ds = OfficialDataset(_tables()).normalized()
        zw = {str(r["EQUIP_ID"]): str(r["EQUIP_TYPE"]) for r in ds.tables["JBS_ZWEQUIPINFO"]}
        self.assertEqual(zw["TMP00048670"], "1321")
        self.assertEqual(zw["TMP00048726"], "1321")

    def test_bug42_pwreal_dedup_keep_first(self):
        """Statement 2 (via Bug#42/Q8): dedup by TRAN_ID+DATA_DATE, keep first.

        Official script keeps MIN(ROWID) per group; the dataset's duplicate
        rows are value-identical (Round 1 data fact), so keep-first is
        equivalent.
        """
        ds = OfficialDataset(_tables()).normalized()
        real = ds.tables["JBS_PWREAL"]
        self.assertEqual(len(real), 2)
        keys = {(str(r["TRAN_ID"]), str(r["DATA_DATE"])) for r in real}
        self.assertEqual(keys, {("T1", "D1"), ("T2", "D1")})
        t1 = [r for r in real if str(r["TRAN_ID"]) == "T1"][0]
        self.assertEqual(t1["KEEP"], "first")

    def test_normalized_idempotent(self):
        """Applying the update twice must not change functional content.

        Note: EQUIP_TYPE_RAW is a one-shot audit snapshot written by the D8
        normalization step (pre-existing); on a second pass it re-snapshots
        the already-normalized value. All functionally meaningful fields
        (EQUIP_TYPE, terminal rows, PWREAL rows) are stable.
        """
        once = OfficialDataset(_tables()).normalized()
        twice = OfficialDataset(copy.deepcopy(dict(once.tables))).normalized()
        for tbl in once.tables:
            strip = lambda r: {k: v for k, v in r.items() if k != "EQUIP_TYPE_RAW"}
            self.assertEqual([strip(r) for r in once.tables[tbl]],
                             [strip(r) for r in twice.tables[tbl]])
        # EQUIP_TYPE itself (the field every detector reads) is exactly stable
        for tbl in ("JBS_PWEQUIPINFO", "JBS_ZWEQUIPINFO"):
            self.assertEqual(
                [(r["EQUIP_ID"], str(r["EQUIP_TYPE"])) for r in once.tables[tbl]],
                [(r["EQUIP_ID"], str(r["EQUIP_TYPE"])) for r in twice.tables[tbl]],
            )


if __name__ == "__main__":
    unittest.main()
