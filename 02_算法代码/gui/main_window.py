# -*- coding: utf-8 -*-
"""主窗口：整合 5 个 Panel + 运行流水线 + GSAP 风格入场动效。

Tab 结构（借鉴 impeccable 的"渐进式披露"原则）：
  ① 文件 —— 一键选择 + 自动识别
  ② 任务 —— 13 任务多选
  ③ 运行 —— 一键执行（中间转场）
  ④ 结果 —— 异常列表 + 6 Sheet 切换
  ⑤ SVG —— 5.1 美化 + 5.2 增删
  ⑥ 评分 —— PDF 4 维展示

GSAP 思路：用 Timeline 编排 Panel 顺序入场（150-300ms stagger）。
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from gui.auto_pipeline import FileDescriptor, PipelineResult, RunOptions, run_pipeline
from gui.motion import Timeline, after_ms
from gui.panels.file_panel import FilePanel
from gui.panels.result_panel import ResultPanel
from gui.panels.score_panel import ScorePanel
from gui.panels.svg_panel import SvgPanel
from gui.panels.task_panel import TaskPanel
from gui.theme import COLORS_LIGHT, DURATION_MS, FONT_ROLES, SPACE, PANEL_PAD, apply_theme, install_fonts


class MainWindow(tk.Tk):
    """配电网图模拓扑校验 GUI 主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        install_fonts()
        self._palette = apply_theme(self, theme="light")
        self._configure_window()
        self._build_menubar()
        self._build_tabs()
        self._last_result: PipelineResult | None = None
        self._result_queue: queue.Queue = queue.Queue()
        self._poll_result_queue()

    # --- 窗口 ------------------------------------------------------------

    def _configure_window(self) -> None:
        self.title("CP-202606 配电网图模拓扑智能识别与修正系统")
        self.geometry("1280x820")
        self.minsize(1020, 700)
        try:
            icon_path = Path(__file__).resolve().parent / "app_icon.ico"
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except Exception:
            pass

    def _build_menubar(self) -> None:
        menu = tk.Menu(self)
        self.config(menu=menu)
        m_file = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="文件", menu=m_file)
        m_file.add_command(label="加载示例数据", command=self._load_demo)
        m_file.add_command(label="打开输出目录", command=self._open_output_dir)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.destroy)

        m_run = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="运行", menu=m_run)
        m_run.add_command(label="一键执行所有任务", command=self._run_pipeline_async)
        m_run.add_command(label="仅评分（用上次结果）", command=self._score_only)

        m_help = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="帮助", menu=m_help)
        m_help.add_command(label="使用说明", command=self._show_help)
        m_help.add_command(label="比赛要求对标", command=self._show_spec)

    def _build_tabs(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=SPACE["md"], pady=SPACE["md"])

        self.tab_files = FilePanel(nb)
        self.tab_tasks = TaskPanel(nb)
        self.tab_run = self._make_run_tab(nb)
        self.tab_results = ResultPanel(nb)
        self.tab_svg = SvgPanel(nb)
        self.tab_score = ScorePanel(nb)

        nb.add(self.tab_files, text="  ① 文件  ")
        nb.add(self.tab_tasks, text="  ② 任务  ")
        nb.add(self.tab_run, text="  ③ 运行  ")
        nb.add(self.tab_results, text="  ④ 结果  ")
        nb.add(self.tab_svg, text="  ⑤ SVG 美化/增删  ")
        nb.add(self.tab_score, text="  ⑥ 4 维评分  ")
        self._notebook = nb

    def _make_run_tab(self, parent: tk.Misc) -> ttk.Frame:
        tab = ttk.Frame(parent, padding=PANEL_PAD)
        ttk.Label(tab, text="一键执行",
                  font=FONT_ROLES["subtitle"],
                  foreground=self._palette["text"]).pack(anchor=tk.W, pady=(0, SPACE["xs"]))
        ttk.Label(tab, text="点击下方按钮即可全流程运行：识别 → 校验 → 13 个检测器 → 6 工作表 xlsx → 4 维评分。",
                  font=FONT_ROLES["caption"],
                  foreground=self._palette["text_muted"]).pack(anchor=tk.W, pady=(0, SPACE["lg"]))

        bar = ttk.Frame(tab)
        bar.pack(fill=tk.X, pady=(0, SPACE["md"]))
        ttk.Button(bar, text="一键执行", style="Primary.TButton",
                   command=self._run_pipeline_async).pack(side=tk.LEFT, padx=(0, SPACE["sm"]))
        ttk.Button(bar, text="选择输出目录", style="Secondary.TButton",
                   command=self._choose_output_dir).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(bar, text="刷新结果页", style="Secondary.TButton",
                   command=self._refresh_results).pack(side=tk.LEFT, padx=SPACE["xs"])

        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "output" / "gui_run"))
        ttk.Label(tab, textvariable=self.output_dir_var,
                  font=FONT_ROLES["micro"],
                  foreground=self._palette["text_dim"]).pack(anchor=tk.W, pady=(0, SPACE["lg"]))

        # 状态日志
        ttk.Label(tab, text="执行日志", font=FONT_ROLES["heading"],
                  foreground=self._palette["text"]).pack(anchor=tk.W, pady=(0, SPACE["sm"]))
        self.log_text = tk.Text(tab, height=14, wrap=tk.WORD, font=FONT_ROLES["mono"],
                                background=self._palette["surface"],
                                foreground=self._palette["text"],
                                insertbackground=self._palette["text"],
                                relief=tk.FLAT, borderwidth=1,
                                highlightbackground=self._palette["border"],
                                highlightthickness=1,
                                state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 入场动效（GSAP timeline 思路）
        self.after(80, lambda: self._entrance_animation(tab))
        return tab

    def _entrance_animation(self, tab: ttk.Frame) -> None:
        """GSAP 时间轴：标题 → 按钮 → 日志区域顺序入场。"""
        tl = Timeline(self)
        title_lbl = tab.winfo_children()[0]
        btn_frame = tab.winfo_children()[3] if len(tab.winfo_children()) > 3 else None
        for child in [title_lbl]:
            tl.to(child, "foreground", self._palette["primary"], duration_ms=200)
        if btn_frame:
            tl.wait(60)
        self.after(50, tl.start)

    # --- 操作 ------------------------------------------------------------

    def _load_demo(self) -> None:
        self.tab_files._load_demo()
        self._log("已加载示例数据（synthetic seed=42）")

    def _choose_output_dir(self) -> None:
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir_var.get())
        if d:
            self.output_dir_var.set(d)

    def _open_output_dir(self) -> None:
        Path(self.output_dir_var.get()).mkdir(parents=True, exist_ok=True)
        import os
        try:
            os.startfile(self.output_dir_var.get())  # type: ignore[attr-defined]
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", self.output_dir_var.get()])

    def _run_pipeline_async(self) -> None:
        files = self.tab_files.selected_files()
        codes = self.tab_tasks.selected_codes()
        if not files:
            messagebox.showinfo("未选择文件", "请先在「① 文件」中选择至少一个数据文件。")
            self._notebook.select(0)
            return
        if not codes:
            messagebox.showinfo("未选择任务", "请先在「② 任务」中勾选至少一个任务。")
            self._notebook.select(1)
            return
        out_dir = self.output_dir_var.get()
        self._log(f"开始一键执行 | 数据文件 {len(files)} | 任务 {len(codes)} | 输出 {out_dir}")
        # 切到运行 Tab
        self._notebook.select(2)
        # 后台线程
        t = threading.Thread(target=self._run_pipeline_worker, args=(files, codes, out_dir), daemon=True)
        t.start()

    def _run_pipeline_worker(self, files: list[FileDescriptor], codes: tuple[str, ...], out_dir: str) -> None:
        """后台线程：跑 pipeline，通过 queue 把结果传给主线程（线程安全）。"""
        try:
            opts = RunOptions(task_codes=codes, write_xlsx=True, run_score=True)
            result = run_pipeline([f.path for f in files], out_dir, opts)
            self._result_queue.put(("done", result))
        except Exception as exc:  # noqa: BLE001
            self._result_queue.put(("error", exc))

    def _poll_result_queue(self) -> None:
        """主线程：从 queue 取结果并分发到 UI（在 mainloop 中安全）。"""
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.after(80, self._poll_result_queue)
            return
        if kind == "done":
            self._on_pipeline_done(payload)
        else:
            self._on_pipeline_error(payload)

    def _on_pipeline_done(self, result: PipelineResult) -> None:
        self._last_result = result
        self.tab_results.set_result(result)
        self.tab_score.set_score(result.score_overall, result.score_lines)
        for w in result.warnings:
            self._log(f"[!] 警告: {w}")
        self._log(f"[√] 完成 | 总记录 {result.total_records} | xlsx {result.xlsx_path} | "
                  f"总分 {result.score_overall}")
        self._notebook.select(3)

    def _on_pipeline_error(self, exc: Exception) -> None:
        self._log(f"[×] 失败: {type(exc).__name__}: {exc}")
        messagebox.showerror("运行失败", f"{type(exc).__name__}: {exc}")

    def _score_only(self) -> None:
        if not self._last_result:
            messagebox.showinfo("尚无结果", "请先执行一次 pipeline")
            return
        self.tab_score.set_score(self._last_result.score_overall, self._last_result.score_lines)
        self._notebook.select(5)

    def _refresh_results(self) -> None:
        if self._last_result:
            self.tab_results.set_result(self._last_result)
            self.tab_score.set_score(self._last_result.score_overall, self._last_result.score_lines)
            self._log("已刷新结果面板")

    def _show_help(self) -> None:
        messagebox.showinfo(
            "使用说明",
            "① 文件页签: 选择 .sql/.json/.csv/.svg（可多选）→ 自动识别格式\n"
            "② 任务页签: 勾选要执行的官方任务（默认全选 13 项）\n"
            "③ 运行页签: 点击「一键执行」开始全流程\n"
            "④ 结果页签: 查看异常列表 + 切换 6 工作表\n"
            "⑤ SVG 美化/增删页签: 上传 SVG → 一键美化或增删\n"
            "⑥ 4 维评分页签: 查看模型质量评分",
        )

    def _show_spec(self) -> None:
        try:
            spec = Path("比赛要求/00_官方要求权威整合清单.md").read_text(encoding="utf-8")
            head = spec[:1200]
        except FileNotFoundError:
            head = "未找到比赛要求文件"
        win = tk.Toplevel(self)
        win.title("比赛要求对标")
        win.geometry("900x600")
        text = tk.Text(win, wrap=tk.WORD, font=FONT_ROLES["mono"])
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", head)

    # --- 辅助 ------------------------------------------------------------

    def _log(self, msg: str) -> None:
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main() -> None:
    app = MainWindow()
    app.mainloop()


__all__ = ["MainWindow", "main"]

