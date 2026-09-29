"""GUI-facing adapter for selected-only official execution."""
from __future__ import annotations

from tasks_official.registry import LazyTaskRegistry
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from data_loader.snapshot import load_json_snapshot

from .execution import ExecutionPlan, OfficialRunResult, OfficialRunner, build_execution_plan


class OfficialGuiController:
    def __init__(self, runner: OfficialRunner | None = None):
        self._runner = runner or OfficialRunner(LazyTaskRegistry.with_module_resolver())

    def create_plan(self, task_codes: Sequence[str]) -> ExecutionPlan:
        return build_execution_plan(task_codes)

    def run_snapshot(
        self,
        task_codes: Sequence[str],
        snapshot_path: str | Path,
        options: Mapping[str, Any] | None = None,
    ) -> OfficialRunResult:
        dataset = load_json_snapshot(snapshot_path)
        return self._runner.run(task_codes, dataset, options=options)