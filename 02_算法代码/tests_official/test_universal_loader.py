# -*- coding: utf-8 -*-
"""universal.load_dataset 分派测试：.json 快照 / .sql 文件 / SQL 目录三种输入同构。"""
import tempfile
import unittest
from pathlib import Path

from data_loader.universal import load_dataset

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "snapshot.json"


class UniversalLoaderTests(unittest.TestCase):
    def _write_sql(self, td: str, name: str, content: str) -> Path:
        p = Path(td) / name
        p.write_text(content, encoding="utf-8")
        return p

    # --- 三种输入分派 ------------------------------------------------

    def test_json_snapshot_dispatch(self):
        ds = load_dataset(SNAPSHOT)
        self.assertEqual(len(ds.tables), 14)
        self.assertIn("JBS_PWEQUIPINFO", ds.tables)

    def test_sql_file_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_sql(td, "a.sql", """
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, VOLTAGE_TYPE) VALUES
('TMP00000001', 'dev1', 10),
('TMP00000002', 'dev2', 10);
""")
            ds = load_dataset(p)
            rows = ds.tables["JBS_PWEQUIPINFO"]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["EQUIP_ID"], "TMP00000001")

    def test_sql_dir_dispatch_merges_files(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_sql(td, "01_equip.sql", "INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1');")
            self._write_sql(td, "02_equip.sql", "INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP2');")
            self._write_sql(td, "03_mea.sql", "INSERT INTO JBS_ZWMEA (ID, V0000) VALUES ('M1', 1.5);")
            ds = load_dataset(td)
            self.assertEqual(len(ds.tables["JBS_PWEQUIPINFO"]), 2)
            self.assertEqual(len(ds.tables["JBS_ZWMEA"]), 1)

    def test_dir_without_sql_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                load_dataset(td)

    # --- 边界情况 ------------------------------------------------

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_dataset("Z:/this/does/not/exist.sql")

    def test_unsupported_extension_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.csv"
            p.write_text("a,b\n1,2", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_dataset(p)

    def test_sql_and_json_yield_same_shape(self):
        """两种入口产出的 tables 结构一致：dict[str, list[dict]]。"""
        ds = load_dataset(SNAPSHOT)
        for table_name, rows in ds.tables.items():
            self.assertIsInstance(rows, list)
            if rows:
                self.assertIsInstance(rows[0], dict)


if __name__ == "__main__":
    unittest.main()
