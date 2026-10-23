"""Port de persistance du graphe (adaptateurs dans ``infrastructure``)."""

from typing import Protocol

from sakg.graph.knowledge_graph import KnowledgeGraph
from sakg.graph.snapshot import GraphSnapshot, SnapshotMeta


class GraphRepository(Protocol):
    """Contrat de persistance : le cœur ne connaît ni JSON ni base de données."""

    def save(self, graph: KnowledgeGraph, *, label: str | None = None, commit_sha: str | None = None) -> GraphSnapshot:
        """Enregistre l'état courant du graphe et archive la version correspondante."""
        ...

    def load(self) -> KnowledgeGraph:
        """Charge l'état courant ; retourne un graphe vide si rien n'est enregistré."""
        ...

    def list_snapshots(self) -> list[SnapshotMeta]:
        """Fiches des versions archivées, par version croissante, sans charger les graphes."""
        ...

    def load_snapshot(self, version: int) -> GraphSnapshot:
        """Charge un snapshot archivé.

        Raises:
            SnapshotNotFoundError: Si la version n'existe pas.
        """
        ...
