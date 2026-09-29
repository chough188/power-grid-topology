# -*- coding: utf-8 -*-
"""auto_pipeline 单元测试：覆盖文件嗅探 + pipeline 一键调用。"""
import io
import tempfile
import unittest
from pathlib import Path

from data_loader.synthetic_gen import make_synthetic_dataset
from gui.auto_pipeline import (
    ALL_TASKS,
    RunOptions,
    run_pipeline,
    sniff_files,
)


def _write_date_sql() -> Path:
    """从 synthetic 生成 14 表的 date.sql 临时文件。"""
    ds = make_synthetic_dataset(seed=42)
    buf = io.StringIO()
    for tname, rows in ds.tables.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        buf.write(f"INSERT INTO {tname} ({', '.join(cols)}) VALUES\n")
        for i, row in enumerate(rows):
            vals = []
            for v in row.values():
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append(f"'{str(v).replace(chr(39), chr(39)*2)}'")
            sep = ",\n" if i < len(rows) - 1 else ";\n"
            buf.write(f"  ({', '.join(vals)}){sep}\n")
        buf.write("\n")
    p = Path(tempfile.mkdtemp(prefix="pipeline_test_")) / "date.sql"
    p.write_text(buf.getvalue(), encoding="utf-8")
    return p


class SniffTests(unittest.TestCase):
    def test_classify_sql(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.sql"
            p.write_text("INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1');")
            files = sniff_files([p])
            self.assertEqual(files[0].kind, "sql")
            self.assertEqual(files[0].role, "data")

    def test_classify_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text("{}")
            files = sniff_files([p])
            self.assertEqual(files[0].kind, "json")

    def test_classify_line215_main(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "LINE215.svg"
            p.write_text("<svg/>")
            files = sniff_files([p])
            self.assertEqual(files[0].kind, "svg_main")

    def test_classify_line216_dist(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "LINE216.svg"
            p.write_text("<svg/>")
            files = sniff_files([p])
            self.assertEqual(files[0].kind, "svg_dist")

    def test_unknown_extension(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.xyz"
            p.write_text("")
            files = sniff_files([p])
            self.assertEqual(files[0].kind, "other")


class PipelineTests(unittest.TestCase):
    def test_run_with_sql_and_svg(self):
        sql = _write_date_sql()
        with tempfile.TemporaryDirectory() as td:
            svg = Path(td) / "LINE215.svg"
            svg.write_text("<svg/>", encoding="utf-8")
            out = Path(td) / "out"
            result = run_pipeline([sql, svg], out)
            self.assertEqual(len(result.detected_tables), 14)
            self.assertGreater(result.total_records, 0)
            self.assertTrue(result.xlsx_path)
            self.assertEqual(len(result.svg_files), 1)

    def test_run_synthetic_fallback_when_no_data(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            opts = RunOptions(task_codes=("1.1", "5.0"))
            result = run_pipeline([], out, opts)
            self.assertEqual(len(result.detected_tables), 14)
            # synthetic 有数据 → 至少跑出 1.1 和 5.0 两条
            self.assertGreater(len(result.records_by_task.get("1.1", ())), 0)

    def test_run_with_custom_task_subset(self):
        sql = _write_date_sql()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            opts = RunOptions(task_codes=("1.1", "2.2"), run_score=False, write_xlsx=False)
            result = run_pipeline([sql], out, opts)
            self.assertIn("1.1", result.records_by_task)
            self.assertIn("2.2", result.records_by_task)
            self.assertNotIn("4.1", result.records_by_task)
            self.assertIsNone(result.xlsx_path)

    def test_all_tasks_constant_is_13(self):
        self.assertEqual(len(ALL_TASKS), 13)


if __name__ == "__main__":
    unittest.main()
