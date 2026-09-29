# -*- coding: utf-8 -*-
"""Panel 5: 4 维评分可视化

借鉴 impeccable 色彩原则：
  - 进度条用 oklch 渐变（深→亮，brand 色）
  - 数字 + 进度条双编码（accessibility）
  - 评级徽章（圆形 + 状态色）
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.theme import COLORS_LIGHT, FONT_ROLES, SPACE


class ScorePanel(ttk.Frame):
    """4 维 PDF 评分展示面板。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=SPACE["md"])
        self._canvas: tk.Canvas | None = None
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="模型质量 4 维评分",
                  font=FONT_ROLES["title"], foreground=COLORS_LIGHT["primary"]).pack(anchor=tk.W, pady=(0, SPACE["sm"]))

        self.overall_var = tk.StringVar(value="尚未评分")
        ttk.Label(self, textvariable=self.overall_var,
                  font=(FONT_ROLES["title"][0], 28, "bold"),
                  foreground=COLORS_LIGHT["primary"]).pack(anchor=tk.W, pady=(0, SPACE["md"]))

        # 4 维进度条
        self._bars: dict[str, dict[str, tk.Widget]] = {}
        for key, label in [
            ("E", "电气规则符合性 (权重 0.20)"),
            ("T", "技术性能 (权重 0.45)"),
            ("G", "工程泛化 (权重 0.20)"),
            ("C", "成果完整 (权重 0.15)"),
        ]:
            row = ttk.Frame(self)
            row.pack(fill=tk.X, pady=SPACE["xs"])
            ttk.Label(row, text=label, font=FONT_ROLES["body"]).pack(side=tk.LEFT, padx=(0, SPACE["sm"]))
            bar_holder = ttk.Frame(row, relief=tk.SUNKEN, borderwidth=1)
            bar_holder.pack(side=tk.LEFT, fill=tk.X, expand=True)
            inner = tk.Frame(bar_holder, background=COLORS_LIGHT["primary"], height=14)
            inner.pack(side=tk.LEFT, fill=tk.Y)
            val_lbl = ttk.Label(row, text="—", font=FONT_ROLES["body_b"], foreground=COLORS_LIGHT["primary"])
            val_lbl.pack(side=tk.RIGHT, padx=(SPACE["sm"], 0))
            self._bars[key] = {"holder": bar_holder, "inner": inner, "label": val_lbl}

        # 原始评分日志
        ttk.Label(self, text="\n评分日志：", font=FONT_ROLES["caption"],
                  foreground=COLORS_LIGHT["text_muted"]).pack(anchor=tk.W, pady=(SPACE["md"], 2))
        self.log_text = tk.Text(self, height=8, wrap=tk.WORD, font=FONT_ROLES["mono"],
                                background=COLORS_LIGHT["surface"], foreground=COLORS_LIGHT["text"],
                                state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def set_score(self, overall: float | None, lines: tuple[str, ...]) -> None:
        """更新评分显示。"""
        if overall is None:
            self.overall_var.set("尚未评分")
        else:
            rating = "优" if overall >= 0.90 else "良" if overall >= 0.75 else "中" if overall >= 0.60 else "差"
            self.overall_var.set(f"总分 {overall:.3f} · {rating}")
        # 解析 4 维度
        dims: dict[str, float] = {}
        for line in lines:
            for key in ("E", "T", "G", "C"):
                if line.startswith(key + ":") or f"({key}):" in line:
                    # 提取 "1.00" 这样的数字
                    import re
                    m = re.search(r"\((\w)\):\s*([0-9.]+)", line)
                    if m and m.group(1) == key:
                        dims[key] = float(m.group(2))
        for key in ("E", "T", "G", "C"):
            v = dims.get(key, 0.0)
            bar = self._bars[key]
            # 进度条按 0..1 比例显示
            bar["inner"].configure(width=max(2, int(v * 200)))
            bar["label"].configure(text=f"{v:.2f}")
        # 日志
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for line in lines:
            self.log_text.insert(tk.END, line + "\n")
        self.log_text.configure(state=tk.DISABLED)


__all__ = ["ScorePanel"]
