# -*- coding: utf-8 -*-
"""Sheet 6 行格式严格对齐官方 xlsx 单元测试。"""
import unittest
from pathlib import Path
from openpyxl import load_workbook

from output_writer.sheet6_dropdown import DROPDOWN_ROWS, render
from output_writer.workbook_schema import SHEETS


class Sheet6RowFormatTests(unittest.TestCase):
    """Sheet 6:问题类型下拉选项 — 严格对齐官方 xlsx 行格式。
    """
    """

    官方格式(拓扑校验问题标准输出.xlsx -> Sheet '问题类型下拉选项'):
      - 12 行二级分类
      - 同一一级分类下,首行一级+二级均填;其余行一级列 None,二级列保留
    """

    def test_first_row_of_each_group_has_primary(self):
        self.assertEqual(len(DROPDOWN_ROWS), 12)
        primaries = [p for p, _ in DROPDOWN_ROWS]
        self.assertEqual(primaries[0], "1 拓扑结构完整性检测")
        self.assertEqual(primaries[5], "2 图模一致性校验")
        self.assertEqual(primaries[9], "3 电气逻辑校验")
        self.assertEqual(primaries[10], "4 主配网接口拓扑完整性校验")

    def test_render_emits_17_rows_like_official(self):
        """官方 Sheet 6 物理 17 行 = 12 数据行 + 5 尾部空行(QC 终检 G1)。

        含保存→重载往返:QC 读的是落盘 xlsx,纯 None append 不落盘,
        必须靠样式化空单元格撑起尾部行。
        """
        import io as _io
        from openpyxl import Workbook, load_workbook
        wb = Workbook()
        # remove default sheet so we start fresh
        wb.remove(wb.active)
        ws = render(records=None, wb=wb, dataset=None)
        self.assertEqual(ws.max_row, 17)
        self.assertEqual(ws.max_column, 2)
        buf = _io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        ws2 = load_workbook(_io.BytesIO(buf.getvalue())).active
        self.assertEqual(ws2.max_row, 17, "trailing rows must survive save/reload")
        rows = list(ws2.iter_rows(values_only=True))
        for i in range(12, 17):
            self.assertEqual(rows[i], (None, None), f"trailing row {i+1} should be empty")

    def test_render_matches_official_row_pattern(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        ws = render(records=None, wb=wb, dataset=None)
        rows = list(ws.iter_rows(values_only=True))
        # Row 1: 一级 + 二级
        self.assertEqual(rows[0][0], "1 拓扑结构完整性检测")
        self.assertEqual(rows[0][1], "1.1 设备拓扑悬空检测任务")
        # Rows 2-5: 一级 None, 二级继续
        for i in range(1, 5):
            self.assertIsNone(rows[i][0], f"row {i+1} primary should be None")
            self.assertTrue(rows[i][1].startswith("1."), f"row {i+1} secondary should start with 1.")
        # Row 6: 新一级分类开始
        self.assertEqual(rows[5][0], "2 图模一致性校验")
        self.assertEqual(rows[5][1], "2.1 图上有、模型无校验任务")
        # Rows 7-9: 续 2.x
        for i in range(6, 9):
            self.assertIsNone(rows[i][0])
            self.assertTrue(rows[i][1].startswith("2."))
        # Row 10: 3.x (孤立一行)
        self.assertEqual(rows[9][0], "3 电气逻辑校验")
        self.assertEqual(rows[9][1], "3.1 开关 - 电压基础状态匹配校验任务")
        # Row 11: 4.x 开始
        self.assertEqual(rows[10][0], "4 主配网接口拓扑完整性校验")
        self.assertEqual(rows[10][1], "4.1 主配接口漏拼接校验任务")
        # Row 12: 续 4.x
        self.assertIsNone(rows[11][0])
        self.assertEqual(rows[11][1], "4.2 主配接口错拼接校验任务")

    def test_matches_official_xlsx_byte_for_byte(self):
        """与官方 xlsx Sheet 6 完全一致(含尾部空行布局)。"""
        from openpyxl import Workbook
        official_path = str(Path(__file__).resolve().parent.parent.parent / "比赛要求" / "拓扑校验问题标准输出.xlsx")
        wb_off = load_workbook(official_path, read_only=True, data_only=True)
        official_rows = list(wb_off["问题类型下拉选项"].iter_rows(values_only=True))
        wb_off.close()
        wb = Workbook()
        wb.remove(wb.active)
        ws = render(records=None, wb=wb, dataset=None)
        ours = list(ws.iter_rows(values_only=True))
        # 前 12 行逐字节一致
        for i, (a, b) in enumerate(zip(official_rows[:12], ours[:12])):
            self.assertEqual(a, b, f"row {i+1} mismatch: official={a} ours={b}")
        # 尾部空行:官方模板 5 行 (None, None),我们同样补 5 行
        trailing_official = [r for r in official_rows[12:] if r == (None, None)]
        trailing_ours = [r for r in ours[12:] if r == (None, None)]
        self.assertEqual(len(trailing_ours), max(5, len(trailing_official)),
                         "trailing empty rows should match official layout (>=5)")


if __name__ == "__main__":
    unittest.main()
