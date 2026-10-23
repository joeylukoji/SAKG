"""Moteur de requêtes : recherche, dépendances, dépendants et chemins."""

from collections import deque
from collections.abc import Sequence

from sakg.domain import Edge, Node, NodeNotFoundError, NodeType, RelationType
from sakg.graph.knowledge_graph import KnowledgeGraph
from sakg.graph.traversal import BoundedBfsStrategy, Direction, TraversalResult, TraversalStrategy

DEPENDENCY_RELATIONS = frozenset(
    {
        RelationType.DEPENDS_ON,
        RelationType.CALLS,
        RelationType.INHERITS,
        RelationType.IMPLEMENTS,
        RelationType.USES_TECHNOLOGY,
        RelationType.READS_FROM,
        RelationType.WRITES_TO,
        RelationType.MAPS_TO,
        # Une route a besoin de la fonction qui la traite : la toucher, c'est toucher l'API.
        RelationType.IMPLEMENTED_BY,
    }
)
"""Relations qui expriment « A a besoin de B » ; ``contains`` en est exclue (c'est une hiérarchie)."""


class GraphQueryEngine:
    """Questions posées au graphe, sans le modifier.

    Example:
        >>> engine = GraphQueryEngine(graph)  # doctest: +SKIP
        >>> engine.dependents("class:src/payment/service.py::PaymentService")  # doctest: +SKIP
    """

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    def nodes(self) -> list[Node]:
        """Tous les nœuds du graphe interrogé."""
        return self._graph.nodes()

    def get_node(self, node_id: str) -> Node | None:
        """Nœud d'identifiant donné, ou ``None``."""
        return self._graph.get_node(node_id)

    def inventory(self, types: Sequence[NodeType], limit: int | None = None) -> list[Node]:
        """Tous les nœuds des types demandés, dans l'ordre d'insertion.

        Répond aux questions d'inventaire — « quelles routes ce projet expose-t-il ? » — qui
        n'ont pas de texte à chercher.

        Raises:
            ValueError: Si ``limit`` est négatif.
        """
        _check_limit(limit)
        wanted = set(types)
        found = [node for node in self._graph.nodes() if node.type in wanted]
        return found[:limit] if limit is not None else found

    def find(self, text: str, types: Sequence[NodeType] | None = None, limit: int | None = None) -> list[Node]:
        """Nœuds dont le nom ou l'identifiant contient ``text`` (insensible à la casse).

        Les correspondances exactes de nom viennent en premier, puis les préfixes, puis le
        reste ; à égalité, l'ordre d'insertion est conservé. Une recherche vide ne retourne
        rien, plutôt que le graphe entier.

        Raises:
            ValueError: Si ``limit`` est négatif.
        """
        _check_limit(limit)
        needle = text.strip().lower()
        if not needle:
            return []
        allowed = set(types) if types else None
        matches: list[tuple[int, Node]] = []
        for node in self._graph.nodes():
            if allowed is not None and node.type not in allowed:
                continue
            name = node.name.lower()
            if name == needle:
                rank = 0
            elif name.startswith(needle):
                rank = 1
            elif needle in name or needle in node.id.lower():
                rank = 2
            else:
                continue
            matches.append((rank, node))
        ordered = [node for _, node in sorted(matches, key=lambda item: item[0])]
        return ordered[:limit] if limit is not None else ordered

    def dependencies(self, node_id: str, depth: int = 1) -> list[Node]:
        """Ce dont le nœud dépend, directement ou non."""
        return self._related(node_id, depth, Direction.OUT)

    def dependents(self, node_id: str, depth: int = 1) -> list[Node]:
        """Ce qui dépend du nœud, directement ou non."""
        return self._related(node_id, depth, Direction.IN)

    def path(self, source_id: str, target_id: str) -> list[Edge]:
        """Chemin le plus court en nombre de relations, en suivant le sens des relations.

        Retourne une liste vide s'il n'existe aucun chemin, et également lorsque la source
        est la cible : dans les deux cas, il n'y a aucune relation à parcourir.

        Raises:
            NodeNotFoundError: Si une extrémité est absente.
        """
        for node_id in (source_id, target_id):
            if self._graph.get_node(node_id) is None:
                raise NodeNotFoundError(f"nœud introuvable : {node_id!r}")
        if source_id == target_id:
            return []
        previous: dict[str, Edge] = {}
        seen = {source_id}
        queue: deque[str] = deque([source_id])
        while queue:
            current = queue.popleft()
            for edge in self._graph.out_edges(current):
                if edge.target_id in seen:
                    continue
                seen.add(edge.target_id)
                previous[edge.target_id] = edge
                if edge.target_id == target_id:
                    return self._rebuild_path(previous, source_id, target_id)
                queue.append(edge.target_id)
        return []

    def traverse(self, start: Sequence[str], strategy: TraversalStrategy) -> TraversalResult:
        """Parcourt le graphe avec la stratégie fournie."""
        return strategy.traverse(self._graph, start)

    def _related(self, node_id: str, depth: int, direction: Direction) -> list[Node]:
        strategy = BoundedBfsStrategy(max_depth=depth, relations=DEPENDENCY_RELATIONS, direction=direction)
        result = strategy.traverse(self._graph, [node_id])
        return [node for node in (self._graph.get_node(found) for found in result.visited if found != node_id) if node]

    @staticmethod
    def _rebuild_path(previous: dict[str, Edge], source_id: str, target_id: str) -> list[Edge]:
        path: list[Edge] = []
        current = target_id
        while current != source_id:
            edge = previous[current]
            path.append(edge)
            current = edge.source_id
        return list(reversed(path))


def _check_limit(limit: int | None) -> None:
    """Refuse une limite négative, qui tronquerait la liste par la fin sans le dire.

    Raises:
        ValueError: Si ``limit`` est négatif.
    """
    if limit is not None and limit < 0:
        raise ValueError(f"limit doit être positif ou nul : {limit}")
