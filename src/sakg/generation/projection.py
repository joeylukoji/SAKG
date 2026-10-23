"""Projections : une vue de diagramme est un filtre de types de nœuds et de relations."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sakg.domain import NodeType, RelationType
from sakg.graph import KnowledgeGraph


class DiagramView(StrEnum):
    """Vues de diagramme prévues (seule ``CLASS`` est générée au MVP)."""

    CLASS = "class"
    USE_CASE = "use_case"
    SEQUENCE = "sequence"
    COMPONENT = "component"
    DEPLOYMENT = "deployment"
    ERD = "erd"


@dataclass(frozen=True)
class ViewProjection:
    """Sous-ensemble du graphe correspondant à une vue.

    Attributes:
        view: Vue projetée.
        node_types: Types de nœuds conservés.
        relations: Relations conservées.
    """

    view: DiagramView
    node_types: frozenset[NodeType]
    relations: frozenset[RelationType]

    @classmethod
    def for_view(cls, view: DiagramView) -> "ViewProjection":
        """Projection standard d'une vue.

        Raises:
            UnsupportedViewError: Si la vue n'est pas encore définie.
        """
        projection = _PROJECTIONS.get(view)
        if projection is None:
            raise UnsupportedViewError(f"vue non disponible au MVP : {view.value}")
        return projection

    def project(self, graph: KnowledgeGraph, focus: Sequence[str] | None = None) -> KnowledgeGraph:
        """Graphe restreint aux types de la vue, et éventuellement au voisinage de ``focus``.

        Les relations hors de la vue sont écartées, même entre deux nœuds conservés.
        """
        kept = {node.id for node in graph.nodes() if node.type in self.node_types}
        if focus:
            kept &= self._neighbourhood(graph, focus)
        projected = graph.subgraph(kept)
        for edge in projected.edges():
            if edge.relation not in self.relations:
                projected.remove_edge(edge.id)
        return projected

    def _neighbourhood(self, graph: KnowledgeGraph, focus: Sequence[str]) -> set[str]:
        """Nœuds de ``focus``, leurs voisins directs par les relations de la vue, et leur contenu."""
        neighbourhood: set[str] = set()
        for node_id in focus:
            if graph.get_node(node_id) is None:
                continue
            neighbourhood.add(node_id)
            for edge in [*graph.out_edges(node_id), *graph.in_edges(node_id)]:
                if edge.relation in self.relations:
                    neighbourhood.update({edge.source_id, edge.target_id})
        contained = {
            edge.target_id
            for node_id in list(neighbourhood)
            for edge in graph.out_edges(node_id)
            if edge.relation == RelationType.CONTAINS
        }
        return neighbourhood | contained


class UnsupportedViewError(NotImplementedError):
    """La vue demandée n'a pas encore de projection."""


_PROJECTIONS = {
    DiagramView.CLASS: ViewProjection(
        view=DiagramView.CLASS,
        node_types=frozenset({NodeType.CLASS, NodeType.INTERFACE, NodeType.METHOD}),
        relations=frozenset(
            {
                RelationType.INHERITS,
                RelationType.IMPLEMENTS,
                RelationType.DEPENDS_ON,
                RelationType.CONTAINS,
                # Les appels sont extraits entre méthodes ; le rendu les remonte entre classes.
                RelationType.CALLS,
            }
        ),
    ),
    DiagramView.USE_CASE: ViewProjection(
        view=DiagramView.USE_CASE,
        node_types=frozenset({NodeType.ACTOR, NodeType.USE_CASE, NodeType.REQUIREMENT}),
        relations=frozenset({RelationType.USED_BY, RelationType.REALIZED_BY}),
    ),
}
