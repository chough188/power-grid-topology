"""Lazy loading for explicitly selected official tasks."""
from __future__ import annotations

import importlib
from collections.abc import Callable

from .catalog import TaskSpec
from .contracts import OfficialDetector


class TaskUnavailableError(RuntimeError):
    pass


class LazyTaskRegistry:
    """Default scaffold registry: rejects every task without importing the package.

    Production callers that want the package's detector implementations should
    explicitly opt-in via :meth:`with_module_resolver` (or any other resolver).
    """

    def __init__(self, resolver: Callable[[TaskSpec], OfficialDetector] | None = None):
        if resolver is None:
            self._resolver: Callable[[TaskSpec], OfficialDetector] = self._reject_default
        else:
            self._resolver = resolver

    @classmethod
    def with_module_resolver(cls) -> "LazyTaskRegistry":
        """Return a registry that lazily imports each detector from its task package."""

        return cls(cls._resolve_module)

    def resolve(self, task: TaskSpec) -> OfficialDetector:
        if task.implementation_status != "ready":
            raise TaskUnavailableError(
                f"Official task {task.code} is {task.implementation_status}; detector execution is disabled"
            )
        return self._resolver(task)

    @staticmethod
    def _reject_default(task: TaskSpec) -> OfficialDetector:
        raise TaskUnavailableError(
            f"Default scaffold registry has no detector for official task {task.code}; "
            f"construct LazyTaskRegistry.with_module_resolver() to enable execution"
        )

    @staticmethod
    def _resolve_module(task: TaskSpec) -> OfficialDetector:
        module_name = f"tasks_official.{task.module_path.replace('/', '.')}.detector"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                raise TaskUnavailableError(f"Detector module is missing for official task {task.code}") from error
            raise
        detector = getattr(module, "detect", None)
        if not callable(detector):
            raise TaskUnavailableError(f"Detector callable is missing for official task {task.code}")
        return detector