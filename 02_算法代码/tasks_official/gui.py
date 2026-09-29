"""Desktop GUI for the official CP-202606 task track.

启动方式:
    双击项目根 启动.bat          → 正常模式 (手动选数据)
    双击项目根 启动.bat --demo   → 演示模式 (内置数据, 全选任务, 一键执行)
    py -3 -m tasks_official.gui --demo
"""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .catalog import OFFICIAL_TASKS
from .execution import SelectionError
from .gui_controller import OfficialGuiController
from .registry import TaskUnavailableError

# 内置演示数据路径 (02_算法代码/data/snapshot.json)
_ALGO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_SNAPSHOT = _ALGO_ROOT / "data" / "snapshot.json"


class OfficialCompetitionGui:
    def __init__(self, root: tk.Tk, controller: OfficialGuiController | None = None, *, demo: bool = False):
        self.root = root
        self.controller = controller or OfficialGuiController()
        self.task_variables: dict[str, tk.BooleanVar] = {}
        self.snapshot_path = tk.StringVar(value="")
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.execute_button: ttk.Button | None = None
        self._demo = demo
        self._configure_window()
        self._build_layout()
        if demo:
            self._init_demo_mode()

    def _configure_window(self):
        self.root.title("CP-202606 配电网拓扑校验——官方 12 子任务")
        self.root.geometry("1180x780")
        self.root.minsize(980, 680)
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Subtitle.TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Group.TLabelframe.Label", font=("Microsoft YaHei UI", 11, "bold"))

    def _build_layout(self):
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="官方 12 子任务独立执行器", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="默认不选择任何任务；仅执行明确勾选项。旧 28 异常、旧 API、LLM、GNN 与旧修正引擎不会加载。",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 14))

        data_frame = ttk.LabelFrame(container, text="1. 官方数据快照", style="Group.TLabelframe", padding=10)
        data_frame.pack(fill=tk.X)
        ttk.Entry(data_frame, textvariable=self.snapshot_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(data_frame, text="选择 JSON…", command=self._choose_snapshot).pack(side=tk.LEFT, padx=(8, 0))

        tasks_frame = ttk.LabelFrame(container, text="2. 明确选择任务", style="Group.TLabelframe", padding=10)
        tasks_frame.pack(fill=tk.X, pady=12)
        self._build_task_groups(tasks_frame)

        selection_actions = ttk.Frame(tasks_frame)
        selection_actions.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        ttk.Button(selection_actions, text="全选 12 项", command=self._select_all).pack(side=tk.LEFT)
        ttk.Button(selection_actions, text="清空选择", command=self._clear_selection).pack(side=tk.LEFT, padx=8)

        action_frame = ttk.Frame(container)
        action_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(action_frame, text="生成执行计划", command=self._show_plan).pack(side=tk.LEFT)
        self.execute_button = ttk.Button(action_frame, text="执行所选任务", command=self._execute_selected)
        self.execute_button.pack(side=tk.LEFT, padx=8)
        ttk.Button(action_frame, text="退出", command=self.root.destroy).pack(side=tk.RIGHT)

        output_frame = ttk.LabelFrame(container, text="3. 执行状态与证据", style="Group.TLabelframe", padding=8)
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state=tk.DISABLED,
        )
        self.output.pack(fill=tk.BOTH, expand=True)
        self._append_output("就绪：尚未选择任务，当前不会触发任何算法。")

    def _build_task_groups(self, parent: ttk.LabelFrame):
        grouped: OrderedDict[str, list] = OrderedDict()
        for task in OFFICIAL_TASKS:
            grouped.setdefault(task.primary_category, []).append(task)
        for group_index, (category, tasks) in enumerate(grouped.items()):
            group_frame = ttk.LabelFrame(parent, text=category, padding=8)
            group_frame.grid(
                row=group_index // 2,
                column=group_index % 2,
                sticky=tk.NSEW,
                padx=(0, 8) if group_index % 2 == 0 else (8, 0),
                pady=4,
            )
            parent.columnconfigure(group_index % 2, weight=1)
            for task in tasks:
                variable = tk.BooleanVar(value=False)
                self.task_variables[task.code] = variable
                ttk.Checkbutton(
                    group_frame,
                    text=f"{task.code}  {task.name}  [{task.implementation_status}]",
                    variable=variable,
                ).pack(anchor=tk.W, pady=2)

    def _init_demo_mode(self):
        """演示模式: 自动加载内置数据 + 全选任务, 一键即可执行。"""
        if _DEMO_SNAPSHOT.exists():
            self.snapshot_path.set(str(_DEMO_SNAPSHOT))
            self._append_output(f"[DEMO] 已自动加载内置测试数据: {_DEMO_SNAPSHOT.name}")
        else:
            self._append_output(f"[DEMO] 警告: 内置数据不存在 ({_DEMO_SNAPSHOT})，请手动选择。")
        self._select_all()
        self._append_output("[DEMO] 演示模式就绪 — 点击「执行所选任务」即可运行全部 12 项检测。")
        self._append_output("[DEMO] 数据为公开合成数据 (76 设备 / 9 馈线 / 3 变电站)，可安全展示。")

    def _choose_snapshot(self):
        selected = filedialog.askopenfilename(
            title="选择官方 14 表 JSON 快照",
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if selected:
            self.snapshot_path.set(str(Path(selected)))

    def _selected_codes(self) -> list[str]:
        return [code for code, variable in self.task_variables.items() if variable.get()]

    def _select_all(self):
        for variable in self.task_variables.values():
            variable.set(True)
        self._append_output("已显式选择全部 12 个官方子任务。")

    def _clear_selection(self):
        for variable in self.task_variables.values():
            variable.set(False)
        self._append_output("已清空选择；所有任务均处于零触发状态。")

    def _show_plan(self):
        selected_codes = self._selected_codes()
        try:
            plan = self.controller.create_plan(selected_codes)
        except SelectionError as error:
            self._append_output(f"未生成计划：{error}")
            messagebox.showwarning("未选择任务", "请至少勾选一个官方子任务。")
            return
        self._append_output("执行模式：selected_only")
        self._append_output(f"所选任务：{', '.join(plan.task_codes)}")
        self._append_output(f"涉及 Sheet：{', '.join(plan.output_sheets)}")
        self._append_output(f"永久隔离：{', '.join(plan.isolated_components)}")
        self._append_output("计划生成阶段未导入任何任务 detector。")

    def _execute_selected(self):
        selected_codes = self._selected_codes()
        if not selected_codes:
            self._append_output("执行已阻止：没有选择任务，零算法触发。")
            messagebox.showwarning("未选择任务", "没有勾选任务，不会执行任何功能。")
            return
        snapshot = self.snapshot_path.get().strip()
        if not snapshot:
            self._append_output("执行已阻止：未选择官方数据快照，零算法触发。")
            messagebox.showwarning("缺少数据", "请选择包含 14 张官方表的 JSON 快照。")
            return
        if self.execute_button is not None:
            self.execute_button.configure(state=tk.DISABLED)
        self._append_output(f"开始预检所选任务：{', '.join(selected_codes)}")
        worker = threading.Thread(
            target=self._run_worker,
            args=(selected_codes, snapshot),
            daemon=True,
        )
        worker.start()
        self.root.after(100, self._poll_worker)

    def _run_worker(self, selected_codes: list[str], snapshot: str):
        try:
            result = self.controller.run_snapshot(selected_codes, snapshot)
            self.worker_queue.put(("success", result))
        except Exception as error:
            self.worker_queue.put(("error", error))

    def _poll_worker(self):
        try:
            status, payload = self.worker_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_worker)
            return
        if self.execute_button is not None:
            self.execute_button.configure(state=tk.NORMAL)
        if status == "success":
            self._handle_success(payload)
        else:
            self._handle_error(payload)

    def _handle_success(self, result):
        self._append_output(f"执行完成：{', '.join(result.executed_task_codes)}")
        for task_code, records in result.records_by_task.items():
            self._append_output(f"任务 {task_code}：{len(records)} 条结果")
            for record in records:
                self._append_output(str(asdict(record)))

    def _handle_error(self, error: Exception):
        if isinstance(error, TaskUnavailableError):
            self._append_output(f"预检拒绝：{error}")
            self._append_output("没有任务被部分执行。请先完成所选任务 detector 并标记为 ready。")
        else:
            self._append_output(f"执行失败：{type(error).__name__}: {error}")
        messagebox.showerror("官方任务未执行", str(error))

    def _append_output(self, text: str):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, f"{text}\n")
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)


def main():
    demo = "--demo" in sys.argv or "demo" in sys.argv
    root = tk.Tk()
    app = OfficialCompetitionGui(root, demo=demo)
    if demo:
        root.title("CP-202606 配电网拓扑校验 [DEMO 演示模式]")
    root.mainloop()


if __name__ == "__main__":
    main()
