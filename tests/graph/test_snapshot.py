from collections.abc import Callable

from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType
from sakg.graph import GraphSnapshot, KnowledgeGraph, compute_graph_hash

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


def _graph_with(nodes: list[Node], edges: list[Edge]) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for node in nodes:
        graph.add_node(node)
    for edge in edges:
        graph.add_edge(edge)
    return graph


def test_snapshot_freezes_the_graph(make_node: MakeNode) -> None:
    """Un snapshot ne doit pas suivre les mutations ultérieures du graphe."""
    graph = _graph_with([make_node(NodeType.CLASS, "A")], [])

    snapshot = GraphSnapshot.of(graph)
    graph.add_node(make_node(NodeType.CLASS, "B"))

    assert len(snapshot.graph) == 1
    assert snapshot.graph is not graph
    assert compute_graph_hash(snapshot.graph) == snapshot.graph_hash


def test_copy_is_independent(make_node: MakeNode, make_edge: MakeEdge) -> None:
    parent = make_node(NodeType.CLASS, "Parent")
    child = make_node(NodeType.CLASS, "Child")
    graph = _graph_with([parent, child], [make_edge(child, RelationType.INHERITS, parent)])

    clone = graph.copy()
    graph.remove_node(child.id)

    assert len(clone) == 2
    assert len(clone.edges()) == 1
    assert clone.version == graph.version


def test_hash_is_stable_across_insertion_order(make_node: MakeNode) -> None:
    first, second = make_node(NodeType.CLASS, "A"), make_node(NodeType.CLASS, "B")

    assert compute_graph_hash(_graph_with([first, second], [])) == compute_graph_hash(_graph_with([second, first], []))


def test_hash_ignores_volatile_provenance_fields(make_node: MakeNode) -> None:
    node = make_node(NodeType.CLASS, "A")
    later = node.model_copy(
        update={
            "provenance": Provenance(
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                detected_by="TEST",
                graph_version=7,
                commit_sha="deadbeef",
            )
        }
    )

    assert compute_graph_hash(_graph_with([node], [])) == compute_graph_hash(_graph_with([later], []))


def test_hash_changes_with_content(make_node: MakeNode, make_edge: MakeEdge) -> None:
    parent, child = make_node(NodeType.CLASS, "Parent"), make_node(NodeType.CLASS, "Child")
    without_edge = compute_graph_hash(_graph_with([parent, child], []))
    with_edge = compute_graph_hash(_graph_with([parent, child], [make_edge(child, RelationType.INHERITS, parent)]))

    assert without_edge != with_edge


def test_hash_changes_with_confidence(make_node: MakeNode) -> None:
    node = make_node(NodeType.CLASS, "A")
    uncertain = node.model_copy(
        update={"provenance": Provenance(evidence_type=EvidenceType.INFERRED, confidence=0.6, detected_by="TEST")}
    )

    assert compute_graph_hash(_graph_with([node], [])) != compute_graph_hash(_graph_with([uncertain], []))
