import json
from collections.abc import Callable
from pathlib import Path

import pytest

from sakg.domain import Edge, Node, NodeType, RelationType, SnapshotNotFoundError
from sakg.graph import KnowledgeGraph, compute_graph_hash
from sakg.infrastructure import JsonGraphRepository
from sakg.infrastructure.json_graph_repository import CorruptedGraphError

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def repository(tmp_path: Path) -> JsonGraphRepository:
    return JsonGraphRepository(tmp_path)


@pytest.fixture
def graph(make_node: MakeNode, make_edge: MakeEdge) -> KnowledgeGraph:
    graph = KnowledgeGraph(version=1)
    parent = graph.add_node(make_node(NodeType.CLASS, "BaseService", "src/core/base.py"))
    child = graph.add_node(make_node(NodeType.CLASS, "PaymentService", "src/payment/service.py"))
    graph.add_edge(make_edge(child, RelationType.INHERITS, parent))
    return graph


def test_load_without_saved_graph_returns_empty_graph(repository: JsonGraphRepository) -> None:
    loaded = repository.load()

    assert len(loaded) == 0
    assert loaded.version == 0


def test_save_then_load_round_trip(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    saved = repository.save(graph, label="reverse")

    loaded = repository.load()

    assert loaded.version == 1
    assert {node.id for node in loaded.nodes()} == {node.id for node in graph.nodes()}
    assert [edge.relation for edge in loaded.edges()] == [RelationType.INHERITS]
    assert loaded.nodes()[0].provenance.created_at == graph.nodes()[0].provenance.created_at
    assert compute_graph_hash(loaded) == saved.graph_hash  # la sérialisation ne perd rien


def test_save_writes_architect_layout(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph, label="reverse", commit_sha="abc123")

    meta = json.loads((repository.graph_dir / "meta.json").read_text(encoding="utf-8"))
    assert (repository.graph_dir / "nodes.json").exists()
    assert (repository.versions_dir / "v0001" / "edges.json").exists()
    assert meta["label"] == "reverse"
    assert meta["commit_sha"] == "abc123"
    assert meta["node_count"] == 2


def test_nodes_are_written_sorted_for_readable_diffs(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph)

    nodes = json.loads((repository.graph_dir / "nodes.json").read_text(encoding="utf-8"))
    assert [node["id"] for node in nodes] == sorted(node["id"] for node in nodes)


def test_list_snapshots_is_ordered_by_version(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph)
    graph.version = 2
    repository.save(graph)

    assert [snapshot.version for snapshot in repository.list_snapshots()] == [1, 2]
    assert repository.list_snapshots()[0].label is None


def test_listing_history_does_not_load_the_graphs(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    """Lister l'historique ne lit que meta.json : un nodes.json illisible n'y change rien."""
    repository.save(graph)
    (repository.versions_dir / "v0001" / "nodes.json").write_text("pas du json", encoding="utf-8")

    metas = repository.list_snapshots()

    assert [(meta.version, meta.node_count, meta.edge_count) for meta in metas] == [(1, 2, 1)]


def test_an_old_meta_without_counts_reports_them_as_unknown(
    repository: JsonGraphRepository, graph: KnowledgeGraph
) -> None:
    """Une version antérieure à l'enregistrement des comptes n'a pas « 0 nœuds »."""
    repository.save(graph)
    meta_path = repository.versions_dir / "v0001" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    del meta["node_count"], meta["edge_count"]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    listed = repository.list_snapshots()[0]

    assert (listed.node_count, listed.edge_count) == (None, None)


def test_a_malformed_meta_is_reported_as_corruption(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph)
    (repository.versions_dir / "v0001" / "meta.json").write_text('{"version": 1}', encoding="utf-8")

    with pytest.raises(CorruptedGraphError, match="métadonnées illisibles"):
        repository.list_snapshots()


def test_list_snapshots_without_versions(repository: JsonGraphRepository) -> None:
    assert repository.list_snapshots() == []


def test_writes_leave_no_temporary_file(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph)

    assert list(repository.graph_dir.glob("*.tmp")) == []


def test_truncated_graph_is_refused_instead_of_silently_loaded(
    repository: JsonGraphRepository, graph: KnowledgeGraph
) -> None:
    """Une écriture interrompue ne doit pas se recharger comme un graphe valide."""
    repository.save(graph)
    nodes = json.loads((repository.graph_dir / "nodes.json").read_text(encoding="utf-8"))
    (repository.graph_dir / "nodes.json").write_text(json.dumps(nodes[:1]), encoding="utf-8")

    with pytest.raises(CorruptedGraphError, match="incohérent"):
        repository.load()


def test_load_missing_snapshot(repository: JsonGraphRepository, graph: KnowledgeGraph) -> None:
    repository.save(graph)

    with pytest.raises(SnapshotNotFoundError):
        repository.load_snapshot(99)
