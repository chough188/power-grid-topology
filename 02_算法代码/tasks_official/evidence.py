# -*- coding: utf-8 -*-
"""Evidence collection helpers for the official 12 detectors.

Each `detect(ctx)` should attach EvidenceItem tuples to every
ProblemRecord it yields. Evidence is what makes a record reviewable:
the reviewer can re-derive the conclusion from the cited rows.

Patterns:
    ev = EvidenceCollector("JBS_PWEQUIPINFO")
    ev.observe("EQUIP_ID", "PW_BREAKER_001", "EQUIP_ID", "PW_BREAKER_001")
    yield ProblemRecord(..., evidence=ev.finalize())
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from tasks_official.contracts import EvidenceItem


class EvidenceCollector:
    """Lightweight builder for EvidenceItem tuples.

    Source defaults to the originating table name (e.g. "JBS_PWEQUIPINFO").
    Each `observe(...)` call appends one EvidenceItem.
    """

    __slots__ = ("_items", "_default_source")

    def __init__(self, default_source: str) -> None:
        self._items: list[EvidenceItem] = []
        self._default_source = default_source

    def observe(
        self,
        field: str,
        observed: Any,
        record_id: str = "",
        expected: Any = None,
        source: str | None = None,
    ) -> "EvidenceCollector":
        self._items.append(
            EvidenceItem(
                source=source or self._default_source,
                record_id=str(record_id),
                field=str(field),
                observed=observed,
                expected=expected,
            )
        )
        return self

    def extend(self, items: Iterable[EvidenceItem]) -> "EvidenceCollector":
        self._items.extend(items)
        return self

    def finalize(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._items)


def evidence_from_row(
    source: str,
    record_id: str,
    row: Mapping[str, Any],
    fields: Iterable[str],
) -> tuple[EvidenceItem, ...]:
    """One-shot helper: build an EvidenceItem for each named field of a row."""
    return tuple(
        EvidenceItem(source=source, record_id=str(record_id), field=f, observed=row.get(f))
        for f in fields
    )


__all__ = ["EvidenceCollector", "evidence_from_row"]