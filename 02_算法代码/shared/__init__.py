"""Dependency-neutral helpers for the official submission track."""
from .exemption import (
    EXEMPT_ROOM_TYPES,
    is_dangle_exempt,
    is_internal_tie_switch_exempt,
    is_loop_exempt,
    is_measurement_exempt,
    is_single_side_allowed,
    is_tie_switch_exempt,
    normalize_room_type,
)
from .switch_state import (
    build_running_adjacency,
    build_signal_point_map,
    is_switch_closed,
    trace_to_source,
)
from .graph_algos import (
    adjacency_from_terminals,
    articulation_points,
    bfs,
    connected_components,
    find_cycles,
    has_cycle,
    shortest_path,
)
from .graph_base import GraphEdge, GraphKind, GraphNode, GraphSnapshot
from .id_prefix import TEMP_DEVICE_PREFIX, ensure_temp_device_id, is_temp_device_id
from .kcl_kvl import ConstraintResult, check_kcl, check_kvl, compute_device_kcl_residual, compute_node_kcl_residual
from .sql_emitter import (
    delete_pw_terminal,
    delete_zw_terminal,
    insert_pw_equip,
    insert_pw_terminal,
    insert_zw_terminal,
    insert_zw_terminal_for_interface,
    mark_tie_pw,
    mark_tie_zw,
    multi_step,
    set_run_status_pw,
    set_run_status_zw,
    update_pw_terminal_node,
    update_zw_terminal_node,
)

__all__ = [
    # exemption
    "EXEMPT_ROOM_TYPES",
    "is_dangle_exempt",
    "is_internal_tie_switch_exempt",
    "is_loop_exempt",
    "is_measurement_exempt",
    "is_single_side_allowed",
    "is_tie_switch_exempt",
    "normalize_room_type",
    # switch state
    "build_signal_point_map",
    "build_running_adjacency",
    "is_switch_closed",
    "trace_to_source",
    # graph algos
    "adjacency_from_terminals",
    "articulation_points",
    "bfs",
    "connected_components",
    "find_cycles",
    "has_cycle",
    "shortest_path",
    # graph base
    "GraphEdge",
    "GraphKind",
    "GraphNode",
    "GraphSnapshot",
    # id prefix
    "TEMP_DEVICE_PREFIX",
    "ensure_temp_device_id",
    "is_temp_device_id",
    # physics
    "ConstraintResult",
    "check_kcl",
    "check_kvl",
    "compute_device_kcl_residual",
    "compute_node_kcl_residual",
    # sql emitter
    "delete_pw_terminal",
    "delete_zw_terminal",
    "insert_pw_equip",
    "insert_pw_terminal",
    "insert_zw_terminal",
    "insert_zw_terminal_for_interface",
    "mark_tie_pw",
    "mark_tie_zw",
    "multi_step",
    "set_run_status_pw",
    "set_run_status_zw",
    "update_pw_terminal_node",
    "update_zw_terminal_node",
]