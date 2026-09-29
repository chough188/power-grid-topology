"""Four graph foundations required by the official delivery plan."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GraphKind(str, Enum):
    MODEL_TOPOLOGY = "model_topology"
    OPERATING_TOPOLOGY = "operating_topology"
    SVG = "svg"
    MAIN_DISTRIBUTION_INTERFACE = "main_distribution_interface"


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSnapshot:
    kind: GraphKind
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
