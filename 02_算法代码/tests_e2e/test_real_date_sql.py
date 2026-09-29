"""End-to-end smoke test for the real competition date.sql.

Two scenarios:
A) ``D:\whb\dianli\date.sql`` (DDL-only today) -> schema_demo branch
   - pipeline must run, warn, and produce xlsx with 6 sheets
   - sheet headers/column counts must match official template 1:1

B) Hand-injected 14-table SQL with real JBS_ZD_OBJECT dictionary
   - source_mode=real, total_records>0
   - EQUIP_TYPE must be normalized to canonical enum via D8 mapping
   - 5.3 auto-draw must produce 5 SVG files
"""
import io, json, pathlib, sys, tempfile, unittest

ROOT = pathlib.Path(r'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码')
sys.path.insert(0, str(ROOT))

from data_loader.sql_importer import import_sql, inspect_sql
from data_loader.schema import REQUIRED_TABLES
from data_loader.object_dictionary import normalize_dataset_types
from gui.auto_pipeline import run_pipeline, RunOptions
from output_writer.workbook_schema import SHEETS

REAL_DATE_SQL = r'D:\whb\dianli\date.sql'

# Official column counts (from official template)
OFFICIAL_COLUMN_COUNTS = {10, 11, 9, 9, 7, 2}  # 6 sheets


def _columns_normalize(cols):
    return tuple("" if c is None else c for c in cols)


