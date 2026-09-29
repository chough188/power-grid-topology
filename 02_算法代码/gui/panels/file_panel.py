# -*- coding: utf-8 -*-
"""Panel 1: 一键文件选择 + 自动识别展示

职责：
  - 提供「选择文件」按钮 + 「选择文件夹」按钮
  - 自动调用 ``gui.auto_pipeline.sniff_files`` 识别格式
  - 显示已识别的文件清单（kind/role）
  - 暴露给主窗口的回调：``on_files_selected(List[FileDescriptor])``

依赖：仅 ``tkinter`` + 项目内模块；不写 detector 代码。
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from gui.auto_pipeline import FileDescriptor, sniff_files


class FilePanel(ttk.Frame):
    """多文件一键导入面板。"""

    def __init__(
        self,
        master: tk.Misc,
        on_files_selected: Callable[[list[FileDescriptor]], None] | None = None,
    ) -> None:
        from gui.theme import PANEL_PAD
        super().__init__(master, padding=PANEL_PAD)
        self._on_files_selected = on_files_selected
        self._files: list[FileDescriptor] = []
        self._build()

    # --- 视图构建 -------------------------------------------------------

    def _build(self) -> None:
        from gui.theme import FONT_ROLES, SPACE, PANEL_PAD, COLORS_LIGHT

        title = ttk.Label(self, text="一键选择文件（自动识别 sql/json/csv/svg）",
                          font=FONT_ROLES["subtitle"], foreground=COLORS_LIGHT["text"])
        title.pack(anchor=tk.W, pady=(0, SPACE["md"]))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, SPACE["md"]))
        ttk.Button(toolbar, text="选择多个文件", style="Primary.TButton",
                   command=self._pick_files).pack(side=tk.LEFT, padx=(0, SPACE["sm"]))
        ttk.Button(toolbar, text="选择文件夹", style="Secondary.TButton",
                   command=self._pick_folder).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="清空", style="Secondary.TButton",
                   command=self._clear).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="加载示例数据", style="Secondary.TButton",
                   command=self._load_demo).pack(side=tk.LEFT, padx=SPACE["xs"])

        self.summary_var = tk.StringVar(value="尚未选择文件")
        ttk.Label(self, textvariable=self.summary_var,
                  font=FONT_ROLES["caption"],
                  foreground=COLORS_LIGHT["text_muted"]).pack(anchor=tk.W, pady=(0, SPACE["sm"]))

        cols = ("name", "kind", "role", "path")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8,
                                 style="Surface.Treeview")
        self.tree.heading("name", text="文件名")
        self.tree.heading("kind", text="类型")
        self.tree.heading("role", text="角色")
        self.tree.heading("path", text="完整路径")
        self.tree.column("name", width=200, anchor=tk.W)
        self.tree.column("kind", width=80, anchor=tk.W)
        self.tree.column("role", width=100, anchor=tk.W)
        self.tree.column("path", width=400, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(SPACE["xs"], 0))

    # --- 公共 API --------------------------------------------------------

    @property
    def files(self) -> list[FileDescriptor]:
        return list(self._files)

    def selected_files(self) -> list[FileDescriptor]:
        return list(self._files)

    # --- 操作 ------------------------------------------------------------

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择数据 / SVG 文件",
            filetypes=(
                ("所有支持", "*.sql *.json *.csv *.svg"),
                ("SQL 文件", "*.sql"),
                ("JSON 文件", "*.json"),
                ("CSV 文件", "*.csv"),
                ("SVG 文件", "*.svg"),
                ("所有文件", "*.*"),
            ),
        )
        if not paths:
            return
        self._ingest_paths(paths)

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择文件夹（自动收纳所有支持的扩展名）")
        if not folder:
            return
        p = Path(folder)
        exts = {".sql", ".json", ".csv", ".svg"}
        paths = [str(x) for x in p.rglob("*") if x.is_file() and x.suffix.lower() in exts]
        if not paths:
            messagebox.showinfo("未发现支持的文件", f"在 {p} 下未发现 .sql/.json/.csv/.svg 文件")
            return
        self._ingest_paths(paths)

    def _load_demo(self) -> None:
        # 用内置 synthetic 生成临时文件，然后选入
        try:
            from data_loader.synthetic_gen import make_synthetic_dataset
            import io as _io
            import tempfile
            ds = make_synthetic_dataset(seed=42)
            buf = _io.StringIO()
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
            tmp = Path(tempfile.gettempdir()) / "demo_date.sql"
            tmp.write_text(buf.getvalue(), encoding="utf-8")
            self._ingest_paths([str(tmp)])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("示例加载失败", str(exc))

    def _clear(self) -> None:
        self._files = []
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.summary_var.set("尚未选择文件")
        if self._on_files_selected:
            self._on_files_selected([])

    def _ingest_paths(self, paths: list[str]) -> None:
        files = sniff_files(paths)
        if not files:
            messagebox.showwarning("未识别", "所选文件全部无法识别，请确认扩展名（.sql/.json/.csv/.svg）")
            return
        # 增量添加（去重）
        existing = {f.path for f in self._files}
        added = [f for f in files if f.path not in existing]
        self._files.extend(added)
        for f in added:
            self.tree.insert("", tk.END, values=(f.display_name, f.kind, f.role, f.path))
        self._refresh_summary()
        if self._on_files_selected:
            self._on_files_selected(self._files)

    def _refresh_summary(self) -> None:
        n_data = sum(1 for f in self._files if f.role == "data")
        n_svg_main = sum(1 for f in self._files if f.role == "svg_main")
        n_svg_dist = sum(1 for f in self._files if f.role == "svg_dist")
        self.summary_var.set(
            f"已识别 {len(self._files)} 个文件 | 数据 {n_data} | 主网 SVG {n_svg_main} | 配网 SVG {n_svg_dist}"
        )


__all__ = ["FilePanel"]
