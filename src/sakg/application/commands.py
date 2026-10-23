"""Commandes de mutation du graphe (pattern Command).

Toute modification du graphe passe par une commande : le ``CommandBus`` peut ainsi
journaliser, annuler et versionner (règle 4 d'AGENTS.md).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress
from typing import Any, TypeVar

from sakg.domain import Edge, EvidenceType, Node, OntologyViolationError
from sakg.graph import KnowledgeGraph, edge_fingerprint, node_fingerprint

OBSERVED_LAYER = frozenset({EvidenceType.OBSERVED, EvidenceType.INFERRED})


class GraphCommand(ABC):
    """Mutation réversible du graphe."""

    @property
    def label(self) -> str:
        """Nom lisible de la commande, repris comme étiquette du snapshot."""
        return type(self).__name__

    @abstractmethod
    def execute(self, graph: KnowledgeGraph) -> None:
        """Applique la mutation."""

    @abstractmethod
    def undo(self, graph: KnowledgeGraph) -> None:
        """Rétablit l'état précédant :meth:`execute`."""


class AddNodeCommand(GraphCommand):
    """Ajoute un nœud ; l'annulation le retire, ainsi que ses relations éventuelles."""

    def __init__(self, node: Node) -> None:
        self.node = node

    def execute(self, graph: KnowledgeGraph) -> None:
        graph.add_node(self.node)

    def undo(self, graph: KnowledgeGraph) -> None:
        graph.remove_node(self.node.id)


class AddEdgeCommand(GraphCommand):
    """Ajoute une relation ; l'annulation la retire."""

    def __init__(self, edge: Edge) -> None:
        self.edge = edge

    def execute(self, graph: KnowledgeGraph) -> None:
        graph.add_edge(self.edge)

    def undo(self, graph: KnowledgeGraph) -> None:
        graph.remove_edge(self.edge.id)


_Element = TypeVar("_Element", Node, Edge)


def _with_first_seen_provenance(
    extracted: _Element,
    previous: _Element | None,
    fingerprint: Callable[[_Element], dict[str, Any]],
) -> _Element:
    """Conserve la provenance précédente quand le contenu n'a pas changé.

    Deux effets : la date et le commit indiquent *depuis quand* le fait est observé, et non
    la dernière exécution ; et les fichiers de ``.architect/`` restent identiques d'un reverse
    à l'autre à code inchangé, ce qui rend leur ``git diff`` lisible (ADR-001, ADR-005).
    """
    if previous is None or fingerprint(previous) != fingerprint(extracted):
        return extracted
    return extracted.model_copy(update={"provenance": previous.provenance})


class ReplaceObservedLayerCommand(GraphCommand):
    """Remplace la couche OBSERVED/INFERRED par le résultat d'un reverse engineering.

    Les nœuds et relations USER_DEFINED, GENERATED et RECOMMENDED sont conservés
    (ARCHITECTURE.md §5.1) ; les relations dont une extrémité disparaît sont retirées et
    restaurées à l'annulation.
    """

    def __init__(self, extracted: KnowledgeGraph) -> None:
        self.extracted = extracted
        self._removed_nodes: list[Node] = []
        self._removed_edges: list[Edge] = []
        self._added_nodes: list[Node] = []
        self._added_edges: list[Edge] = []
        self._relinked_edges: list[Edge] = []

    def execute(self, graph: KnowledgeGraph) -> None:
        obsolete = [node.id for node in graph.nodes() if node.provenance.evidence_type in OBSERVED_LAYER]
        obsolete_set = set(obsolete)
        self._removed_nodes = [node for node in graph.nodes() if node.id in obsolete_set]
        self._removed_edges = [
            edge
            for edge in graph.edges()
            if edge.provenance.evidence_type in OBSERVED_LAYER
            or edge.source_id in obsolete_set
            or edge.target_id in obsolete_set
        ]
        self._added_nodes = []
        self._added_edges = []
        try:
            for edge in self._removed_edges:
                graph.remove_edge(edge.id)
            for node_id in obsolete:
                graph.remove_node(node_id)
            previous_nodes = {node.id: node for node in self._removed_nodes}
            previous_edges = {edge.id: edge for edge in self._removed_edges}
            for node in self.extracted.nodes():
                if node.id not in graph:
                    kept_node = _with_first_seen_provenance(node, previous_nodes.get(node.id), node_fingerprint)
                    self._added_nodes.append(graph.add_node(kept_node))
            for edge in self.extracted.edges():
                if graph.get_edge(edge.id) is None:
                    kept_edge = _with_first_seen_provenance(edge, previous_edges.get(edge.id), edge_fingerprint)
                    self._added_edges.append(graph.add_edge(kept_edge))
            self._relink_curated_edges(graph)
        except Exception:
            self.undo(graph)
            raise

    def _relink_curated_edges(self, graph: KnowledgeGraph) -> None:
        """Rétablit les relations non observées dont les deux extrémités existent de nouveau.

        Un reverse re-crée la plupart des nœuds à l'identique : une relation saisie par
        l'utilisateur (``Test tests Class``, ``UseCase implemented_by Component``) doit
        survivre à l'opération (ARCHITECTURE.md §5.1). Celle dont le type d'extrémité a
        changé entre-temps n'est pas rétablie et reste supprimée.
        """
        for edge in self._removed_edges:
            if edge.provenance.evidence_type in OBSERVED_LAYER or graph.get_edge(edge.id) is not None:
                continue
            if edge.source_id in graph and edge.target_id in graph:
                with suppress(OntologyViolationError):
                    self._relinked_edges.append(graph.add_edge(edge))

    def undo(self, graph: KnowledgeGraph) -> None:
        for edge in reversed(self._relinked_edges):
            if graph.get_edge(edge.id) is not None:
                graph.remove_edge(edge.id)
        for edge in reversed(self._added_edges):
            if graph.get_edge(edge.id) is not None:
                graph.remove_edge(edge.id)
        for node in reversed(self._added_nodes):
            if node.id in graph:
                graph.remove_node(node.id)
        for node in self._removed_nodes:
            if node.id not in graph:
                graph.add_node(node)
        for edge in self._removed_edges:
            if graph.get_edge(edge.id) is None:
                graph.add_edge(edge)
        self._added_nodes = []
        self._added_edges = []
        self._relinked_edges = []
