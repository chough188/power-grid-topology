import tempfile
import unittest
from pathlib import Path

from data_loader.sql_importer import import_sql
from data_loader.strict_sql_exporter import export_strict_sql, extract_contract, read_text


class StrictSqlExporterTests(unittest.TestCase):
    def _ddl_path(self):
        p = Path(__file__).resolve().parent.parent.parent / "比赛要求" / "date.sql"
        return p if p.exists() else Path(r"D:\whb\dianli\date.sql")

    def test_export_uses_only_authoritative_columns_and_schema_qualified_insert(self):
        ddl = self._ddl_path()
        if not ddl.exists():
            self.skipTest("authoritative date.sql unavailable")
        tables = {
            "JBS_PWEQUIPINFO": [{"EQUIP_ID": "E1", "EQUIP_NAME": "设备1", "UNKNOWN": "drop"}],
            "JBS_ZD_VOLTAGETYPE": [{"VOLTAGE_ID": 10, "VOLTAGE_NAME": "10kV"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "strict.sql"
            export_strict_sql(tables, ddl, output, "unit-test")
            text = output.read_text(encoding="utf-8-sig")
            self.assertIn('INSERT INTO "EQUIP"."JBS_PWEQUIPINFO"', text)
            self.assertNotIn('"UNKNOWN"', text)
            imported = import_sql(output)
            self.assertEqual(imported["JBS_PWEQUIPINFO"][0]["EQUIP_ID"], "E1")
            self.assertEqual(imported["JBS_ZD_VOLTAGETYPE"][0]["VOLTAGE_ID"], 10)

    def test_authoritative_contract_has_fourteen_tables(self):
        ddl = self._ddl_path()
        if not ddl.exists():
            self.skipTest("authoritative date.sql unavailable")
        text, _ = read_text(ddl)
        self.assertEqual(len(extract_contract(text)), 14)


if __name__ == "__main__":
    unittest.main()
