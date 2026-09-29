# -*- coding: utf-8 -*-
"""GUI 动效：借鉴 GSAP 时间轴思路，用 tk.after() 在 Tkinter 中实现。

- :func:`after_ms` —— 100/300/500 规则的标准延迟
- :func:`fade_in` —— 透明度模拟（用 fg/bg 渐变）
- :func:`pulse` —— 关键设备闪烁（GSAP 思路）
- :class:`Timeline` —— GSAP 风格时间轴，支持 ``.to()``/``.wait()``/``.start()``

设计原则（来自 impeccable motion-design.md）：
  - 时长比缓动更重要：100-150ms 即时反馈 / 200-300ms 状态切换 / 500ms 模态入场
  - ease-out-quart 优于线性（expo/quart 系列）
  - 仅"transform/opacity" — Tkinter 等价物是 move() + 颜色渐变
  - 退出动画比进入快（≈75%）
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from gui.theme import DURATION_MS, easing_out_quart


def after_ms(root: tk.Misc, delay_ms: int, fn: Callable[[], Any]) -> str:
    """``after()`` 的便捷封装，返回 after_id 便于 cancel。"""
    return root.after(delay_ms, fn)


def cancel(root: tk.Misc, after_id: str) -> None:
    try:
        root.after_cancel(after_id)
    except tk.TclError:
        pass


# ---------------------------------------------------------------------------
# 渐变 / 闪烁
# ---------------------------------------------------------------------------


def animate_color(
    widget: tk.Misc,
    attr: str,
    start_hex: str,
    end_hex: str,
    duration_ms: int = DURATION_MS["fast"],
    steps: int = 12,
    on_done: Callable[[], Any] | None = None,
) -> None:
    """把 widget 的 ``attr``（如 ``"background"`` / ``"foreground"``）从 start 渐变到 end。"""
    def _hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    s = _hex_to_rgb(start_hex)
    e = _hex_to_rgb(end_hex)
    started = [0]

    def _step() -> None:
        started[0] += 1
        t = started[0] / steps
        tt = easing_out_quart(t)
        r = int(s[0] + (e[0] - s[0]) * tt)
        g = int(s[1] + (e[1] - s[1]) * tt)
        b = int(s[2] + (e[2] - s[2]) * tt)
        try:
            widget.configure(**{attr: f"#{r:02x}{g:02x}{b:02x}"})
        except tk.TclError:
            return
        if started[0] < steps:
            widget.after(duration_ms // steps, _step)
        elif on_done:
            on_done()

    _step()


def fade_in(
    widget: tk.Misc,
    final_alpha_bg: str | None = None,
    final_alpha_fg: str | None = None,
    start_bg: str = "#FFFFFF",
    duration_ms: int = DURATION_MS["entrance"],
    on_done: Callable[[], Any] | None = None,
) -> None:
    """模拟 fade-in：从白色渐变到 final_alpha_bg（颜色淡入）。"""
    if final_alpha_bg:
        animate_color(widget, "background", start_bg, final_alpha_bg, duration_ms, on_done=on_done)
    if final_alpha_fg:
        animate_color(widget, "foreground", start_bg, final_alpha_bg, duration_ms, on_done=on_done)


def pulse(
    widget: tk.Misc,
    attr: str = "background",
    color_a: str = "#FF6F00",
    color_b: str = "#E08400",
    period_ms: int = 900,
    cycles: int = 3,
) -> None:
    """关键告警闪烁（GSAP yoyo 思路）。"""
    counter = [0]

    def _step_a() -> None:
        if counter[0] >= cycles * 2:
            return
        animate_color(widget, attr, color_a, color_b, period_ms // 2)
        widget.after(period_ms // 2, _step_b)

    def _step_b() -> None:
        counter[0] += 1
        if counter[0] >= cycles * 2:
            return
        animate_color(widget, attr, color_b, color_a, period_ms // 2)
        widget.after(period_ms // 2, _step_a)

    _step_a()


# ---------------------------------------------------------------------------
# 时间轴（GSAP-style）
# ---------------------------------------------------------------------------


@dataclass
class _Tween:
    target: tk.Misc
    attr: str
    end: str
    duration_ms: int
    on_done: Callable[[], Any] | None = None


class Timeline:
    """GSAP 风格时间轴：编排一组 Tween + 延迟。

    用法::

        tl = Timeline(root)
        tl.to(widget_a, "background", "#0B66C2", duration_ms=240)
        tl.wait(80)
        tl.to(widget_b, "foreground", "#E08400", duration_ms=300)
        tl.start()
    """

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._queue: list[tuple[int, _Tween | None]] = [(0, None)]  # (delay_ms, tween_or_None)
        self._cursor = 0

    def to(
        self,
        target: tk.Misc,
        attr: str,
        end: str,
        duration_ms: int = DURATION_MS["fast"],
        on_done: Callable[[], Any] | None = None,
    ) -> "Timeline":
        tween = _Tween(target, attr, end, duration_ms, on_done)
        self._queue.append((self._cursor, tween))
        return self

    def wait(self, ms: int) -> "Timeline":
        self._cursor += ms
        self._queue.append((self._cursor, None))
        return self

    def start(self) -> None:
        for delay, tween in self._queue:
            if tween is None:
                continue
            self._root.after(delay, lambda t=tween: animate_color(
                t.target, t.attr, _current_hex(t.target, t.attr), t.end,
                t.duration_ms, on_done=t.on_done,
            ))


def _current_hex(widget: tk.Misc, attr: str) -> str:
    try:
        val = widget.cget(attr)
        if isinstance(val, str) and val.startswith("#") and len(val) in (7, 4):
            return val
    except (tk.TclError, AttributeError):
        pass
    return "#FFFFFF"


__all__ = [
    "after_ms", "cancel",
    "animate_color", "fade_in", "pulse",
    "Timeline",
]
