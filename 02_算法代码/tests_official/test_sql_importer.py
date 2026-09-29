# -*- coding: utf-8 -*-
"""sql_importer 单元测试：覆盖比赛要求里 14 表 + 别名归一 + 边界情况。"""
import io
import tempfile
import unittest
from pathlib import Path

from data_loader.sql_importer import (
    SqlImportError,
    import_sql,
    import_sql_files,
    parse_sql_text,
)


class SqlImporterTests(unittest.TestCase):
    def _write(self, name: str, content: str) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="sql_test_")) / name
        tmp.write_text(content, encoding="utf-8")
        return tmp

    # --- 基础解析 -------------------------------------------------------

    def test_single_insert_with_columns(self):
        path = self._write("a.sql", """
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, VOLTAGE_TYPE) VALUES
('TMP00000001', 'dev1', 10),
('TMP00000002', 'dev2', 10);
""")
        tables = import_sql(path)
        self.assertEqual(set(tables.keys()), {"JBS_PWEQUIPINFO"})
        self.assertEqual(len(tables["JBS_PWEQUIPINFO"]), 2)
        row = tables["JBS_PWEQUIPINFO"][0]
        self.assertEqual(row["EQUIP_ID"], "TMP00000001")
        self.assertEqual(row["VOLTAGE_TYPE"], 10)

    def test_null_and_string_quoting(self):
        path = self._write("a.sql", """
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, DSUBSTATION_ID) VALUES
('TMP1', 'O''Brien', NULL),
('TMP2', 'normal', 'ROOM1');
""")
        rows = import_sql(path)["JBS_PWEQUIPINFO"]
        self.assertEqual(rows[0]["EQUIP_NAME"], "O'Brien")
        self.assertIsNone(rows[0]["DSUBSTATION_ID"])
        self.assertEqual(rows[1]["DSUBSTATION_ID"], "ROOM1")

    def test_alias_normalization_for_voltage_table(self):
        """比赛数据集结构说明里 JBS_VOLTAGETYPE 形式 vs 代码里 JBS_ZD_VOLTAGETYPE。"""
        path = self._write("a.sql", """
INSERT INTO JBS_VOLTAGETYPE (VOLTAGE_ID, VOLTAGE_NAME) VALUES (10, '10kV'), (110, '110kV');
""")
        tables = import_sql(path)
        self.assertIn("JBS_ZD_VOLTAGETYPE", tables)
        self.assertNotIn("JBS_VOLTAGETYPE", tables)
        self.assertEqual(tables["JBS_ZD_VOLTAGETYPE"][0]["VOLTAGE_NAME"], "10kV")

    def test_comments_are_stripped(self):
        path = self._write("a.sql", """
-- 比赛数据集
/* 多行
   注释 */
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1'); -- 行尾注释
""")
        tables = import_sql(path)
        self.assertEqual(len(tables["JBS_PWEQUIPINFO"]), 1)

    def test_extras_preserved_but_ignored_in_official_load(self):
        path = self._write("a.sql", """
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1');
INSERT INTO MY_CUSTOM_TABLE (a, b) VALUES (1, 'x');
""")
        parsed = parse_sql_text(path.read_text(encoding="utf-8"))
        self.assertIn("JBS_PWEQUIPINFO", parsed.tables)
        self.assertIn("MY_CUSTOM_TABLE", parsed.extras)

    def test_multiple_files_merge_same_table(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.sql"
            p1.write_text("INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1');", encoding="utf-8")
            p2 = Path(td) / "b.sql"
            p2.write_text("INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP2');", encoding="utf-8")
            merged = import_sql_files([p1, p2])
            self.assertEqual(len(merged["JBS_PWEQUIPINFO"]), 2)

    def test_no_official_tables_raises(self):
        path = self._write("a.sql", "INSERT INTO NOT_OFFICIAL (x) VALUES (1);")
        with self.assertRaises(SqlImportError):
            import_sql(path)

    def test_no_insert_is_empty(self):
        path = self._write("a.sql", "SELECT * FROM JBS_PWEQUIPINFO;")
        with self.assertRaises(SqlImportError):
            import_sql(path)

    def test_empty_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            import_sql("Z:/this/does/not/exist.sql")

    def test_scientific_notation_float(self):
        path = self._write("a.sql", """
INSERT INTO JBS_ZWMEA (ID, V0000) VALUES ('M1', 1.5e2);
""")
        rows = import_sql(path)["JBS_ZWMEA"]
        self.assertEqual(rows[0]["V0000"], 150.0)

    def test_lowercase_keywords_and_table(self):
        """真实 SQL 文件经常关键字小写，导入器应大小写不敏感。"""
        path = self._write("a.sql", """
insert into jbs_pwequipinfo (equip_id) values ('tmp00000001');
""")
        tables = import_sql(path)
        self.assertIn("JBS_PWEQUIPINFO", tables)
        self.assertEqual(tables["JBS_PWEQUIPINFO"][0]["EQUIP_ID"], "tmp00000001")


    def test_schema_qualified_insert(self):
        path = self._write("a.sql", """
INSERT INTO "EQUIP"."JBS_PWEQUIPINFO" ("EQUIP_ID", "EQUIP_NAME")
VALUES ('TMP00000001', 'schema qualified');
""")
        tables = import_sql(path)
        self.assertEqual(tables["JBS_PWEQUIPINFO"][0]["EQUIP_ID"], "TMP00000001")
        self.assertEqual(tables["JBS_PWEQUIPINFO"][0]["EQUIP_NAME"], "schema qualified")

if __name__ == "__main__":
    unittest.main()