class RealDateSqlE2ETests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="e2e_real_")

    # ------------------------------------------------------------------
    # Scenario A: DDL-only (current state of D:\whb\dianli\date.sql)
    # ------------------------------------------------------------------
    def test_A_ddl_only_pipeline_runs_and_keeps_six_sheet_contract(self):
        info = inspect_sql(REAL_DATE_SQL)
        self.assertEqual(info.mode, "schema_only")
        self.assertEqual(set(info.table_names), set(REQUIRED_TABLES))

        out = pathlib.Path(self.td) / "out_ddl"
        res = run_pipeline(
            [REAL_DATE_SQL],
            out,
            RunOptions(task_codes=("1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.4",
                                   "3.1", "4.1", "4.2", "5.0", "5.1", "5.2", "5.3")),
        )

        # 必须明确标注演示模式
        self.assertEqual(res.source_mode, "schema_demo")
        self.assertTrue(any("演示" in w or "DDL" in w for w in res.warnings),
                        f"缺少演示提示: {res.warnings}")

        # 6 Sheet xlsx 必须生成
        import openpyxl
        self.assertTrue(res.xlsx_path and pathlib.Path(res.xlsx_path).exists())
        wb = openpyxl.load_workbook(res.xlsx_path, data_only=True)

        # 字段名/列数与官方 1:1 对齐
        self.assertEqual(set(wb.sheetnames), {s.name for s in SHEETS})
        for sheet in SHEETS:
            ws = wb[sheet.name]
            expected_named = tuple(c for c in sheet.columns if c is not None)
            expected_total = len(sheet.columns)
            # max_column: 实际写出列数, Sheet 6 允许 max_column == expected_named len
            if sheet.has_header:
                actual_cols = _columns_normalize(tuple(c.value for c in ws[1]))
                self.assertEqual(actual_cols, expected_named,
                                 f"表头不匹配: {sheet.name}")
                # max_column: 官方定义含 None 时只统计非 None 列
                self.assertGreaterEqual(ws.max_column, len(expected_named))
                self.assertLessEqual(ws.max_column, expected_total)
            else:
                # Sheet 6 has_header=False, 全部行是数据
                self.assertGreaterEqual(ws.max_column, len(expected_named))
                self.assertLessEqual(ws.max_column, expected_total)

        # manifest 存在且 source_mode 正确
        self.assertTrue(res.manifest_path and pathlib.Path(res.manifest_path).exists())
        manifest = json.loads(pathlib.Path(res.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_mode"], "schema_demo")
        # 5.3 至少产出 1 张图
        self.assertGreater(len(manifest["auto_draw"]), 0)

    # ------------------------------------------------------------------
    # Scenario B: real 14-table SQL with JBS_ZD_OBJECT dictionary
    # ------------------------------------------------------------------
    def _write_real_sql(self) -> pathlib.Path:
        zd_object = [
            ("1", "0102", "断路器", "Breaker"),
            ("2", "0103", "负荷开关", "LoadSwitch"),
            ("3", "0104", "隔离开关", "Disconnector"),
            ("4", "0105", "变压器", "Transformer"),
            ("5", "0106", "母线", "Bus"),
        ]
        pw_equip = [
            ("DEV0001", "P-1", "0102", 10, "F101", "ST01", "0"),
            ("DEV0002", "P-2", "0103", 10, "F101", "ST01", "0"),
            ("DEV0003", "P-3", "0104", 10, "F101", "ST01", "0"),
            ("DEV0004", "P-4", "0105", 10, "F101", "ST01", "0"),
            ("DEV0005", "P-5", "0106", 10, "F101", "ST01", "0"),
        ]
        feeder = [("F101", "F101", "ST01", 10)]
        pw_term = [
            ("T1", "DEV0001", "N1"), ("T2", "DEV0002", "N1"),
            ("T3", "DEV0003", "N2"), ("T4", "DEV0004", "N2"),
            ("T5", "DEV0005", "N3"),
        ]
        room = [("R001", "R001", 10, "F101")]
        zw_sub = [("ST01", "ST01", 110)]
        zd_volt = [(10, "10kV"), (110, "110kV")]
        rows_by_table = {
            "JBS_ZD_OBJECT": (("OBJ_ID", "OBJ_CODE", "OBJ_CNNAME", "OBJ_ENNAME"), zd_object),
            "JBS_PWFEEDERLINE": (("LINE_ID", "LINE_NAME", "START_ST_ID", "VOLTAGE_TYPE"), feeder),
            "JBS_PWEQUIPINFO": (("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "VOLTAGE_TYPE",
                                  "FEEDER_ID", "DSUBSTATION_ID", "COMPOSITESWITCH"), pw_equip),
            "JBS_PWTERMINAL": (("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"), pw_term),
            "JBS_PWROOM": (("ROOM_ID", "ROOM_NAME", "TOP_VOLTAGE_TYPE", "FEEDER_ID"), room),
            "JBS_PWREAL": (("NUM", "TRAN_ID", "DATA_DATE", "POINT", "BDZ_ID", "FEEDER_ID"), []),
            "JBS_ZWSUBSTATION": (("ST_ID", "ST_NAME", "TOP_AC_VOLTAGE_TYPE"), zw_sub),
            "JBS_ZD_VOLTAGETYPE": (("VOLTAGE_ID", "VOLTAGE_NAME"), zd_volt),
        }
        empty = {
            "JBS_ZWEQUIPINFO": ("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "ST_ID", "VOLTAGE_TYPE"),
            "JBS_ZWLINEEND": ("LINEEND_ID", "LINEEND_NAME", "VOLTAGE_TYPE", "ST_ID"),
            "JBS_ZWMEA": ("CREATE_DATE", "ID", "MEAS_TYPE"),
            "JBS_ZWSIGNAL": ("ID", "POINT"),
            "JBS_ZWTERMINAL": ("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"),
            "JBS_ZD_MEASTYPE": ("CODE", "NAME_CHN"),
        }
        out_lines = []
        for tname in REQUIRED_TABLES:
            if tname in rows_by_table:
                cols, rows = rows_by_table[tname]
            else:
                cols, rows = empty[tname], []
            out_lines.append(f"INSERT INTO {tname} ({', '.join(cols)}) VALUES")
            if rows:
                for i, r in enumerate(rows):
                    vals = []
                    for v in r:
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        else:
                            vals.append("'" + str(v).replace("'", "''") + "'")
                    sep = "," if i < len(rows) - 1 else ";"
                    out_lines.append("  (" + ", ".join(vals) + ")" + sep)
            else:
                out_lines.append(";")
            out_lines.append("")
        path = pathlib.Path(self.td) / "real_14t.sql"
        path.write_text("\n".join(out_lines), encoding="utf-8")
        return path

    def test_B_real_sql_runs_as_real_with_d8_normalization(self):
        sql_path = self._write_real_sql()
        info = inspect_sql(sql_path)
        self.assertEqual(info.mode, "data")
        self.assertEqual(set(info.table_names), set(REQUIRED_TABLES))

        # 离线归一：验证 OBJ_CODE -> 规范枚举
        tables = import_sql(sql_path)
        normalized = normalize_dataset_types(tables)
        equip = {r["EQUIP_ID"]: r for r in normalized["JBS_PWEQUIPINFO"]}
        self.assertEqual(equip["DEV0001"]["EQUIP_TYPE"], "BREAKER")
        self.assertEqual(equip["DEV0001"]["EQUIP_TYPE_RAW"], "0102")
        self.assertEqual(equip["DEV0002"]["EQUIP_TYPE"], "SWITCH")
        self.assertEqual(equip["DEV0003"]["EQUIP_TYPE"], "DISCONNECTOR")
        self.assertEqual(equip["DEV0004"]["EQUIP_TYPE"], "TRANSFORMER")
        self.assertEqual(equip["DEV0005"]["EQUIP_TYPE"], "BUS")

        # 端到端跑 9 任务
        out = pathlib.Path(self.td) / "out_real"
        res = run_pipeline(
            [str(sql_path)],
            out,
            RunOptions(task_codes=("1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2",
                                   "2.3", "2.4", "3.1", "4.1", "4.2", "5.0", "5.1",
                                   "5.2", "5.3")),
        )
        self.assertEqual(res.source_mode, "real", res.warnings)
        self.assertGreater(res.total_records, 0)

        # xlsx 6 Sheet 字段对齐
        import openpyxl
        wb = openpyxl.load_workbook(res.xlsx_path, data_only=True)
        self.assertEqual(set(wb.sheetnames), {s.name for s in SHEETS})
        for sheet in SHEETS:
            ws = wb[sheet.name]
            expected_named = tuple(c for c in sheet.columns if c is not None)
            expected_total = len(sheet.columns)
            if sheet.has_header:
                # Sheet 2 第 11 列被定义为 None 占位, openpyxl 写为空字符串; 实际表头 = 非 None 列名
                actual_cols = _columns_normalize(tuple(c.value for c in ws[1]))
                self.assertEqual(actual_cols[: len(expected_named)], expected_named,
                                 f"表头不匹配: {sheet.name}")
            self.assertGreaterEqual(ws.max_column, len(expected_named))
            self.assertLessEqual(ws.max_column, expected_total)

        # 5.3 自动出图 5 张
        manifest = json.loads(pathlib.Path(res.manifest_path).read_text(encoding="utf-8"))
        auto_draw_names = {d["name"] for d in manifest["auto_draw"]}
        self.assertEqual(auto_draw_names, {
            "5.3.1_LINE215", "5.3.1_LINE216", "5.3.2_LINE111",
            "5.3.3_SUB004", "5.3.4_trace",
        })
        for entry in manifest["auto_draw"]:
            p = pathlib.Path(entry["path"])
            self.assertTrue(p.exists() and p.stat().st_size > 100,
                            f"5.3 图 {p} 不存在或太小")


if __name__ == "__main__":
    unittest.main()
