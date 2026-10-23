"""Dépôt JSON : le graphe voyage avec le code dans ``.architect/`` (MVP)."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sakg.domain import Edge, Node, OntologySchema, SakgError, SnapshotNotFoundError
from sakg.graph import GraphRepository, GraphSnapshot, KnowledgeGraph, SnapshotMeta


class CorruptedGraphError(SakgError):
    """Les fichiers du graphe ne correspondent pas à leurs métadonnées."""


ARCHITECT_DIR = ".architect"
GRAPH_DIR = "graph"
VERSIONS_DIR = "versions"
NODES_FILE = "nodes.json"
EDGES_FILE = "edges.json"
META_FILE = "meta.json"


class JsonGraphRepository:
    """Persiste le graphe en JSON trié, lisible et diffable dans Git.

    Chaque sauvegarde écrit l'état courant dans ``.architect/graph/`` et l'archive dans
    ``.architect/versions/vXXXX/``.

    Attributes:
        root: Racine du projet analysé, celle qui contient ``.architect/``.
    """

    def __init__(self, root: Path, schema: OntologySchema | None = None) -> None:
        self.root = Path(root)
        self._schema = schema if schema is not None else OntologySchema.default()

    @property
    def architect_dir(self) -> Path:
        """Dossier ``.architect`` du projet."""
        return self.root / ARCHITECT_DIR

    @property
    def graph_dir(self) -> Path:
        """Dossier de l'état courant du graphe."""
        return self.architect_dir / GRAPH_DIR

    @property
    def versions_dir(self) -> Path:
        """Dossier des versions archivées."""
        return self.architect_dir / VERSIONS_DIR

    def save(self, graph: KnowledgeGraph, *, label: str | None = None, commit_sha: str | None = None) -> GraphSnapshot:
        """Écrit l'état courant puis archive la version ``graph.version``."""
        snapshot = GraphSnapshot.of(graph, label=label, commit_sha=commit_sha)
        self._write_snapshot(self.graph_dir, snapshot)
        self._write_snapshot(self._version_dir(snapshot.version), snapshot)
        return snapshot

    def load(self) -> KnowledgeGraph:
        """Charge l'état courant, ou un graphe vide si le projet n'a rien enregistré."""
        if not (self.graph_dir / NODES_FILE).exists():
            return KnowledgeGraph(self._schema)
        return self._read_snapshot(self.graph_dir).graph

    def list_snapshots(self) -> list[SnapshotMeta]:
        """Fiches des versions archivées, par version croissante.

        Seul ``meta.json`` est lu : lister l'historique ne coûte pas le rechargement de tous
        les graphes, qui deviendrait prohibitif à mesure que les versions s'accumulent.
        """
        if not self.versions_dir.exists():
            return []
        metas = [
            self._read_meta(directory)
            for directory in self.versions_dir.iterdir()
            if directory.is_dir() and (directory / META_FILE).exists()
        ]
        return sorted(metas, key=lambda meta: meta.version)

    def _read_meta(self, directory: Path) -> SnapshotMeta:
        """Fiche d'une version.

        Raises:
            CorruptedGraphError: Si ``meta.json`` est illisible ou incomplet.
        """
        try:
            meta: dict[str, Any] = _read_json(directory / META_FILE)
            return SnapshotMeta(
                version=int(meta["version"]),
                graph_hash=str(meta["graph_hash"]),
                created_at=datetime.fromisoformat(str(meta["created_at"])),
                commit_sha=meta.get("commit_sha"),
                label=meta.get("label"),
                node_count=_optional_int(meta.get("node_count")),
                edge_count=_optional_int(meta.get("edge_count")),
            )
        except (KeyError, ValueError, TypeError) as error:
            raise CorruptedGraphError(f"métadonnées illisibles dans {directory} ({error})") from error

    def load_snapshot(self, version: int) -> GraphSnapshot:
        """Charge un snapshot archivé.

        Raises:
            SnapshotNotFoundError: Si la version n'existe pas.
        """
        directory = self._version_dir(version)
        if not (directory / NODES_FILE).exists():
            raise SnapshotNotFoundError(f"version introuvable : {version}")
        return self._read_snapshot(directory)

    def _version_dir(self, version: int) -> Path:
        return self.versions_dir / f"v{version:04d}"

    def _write_snapshot(self, directory: Path, snapshot: GraphSnapshot) -> None:
        """Écrit les trois fichiers d'un snapshot, en publiant ``meta.json`` en dernier.

        Chaque fichier est écrit à côté puis renommé (``os.replace``, atomique sur le même
        volume) : une écriture interrompue laisse l'état précédent intact plutôt qu'un
        mélange de deux versions.
        """
        directory.mkdir(parents=True, exist_ok=True)
        nodes = [node.model_dump(mode="json") for node in sorted(snapshot.graph.nodes(), key=lambda n: n.id)]
        edges = [edge.model_dump(mode="json") for edge in sorted(snapshot.graph.edges(), key=lambda e: e.id)]
        meta = {
            "version": snapshot.version,
            "graph_hash": snapshot.graph_hash,
            "commit_sha": snapshot.commit_sha,
            "label": snapshot.label,
            "created_at": snapshot.created_at.isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
        _write_json_atomically(directory / NODES_FILE, nodes)
        _write_json_atomically(directory / EDGES_FILE, edges)
        _write_json_atomically(directory / META_FILE, meta)

    def _read_snapshot(self, directory: Path) -> GraphSnapshot:
        meta: dict[str, Any] = _read_json(directory / META_FILE)
        graph = KnowledgeGraph(self._schema, version=int(meta["version"]))
        raw_nodes = _read_json(directory / NODES_FILE)
        raw_edges = _read_json(directory / EDGES_FILE)
        _check_counts(directory, meta, len(raw_nodes), len(raw_edges))
        for raw_node in raw_nodes:
            graph.add_node(Node.model_validate(raw_node))
        for raw_edge in raw_edges:
            graph.add_edge(Edge.model_validate(raw_edge))
        return GraphSnapshot(
            version=graph.version,
            graph_hash=str(meta["graph_hash"]),
            graph=graph,
            commit_sha=meta.get("commit_sha"),
            label=meta.get("label"),
            created_at=datetime.fromisoformat(str(meta["created_at"])),
        )


def _conforms_to_port(repository: JsonGraphRepository) -> GraphRepository:
    """Vérification statique (mypy) de la conformité de l'adaptateur au port."""
    return repository


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _check_counts(directory: Path, meta: dict[str, Any], nodes: int, edges: int) -> None:
    """Refuse un graphe dont le contenu ne correspond pas à ses métadonnées.

    Raises:
        CorruptedGraphError: Si les comptes diffèrent, signe d'une écriture interrompue.
    """
    expected_nodes, expected_edges = meta.get("node_count"), meta.get("edge_count")
    if (expected_nodes is not None and expected_nodes != nodes) or (
        expected_edges is not None and expected_edges != edges
    ):
        raise CorruptedGraphError(
            f"graphe incohérent dans {directory} : {nodes} nœuds et {edges} relations lus, "
            f"{expected_nodes} et {expected_edges} attendus (relancer « sakg reverse »)"
        )


def _write_json_atomically(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
