# -*- coding: utf-8 -*-
"""Task 2.2: 模型有、图上无校验 (official algorithm).

Per 比赛要求/00_12个二级分类算法伪代码.md §2.2:
  svg_set      = ctx.options["svg_devices"]
  model_set    = {d.EQUIP_ID for d in PWEQUIPINFO | ZWEQUIPINFO}
  orphan(M)    = model_set - svg_set

Per official §2.2 rules:
  - correction_sql: UPDATE LIFECYCLE per classification
  - COMPOSITESWITCH non-empty: skip (already merged into composite device)
  - LIFECYCLE=RETIRED: mark as retired_in_db (informational, not orphan)
  - DISCONNECTOR with single terminal: mark as disconnect_candidate

Algorithm:
  1. Compute model_set and svg_set.
  2. Filter out COMPOSITESWITCH (already-merged).
  3. Classify remaining: retired_in_db / disconnect_candidate / orphan.
  4. Emit one ProblemRecord per orphan with correction_sql per classification.
"""
from collections.abc import Sequence

from tasks_official.contracts import ProblemRecord, TaskContext
from tasks_official.evidence import EvidenceCollector

SEVERITY_DEFAULT = "medium"


def _classify(meta: dict, terminal_count: int) -> str:
    """Return one of: retired_in_db / disconnect_candidate / orphan."""
    lifecycle = (meta.get("LIFECYCLE") or "").upper()
    if lifecycle == "RETIRED":
        return "retired_in_db"
    equip_type = (meta.get("EQUIP_TYPE") or "").upper()
    if equip_type == "DISCONNECTOR" and terminal_count <= 1:
        return "disconnect_candidate"
    return "orphan"


def detect(ctx: TaskContext) -> Sequence[ProblemRecord]:
    tables = ctx.tables
    svg_set = set(ctx.options.get("svg_devices", ()) or ())

    terminal_count_by_equip: dict = {}
    for t in list(tables.get("JBS_PWTERMINAL", ())) + list(tables.get("JBS_ZWTERMINAL", ())):
        eid = t.get("EQUIP_ID")
        if eid:
            terminal_count_by_equip[eid] = terminal_count_by_equip.get(eid, 0) + 1

    emitted: list = []
    seen: set = set()
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        eid = d.get("EQUIP_ID")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        if eid in svg_set:
            continue  # already drawn
        # Rule: COMPOSITESWITCH non-empty means the device is already merged
        if (d.get("COMPOSITESWITCH") or "").strip():
            continue
        classification = _classify(d, terminal_count_by_equip.get(eid, 0))
        # Even retired_in_db still deserves an informational ProblemRecord
        ev = EvidenceCollector("JBS_PWEQUIPINFO" if d.get("FEEDER_ID") else "JBS_ZWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_TYPE", d.get("EQUIP_TYPE"))
        ev.observe("VOLTAGE_TYPE", d.get("VOLTAGE_TYPE"))
        ev.observe("LIFECYCLE", d.get("LIFECYCLE"))
        ev.observe("COMPOSITESWITCH", d.get("COMPOSITESWITCH"))
        ev.observe("IN_SVG", False)
        ev.observe("CLASSIFICATION", classification)

        _correction_sql = ""
        if classification == "retired_in_db":
            _correction_sql = (
                f"UPDATE JBS_PWEQUIPINFO SET LIFECYCLE='RETIRED', "
                f"RETIRE_REASON='svg_missing' WHERE EQUIP_ID='{eid}';"
            )
        elif classification == "disconnect_candidate":
            _correction_sql = (
                f"UPDATE JBS_PWTERMINAL SET VALID_FLAG=0 "
                f"WHERE EQUIP_ID='{eid}';"
            )

        emitted.append(ProblemRecord(
            task_code="2.2",
            device_id=eid,
            device_name=d.get("EQUIP_NAME", ""),
            feeder_id=d.get("FEEDER_ID", ""),
            station_id=d.get("DSUBSTATION_ID", "") or d.get("ST_ID", ""),
            description=(
                f"模型存在但 SVG 上缺失的设备 {d.get('EQUIP_NAME', eid)} "
                f"(分类={classification})"
            ),
            correction="需人工复核：补绘 SVG / 标注 RETIRED / 合并至 COMPOSITESWITCH",
            correction_sql=_correction_sql,
            severity=SEVERITY_DEFAULT,
            confidence=0.85,
            evidence=ev.finalize(),
            extra={
                "classification": classification,
                "retired_in_db": classification == "retired_in_db",
                "disconnect_candidate": classification == "disconnect_candidate",
                "terminal_count": terminal_count_by_equip.get(eid, 0),
                "in_svg": False,
            },
        ))
    for rec in emitted:
        yield rec
    return ()


__all__ = ["detect", "SEVERITY_DEFAULT"]
