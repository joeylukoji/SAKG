"""Modèle du domaine : nœuds, relations, provenance et ontologie. Aucune dépendance hors stdlib et Pydantic."""

from sakg.domain.edge import Edge, make_edge_id
from sakg.domain.errors import (
    DuplicateEdgeError,
    DuplicateNodeError,
    EdgeNotFoundError,
    NodeNotFoundError,
    OntologyViolationError,
    SakgError,
    SnapshotNotFoundError,
)
from sakg.domain.node import Node, make_node_id
from sakg.domain.node_type import NodeType
from sakg.domain.ontology import NodeResolver, OntologySchema
from sakg.domain.provenance import Evidence, EvidenceType, Provenance
from sakg.domain.relation_type import RelationType

__all__ = [
    "DuplicateEdgeError",
    "DuplicateNodeError",
    "Edge",
    "EdgeNotFoundError",
    "Evidence",
    "EvidenceType",
    "Node",
    "NodeNotFoundError",
    "NodeResolver",
    "NodeType",
    "OntologySchema",
    "OntologyViolationError",
    "Provenance",
    "RelationType",
    "SakgError",
    "SnapshotNotFoundError",
    "make_edge_id",
    "make_node_id",
]
