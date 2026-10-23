"""Knowledge Graph : agrégat, requêtes, traversées et snapshots."""

from sakg.graph.knowledge_graph import KnowledgeGraph
from sakg.graph.query import DEPENDENCY_RELATIONS, GraphQueryEngine
from sakg.graph.repository import GraphRepository
from sakg.graph.snapshot import (
    GraphSnapshot,
    SnapshotMeta,
    compute_graph_hash,
    edge_fingerprint,
    node_fingerprint,
)
from sakg.graph.traversal import (
    BoundedBfsStrategy,
    Direction,
    TraversalResult,
    TraversalStrategy,
)

__all__ = [
    "DEPENDENCY_RELATIONS",
    "BoundedBfsStrategy",
    "Direction",
    "GraphQueryEngine",
    "GraphRepository",
    "GraphSnapshot",
    "KnowledgeGraph",
    "SnapshotMeta",
    "TraversalResult",
    "TraversalStrategy",
    "compute_graph_hash",
    "edge_fingerprint",
    "node_fingerprint",
]
