"""Agrégat ``KnowledgeGraph`` : garantit l'unicité des identifiants et le respect de l'ontologie."""

from collections.abc import Iterable

import networkx as nx

from sakg.domain import (
    DuplicateEdgeError,
    DuplicateNodeError,
    Edge,
    EdgeNotFoundError,
    Node,
    NodeNotFoundError,
    NodeType,
    OntologySchema,
)


class KnowledgeGraph:
    """Graphe architectural ``G = (V, E)`` en mémoire.

    Les nœuds et relations sont conservés dans l'ordre d'insertion, ce qui rend les
    exports déterministes. Toute relation est validée contre l'ontologie à l'ajout.

    Attributes:
        version: Version du graphe, incrémentée par les commandes (sprint 2).
    """

    def __init__(self, schema: OntologySchema | None = None, version: int = 0) -> None:
        self._schema = schema if schema is not None else OntologySchema.default()
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._out: dict[str, list[str]] = {}
        self._in: dict[str, list[str]] = {}
        self.version = version

    @property
    def schema(self) -> OntologySchema:
        """Ontologie appliquée aux relations."""
        return self._schema

    def nodes(self) -> list[Node]:
        """Tous les nœuds, dans l'ordre d'insertion."""
        return list(self._nodes.values())

    def edges(self) -> list[Edge]:
        """Toutes les relations, dans l'ordre d'insertion."""
        return list(self._edges.values())

    def add_node(self, node: Node) -> Node:
        """Ajoute un nœud.

        Raises:
            DuplicateNodeError: Si l'identifiant existe déjà.
        """
        if node.id in self._nodes:
            raise DuplicateNodeError(f"nœud déjà présent : {node.id!r}")
        self._nodes[node.id] = node
        self._out[node.id] = []
        self._in[node.id] = []
        return node

    def add_edge(self, edge: Edge) -> Edge:
        """Ajoute une relation après validation des extrémités et de l'ontologie.

        Raises:
            DuplicateEdgeError: Si l'identifiant existe déjà.
            NodeNotFoundError: Si la source ou la cible est absente.
            OntologyViolationError: Si le triplet n'est pas autorisé.
        """
        if edge.id in self._edges:
            raise DuplicateEdgeError(f"relation déjà présente : {edge.id!r}")
        self._schema.validate_edge(edge, self)
        self._edges[edge.id] = edge
        self._out[edge.source_id].append(edge.id)
        self._in[edge.target_id].append(edge.id)
        return edge

    def remove_edge(self, edge_id: str) -> Edge:
        """Retire une relation et la retourne.

        Raises:
            EdgeNotFoundError: Si la relation est absente.
        """
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            raise EdgeNotFoundError(f"relation introuvable : {edge_id!r}")
        self._out[edge.source_id].remove(edge_id)
        self._in[edge.target_id].remove(edge_id)
        return edge

    def remove_node(self, node_id: str) -> None:
        """Retire un nœud et toutes ses relations entrantes et sortantes.

        Raises:
            NodeNotFoundError: Si le nœud est absent.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(f"nœud introuvable : {node_id!r}")
        for edge_id in dict.fromkeys(self._out[node_id] + self._in[node_id]):
            self.remove_edge(edge_id)
        del self._nodes[node_id], self._out[node_id], self._in[node_id]

    def get_node(self, node_id: str) -> Node | None:
        """Retourne le nœud, ou ``None`` s'il est absent."""
        return self._nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Edge | None:
        """Retourne la relation, ou ``None`` si elle est absente."""
        return self._edges.get(edge_id)

    def nodes_of_type(self, node_type: NodeType) -> list[Node]:
        """Nœuds d'un type donné, dans l'ordre d'insertion."""
        return [node for node in self._nodes.values() if node.type == node_type]

    def out_edges(self, node_id: str) -> list[Edge]:
        """Relations sortantes du nœud.

        Raises:
            NodeNotFoundError: Si le nœud est absent.
        """
        return [self._edges[edge_id] for edge_id in self._adjacency(self._out, node_id)]

    def in_edges(self, node_id: str) -> list[Edge]:
        """Relations entrantes du nœud.

        Raises:
            NodeNotFoundError: Si le nœud est absent.
        """
        return [self._edges[edge_id] for edge_id in self._adjacency(self._in, node_id)]

    def copy(self) -> "KnowledgeGraph":
        """Copie indépendante du graphe.

        Les nœuds et relations sont des modèles immuables : seuls les conteneurs sont
        dupliqués. Utilisée par les snapshots, qui doivent figer un état.
        """
        clone = KnowledgeGraph(self._schema, self.version)
        clone._nodes = dict(self._nodes)
        clone._edges = dict(self._edges)
        clone._out = {node_id: list(edges) for node_id, edges in self._out.items()}
        clone._in = {node_id: list(edges) for node_id, edges in self._in.items()}
        return clone

    def subgraph(self, node_ids: Iterable[str]) -> "KnowledgeGraph":
        """Nouveau graphe restreint aux nœuds donnés et aux relations internes à cet ensemble.

        Raises:
            NodeNotFoundError: Si un identifiant est absent.
        """
        selected = set(node_ids)
        missing = selected - self._nodes.keys()
        if missing:
            raise NodeNotFoundError(f"nœuds introuvables : {sorted(missing)!r}")
        result = KnowledgeGraph(self._schema, self.version)
        for node in self._nodes.values():
            if node.id in selected:
                result.add_node(node)
        for edge in self._edges.values():
            if edge.source_id in selected and edge.target_id in selected:
                result.add_edge(edge)
        return result

    def to_networkx(self) -> "nx.MultiDiGraph[str]":
        """Export NetworkX ; plusieurs relations peuvent relier la même paire de nœuds."""
        graph: nx.MultiDiGraph[str] = nx.MultiDiGraph()
        for node in self._nodes.values():
            graph.add_node(node.id, type=node.type.value, name=node.name)
        for edge in self._edges.values():
            graph.add_edge(
                edge.source_id,
                edge.target_id,
                key=edge.id,
                relation=edge.relation.value,
                confidence=edge.provenance.confidence,
            )
        return graph

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def _adjacency(self, index: dict[str, list[str]], node_id: str) -> list[str]:
        if node_id not in index:
            raise NodeNotFoundError(f"nœud introuvable : {node_id!r}")
        return index[node_id]
