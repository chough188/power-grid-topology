"""Small, unit-neutral KCL/KVL residual helpers."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConstraintResult:
    residual: float
    tolerance: float

    @property
    def passed(self) -> bool:
        return abs(self.residual) <= self.tolerance


def check_kcl(
    incoming_currents: Iterable[float],
    outgoing_currents: Iterable[float],
    tolerance: float,
) -> ConstraintResult:
    if tolerance < 0:
        raise ValueError("KCL tolerance must be non-negative")
    residual = sum(incoming_currents) - sum(outgoing_currents)
    return ConstraintResult(float(residual), float(tolerance))


def check_kvl(voltage_drops: Iterable[float], tolerance: float) -> ConstraintResult:
    if tolerance < 0:
        raise ValueError("KVL tolerance must be non-negative")
    return ConstraintResult(float(sum(voltage_drops)), float(tolerance))


def compute_node_kcl_residual(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    node_id: str,
    *,
    tolerance: float = 0.5,
) -> ConstraintResult:
    """Compute KCL residual at a connectivity node from PWREAL current data.

    Sums |IA+IB+IC| for all devices touching ``node_id`` via their terminals.
    In a balanced radial feed, the sum should be ~0 (current in = current out).
    A non-zero residual indicates a topology anomaly (e.g. unmeasured branch,
    false link, or loop).

    Returns a :class:`ConstraintResult` with the residual and tolerance.
    """
    # Find all EQUIP_IDs touching this node
    node_equips: set[str] = set()
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(tbl, ()):
            if str(row.get("CONNECTIVITYNODE_ID") or "") == str(node_id):
                eid = row.get("EQUIP_ID")
                if eid:
                    node_equips.add(str(eid))

    if not node_equips:
        return ConstraintResult(0.0, tolerance)

    # Sum currents from PWREAL for those devices
    total_current = 0.0
    found_any = False
    for row in tables.get("JBS_PWREAL", ()):
        tran = str(row.get("TRAN_ID") or "")
        if tran in node_equips:
            found_any = True
            for ck in ("IA", "IB", "IC"):
                v = row.get(ck)
                try:
                    total_current += float(v) if v not in (None, "") else 0.0
                except (TypeError, ValueError):
                    pass

    if not found_any:
        return ConstraintResult(0.0, tolerance)

    # KCL: sum of all currents at a node should be ~0 (in = out)
    # residual = |total| (deviation from balance)
    return ConstraintResult(abs(total_current), tolerance)


def compute_device_kcl_residual(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    equip_id: str,
    *,
    tolerance: float = 0.5,
) -> ConstraintResult:
    """Compute KCL residual for a specific device from its PWREAL current data.

    For a switch, the residual is |IA+IB+IC| — non-zero indicates current
    flowing through an open switch or imbalance.
    """
    total_current = 0.0
    found = False
    for row in tables.get("JBS_PWREAL", ()):
        if str(row.get("TRAN_ID") or "") == str(equip_id):
            found = True
            for ck in ("IA", "IB", "IC"):
                v = row.get(ck)
                try:
                    total_current += float(v) if v not in (None, "") else 0.0
                except (TypeError, ValueError):
                    pass

    if not found:
        return ConstraintResult(0.0, tolerance)
    return ConstraintResult(abs(total_current), tolerance)

