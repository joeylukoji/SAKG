"""Règles d'architecture : une politique du projet, vérifiable sur son graphe.

``ArchitectureRule`` est le point d'extension (règle 6 d'AGENTS.md) : une nouvelle règle est une
nouvelle classe enregistrée dans le registre de :mod:`sakg.validation.loader`, sans toucher à
``ArchitectureValidator`` ni au reste du cœur.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import networkx as nx

from sakg.domain import RelationType
from sakg.graph import KnowledgeGraph
from sakg.validation.findings import Finding, Severity

__all__ = ["ArchitectureRule", "LayerDependencyRule", "NoCycleRule"]


class ArchitectureRule(Protocol):
    """Politique vérifiable sur le graphe (ARCHITECTURE.md §4.4)."""

    @property
    def id(self) -> str:
        """Identifiant stable, cité dans chaque ``Finding`` qu'elle produit."""
        ...

    @property
    def severity(self) -> Severity:
        """Gravité par défaut des constats de cette règle."""
        ...

    def check(self, graph: KnowledgeGraph) -> list[Finding]:
        """Constats trouvés dans ce graphe, vide si la règle est respectée."""
        ...


@dataclass(frozen=True)
class LayerDependencyRule:
    """Une couche interne ne dépend jamais d'une couche plus externe.

    ``layers`` va du cœur vers l'extérieur, par exemple ``("sakg.domain", "sakg.graph", ...)``.
    Un module absent de toute couche n'est pas contrôlé : la règle ne porte que sur ce qu'elle
    connaît, plutôt que de deviner. Le module d'un nœud vient de sa propriété ``module``
    (posée par ``CodeStructureExtractor``) ; le préfixe le plus long qui correspond l'emporte,
    pour que ``sakg.domain.node`` se range dans la couche ``sakg.domain``.
    """

    id: str
    layers: tuple[str, ...]
    severity: Severity = Severity.ERROR

    def check(self, graph: KnowledgeGraph) -> list[Finding]:
        """Relations ``depends_on`` qui remontent d'une couche interne vers une couche externe."""
        rank = {prefix: index for index, prefix in enumerate(self.layers)}
        findings: list[Finding] = []
        for relation_edge in graph.edges():
            if relation_edge.relation is not RelationType.DEPENDS_ON:
                continue
            source = graph.get_node(relation_edge.source_id)
            target = graph.get_node(relation_edge.target_id)
            if source is None or target is None:
                continue
            source_rank = _rank_of(str(source.properties.get("module", "")), rank)
            target_rank = _rank_of(str(target.properties.get("module", "")), rank)
            if source_rank is None or target_rank is None or source_rank >= target_rank:
                continue
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=(
                        f"{source.name} ({self.layers[source_rank]}) dépend de {target.name} "
                        f"({self.layers[target_rank]}) : une couche interne ne dépend pas d'une couche "
                        "plus externe"
                    ),
                    node_ids=(source.id, target.id),
                    edge_ids=(relation_edge.id,),
                )
            )
        return findings

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "LayerDependencyRule":
        """Construit la règle depuis une entrée de ``.architect/rules/*.yaml``."""
        return cls(
            id=str(config["id"]),
            layers=tuple(str(layer) for layer in config["layers"]),
            severity=Severity(config.get("severity", Severity.ERROR.value)),
        )


@dataclass(frozen=True)
class NoCycleRule:
    """Cycle dans les imports d'exécution.

    Un import placé sous ``if TYPE_CHECKING`` (``properties.type_only``) n'engage rien à
    l'exécution : il ne peut donc pas fermer un cycle réel, et n'est jamais retenu ici.
    """

    id: str = "no_cycle"
    relation: RelationType = RelationType.DEPENDS_ON
    severity: Severity = Severity.ERROR

    def check(self, graph: KnowledgeGraph) -> list[Finding]:
        """Un constat par cycle trouvé parmi les relations d'exécution du type suivi."""
        runtime: nx.DiGraph[str] = nx.DiGraph()
        edge_of: dict[tuple[str, str], str] = {}
        for relation_edge in graph.edges():
            if relation_edge.relation is not self.relation or bool(relation_edge.properties.get("type_only")):
                continue
            runtime.add_edge(relation_edge.source_id, relation_edge.target_id)
            edge_of[(relation_edge.source_id, relation_edge.target_id)] = relation_edge.id

        findings: list[Finding] = []
        for cycle in nx.simple_cycles(runtime):
            edge_ids = tuple(edge_of[(cycle[index], cycle[(index + 1) % len(cycle)])] for index in range(len(cycle)))
            names = " → ".join(_name_of(graph, node_id) for node_id in (*cycle, cycle[0]))
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"cycle d'imports d'exécution : {names}",
                    node_ids=tuple(cycle),
                    edge_ids=edge_ids,
                )
            )
        return findings

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "NoCycleRule":
        """Construit la règle depuis une entrée de ``.architect/rules/*.yaml``."""
        return cls(
            id=str(config.get("id", "no_cycle")),
            relation=RelationType(config["relation"]) if "relation" in config else RelationType.DEPENDS_ON,
            severity=Severity(config.get("severity", Severity.ERROR.value)),
        )


def _rank_of(module: str, rank: Mapping[str, int]) -> int | None:
    """Rang du préfixe de couche le plus long qui correspond à ``module``, ou ``None``."""
    matches = [prefix for prefix in rank if module == prefix or module.startswith(f"{prefix}.")]
    return rank[max(matches, key=len)] if matches else None


def _name_of(graph: KnowledgeGraph, node_id: str) -> str:
    node = graph.get_node(node_id)
    return node.name if node is not None else node_id
