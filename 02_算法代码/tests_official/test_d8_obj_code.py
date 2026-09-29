import os, sys, io, json, tempfile, unittest, pathlib

_HERE = pathlib.Path(__file__).resolve().parent
_ALGO_ROOT = _HERE.parent
_PROJECT_ROOT = _ALGO_ROOT.parent
sys.path.insert(0, str(_ALGO_ROOT))

from data_loader.sql_importer import import_sql, inspect_sql
from data_loader.object_dictionary import (
    normalize_dataset_types, build_obj_code_map, normalize_equip_type,
    CANONICAL_EQUIP_TYPES, SEED_OBJ_CODE_MAP,
)
from data_loader.loader import OfficialDataset
from data_loader.schema import REQUIRED_TABLES
from gui.auto_pipeline import run_pipeline, RunOptions

REAL_DATE_SQL = str(_PROJECT_ROOT / "比赛要求" / "date.sql")

class D8ObjCodeTests(unittest.TestCase):
    """验证 D8 修复：JBS_ZD_OBJECT 真表 -> OBJ_CODE -> 规范枚举。"""

    def test_inspect_real_date_sql(self):
        info = inspect_sql(REAL_DATE_SQL)
        self.assertEqual(info.mode, "schema_only")
        self.assertEqual(set(info.table_names), set(REQUIRED_TABLES))
        self.assertEqual(info.insert_statements, 0)

    def test_normalize_handles_obj_codes(self):
        # 手工构造字典 + 设备行：OBJ_CODE -> 中文
        zd = [
            {"OBJ_ID": "1", "OBJ_CODE": "0102", "OBJ_CNNAME": "断路器", "OBJ_ENNAME": "Breaker"},
            {"OBJ_ID": "2", "OBJ_CODE": "0103", "OBJ_CNNAME": "负荷开关", "OBJ_ENNAME": "LoadSwitch"},
            {"OBJ_ID": "3", "OBJ_CODE": "0104", "OBJ_CNNAME": "隔离开关", "OBJ_ENNAME": "Disconnector"},
            {"OBJ_ID": "4", "OBJ_CODE": "0105", "OBJ_CNNAME": "变压器", "OBJ_ENNAME": "Transformer"},
            {"OBJ_ID": "5", "OBJ_CODE": "0106", "OBJ_CNNAME": "母线", "OBJ_ENNAME": "Bus"},
        ]
        mapping = build_obj_code_map(zd)
        self.assertEqual(mapping["0102"], "BREAKER")
        self.assertEqual(mapping["0103"], "SWITCH")
        self.assertEqual(mapping["0104"], "DISCONNECTOR")
        self.assertEqual(mapping["0105"], "TRANSFORMER")
        self.assertEqual(mapping["0106"], "BUS")

    def test_full_pipeline_normalizes_equip_type(self):
        # 14 张表完整真实数据（手工注入）
        zd = [
            {"OBJ_ID": "1", "OBJ_CODE": "0102", "OBJ_CNNAME": "断路器", "OBJ_ENNAME": "Breaker"},
            {"OBJ_ID": "2", "OBJ_CODE": "0103", "OBJ_CNNAME": "负荷开关", "OBJ_ENNAME": "LoadSwitch"},
            {"OBJ_ID": "3", "OBJ_CODE": "0104", "OBJ_CNNAME": "隔离开关", "OBJ_ENNAME": "Disconnector"},
            {"OBJ_ID": "4", "OBJ_CODE": "0105", "OBJ_CNNAME": "变压器", "OBJ_ENNAME": "Transformer"},
            {"OBJ_ID": "5", "OBJ_CODE": "0106", "OBJ_CNNAME": "母线", "OBJ_ENNAME": "Bus"},
        ]
        pw_equip = [
            {"EQUIP_ID": "DEV0001", "EQUIP_NAME": "P-1", "EQUIP_TYPE": "0102",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
            {"EQUIP_ID": "DEV0002", "EQUIP_NAME": "P-2", "EQUIP_TYPE": "0103",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
            {"EQUIP_ID": "DEV0003", "EQUIP_NAME": "P-3", "EQUIP_TYPE": "0104",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
            {"EQUIP_ID": "DEV0004", "EQUIP_NAME": "P-4", "EQUIP_TYPE": "0105",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
            {"EQUIP_ID": "DEV0005", "EQUIP_NAME": "P-5", "EQUIP_TYPE": "0106",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
            {"EQUIP_ID": "DEV0006", "EQUIP_NAME": "P-6", "EQUIP_TYPE": "UNMAPPED_CODE",
             "VOLTAGE_TYPE": 10, "FEEDER_ID": "F101", "DSUBSTATION_ID": "ST01", "COMPOSITESWITCH": "0"},
        ]
        feeder = {"LINE_ID": "F101", "LINE_NAME": "F101", "START_ST_ID": "ST01", "VOLTAGE_TYPE": 10}
        pw_term = [
            {"ID": "T1", "EQUIP_ID": "DEV0001", "CONNECTIVITYNODE_ID": "N1"},
            {"ID": "T2", "EQUIP_ID": "DEV0002", "CONNECTIVITYNODE_ID": "N1"},
            {"ID": "T3", "EQUIP_ID": "DEV0003", "CONNECTIVITYNODE_ID": "N2"},
            {"ID": "T4", "EQUIP_ID": "DEV0004", "CONNECTIVITYNODE_ID": "N2"},
            {"ID": "T5", "EQUIP_ID": "DEV0005", "CONNECTIVITYNODE_ID": "N3"},
            {"ID": "T6", "EQUIP_ID": "DEV0006", "CONNECTIVITYNODE_ID": "N3"},
        ]
        tables = {
            "JBS_PWEQUIPINFO": pw_equip,
            "JBS_PWFEEDERLINE": [feeder],
            "JBS_PWTERMINAL": pw_term,
            "JBS_PWREAL": [],
            "JBS_PWROOM": [],
            "JBS_ZD_OBJECT": zd,
            "JBS_ZD_VOLTAGETYPE": [{"VOLTAGE_ID": 10, "VOLTAGE_NAME": "10kV"}],
            "JBS_ZD_MEASTYPE": [],
            "JBS_ZWEQUIPINFO": [],
            "JBS_ZWLINEEND": [],
            "JBS_ZWMEA": [],
            "JBS_ZWSIGNAL": [],
            "JBS_ZWTERMINAL": [],
            "JBS_ZWSUBSTATION": [],
        }
        normalized = normalize_dataset_types(tables)
        # 验证 5 条 OBJ_CODE 全部归一 + 1 条原值保留
        equip_by_id = {r["EQUIP_ID"]: r for r in normalized["JBS_PWEQUIPINFO"]}
        self.assertEqual(equip_by_id["DEV0001"]["EQUIP_TYPE"], "BREAKER")
        self.assertEqual(equip_by_id["DEV0001"]["EQUIP_TYPE_RAW"], "0102")
        self.assertEqual(equip_by_id["DEV0002"]["EQUIP_TYPE"], "SWITCH")
        self.assertEqual(equip_by_id["DEV0003"]["EQUIP_TYPE"], "DISCONNECTOR")
        self.assertEqual(equip_by_id["DEV0004"]["EQUIP_TYPE"], "TRANSFORMER")
        self.assertEqual(equip_by_id["DEV0005"]["EQUIP_TYPE"], "BUS")
        self.assertEqual(equip_by_id["DEV0006"]["EQUIP_TYPE"], "UNMAPPED_CODE")
        self.assertEqual(equip_by_id["DEV0006"]["EQUIP_TYPE_RAW"], "UNMAPPED_CODE")

    def test_run_pipeline_uses_real_health_after_normalization(self):
        """把上面真实数据集写到 SQL，灌入 run_pipeline，验证 source_mode=real。"""
        td = tempfile.mkdtemp(prefix='d8_')
        sql = pathlib.Path(td) / "real_with_obj.sql"
        zd_rows = [
            ("JBS_ZD_OBJECT", ["OBJ_ID", "OBJ_CODE", "OBJ_CNNAME", "OBJ_ENNAME"], [
                ("1", "0102", "断路器", "Breaker"),
                ("2", "0103", "负荷开关", "LoadSwitch"),
                ("3", "0104", "隔离开关", "Disconnector"),
                ("4", "0105", "变压器", "Transformer"),
                ("5", "0106", "母线", "Bus"),
            ]),
            ("JBS_PWFEEDERLINE", ["LINE_ID", "LINE_NAME", "START_ST_ID", "VOLTAGE_TYPE"], [
                ("F101", "F101", "ST01", 10),
            ]),
            ("JBS_PWEQUIPINFO", ["EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "VOLTAGE_TYPE",
                                  "FEEDER_ID", "DSUBSTATION_ID", "COMPOSITESWITCH"], [
                ("DEV0001", "P-1", "0102", 10, "F101", "ST01", "0"),
                ("DEV0002", "P-2", "0103", 10, "F101", "ST01", "0"),
                ("DEV0003", "P-3", "0104", 10, "F101", "ST01", "0"),
            ]),
            ("JBS_PWTERMINAL", ["ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"], [
                ("T1", "DEV0001", "N1"),
                ("T2", "DEV0002", "N1"),
                ("T3", "DEV0003", "N2"),
            ]),
            ("JBS_PWROOM", ["ROOM_ID", "ROOM_NAME", "TOP_VOLTAGE_TYPE", "FEEDER_ID"], [
                ("R001", "R001", 10, "F101"),
            ]),
            ("JBS_PWREAL", ["NUM", "TRAN_ID", "DATA_DATE", "POINT", "BDZ_ID", "FEEDER_ID"], []),
            ("JBS_ZWEQUIPINFO", ["EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "ST_ID", "VOLTAGE_TYPE"], []),
            ("JBS_ZWLINEEND", ["LINEEND_ID", "LINEEND_NAME", "VOLTAGE_TYPE", "ST_ID"], []),
            ("JBS_ZWMEA", ["CREATE_DATE", "ID", "MEAS_TYPE"], []),
            ("JBS_ZWSIGNAL", ["ID", "POINT"], []),
            ("JBS_ZWTERMINAL", ["ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"], []),
            ("JBS_ZWSUBSTATION", ["ST_ID", "ST_NAME", "TOP_AC_VOLTAGE_TYPE"], [("ST01", "ST01", 110)]),
            ("JBS_ZD_VOLTAGETYPE", ["VOLTAGE_ID", "VOLTAGE_NAME"], [(10, "10kV")]),
            ("JBS_ZD_MEASTYPE", ["CODE", "NAME_CHN"], []),
        ]
        lines = []
        for table, cols, rows in zd_rows:
            lines.append(f'INSERT INTO {table} ({", ".join(cols)}) VALUES')
            if rows:
                for i, r in enumerate(rows):
                    vals = []
                    for v in r:
                        if v is None: vals.append("NULL")
                        elif isinstance(v, (int, float)): vals.append(str(v))
                        else: vals.append("'" + str(v).replace("'", "''") + "'")
                    sep = "," if i < len(rows) - 1 else ";"
                    lines.append("  (" + ", ".join(vals) + ")" + sep)
            else:
                lines.append(";")
            lines.append("")
        sql.write_text("\n".join(lines), encoding="utf-8")
        out = pathlib.Path(td) / "out"
        res = run_pipeline([str(sql)], out, RunOptions(task_codes=("1.1", "2.1", "5.0", "5.3")))
        self.assertEqual(res.source_mode, "real", res.warnings)
        self.assertGreater(res.total_records, 0)
        manifest = json.loads(pathlib.Path(res.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_mode"], "real")
        # 5.3 自动出图至少产出 1 张
        self.assertGreater(len(manifest["auto_draw"]), 0)


if __name__ == "__main__":
    unittest.main()
