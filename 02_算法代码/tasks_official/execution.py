"""Selected-only orchestration for the official submission track."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from data_loader.loader import OfficialDataset

from shared.contract_gate import validate_output_contract  # re-exported below
from shared.graph_algos import adjacency_from_terminals
from shared.switch_state import build_running_adjacency, build_signal_point_map

from .catalog import TaskSpec, get_task
from .contracts import ProblemRecord, TaskContext
from .registry import LazyTaskRegistry


ISOLATED_COMPONENTS = (
    "legacy_28_anomaly",
    "legacy_api",
    "legacy_correction_engine",
    "llm_assistant",
    "gnn_classifier",
)


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionPlan:
    tasks: tuple[TaskSpec, ...]
    output_sheets: tuple[str, ...]
    mode: str = "selected_only"
    isolated_components: tuple[str, ...] = ISOLATED_COMPONENTS

    @property
    def task_codes(self) -> tuple[str, ...]:
        return tuple(task.code for task in self.tasks)


@dataclass(frozen=True)
class OfficialRunResult:
    plan: ExecutionPlan
    executed_task_codes: tuple[str, ...]
    records_by_task: Mapping[str, tuple[ProblemRecord, ...]]


def build_execution_plan(task_codes: Sequence[str]) -> ExecutionPlan:
    normalized = tuple(str(code).strip() for code in task_codes if str(code).strip())
    if not normalized:
        raise SelectionError("At least one official task code must be selected")
    if len(set(normalized)) != len(normalized):
        raise SelectionError("Duplicate official task codes are not allowed")
    try:
        tasks = tuple(get_task(code) for code in normalized)
    except ValueError as error:
        raise SelectionError(str(error)) from error
    # Stub tasks (2.3) are excluded from execution but may be requested by callers;
    # filter them out so the runner doesn't try to resolve them and get TaskUnavailableError.
    ready_tasks = tuple(t for t in tasks if t.implementation_status == "ready")
    if len(ready_tasks) < len(tasks):
        stub_codes = [t.code for t in tasks if t.implementation_status != "ready"]
    output_sheets = tuple(dict.fromkeys(task.output_sheet for task in ready_tasks))
    return ExecutionPlan(tasks=ready_tasks, output_sheets=output_sheets)


class OfficialRunner:
    def __init__(self, registry: LazyTaskRegistry | None = None):
        # Default to module-resolving registry so detectors are actually loaded
        self._registry = registry or LazyTaskRegistry.with_module_resolver()

    def run(
        self,
        task_codes: Sequence[str],
        dataset: OfficialDataset,
        options: Mapping[str, Any] | None = None,
    ) -> OfficialRunResult:
        plan = build_execution_plan(task_codes)
        if (options or {}).get("__allow_incomplete_dataset__"):
            warnings_collected: list[str] = []
            try:
                dataset.validate()
            except ValueError as exc:
                warnings_collected.append(f"schema 校验告警：{exc}")
        else:
            dataset = dataset.normalized()  # EQUIP_TYPE 归一（解 D8 静默失效）
        resolved = tuple((task, self._registry.resolve(task)) for task in plan.tasks)
        # P1-1: 预构建共享图数据，通过 options 注入缓存，避免 6+ 个检测器各自
        # 重复扫描 TERMINAL 表构建邻接表 / 信号表（检测器内部读取时带 fallback，
        # 直接调用检测器（如单元测试）不受影响）
        _adj = adjacency_from_terminals(dataset.tables)
        _sig = build_signal_point_map(dataset.tables)
        shared_cache = {
            "adjacency": _adj,
            "signal_map": _sig,
            "running_adj": build_running_adjacency(dataset.tables, base_adj=_adj, signal_map=_sig),
        }
        context_options = dict(options or {})
        context_options["_shared_cache"] = shared_cache
        records_by_task: dict[str, tuple[ProblemRecord, ...]] = {}
        # P2-2: 5.0 自评分可复用本批已执行的检测结果（live dict 引用，
        # 5.0 执行时可见其之前任务的结果）
        context_options["_records_by_task"] = records_by_task
        # 仅当 5.0 传入的是全量表对象时才允许复用，避免作用域（按站/馈线过滤）计数被全局结果污染
        context_options["_full_tables"] = dataset.tables
        context = TaskContext(tables=dataset.tables, options=context_options)
        executed: list[str] = []
        for task, detector in resolved:
            records = tuple(detector(context))
            for record in records:
                if not isinstance(record, ProblemRecord):
                    raise TypeError(f"Official task {task.code} returned a non-ProblemRecord value")
                if record.task_code != task.code:
                    raise ValueError(f"Official task {task.code} returned record for {record.task_code}")
            records_by_task[task.code] = records
            executed.append(task.code)
        return OfficialRunResult(
            plan=plan,
            executed_task_codes=tuple(executed),
            records_by_task=records_by_task,
        )


# D16 内容级契约门禁：实现位于 shared 公共层（避免 output_writer 反向依赖本轨道）。
# 此处保留 ``validate_output_contract`` 名称以兼容
# ``from tasks_official.execution import validate_output_contract`` 既有调用/测试。
