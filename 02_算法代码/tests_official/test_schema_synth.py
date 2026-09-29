# -*- coding: utf-8 -*-
"""schema_synth 与 schema-only import_sql 单元测试。"""
import unittest
from pathlib import Path

from data_loader.schema_synth import (
    _parse_columns,
    _split_top_commas,
    extract_schemas,
    synthesize_rows_from_schemas,
)
from data_loader.sql_importer import import_sql, SqlImportError


DATE_SQL = Path(__file__).resolve().parent.parent.parent / "比赛要求" / "date.sql"


class SchemaSynthUnitTests(unittest.TestCase):
    def test_split_top_commas_respects_parens_and_strings(self):
        body = '"col1" VARCHAR(50), "col2" VARCHAR2(100, 2), "col3" VARCHAR(10)'
        parts = _split_top_commas(body)
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].endswith("VARCHAR(50)"))
        self.assertTrue(parts[1].endswith("VARCHAR2(100, 2)"))

    def test_parse_columns_handles_types_and_not_null(self):
        body = '"EQUIP_ID" VARCHAR(200) NOT NULL, "EQUIP_NAME" VARCHAR(200) NULL, "VOLTAGE_TYPE" VARCHAR2(50) NULL'
        cols = _parse_columns(body)
        names = [c["name"] for c in cols]
        self.assertEqual(names, ["EQUIP_ID", "EQUIP_NAME", "VOLTAGE_TYPE"])
        self.assertTrue(cols[0]["not_null"])
        self.assertFalse(cols[1]["not_null"])
        self.assertEqual(cols[2]["type"], "VARCHAR2")

    def test_parse_columns_ignores_table_constraints(self):
        body = '"X" INT, CLUSTER PRIMARY KEY("X") ENABLE, "Y" VARCHAR(10) NULL'
        cols = _parse_columns(body)
        names = [c["name"] for c in cols]
        self.assertEqual(names, ["X", "Y"])

    def test_extract_schemas_from_real_date_sql(self):
        if not DATE_SQL.exists():
            self.skipTest("date.sql 不存在(D:\\whb\\dianli\\date.sql)")
        text = DATE_SQL.read_bytes().decode("gbk")
        schemas = extract_schemas(text)
        self.assertEqual(len(schemas), 14, "必须识别全部 14 张官方表")
        equip_cols = [c["name"] for c in schemas["JBS_PWEQUIPINFO"]]
        self.assertIn("EQUIP_ID", equip_cols)
        self.assertIn("EQUIP_TYPE", equip_cols)
        self.assertIn("VOLTAGE_TYPE", equip_cols)
        # 必须包含 14 张表中的关键表
        self.assertIn("JBS_ZD_VOLTAGETYPE", schemas)
        self.assertIn("JBS_ZWMEA", schemas)

    def test_synthesize_rows_uses_id_prefixes(self):
        schemas = {"JBS_PWEQUIPINFO": [
            {"name": "EQUIP_ID", "type": "VARCHAR", "python_type": "str", "not_null": True},
            {"name": "VOLTAGE_TYPE", "type": "INT", "python_type": "int", "not_null": False},
        ]}
        tables, _ = synthesize_rows_from_schemas(schemas, n_rows_per_table=2)
        rows = tables["JBS_PWEQUIPINFO"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["EQUIP_ID"], "TMP00000001")
        self.assertEqual(rows[1]["EQUIP_ID"], "TMP00000002")
        self.assertEqual(rows[0]["VOLTAGE_TYPE"], 10)

    def test_synthesize_rows_uses_110kv_for_main_grid(self):
        schemas = {"JBS_ZWEQUIPINFO": [
            {"name": "EQUIP_ID", "type": "VARCHAR", "python_type": "str", "not_null": True},
            {"name": "VOLTAGE_TYPE", "type": "INT", "python_type": "int", "not_null": False},
        ]}
        tables, _ = synthesize_rows_from_schemas(schemas, n_rows_per_table=1)
        self.assertEqual(tables["JBS_ZWEQUIPINFO"][0]["VOLTAGE_TYPE"], 110)


class SqlImporterSchemaOnlyTests(unittest.TestCase):
    def test_import_sql_falls_back_to_schema_synthesis(self):
        if not DATE_SQL.exists():
            self.skipTest("date.sql 不存在")
        tables = import_sql(DATE_SQL)
        self.assertEqual(len(tables), 14)
        for name, rows in tables.items():
            self.assertGreater(len(rows), 0, f"{name} 应该有合成行")

    def test_import_sql_raises_when_no_schema_or_insert(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "empty.sql"
        tmp.write_text("-- no schema, no insert", encoding="utf-8")
        with self.assertRaises(SqlImportError):
            import_sql(tmp)


if __name__ == "__main__":
    unittest.main()
