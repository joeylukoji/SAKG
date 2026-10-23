"""Construction incrémentale du graphe à partir des résultats d'extraction (Builder)."""

from sakg.domain import Edge, Node, OntologySchema
from sakg.graph import KnowledgeGraph
from sakg.reverse.models import ExtractionResult


class GraphBuilder:
    """Fusionne les ``ExtractionResult``, dédoublonne et écarte les relations irrésolues.

    Un extracteur peut produire une relation vers un nœud qu'un autre n'a pas créé (import
    vers un module exclu du scan, par exemple) : ces relations sont retirées et signalées
    dans :attr:`warnings` plutôt que de faire échouer le reverse.

    Example:
        >>> graph = GraphBuilder().add(result).resolve_references().build()  # doctest: +SKIP
    """

    def __init__(self, schema: OntologySchema | None = None) -> None:
        self._schema = schema if schema is not None else OntologySchema.default()
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._reported: set[str] = set()
        self.warnings: list[str] = []

    def add(self, result: ExtractionResult) -> "GraphBuilder":
        """Ajoute le résultat d'un extracteur ; le premier nœud gagne en cas de doublon.

        Deux extracteurs qui butent sur le même fichier illisible le signalent chacun : seul
        le premier message est conservé, pour ne pas montrer deux fois le même problème.
        """
        for node in result.nodes:
            self._nodes.setdefault(node.id, node)
        for edge in result.edges:
            self._edges.setdefault(edge.id, edge)
        self.warnings.extend(warning for warning in result.warnings if self._is_new(warning))
        return self

    def _is_new(self, warning: str) -> bool:
        problem = warning.split(" : ", 1)[-1]  # le préfixe est le nom de l'extracteur
        if problem in self._reported:
            return False
        self._reported.add(problem)
        return True

    def resolve_references(self) -> "GraphBuilder":
        """Retire les relations dont une extrémité n'a pas été extraite."""
        dangling = [
            edge_id
            for edge_id, edge in self._edges.items()
            if edge.source_id not in self._nodes or edge.target_id not in self._nodes
        ]
        for edge_id in dangling:
            del self._edges[edge_id]
            self.warnings.append(f"relation ignorée, extrémité absente du graphe : {edge_id}")
        return self

    def build(self) -> KnowledgeGraph:
        """Construit le graphe extrait.

        Raises:
            OntologyViolationError: Si une relation extraite n'est pas autorisée.
        """
        return self.merge_into(KnowledgeGraph(self._schema))

    def merge_into(self, existing: KnowledgeGraph) -> KnowledgeGraph:
        """Ajoute ce qui a été construit à un graphe existant, sans toucher à ce qu'il contient.

        La cible doit être un graphe détaché : le graphe du projet, lui, ne se modifie que par
        une ``GraphCommand`` passée au ``CommandBus`` (règle 4 d'AGENTS.md).
        """
        self.resolve_references()
        for node in self._nodes.values():
            if node.id not in existing:
                existing.add_node(node)
        for edge in self._edges.values():
            if existing.get_edge(edge.id) is None:
                existing.add_edge(edge)
        return existing
