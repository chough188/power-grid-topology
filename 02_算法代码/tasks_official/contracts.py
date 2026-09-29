"""Stable contracts shared by the official task implementations."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


TableRow = Mapping[str, Any]
TableData = Sequence[TableRow]


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    record_id: str
    field: str
    observed: Any
    expected: Any | None = None


@dataclass(frozen=True)
class ProblemRecord:
    task_code: str
    device_id: str
    device_name: str = ""
    feeder_id: str = ""
    station_id: str = ""
    description: str = ""
    correction: str = ""
    correction_sql: str = ""
    confidence: float | None = None
    severity: str = "warning"
    evidence: tuple[EvidenceItem, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskContext:
    tables: Mapping[str, TableData]
    options: Mapping[str, Any] = field(default_factory=dict)


class OfficialDetector(Protocol):
    def __call__(self, context: TaskContext) -> Sequence[ProblemRecord]: ...
