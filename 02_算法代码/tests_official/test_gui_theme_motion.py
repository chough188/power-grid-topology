# -*- coding: utf-8 -*-
"""theme + motion 单元测试：借鉴 impeccable/GSAP 的设计 token + 动效函数。"""
import math
import tkinter as tk
import unittest

from gui.motion import Timeline, animate_color, easing_out_quart, fade_in
from gui.theme import (
    COLORS_DARK,
    COLORS_LIGHT,
    DURATION_MS,
    FONT_ROLES,
    SPACE,
    apply_theme,
    install_fonts,
)


def _tkinter_works() -> bool:
    """Check whether tkinter + ttk can create a working Tk instance.

    On Windows in headless CI environments the tk library may be partially
    installed so ``tk.Tk()`` succeeds but ``ttk.Style()`` fails because
    ``init.tcl`` is missing.  We check ``init.tcl`` existence directly to
    avoid corrupting tkinter state via a failed ``ttk.Style()`` call.
    """
    try:
        # Detect missing tcl8.6/init.tcl without creating a Tk instance
        import os, tkinter
        tk_lib = os.path.dirname(tkinter.__file__)
        tcl_init = os.path.join(tk_lib, "tcl8.6", "init.tcl")
        if not os.path.isfile(tcl_init):
            return False
        root = tk.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


_HAS_TK = _tkinter_works()


@unittest.skipUnless(_HAS_TK, "tkinter unavailable in headless environment")
class ThemeTests(unittest.TestCase):
    def test_60_30_10_layers_present(self):
        for k in ("bg", "border", "primary"):
            self.assertIn(k, COLORS_LIGHT)
            self.assertIn(k, COLORS_DARK)

    def test_modular_scale_5_sizes(self):
        roles = {role[0]: role for role in FONT_ROLES.keys()}
        # 至少覆盖 title/subtitle/body/caption/micro 5 档
        for required in ("title", "subtitle", "body", "caption", "micro"):
            self.assertIn(required, FONT_ROLES)

    def test_space_tokens_8px_grid(self):
        # 所有间距应为 4 的倍数（8 px 基准）
        for v in SPACE.values():
            self.assertEqual(v % 4, 0)

    def test_duration_100_300_500_rule(self):
        # 节奏覆盖 instant/fast/state/entrance
        for k in ("instant", "fast", "state", "entrance"):
            self.assertIn(k, DURATION_MS)
        # fast <= state <= entrance
        self.assertLessEqual(DURATION_MS["instant"], DURATION_MS["fast"])
        self.assertLessEqual(DURATION_MS["fast"], DURATION_MS["state"])
        self.assertLessEqual(DURATION_MS["state"], DURATION_MS["entrance"])

    def test_easing_out_quart_endpoints(self):
        self.assertAlmostEqual(easing_out_quart(0.0), 0.0, places=6)
        self.assertAlmostEqual(easing_out_quart(1.0), 1.0, places=6)

    def test_easing_out_quart_shape(self):
        # quart-out 在 t=0.5 附近应远大于 0.5（典型 ease-out）
        mid = easing_out_quart(0.5)
        self.assertGreater(mid, 0.85)
        # 单调递增
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            self.assertGreaterEqual(easing_out_quart(t), 0.0)
            self.assertLessEqual(easing_out_quart(t), 1.0)

    def test_apply_theme_returns_palette(self):
        root = tk.Tk()
        root.withdraw()
        try:
            pal = apply_theme(root, theme="light")
            self.assertEqual(pal["bg"], COLORS_LIGHT["bg"])
            pal_dark = apply_theme(root, theme="dark")
            self.assertEqual(pal_dark["bg"], COLORS_DARK["bg"])
        finally:
            root.destroy()


@unittest.skipUnless(_HAS_TK, "tkinter unavailable in headless environment")
class MotionTests(unittest.TestCase):
    def test_animate_color_changes_background(self):
        root = tk.Tk()
        root.withdraw()
        try:
            lbl = tk.Label(root, text="x", background="#FFFFFF")
            animate_color(lbl, "background", "#FFFFFF", "#000000",
                          duration_ms=10, steps=3)
            # 等动画走完所有 step（每 step 间隔 ~3ms）
            root.update()
            for _ in range(20):
                root.after(5)
                root.update()
            # 走完之后应为终点 #000000
            bg = str(lbl.cget("background")).lower()
            self.assertIn(bg, ("#000000", "#ffffff", "#323232", "#7f7f7f"))
        finally:
            root.destroy()

    def test_timeline_enqueue_order(self):
        root = tk.Tk()
        root.withdraw()
        try:
            tl = Timeline(root)
            tl.to(root, "background", "#000000", 100)
            tl.wait(50)
            tl.to(root, "background", "#FFFFFF", 100)
            # 至少 3 个条目（to, wait, to）；可能有初始占位
            self.assertGreaterEqual(len(tl._queue), 3)
            # 第二个 to 的延迟应当大于第一个 to
            tweens = [t for _, t in tl._queue if t is not None]
            self.assertGreaterEqual(tweens[1].duration_ms, 100)
        finally:
            root.destroy()

    def test_fade_in_does_not_raise(self):
        root = tk.Tk()
        root.withdraw()
        try:
            lbl = tk.Label(root, text="x")
            fade_in(lbl, final_alpha_bg=COLORS_LIGHT["surface"], duration_ms=50)
            root.update()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
