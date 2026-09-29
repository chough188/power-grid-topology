"""Switch-state resolution: prefers signal POINT, falls back to RUN_STATUS.

R12 mitigation: JBS_PWREAL.TRAN_ID can map to an EQUIP_ID, providing a
signal-level POINT for distribution-net devices. JBS_ZWSIGNAL has only
(ID, POINT) with no direct EQUIP_ID foreign key, so for main-net devices
we fall back to JBS_ZWEQUIPINFO.RUN_STATUS.

All detectors that need "is this switch closed?" should use
:func:`is_switch_closed` instead of raw ``dev.get("RUN_STATUS")``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_signal_point_map(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, bool]:
    """Map EQUIP_ID -> is_closed (True=合位, False=分位) from signal tables.

    Priority:
      1. JBS_PWREAL: use TRAN_ID as equip key.  If multiple signals
         exist for the same TRAN_ID, the row with the latest DATA_DATE
         wins (state snapshot should reflect the most recent telemetry,
         not iteration order).
      2. JBS_ZWSIGNAL: use EQUIP_ID if present, otherwise ID.  If multiple
         signals exist for the same key, the latest DATA_DATE wins.
         Since ZWSIGNAL has no reliable EQUIP_ID foreign key, this is
         best-effort; ID matching a device's EQUIP_ID is data-model-dependent.
    """

    def _group_by_key(rows, key_field) -> dict[str, list]:
        by_key: dict[str, list] = {}
        for row in rows:
            eid = row.get(key_field)
            point = row.get("POINT")
            if eid is not None and point is not None:
                dt = row.get("DATA_DATE") or row.get("DATE_TIME") or ""
                by_key.setdefault(str(eid), []).append((str(dt), point))
        return by_key

    def _latest_point(records: list) -> Any:
        # 按时间降序，取最新一条的 POINT（无时间字段时退化为原始顺序的末尾）
        records.sort(key=lambda x: x[0], reverse=True)
        return records[0][1]

    signal_map: dict[str, bool] = {}

    # 1. JBS_PWREAL — reliable: TRAN_ID matches a device's EQUIP_ID
    for eid, records in _group_by_key(tables.get("JBS_PWREAL", ()), "TRAN_ID").items():
        signal_map[eid] = _point_is_closed(_latest_point(records))

    # 2. JBS_ZWSIGNAL — best-effort: per-row key = EQUIP_ID if present else ID
    by_zws: dict[str, list] = {}
    for row in tables.get("JBS_ZWSIGNAL", ()):
        eid = row.get("EQUIP_ID")
        if eid is None:
            eid = row.get("ID")
        point = row.get("POINT")
        if eid is not None and point is not None:
            dt = row.get("DATA_DATE") or row.get("DATE_TIME") or ""
            by_zws.setdefault(str(eid), []).append((str(dt), point))
    for eid, records in by_zws.items():
        signal_map.setdefault(eid, _point_is_closed(_latest_point(records)))

    return signal_map


def _point_is_closed(point: Any) -> bool:
    """Signal POINT: 合位=1/closed, 分位=0/open.

    Accepts int/str/float variants: 1,"1","Y"→closed; 0,"0","N"→open.
    Returns True (closed) for unknown/non-standard values (conservative)."""
    if point in (1, "1", "Y", "y", "True", "true", 1.0):
        return True
    if point in (0, "0", "N", "n", "False", "false", 0.0):
        return False
    return True  # default: assume closed


def _run_status_closed(dev: Mapping[str, Any]) -> bool | None:
    """Parse device RUN_STATUS.  Returns True=closed, False=open, None=unknown."""
    rs = dev.get("RUN_STATUS")
    if rs in (1, "1", "Y", "y", "True", "true", 1.0):
        return True
    if rs in (0, "0", "N", "n", "False", "false", 0.0):
        return False
    return None


def is_switch_closed(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    dev: Mapping[str, Any],
    signal_map: dict[str, bool] | None = None,
) -> bool | None:
    """Get effective switch closed state: prefer signal POINT, fall back RUN_STATUS.

    Returns:
      - True  = device is closed (合位)
      - False = device is open  (分位)
      - None  = no signal and no RUN_STATUS available

    When ``signal_map`` is provided, it is used for look-up instead of
    re-building from ``tables`` (avoids repeated table-scanning per device).
    """
    eid = dev.get("EQUIP_ID")
    if eid is not None:
        # Prefer signal POINT
        if signal_map is not None:
            if eid in signal_map:
                return signal_map[str(eid)]
        else:
            # Build on-the-fly lookup
            sm = build_signal_point_map(tables)
            if eid in sm:
                return sm[str(eid)]

    # Fall back to RUN_STATUS
    return _run_status_closed(dev)


def build_running_adjacency(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    base_adj: dict[str, set[str]] | None = None,
    signal_map: dict[str, bool] | None = None,
) -> dict[str, set[str]]:
    """Build G_R = model topology minus OPEN-switch edges.

    Per spec §1.2/§1.3/§1.5: the running graph filters out edges contributed
    by split (分位/POINT=0) switches so that trace_to_source cannot traverse
    an open switch.  Devices that are not switches, or switches that are
    closed, keep their terminal-to-terminal edges.

    Implementation: delegate to ``adjacency_from_terminals`` for the model
    graph (guaranteeing identical edge structure), then remove edges
    contributed by OPEN switches.
    """
    from .graph_algos import adjacency_from_terminals

    if signal_map is None:
        signal_map = build_signal_point_map(tables)

    # Identify OPEN switch equipment ids
    open_switch_equips: set[str] = set()
    for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
        et = (d.get("EQUIP_TYPE") or "").upper()
        if et not in ("BREAKER", "SWITCH", "DISCONNECTOR"):
            continue
        if is_switch_closed(tables, d, signal_map) is False:
            eid = d.get("EQUIP_ID")
            if eid:
                open_switch_equips.add(str(eid))

    if not open_switch_equips:
        # No open switches → running graph == model graph
        if base_adj is not None:
            return {k: set(v) for k, v in base_adj.items()}
        return adjacency_from_terminals(tables)

    # Build model graph, then remove edges contributed by open switches.
    # An open switch with terminals [A, B, ...] contributed edges A-B, B-C, ...
    # We must remove exactly those edges (and only those).
    if base_adj is not None:
        adj = {k: set(v) for k, v in base_adj.items()}
    else:
        adj = adjacency_from_terminals(tables)

    # Collect each open switch's terminal nodes
    open_equip_nodes: dict[str, list[str]] = {}
    for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
        for row in tables.get(tbl, ()):
            eid = row.get("EQUIP_ID")
            nid = row.get("CONNECTIVITYNODE_ID")
            if eid and nid and str(eid) in open_switch_equips:
                open_equip_nodes.setdefault(str(eid), []).append(str(nid))

    # Remove edges contributed by each open switch (same consecutive-pair logic)
    for eid, nodes in open_equip_nodes.items():
        nl = list(dict.fromkeys(nodes))
        if len(nl) < 2:
            continue
        for a, b in zip(nl, nl[1:]):
            adj.get(a, set()).discard(b)
            adj.get(b, set()).discard(a)

    return adj


def trace_to_source(
    adj: Mapping[str, "set[str]"],
    start_node: str,
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    exclude_equip: str | None = None,
    node_to_equips: dict[str, set[str]] | None = None,
    equip_meta: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    """BFS from a connectivity node to the nearest SOURCE/TRANSFORMER/MAIN.

    Returns ``{"equip_id", "station", "feeder", "voltage"}`` for the first
    source-class device reachable from ``start_node`` in ``adj``, or ``None``
    if no source is reachable.  ``exclude_equip`` lets callers (e.g. 1.3)
    exclude the tie-switch itself from the trace.

    Bug#22: ``node_to_equips`` and ``equip_meta`` can be pre-built by callers
    and passed in to avoid rebuilding on every call (was O(N_terminals +
    N_equips) per call, called 2x per candidate switch in 1.3/1.4).
    """
    from collections import deque

    if node_to_equips is None:
        node_to_equips = {}
        for tbl in ("JBS_PWTERMINAL", "JBS_ZWTERMINAL"):
            for row in tables.get(tbl, ()):
                nid = row.get("CONNECTIVITYNODE_ID")
                eid = row.get("EQUIP_ID")
                if nid and eid:
                    node_to_equips.setdefault(str(nid), set()).add(str(eid))

    if equip_meta is None:
        equip_meta = {}
        for d in list(tables.get("JBS_PWEQUIPINFO", ())) + list(tables.get("JBS_ZWEQUIPINFO", ())):
            eid = d.get("EQUIP_ID")
            if eid:
                equip_meta[str(eid)] = d

    source_types = {"SOURCE", "TRANSFORMER", "MAIN"}
    seen: set[str] = set()
    queue: deque[str] = deque([str(start_node)])
    seen.add(str(start_node))
    while queue:
        node = queue.popleft()
        for eid in sorted(node_to_equips.get(node, ())):
            if exclude_equip and eid == exclude_equip:
                continue
            dev = equip_meta.get(eid)
            if not dev:
                continue
            if (dev.get("EQUIP_TYPE") or "").upper() in source_types:
                return {
                    "equip_id": eid,
                    "station": str(dev.get("ST_ID") or dev.get("DSUBSTATION_ID") or ""),
                    "feeder": str(dev.get("FEEDER_ID") or ""),
                    "voltage": dev.get("VOLTAGE_TYPE"),
                }
        for nb in sorted(adj.get(node, ())):
            if nb not in seen:
                seen.add(nb)
                queue.append(nb)
    return None


def resolve_side_feeders(
    running_adj: Mapping[str, "set[str]"],
    port_node: str,
    *,
    exclude_equip: str | None = None,
    node_to_equips: dict[str, set[str]] | None = None,
    equip_feeder: Mapping[str, str] | None = None,
    depth: int = 3,
) -> set[str]:
    """Bounded BFS from one port of an open switch over the RUNNING graph.

    Returns the set of ``FEEDER_ID``s carried by equipment attached to nodes
    reached within ``depth`` hops (the switch itself is excluded).  Because
    ``running_adj`` has the open switch's own terminal edges removed, the two
    sides of the switch cannot leak into each other through it.

    Used by task 1.3 (secondary tie path when port-level source tracing fails
    on fragmented real-data graphs) and by the 5.3.3 substation diagram to
    decide which feeder(s) each side of a confirmed-open switch belongs to.
    Tie semantics: the sides' feeder sets contain different feeders.
    """
    from collections import deque as _deque

    if node_to_equips is None:
        node_to_equips = {}
    if equip_feeder is None:
        equip_feeder = {}

    start = str(port_node)
    found: set[str] = set()
    seen: set[str] = {start}
    queue: _deque = _deque([(start, 0)])
    while queue:
        node, d = queue.popleft()
        if d > depth:
            continue
        for eid in sorted(node_to_equips.get(node, ())):
            if exclude_equip and eid == exclude_equip:
                continue
            fid = equip_feeder.get(eid)
            if fid:
                found.add(str(fid))
        if d >= depth:
            continue
        for nb in sorted(running_adj.get(node, ())):
            if nb not in seen:
                seen.add(nb)
                queue.append((nb, d + 1))
    return found
