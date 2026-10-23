"""Schéma d'ontologie : triplets ``(source, relation, cible)`` autorisés (ARCHITECTURE.md §3.3)."""

from collections.abc import Iterable
from typing import Protocol

from sakg.domain.edge import Edge
from sakg.domain.errors import NodeNotFoundError, OntologyViolationError
from sakg.domain.node import Node
from sakg.domain.node_type import NodeType
from sakg.domain.relation_type import RelationType

Triple = tuple[NodeType, RelationType, NodeType]


class NodeResolver(Protocol):
    """Tout objet capable de retrouver un nœud par identifiant (ex. ``KnowledgeGraph``)."""

    def get_node(self, node_id: str) -> Node | None: ...


_N = NodeType
_R = RelationType

DEFAULT_TRIPLES: frozenset[Triple] = frozenset(
    {
        (_N.REQUIREMENT, _R.REALIZED_BY, _N.USE_CASE),
        (_N.REQUIREMENT, _R.CONSTRAINED_BY, _N.CONSTRAINT),
        (_N.USE_CASE, _R.USED_BY, _N.ACTOR),
        (_N.USE_CASE, _R.IMPLEMENTED_BY, _N.COMPONENT),
        (_N.ENDPOINT, _R.IMPLEMENTED_BY, _N.METHOD),
        (_N.ENDPOINT, _R.IMPLEMENTED_BY, _N.FUNCTION),
        (_N.FILE, _R.EXPOSES, _N.ENDPOINT),
        (_N.COMPONENT, _R.CONTAINS, _N.CLASS),
        (_N.FILE, _R.CONTAINS, _N.CLASS),
        (_N.FILE, _R.CONTAINS, _N.FUNCTION),
        (_N.CLASS, _R.CONTAINS, _N.METHOD),
        (_N.COMPONENT, _R.DEPENDS_ON, _N.COMPONENT),
        (_N.CLASS, _R.DEPENDS_ON, _N.CLASS),
        (_N.FILE, _R.DEPENDS_ON, _N.FILE),
        (_N.FILE, _R.DEPENDS_ON, _N.CLASS),
        (_N.FILE, _R.DEPENDS_ON, _N.FUNCTION),
        (_N.REQUIREMENT, _R.DEPENDS_ON, _N.REQUIREMENT),
        (_N.CLASS, _R.INHERITS, _N.CLASS),
        (_N.CLASS, _R.IMPLEMENTS, _N.INTERFACE),
        (_N.METHOD, _R.CALLS, _N.METHOD),
        (_N.METHOD, _R.CALLS, _N.FUNCTION),
        (_N.FUNCTION, _R.CALLS, _N.FUNCTION),
        (_N.FUNCTION, _R.CALLS, _N.METHOD),
        (_N.COMPONENT, _R.EXPOSES, _N.ENDPOINT),
        (_N.CLASS, _R.MAPS_TO, _N.TABLE),
        (_N.CLASS, _R.READS_FROM, _N.TABLE),
        (_N.CLASS, _R.WRITES_TO, _N.TABLE),
        (_N.TABLE, _R.CONTAINS, _N.COLUMN),
        (_N.COLUMN, _R.REFERENCES, _N.COLUMN),
        (_N.FILE, _R.CONTAINS, _N.CONTAINER),
        (_N.CONTAINER, _R.DEPENDS_ON, _N.CONTAINER),
        (_N.CONTAINER, _R.USES_TECHNOLOGY, _N.TECHNOLOGY),
        (_N.TEST, _R.VERIFIES, _N.REQUIREMENT),
        (_N.TEST, _R.TESTS, _N.CLASS),
        (_N.TEST, _R.TESTS, _N.ENDPOINT),
        (_N.COMPONENT, _R.DEPLOYED_IN, _N.CONTAINER),
        (_N.TECHNOLOGY, _R.DECIDED_BY, _N.ADR),
        (_N.COMPONENT, _R.USES_TECHNOLOGY, _N.TECHNOLOGY),
        (_N.COMPONENT, _R.BELONGS_TO, _N.LAYER),
        (_N.MODULE, _R.BELONGS_TO, _N.LAYER),
        (_N.PACKAGE, _R.BELONGS_TO, _N.LAYER),
    }
)


class OntologySchema:
    """Liste blanche des relations autorisées ; toute relation hors schéma est rejetée."""

    def __init__(self, triples: Iterable[Triple]) -> None:
        self._allowed: frozenset[Triple] = frozenset(triples)

    @classmethod
    def default(cls) -> "OntologySchema":
        """Schéma défini dans ARCHITECTURE.md §3.3."""
        return cls(DEFAULT_TRIPLES)

    @property
    def triples(self) -> frozenset[Triple]:
        """Triplets autorisés."""
        return self._allowed

    def is_allowed(self, source: NodeType, relation: RelationType, target: NodeType) -> bool:
        """Indique si le triplet est autorisé."""
        return (source, relation, target) in self._allowed

    def validate_edge(self, edge: Edge, nodes: NodeResolver) -> None:
        """Vérifie que les extrémités existent et que le triplet est autorisé.

        Raises:
            NodeNotFoundError: Si la source ou la cible est absente.
            OntologyViolationError: Si le triplet n'est pas dans le schéma.
        """
        source = _require_node(nodes, edge.source_id, edge)
        target = _require_node(nodes, edge.target_id, edge)
        if not self.is_allowed(source.type, edge.relation, target.type):
            raise OntologyViolationError(
                f"relation non autorisée : {source.type.value} -[{edge.relation.value}]-> {target.type.value}"
            )


def _require_node(nodes: NodeResolver, node_id: str, edge: Edge) -> Node:
    node = nodes.get_node(node_id)
    if node is None:
        raise NodeNotFoundError(f"nœud introuvable pour la relation {edge.id!r} : {node_id!r}")
    return node
