# -*- coding: utf-8 -*-
"""端到端 6-Sheet 表头字节级对齐官方 xlsx 单元测试。"""
import unittest
from pathlib import Path

from openpyxl import load_workbook

from gui.auto_pipeline import run_pipeline

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
# 比赛要求目录在 _PROJECT_ROOT 下（不在 parent 下）
_OFFICIAL_DIR = _PROJECT_ROOT / "比赛要求"

OFFICIAL = _OFFICIAL_DIR / "拓扑校验问题标准输出.xlsx"
DATE_SQL = _OFFICIAL_DIR / "date.sql"


class SixSheetHeaderAlignmentTests(unittest.TestCase):
    """6 Sheet 表头必须与官方 xlsx 完全字节级一致。"""

    @classmethod
    def setUpClass(cls):
        wb = load_workbook(OFFICIAL, read_only=True, data_only=True)
        cls.official_headers = {}
        for n in wb.sheetnames:
            row = next(wb[n].iter_rows(min_row=1, max_row=1, values_only=True))
            cls.official_headers[n] = tuple(row)
        wb.close()

        # 输出必须落在项目外, 否则 assert_output_outside_project 会阻断
        out_dir = _PROJECT_ROOT.parent / "_dianli_output" / "_e2e_align"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = run_pipeline(file_paths=[DATE_SQL], output_dir=out_dir)
        cls.ours_path = Path(result.xlsx_path)

    def test_all_six_sheets_match(self):
        wb = load_workbook(self.ours_path, read_only=True, data_only=True)
        try:
            for i, name in enumerate(wb.sheetnames):
                with self.subTest(sheet=name):
                    o_hdr = self.official_headers.get(name)
                    our_hdr = next(wb[name].iter_rows(min_row=1, max_row=1, values_only=True))
                    self.assertEqual(
                        our_hdr, o_hdr,
                        f"Sheet {i+1} ({name}) header mismatch:\n  Official: {o_hdr}\n  Ours:     {our_hdr}",
                    )
        finally:
            wb.close()

    def test_sheet2_has_eleven_columns(self):
        """Sheet 2 (拓扑连通性) 必须有 11 列 (10 名称 + 1 None 备注)。"""
        wb = load_workbook(self.ours_path, read_only=True, data_only=True)
        try:
            ws = wb["拓扑连通性异常诊断与断点定位结果"]
            self.assertEqual(ws.max_column, 11)
            hdr = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            self.assertIsNone(hdr[10], "Sheet 2 第 11 列表头应为 None")
        finally:
            wb.close()

    def test_sheet6_has_twelve_rows(self):
        """Sheet 6 必须有 12 行(11 二级 + 1 余)。"""
        wb = load_workbook(self.ours_path, read_only=True, data_only=True)
        try:
            ws = wb["问题类型下拉选项"]
            self.assertGreaterEqual(ws.max_row, 12)
        finally:
            wb.close()


if __name__ == "__main__":
    unittest.main()
