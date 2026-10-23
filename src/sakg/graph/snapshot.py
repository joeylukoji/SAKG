"""Snapshot : état figé du graphe, identifié par un hash de contenu."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sakg.domain import Edge, Node
from sakg.graph.knowledge_graph import KnowledgeGraph


def node_fingerprint(node: Node) -> dict[str, Any]:
    """Contenu d'un nœud au sens d'ADR-005 : ce qui distingue deux architectures."""
    return {
        "id": node.id,
        "type": node.type.value,
        "name": node.name,
        "properties": node.properties,
        "evidence_type": node.provenance.evidence_type.value,
        "confidence": node.provenance.confidence,
    }


def edge_fingerprint(edge: Edge) -> dict[str, Any]:
    """Contenu d'une relation au sens d'ADR-005."""
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relation": edge.relation.value,
        "properties": edge.properties,
        "evidence_type": edge.provenance.evidence_type.value,
        "confidence": edge.provenance.confidence,
    }


def compute_graph_hash(graph: KnowledgeGraph) -> str:
    """Hash SHA-256 du contenu du graphe.

    Les champs volatils de la provenance (``created_at``, ``graph_version``, ``commit_sha``)
    sont exclus : deux reverse successifs d'un code inchangé produisent le même hash, ce qui
    rend le diff et la détection de dérive exploitables.
    """
    payload = {
        "nodes": [node_fingerprint(node) for node in sorted(graph.nodes(), key=lambda n: n.id)],
        "edges": [edge_fingerprint(edge) for edge in sorted(graph.edges(), key=lambda e: e.id)],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, kw_only=True)
class SnapshotMeta:
    """Fiche d'une version archivée, sans son graphe.

    Lister l'historique ne doit pas coûter le rechargement de tous les graphes : cette fiche
    suffit à afficher ``sakg history`` et à choisir les versions à comparer.

    Attributes:
        version: Numéro de version.
        graph_hash: Hash de contenu du graphe.
        commit_sha: Commit du code analysé, s'il est connu.
        label: Étiquette lisible, en général la commande à l'origine de la version.
        created_at: Horodatage UTC de la version, relu tel quel (jamais « maintenant »).
        node_count: Nombre de nœuds, ou ``None`` si la version est antérieure à son
            enregistrement : une donnée absente n'est pas un zéro.
        edge_count: Nombre de relations, avec la même réserve.
    """

    version: int
    graph_hash: str
    created_at: datetime
    commit_sha: str | None = None
    label: str | None = None
    node_count: int | None = None
    edge_count: int | None = None


@dataclass(frozen=True, kw_only=True)
class GraphSnapshot:
    """État du graphe à une version donnée.

    Attributes:
        version: Numéro de version, croissant.
        graph_hash: Hash de contenu, voir :func:`compute_graph_hash`.
        graph: Graphe correspondant.
        commit_sha: Commit du code analysé, s'il est connu.
        label: Étiquette lisible, par exemple le nom de la commande à l'origine du snapshot.
        created_at: Horodatage UTC.
    """

    version: int
    graph_hash: str
    graph: KnowledgeGraph
    commit_sha: str | None = None
    label: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def meta(self) -> SnapshotMeta:
        """Fiche de cette version, sans le graphe."""
        return SnapshotMeta(
            version=self.version,
            graph_hash=self.graph_hash,
            commit_sha=self.commit_sha,
            label=self.label,
            created_at=self.created_at,
            node_count=len(self.graph),
            edge_count=len(self.graph.edges()),
        )

    @classmethod
    def of(
        cls,
        graph: KnowledgeGraph,
        *,
        commit_sha: str | None = None,
        label: str | None = None,
    ) -> "GraphSnapshot":
        """Construit un snapshot à partir du graphe et de sa version courante.

        Le graphe est copié : un snapshot est un état figé, insensible aux commandes
        exécutées ensuite.
        """
        return cls(
            version=graph.version,
            graph_hash=compute_graph_hash(graph),
            graph=graph.copy(),
            commit_sha=commit_sha,
            label=label,
        )
