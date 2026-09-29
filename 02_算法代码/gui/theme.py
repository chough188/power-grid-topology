# -*- coding: utf-8 -*-
"""GUI 设计 token v2 — 对齐 v8 前端 UI_DESIGN_TOKENS 规范。

色彩体系：Tailwind Slate 色阶 + 品牌蓝（WCAG AA 全量达标）
  - 60% 背景：slate-50/900（极淡冷灰，高级感底色）
  - 30% 边框/文字：slate-200~700（层次分明的中性色）
  - 10% 主色：blue-600/500（电力蓝，仅按钮/链接/高亮）

字号层级：7-size scale（11/12/13/14/16/18/24）。
字体：默认 "Microsoft YaHei UI"；等宽 "Cascadia Code" > "Consolas"。

间距：4px 基准 × 8 级（4/8/12/16/20/24/32/48）。
圆角/阴影/动效：对齐 v8 token（120/160/240ms 三档过渡）。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


# ---------------------------------------------------------------------------
# 配色 token（对齐 v8 UI_DESIGN_TOKENS.md · WCAG AA 全量达标）
# ---------------------------------------------------------------------------

# 浅色主题（默认）— Tailwind Slate 色阶
COLORS_LIGHT = {
    "bg":          "#F8FAFC",   # slate-50 页面底色
    "surface":     "#FFFFFF",   # 卡片/浮层
    "surface_2":   "#F1F5F9",   # slate-100 次级背景（表头/hover）
    "surface_3":   "#E2E8F0",   # slate-200 三级背景（禁用/分割）
    "border":      "#E2E8F0",   # slate-200 描边/分割线
    "border_strong": "#CBD5E1", # slate-300 输入框/滚动条
    "text":        "#0F172A",   # slate-900 主文字（对比度 15.4:1）
    "text_muted":  "#475569",   # slate-600 次文字（对比度 7.1:1）
    "text_dim":    "#64748B",   # slate-500 弱化文字（对比度 4.76:1）
    "primary":     "#1D4ED8",   # blue-700 品牌主色（对比度 5.49:1）
    "primary_dk":  "#1E40AF",   # blue-800 主色深（hover）
    "primary_lt":  "#DBEAFE",   # blue-100 主色浅底（选中/焦点）
    "accent":      "#D97706",   # amber-600 强调色（关键告警）
    "accent_lt":   "#FEF3C7",   # amber-100 强调浅底
    "ok":          "#16A34A",   # green-600 成功
    "ok_lt":       "#DCFCE7",   # green-100
    "warn":        "#F59E0B",   # amber-500 警告
    "warn_lt":     "#FEF9C3",   # yellow-100
    "err":         "#DC2626",   # red-600 错误
    "err_lt":      "#FEE2E2",   # red-100
    "info":        "#0891B2",   # cyan-600 信息
    "info_lt":     "#CFFAFE",   # cyan-100
}

# 深色主题（比赛展示 / 暗色模式）
COLORS_DARK = {
    "bg":          "#0B1220",   # 深蓝黑底色
    "surface":     "#111827",   # gray-900 卡片
    "surface_2":   "#1F2937",   # gray-800 次级
    "surface_3":   "#374151",   # gray-700 三级
    "border":      "#1F2937",   # gray-800 描边
    "border_strong": "#334155", # slate-700 输入框
    "text":        "#F8FAFC",   # slate-50 主文字
    "text_muted":  "#CBD5E1",   # slate-300 次文字
    "text_dim":    "#94A3B8",   # slate-400 弱化（对比度 6.92:1）
    "primary":     "#3B82F6",   # blue-500 品牌主色
    "primary_dk":  "#2563EB",   # blue-600 hover
    "primary_lt":  "#0E1A30",   # 深蓝底（选中）
    "accent":      "#FBBF24",   # amber-400 强调
    "accent_lt":   "#3A2A0E",   # 深琥珀底
    "ok":          "#22C55E",   # green-500
    "ok_lt":       "#052E16",
    "warn":        "#FBBF24",   # amber-400
    "warn_lt":     "#422006",
    "err":         "#F87171",   # red-400
    "err_lt":      "#450A0A",
    "info":        "#22D3EE",   # cyan-400
    "info_lt":     "#083344",
}


# ---------------------------------------------------------------------------
# 字号 token（7-size scale，对齐 v8: 11/12/13/14/16/18/24）
# ---------------------------------------------------------------------------

FONT_BASE_PX = 13
FONT_SCALE = {
    "xs":   0.846,   # 11px caption / 微标签
    "sm":   0.923,   # 12px 副 UI / 辅助
    "base": 1.0,     # 13px 正文
    "md":   1.077,   # 14px 正文加粗 / 按钮
    "lg":   1.231,   # 16px 子标题
    "xl":   1.385,   # 18px 面板标题
    "2xl":  1.846,   # 24px 主标题 / 大数字
}

FONT_FAMILY = "Microsoft YaHei UI"   # 中文技术栈首选
FONT_MONO = "Cascadia Code"          # 现代等宽字体（Win11 内置）
FONT_MONO_FALLBACK = "Consolas"

FONT_ROLES = {
    "title":    (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["2xl"]), "bold"),
    "subtitle": (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["xl"]), "bold"),
    "heading":  (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["lg"]), "bold"),
    "body":     (FONT_FAMILY, FONT_BASE_PX, "normal"),
    "body_b":   (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["md"]), "bold"),
    "caption":  (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["sm"]), "normal"),
    "micro":    (FONT_FAMILY, int(FONT_BASE_PX * FONT_SCALE["xs"]), "normal"),
    "mono":     (FONT_MONO, int(FONT_BASE_PX * FONT_SCALE["sm"]), "normal"),
    "mono_lg":  (FONT_MONO, FONT_BASE_PX, "normal"),
}


# ---------------------------------------------------------------------------
# 间距 token（4px 基准 × 8 级，对齐 v8 spacing scale）
# ---------------------------------------------------------------------------

SPACE = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "2xl": 24,
    "3xl": 32,
    "4xl": 48,
}

# 面板内边距（比原来更宽松，提升呼吸感）
PANEL_PAD = 16
CARD_PAD = 14
SECTION_GAP = 20


# ---------------------------------------------------------------------------
# 动效 token（对齐 v8: 120/160/240ms 三档过渡）
# ---------------------------------------------------------------------------

DURATION_MS = {
    "instant": 80,      # 按钮按下反馈
    "fast":    120,     # hover、微交互
    "state":   160,     # 状态切换、菜单
    "entrance": 240,    # 页面/大块进入
    "slow":    400,     # 模态/全屏过渡
}

# ease-out-quart 曲线（cubic-bezier(0.25, 1, 0.5, 1)）用步进近似
EASING_OUT_QUART_STEPS = 16


def easing_out_quart(t: float) -> float:
    """Quart out 缓动函数，返回 0..1 的进度。"""
    return 1 - (1 - t) ** 4


# ---------------------------------------------------------------------------
# ttk Style 应用
# ---------------------------------------------------------------------------


def apply_theme(root: tk.Tk | tk.Toplevel, theme: str = "light") -> dict[str, str]:
    """应用主题到 ttk Style，返回当前主题的 COLORS 字典。

    对齐 v8 UI_DESIGN_TOKENS 规范：
      - 60% 背景（slate-50/900）
      - 30% 边框/文字（slate-200~700）
      - 10% 主色（blue-600/500，仅按钮/链接/高亮）
    """
    palette = COLORS_DARK if theme == "dark" else COLORS_LIGHT
    style = ttk.Style(root)
    try:
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
    except tk.TclError:
        pass

    # --- 全局 Frame ---
    style.configure("Surface.TFrame", background=palette["surface"])
    style.configure("Canvas.TFrame", background=palette["bg"])
    style.configure("Card.TFrame", background=palette["surface"],
                    relief="flat", borderwidth=0)

    # --- 文字层级 ---
    style.configure("Title.TLabel",
                    font=FONT_ROLES["title"],
                    background=palette["bg"],
                    foreground=palette["text"])
    style.configure("Subtitle.TLabel",
                    font=FONT_ROLES["subtitle"],
                    background=palette["bg"],
                    foreground=palette["text"])
    style.configure("Heading.TLabel",
                    font=FONT_ROLES["heading"],
                    background=palette["bg"],
                    foreground=palette["text"])
    style.configure("Body.TLabel",
                    font=FONT_ROLES["body"],
                    background=palette["bg"],
                    foreground=palette["text"])
    style.configure("Muted.TLabel",
                    font=FONT_ROLES["caption"],
                    background=palette["bg"],
                    foreground=palette["text_muted"])
    style.configure("Micro.TLabel",
                    font=FONT_ROLES["micro"],
                    background=palette["bg"],
                    foreground=palette["text_dim"])
    # 卡片内文字（背景为 surface 而非 bg）
    style.configure("Card.Title.TLabel",
                    font=FONT_ROLES["subtitle"],
                    background=palette["surface"],
                    foreground=palette["text"])
    style.configure("Card.Body.TLabel",
                    font=FONT_ROLES["body"],
                    background=palette["surface"],
                    foreground=palette["text"])
    style.configure("Card.Muted.TLabel",
                    font=FONT_ROLES["caption"],
                    background=palette["surface"],
                    foreground=palette["text_muted"])

    # --- 按钮（10% 视觉重量，精致间距） ---
    _btn_pad = (SPACE["lg"], SPACE["sm"] + 2)
    style.configure("Primary.TButton",
                    font=FONT_ROLES["body_b"],
                    foreground="#FFFFFF",
                    background=palette["primary"],
                    bordercolor=palette["primary_dk"],
                    focuscolor=palette["primary_lt"],
                    padding=_btn_pad)
    style.map("Primary.TButton",
              background=[("active", palette["primary_dk"]),
                          ("disabled", palette["surface_3"])],
              foreground=[("disabled", palette["text_dim"])])

    style.configure("Secondary.TButton",
                    font=FONT_ROLES["body"],
                    foreground=palette["text_muted"],
                    background=palette["surface"],
                    bordercolor=palette["border_strong"],
                    focuscolor=palette["primary_lt"],
                    padding=_btn_pad)
    style.map("Secondary.TButton",
              background=[("active", palette["surface_2"])],
              foreground=[("active", palette["text"])])

    style.configure("Critical.TButton",
                    font=FONT_ROLES["body_b"],
                    foreground="#FFFFFF",
                    background=palette["accent"],
                    bordercolor=palette["accent"],
                    padding=_btn_pad)
    style.map("Critical.TButton",
              background=[("active", "#B45309")])

    # --- Notebook（高级感 Tab 栏） ---
    style.configure("TNotebook",
                    background=palette["bg"],
                    borderwidth=0,
                    tabmargins=[SPACE["sm"], SPACE["xs"], SPACE["sm"], 0])
    style.configure("TNotebook.Tab",
                    font=FONT_ROLES["body_b"],
                    background=palette["surface_2"],
                    foreground=palette["text_muted"],
                    padding=(SPACE["lg"], SPACE["sm"]),
                    borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", palette["surface"]),
                          ("active", palette["surface_2"])],
              foreground=[("selected", palette["primary"]),
                          ("active", palette["text"])],
              expand=[("selected", (0, 0, 0, 2))])

    # --- LabelFrame（卡片分组） ---
    style.configure("Group.TLabelframe",
                    background=palette["surface"],
                    bordercolor=palette["border"],
                    relief="solid",
                    borderwidth=1)
    style.configure("Group.TLabelframe.Label",
                    font=FONT_ROLES["heading"],
                    foreground=palette["primary"],
                    background=palette["surface"])

    # --- Treeview（精致表格） ---
    _row_h = int(FONT_BASE_PX * 2.4)
    style.configure("Surface.Treeview",
                    font=FONT_ROLES["body"],
                    background=palette["surface"],
                    fieldbackground=palette["surface"],
                    foreground=palette["text"],
                    bordercolor=palette["border"],
                    borderwidth=1,
                    rowheight=_row_h)
    style.configure("Surface.Treeview.Heading",
                    font=FONT_ROLES["body_b"],
                    background=palette["surface_2"],
                    foreground=palette["text_muted"],
                    bordercolor=palette["border"],
                    padding=(SPACE["sm"], SPACE["xs"]))
    style.map("Surface.Treeview",
              background=[("selected", palette["primary_lt"])],
              foreground=[("selected", palette["primary_dk"] if theme == "light" else palette["text"])])

    # --- Combobox ---
    style.configure("TCombobox",
                    font=FONT_ROLES["body"],
                    fieldbackground=palette["surface"],
                    foreground=palette["text"],
                    bordercolor=palette["border_strong"],
                    padding=(SPACE["sm"], SPACE["xs"]))
    style.map("TCombobox",
              fieldbackground=[("readonly", palette["surface_2"])],
              bordercolor=[("focus", palette["primary"])])

    # --- Checkbutton ---
    style.configure("TCheckbutton",
                    font=FONT_ROLES["body"],
                    background=palette["surface"],
                    foreground=palette["text"])
    style.map("TCheckbutton",
              background=[("active", palette["surface_2"])])

    # --- Separator ---
    style.configure("TSeparator", background=palette["border"])

    # --- 设置根窗口背景 ---
    try:
        root.configure(background=palette["bg"])
    except tk.TclError:
        pass

    return palette


def install_fonts() -> None:
    """确保 Tk 内部字体数据库中注册我们用的字体家族。"""
    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(family=FONT_FAMILY, size=FONT_BASE_PX)


__all__ = [
    "COLORS_DARK", "COLORS_LIGHT", "FONT_ROLES", "FONT_SCALE",
    "FONT_MONO_FALLBACK", "SPACE", "PANEL_PAD", "CARD_PAD", "SECTION_GAP",
    "DURATION_MS", "EASING_OUT_QUART_STEPS",
    "apply_theme", "install_fonts", "easing_out_quart",
]
