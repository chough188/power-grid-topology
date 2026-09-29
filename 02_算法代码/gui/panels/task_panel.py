# -*- coding: utf-8 -*-
"""Panel 2: 13 任务多选

按官方 5 大模块分组：
  1 拓扑完整性 (1.1-1.5)
  2 图模一致性 (2.1-2.4)
  3 电气逻辑 (3.1)
  4 主配接口 (4.1-4.2)
  5 SVG / 自评 (5.0/5.1/5.2/5.3)
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from tasks_official.catalog import OFFICIAL_TASKS


class TaskPanel(ttk.Frame):
    """任务多选面板（默认全选）。"""

    def __init__(
        self,
        master: tk.Misc,
        on_change: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        from gui.theme import PANEL_PAD
        super().__init__(master, padding=PANEL_PAD)
        self._on_change = on_change
        self._vars: dict[str, tk.BooleanVar] = {}
        self._build()

    def _build(self) -> None:
        from gui.theme import FONT_ROLES, SPACE, COLORS_LIGHT

        title = ttk.Label(self, text="选择要执行的官方任务（默认全选 13 项）",
                          font=FONT_ROLES["subtitle"], foreground=COLORS_LIGHT["text"])
        title.pack(anchor=tk.W, pady=(0, SPACE["md"]))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, SPACE["md"]))
        ttk.Button(toolbar, text="全选", style="Secondary.TButton",
                   command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=(0, SPACE["xs"]))
        ttk.Button(toolbar, text="全不选", style="Secondary.TButton",
                   command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="必选 1.1/1.2/3.1/4.1", style="Secondary.TButton",
                   command=self._set_bisha).pack(side=tk.LEFT, padx=SPACE["xs"])

        # 分组网格
        grouped: dict[str, list] = {}
        for task in OFFICIAL_TASKS:
            grouped.setdefault(task.primary_category, []).append(task)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, pady=(SPACE["sm"], 0))

        row = 0
        col = 0
        for category, tasks in grouped.items():
            group = ttk.LabelFrame(body, text=category, padding=SPACE["md"],
                                   style="Group.TLabelframe")
            group.grid(row=row, column=col, sticky="nsew",
                       padx=(0, SPACE["md"]), pady=(0, SPACE["md"]))
            body.columnconfigure(col, weight=1)
            for task in tasks:
                var = tk.BooleanVar(value=True)
                self._vars[task.code] = var
                ttk.Checkbutton(
                    group,
                    text=f"{task.code}  {task.name}",
                    variable=var,
                    command=self._emit,
                ).pack(anchor=tk.W, pady=2)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        self.summary_var = tk.StringVar()
        self._emit()
        ttk.Label(self, textvariable=self.summary_var,
                  font=FONT_ROLES["caption"],
                  foreground=COLORS_LIGHT["text_muted"]).pack(anchor=tk.W, pady=(SPACE["sm"], 0))

    # --- 公共 API --------------------------------------------------------

    def selected_codes(self) -> tuple[str, ...]:
        return tuple(code for code, var in self._vars.items() if var.get())

    def select_all(self) -> None:
        self._set_all(True)

    def clear(self) -> None:
        self._set_all(False)

    def select_bisha(self) -> None:
        """只勾选官方「必杀题」：1.1/1.2/3.1/4.1。"""
        self._set_bisha()

    # --- 内部 ------------------------------------------------------------

    def _set_all(self, value: bool) -> None:
        for var in self._vars.values():
            var.set(value)
        self._emit()

    def _set_bisha(self) -> None:
        bisha = {"1.1", "1.2", "3.1", "4.1"}
        for code, var in self._vars.items():
            var.set(code in bisha)
        self._emit()

    def _emit(self) -> None:
        codes = self.selected_codes()
        self.summary_var.set(f"已勾选 {len(codes)} / 13 项任务")
        if self._on_change:
            self._on_change(codes)


__all__ = ["TaskPanel"]
