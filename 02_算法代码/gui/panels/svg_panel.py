# -*- coding: utf-8 -*-
"""Panel 4: SVG 美化 + 增删 + Canvas 预览（真正可视化）

借鉴 frontend-dev 与 impeccable 设计原则：
- 美化前后对比（GSAP 时间轴思路的"双栏同时入场"）
- 关键设备高亮（pulse 动画）
- 拓扑等价即时校验
- **Canvas 渲染 SVG**（不止源码对比，真实图形可视化）
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from gui.panels.svg_renderer import render_svg
from gui.theme import COLORS_LIGHT, FONT_ROLES, SPACE


class SvgPanel(ttk.Frame):
    """SVG 上传 + 美化 + 增删 + Canvas 可视化预览面板。

    每个视图 = Canvas（上方，可视化）+ Text（下方，源码）。
    严格遵循比赛要求 §5.1/5.2。
    """

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=SPACE["md"])
        self._src_svg: str = ""
        self._beautified_svg: str = ""
        self._modified_svg: str = ""
        self._build()

    def _build(self) -> None:
        title = ttk.Label(self, text="SVG 美化与增删（任务 5.1 / 5.2）",
                          font=FONT_ROLES["title"], foreground=COLORS_LIGHT["primary"])
        title.pack(anchor=tk.W, pady=(0, SPACE["sm"]))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, SPACE["sm"]))
        ttk.Button(toolbar, text="上传 SVG",
                   command=self._load_svg).pack(side=tk.LEFT, padx=(0, SPACE["xs"]))
        ttk.Button(toolbar, text="5.1 美化",
                   command=self._beautify).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="5.2 添加站房",
                   command=self._add_room).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="5.2 删除设备",
                   command=self._remove_device).pack(side=tk.LEFT, padx=SPACE["xs"])
        ttk.Button(toolbar, text="保存",
                   command=self._save).pack(side=tk.LEFT, padx=SPACE["xs"])

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        # 左：原文 / 右：美化结果（并排 pack，每个含 Canvas + Text）
        self.src_pane = self._make_code_pane(body, "原文（上传后显示）")
        self.dst_pane = self._make_code_pane(body, "美化结果 / 增删后")

        # 校验提示
        self.verify_var = tk.StringVar(value="尚未上传 SVG")
        ttk.Label(self, textvariable=self.verify_var, foreground=COLORS_LIGHT["text_muted"],
                  font=FONT_ROLES["caption"]).pack(anchor=tk.W, pady=(SPACE["sm"], 0))

    def _make_code_pane(self, parent: tk.Misc, label: str) -> dict[str, tk.Widget]:
        """创建一个含 Canvas + Text 的双视图面板：上方 Canvas 可视化，下方 Text 源码。"""
        frame = ttk.LabelFrame(parent, text=label, padding=SPACE["sm"])
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, SPACE["xs"]))
        canvas = tk.Canvas(frame, background=COLORS_LIGHT["surface"],
                           highlightthickness=1, highlightbackground=COLORS_LIGHT["border"])
        canvas.pack(fill=tk.BOTH, expand=True, pady=(0, SPACE["xs"]))
        text = tk.Text(frame, wrap=tk.NONE, font=FONT_ROLES["mono"], height=8,
                       background=COLORS_LIGHT["surface_2"], foreground=COLORS_LIGHT["text"],
                       borderwidth=0)
        text.pack(fill=tk.X)
        return {"frame": frame, "canvas": canvas, "text": text}

    # --- 操作 ------------------------------------------------------------

    def _load_svg(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 SVG 文件（LINE215.svg / LINE216.svg 等）",
            filetypes=(("SVG", "*.svg"), ("所有", "*.*")),
        )
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        self._src_svg = text
        self._modified_svg = ""
        self._refresh_panes()

    def _beautify(self) -> None:
        if not self._src_svg:
            messagebox.showinfo("请先上传 SVG", "请先点击「上传 SVG」选择文件")
            return
        try:
            from tasks_official.task5_svg.task_5_1_beautify.detector import beautify, verify_topological_equivalence
            from tasks_official.task5_svg.task_5_1_beautify.detector import (
                _parse_devices, _parse_edges,
            )
            devices = _parse_devices(self._src_svg)
            voltage_lookup = {d["equip_id"]: d.get("voltage") or 10 for d in devices}
            equip_type_lookup = {d["equip_id"]: d.get("equip_type") or "DEVICE" for d in devices}
            edges = _parse_edges(self._src_svg)
            out = beautify(
                self._src_svg,
                voltage_lookup=voltage_lookup,
                equip_type_lookup=equip_type_lookup,
                edge_lookup=edges,
            )
            self._beautified_svg = out
            self._modified_svg = out
            res = verify_topological_equivalence(
                self._src_svg, out,
                edges_before=edges, edges_after=edges,
            )
            status = "✓ 拓扑等价" if res["ok"] else f"✗ {res['summary']}"
            self.verify_var.set(f"美化完成 {len(out)} 字节 | 设备 {len(devices)} | 边 {len(edges)} | {status}")
            self._refresh_panes()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("美化失败", f"{type(exc).__name__}: {exc}")

    def _add_room(self) -> None:
        src = self._modified_svg or self._src_svg
        if not src:
            messagebox.showinfo("请先上传 SVG", "请先上传 SVG 再添加站房")
            return
        dlg = _AddRoomDialog(self)
        if dlg.result is None:
            return
        room_id, switch_ids, left_id, right_id = dlg.result
        try:
            from tasks_official.task5_svg.task_5_2_modify.detector import TransactionalEditor
            editor = TransactionalEditor(src)
            editor.choose("add_room", room_id=room_id,
                          inner_switch_ids=switch_ids,
                          left_switch_id=left_id, right_switch_id=right_id)
            editor.validate()
            editor.apply()
            editor.validate()
            editor.confirm(user="gui")
            new_svg = editor.save()
            self._modified_svg = new_svg
            self._refresh_panes()
            self.verify_var.set(f"✓ 已添加站房 {room_id}（{len(switch_ids)} 个内部开关）")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("添加失败", f"{type(exc).__name__}: {exc}")

    def _remove_device(self) -> None:
        src = self._modified_svg or self._src_svg
        if not src:
            messagebox.showinfo("请先上传 SVG", "请先上传 SVG 再删除设备")
            return
        from tasks_official.task5_svg.task_5_2_modify.detector import list_devices
        devices = list_devices(src)
        dlg = _RemoveDeviceDialog(self, devices)
        if dlg.result is None:
            return
        device_id = dlg.result
        try:
            from tasks_official.task5_svg.task_5_2_modify.detector import TransactionalEditor
            editor = TransactionalEditor(src)
            editor.choose("remove_device", device_id=device_id)
            editor.validate()
            editor.apply()
            editor.confirm()
            new_svg = editor.save()
            self._modified_svg = new_svg
            self._refresh_panes()
            self.verify_var.set(f"✓ 已删除设备 {device_id}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("删除失败", f"{type(exc).__name__}: {exc}")

    def _save(self) -> None:
        target = self._modified_svg or self._beautified_svg
        if not target:
            messagebox.showinfo("无可保存内容", "请先美化或修改 SVG")
            return
        path = filedialog.asksaveasfilename(
            title="保存 SVG", defaultextension=".svg",
            filetypes=(("SVG", "*.svg"),),
        )
        if not path:
            return
        Path(path).write_text(target, encoding="utf-8")
        messagebox.showinfo("已保存", path)

    # --- 视图 ------------------------------------------------------------

    def _refresh_panes(self) -> None:
        # 原文
        self.src_pane["text"].configure(state=tk.NORMAL)
        self.src_pane["text"].delete("1.0", tk.END)
        self.src_pane["text"].insert("1.0", self._src_svg)
        self.src_pane["text"].configure(state=tk.DISABLED)
        if self._src_svg:
            render_svg(self.src_pane["canvas"], self._src_svg)
        else:
            self.src_pane["canvas"].delete("all")
        # 美化/修改结果
        result_svg = self._modified_svg or self._beautified_svg
        self.dst_pane["text"].configure(state=tk.NORMAL)
        self.dst_pane["text"].delete("1.0", tk.END)
        self.dst_pane["text"].insert("1.0", result_svg)
        self.dst_pane["text"].configure(state=tk.DISABLED)
        if result_svg:
            render_svg(self.dst_pane["canvas"], result_svg)
        else:
            self.dst_pane["canvas"].delete("all")


# ---------------------------------------------------------------------------
# 子对话框
# ---------------------------------------------------------------------------


class _AddRoomDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("5.2 添加站房")
        self.resizable(False, False)
        self.result: tuple[str, tuple[str, ...], str, str] | None = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="房间 ID:").grid(row=0, column=0, sticky=tk.W)
        self.room = tk.StringVar(value="ROOM000300")
        ttk.Entry(body, textvariable=self.room, width=20).grid(row=0, column=1)
        ttk.Label(body, text="内部开关 ID (逗号):").grid(row=1, column=0, sticky=tk.W)
        self.sw = tk.StringVar(value="00301,00302,00303")
        ttk.Entry(body, textvariable=self.sw, width=20).grid(row=1, column=1)
        ttk.Label(body, text="左侧设备 ID:").grid(row=2, column=0, sticky=tk.W)
        self.left = tk.StringVar(value="00104")
        ttk.Entry(body, textvariable=self.left, width=20).grid(row=2, column=1)
        ttk.Label(body, text="右侧设备 ID:").grid(row=3, column=0, sticky=tk.W)
        self.right = tk.StringVar(value="00102")
        ttk.Entry(body, textvariable=self.right, width=20).grid(row=3, column=1)
        bar = ttk.Frame(body)
        bar.grid(row=4, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(bar, text="确定", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.transient(master)
        self.grab_set()
        self.wait_window()

    def _ok(self) -> None:
        try:
            self.result = (
                self.room.get().strip(),
                tuple(s.strip() for s in self.sw.get().split(",") if s.strip()),
                self.left.get().strip(),
                self.right.get().strip(),
            )
            self.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("输入错误", str(exc), parent=self)


class _RemoveDeviceDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, devices: Sequence[str]) -> None:
        super().__init__(master)
        self.title("5.2 删除设备")
        self.result: str | None = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="选择要删除的设备 ID:").pack(anchor=tk.W)
        self.choice = tk.StringVar()
        combo = ttk.Combobox(body, textvariable=self.choice, values=devices, state="readonly", width=20)
        combo.pack(anchor=tk.W, pady=(4, 8))
        if devices:
            combo.current(0)
        bar = ttk.Frame(body)
        bar.pack()
        ttk.Button(bar, text="确定", command=lambda: self._ok(combo)).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.transient(master)
        self.grab_set()
        self.wait_window()

    def _ok(self, combo: ttk.Combobox) -> None:
        self.result = combo.get()
        self.destroy()


__all__ = ["SvgPanel"]
