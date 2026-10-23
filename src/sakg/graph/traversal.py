"""Stratégies de traversée du graphe (pattern Strategy)."""

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from sakg.domain import Edge, NodeNotFoundError, RelationType
from sakg.graph.knowledge_graph import KnowledgeGraph


class Direction(StrEnum):
    """Sens de parcours d'une relation ``source → cible``."""

    OUT = "out"
    """Du nœud vers ce dont il dépend."""
    IN = "in"
    """Du nœud vers ce qui dépend de lui."""
    BOTH = "both"


@dataclass(frozen=True)
class TraversalResult:
    """Nœuds atteints par une traversée.

    Attributes:
        visited: Identifiant du nœud → profondeur à laquelle il a été atteint.
        scores: Identifiant du nœud → score d'atteinte, décroissant avec la profondeur.
        edges: Relations empruntées, dans l'ordre de parcours.
    """

    visited: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def at_depth(self, depth: int) -> list[str]:
        """Identifiants atteints à une profondeur donnée."""
        return [node_id for node_id, reached in self.visited.items() if reached == depth]


class TraversalStrategy(Protocol):
    """Algorithme de parcours interchangeable."""

    def traverse(self, graph: KnowledgeGraph, start: Sequence[str]) -> TraversalResult:
        """Parcourt le graphe depuis les nœuds de départ.

        Raises:
            NodeNotFoundError: Si un nœud de départ est absent.
        """
        ...


@dataclass(frozen=True)
class BoundedBfsStrategy:
    """Parcours en largeur borné en profondeur, filtrable par type de relation.

    Le score décroît avec la profondeur (``1 / (1 + profondeur)``) : un nœud de départ pèse
    1.0, un voisin direct 0.5, un nœud à deux sauts 0.33. C'est la stratégie du MVP ; une
    propagation pondérée par type de relation et confiance est prévue en S8.

    Attributes:
        max_depth: Profondeur maximale ; 0 ne retourne que les nœuds de départ.
        relations: Relations suivies ; toutes si vide.
        direction: Sens de parcours.
    """

    max_depth: int = 2
    relations: frozenset[RelationType] = frozenset()
    direction: Direction = Direction.OUT

    def traverse(self, graph: KnowledgeGraph, start: Sequence[str]) -> TraversalResult:
        """Parcourt le graphe en largeur depuis les nœuds de départ."""
        result = TraversalResult()
        queue: deque[tuple[str, int]] = deque()
        for node_id in start:
            if graph.get_node(node_id) is None:
                raise NodeNotFoundError(f"nœud de départ introuvable : {node_id!r}")
            if node_id not in result.visited:
                result.visited[node_id] = 0
                result.scores[node_id] = 1.0
                queue.append((node_id, 0))

        seen_edges: set[str] = set()
        while queue:
            node_id, depth = queue.popleft()
            if depth >= self.max_depth:
                continue
            for edge, neighbour in self._neighbours(graph, node_id):
                if edge.id not in seen_edges:  # en Direction.BOTH, une relation se présente deux fois
                    seen_edges.add(edge.id)
                    result.edges.append(edge)
                if neighbour in result.visited:
                    continue
                result.visited[neighbour] = depth + 1
                result.scores[neighbour] = 1 / (2 + depth)
                queue.append((neighbour, depth + 1))
        return result

    def _neighbours(self, graph: KnowledgeGraph, node_id: str) -> Iterable[tuple[Edge, str]]:
        if self.direction in {Direction.OUT, Direction.BOTH}:
            for edge in graph.out_edges(node_id):
                if self._follows(edge):
                    yield edge, edge.target_id
        if self.direction in {Direction.IN, Direction.BOTH}:
            for edge in graph.in_edges(node_id):
                if self._follows(edge):
                    yield edge, edge.source_id

    def _follows(self, edge: Edge) -> bool:
        return not self.relations or edge.relation in self.relations
