# -*- coding: utf-8 -*-
"""GUI Panel 单元测试：所有 5 个 Panel + 主窗口的构造与基础交互。

不打开真实窗口（root.withdraw()），仅验证 widget 树正确构建。
"""
import io
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from data_loader.synthetic_gen import make_synthetic_dataset
from gui.auto_pipeline import run_pipeline


class PanelConstructionTests(unittest.TestCase):
    """仅验证构造和基础属性，不打开窗口。"""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_file_panel_lists_files(self):
        from gui.panels.file_panel import FilePanel
        panel = FilePanel(self.root)
        self.assertEqual(panel.files, [])

        # 模拟 ingest 一个 sql 文件
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "date.sql"
            p.write_text("INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID) VALUES ('TMP1');")
            panel._ingest_paths([str(p)])
        self.assertEqual(len(panel.files), 1)
        self.assertEqual(panel.files[0].kind, "sql")

    def test_task_panel_default_all_selected(self):
        from gui.panels.task_panel import TaskPanel
        panel = TaskPanel(self.root)
        codes = panel.selected_codes()
        # OFFICIAL_TASKS 含 12 官方任务 + 5.0 自评分 + 5.1/5.2/5.3 SVG 共 16 项
        self.assertEqual(len(codes), 16)

    def test_task_panel_select_bisha(self):
        from gui.panels.task_panel import TaskPanel
        panel = TaskPanel(self.root)
        panel.select_bisha()
        codes = panel.selected_codes()
        self.assertIn("1.1", codes)
        self.assertIn("1.2", codes)
        self.assertNotIn("2.1", codes)

    def test_result_panel_set_result(self):
        from gui.panels.result_panel import ResultPanel
        panel = ResultPanel(self.root)
        # 构造一个最小 pipeline 结果
        with tempfile.TemporaryDirectory() as td:
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
            sql = Path(td) / "date.sql"
            sql.write_text(buf.getvalue(), encoding="utf-8")
            result = run_pipeline([sql], Path(td) / "out")
            panel.set_result(result)
            self.assertIn("总记录", panel.summary_var.get())
            self.assertGreater(len(panel.task_combo.cget("values")), 0)

    def test_svg_panel_has_dual_panes(self):
        from gui.panels.svg_panel import SvgPanel
        panel = SvgPanel(self.root)
        # 适配 Canvas + Text 双视图结构
        self.assertIsNotNone(panel.src_pane)
        self.assertIn("canvas", panel.src_pane)
        self.assertIn("text", panel.src_pane)
        self.assertIsNotNone(panel.dst_pane)

    def test_svg_panel_canvas_renders_svg(self):
        """真实 SVG 加载到 SvgPanel 后，Canvas 上有图形（真正可视化）。"""
        from gui.panels.svg_panel import SvgPanel
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300">
          <rect x="10" y="10" width="40" height="20" fill="#2CA02C"/>
          <rect x="80" y="10" width="40" height="20" fill="#2CA02C"/>
          <line x1="30" y1="20" x2="80" y2="20" stroke="#000"/>
        </svg>'''
        panel = SvgPanel(self.root)
        panel._src_svg = svg
        panel._refresh_panes()
        items = panel.src_pane["canvas"].find_all()
        self.assertGreaterEqual(len(items), 3, "Canvas 应该渲染至少 3 个图形")

    def test_score_panel_set_score(self):
        from gui.panels.score_panel import ScorePanel
        panel = ScorePanel(self.root)
        panel.set_score(0.85, ("=== 评分 ===", "总分: 0.85"))
        self.assertIn("0.850", panel.overall_var.get())

    def test_main_window_has_six_tabs(self):
        from gui.main_window import MainWindow
        mw = MainWindow()
        try:
            self.assertEqual(mw._notebook.index("end"), 6)
        finally:
            mw.destroy()


if __name__ == "__main__":
    unittest.main()

