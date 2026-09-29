import os, sys, io, json, tempfile, unittest, pathlib

_HERE = pathlib.Path(__file__).resolve().parent
_ALGO_ROOT = _HERE.parent
sys.path.insert(0, str(_ALGO_ROOT))
from data_loader.sql_importer import inspect_sql, SqlSourceInfo
from gui.auto_pipeline import run_pipeline, RunOptions
from data_loader.synthetic_gen import make_synthetic_dataset

_HERE = pathlib.Path(__file__).resolve().parent
REAL_DDL = str(_HERE.parent.parent / "比赛要求" / "date.sql")

class InspectSqlTests(unittest.TestCase):
    def test_inspect_real_ddl(self):
        info = inspect_sql(REAL_DDL)
        self.assertEqual(info.mode, "schema_only")
        self.assertEqual(len(info.table_names), 14)
    def test_inspect_unrecognised(self):
        td = tempfile.mkdtemp()
        p = pathlib.Path(td) / "x.sql"
        p.write_text("-- nothing", encoding="utf-8")
        info = inspect_sql(p)
        self.assertEqual(info.mode, "unrecognised")
        self.assertEqual(info.table_names, ())

class SourceModeTests(unittest.TestCase):
    def _write_real_sql(self, p):
        ds = make_synthetic_dataset(seed=42)
        buf = io.StringIO()
        for t, rows in ds.tables.items():
            if not rows: continue
            cols = list(rows[0].keys())
            buf.write(f"INSERT INTO {t} ({', '.join(cols)}) VALUES\n")
            for i, row in enumerate(rows):
                vals = []
                for v in row.values():
                    if v is None: vals.append("NULL")
                    elif isinstance(v, (int, float)): vals.append(str(v))
                    else: vals.append("'" + str(v).replace("'", "''") + "'")
                sep = ",\n" if i < len(rows) - 1 else ";\n"
                buf.write("  (" + ", ".join(vals) + ")" + sep)
            buf.write("\n")
        pathlib.Path(p).write_text(buf.getvalue(), encoding="utf-8")

    def test_real_sql_runs_as_real(self):
        td = tempfile.mkdtemp()
        sql = pathlib.Path(td) / "d.sql"; self._write_real_sql(sql)
        out = pathlib.Path(td) / "out"
        res = run_pipeline([str(sql)], out, RunOptions(task_codes=("1.1","2.3","5.3")))
        self.assertEqual(res.source_mode, "real")
        self.assertGreater(res.total_records, 0)
        self.assertTrue(res.manifest_path and pathlib.Path(res.manifest_path).exists())
        manifest = json.loads(pathlib.Path(res.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_mode"], "real")
        names = {d["name"] for d in manifest["auto_draw"]}
        self.assertIn("5.3.1_LINE215", names)

    def test_schema_only_ddl_labeled_demo(self):
        out = pathlib.Path(tempfile.mkdtemp()) / "out"
        res = run_pipeline([REAL_DDL], out, RunOptions(task_codes=("1.1","5.3")))
        self.assertEqual(res.source_mode, "schema_demo")
        text = pathlib.Path(res.manifest_path).read_text(encoding="utf-8")
        self.assertIn("schema_demo", text)
        self.assertTrue(any("演示" in w for w in res.warnings))

    def test_unrecognised_labeled_empty(self):
        td = tempfile.mkdtemp()
        p = pathlib.Path(td) / "x.sql"
        p.write_text("-- nothing here", encoding="utf-8")
        out = pathlib.Path(td) / "out"
        res = run_pipeline([str(p)], out, RunOptions(task_codes=("1.1","5.3")))
        self.assertEqual(res.source_mode, "empty")
        self.assertEqual(res.total_records, 0)

if __name__ == "__main__":
    unittest.main()