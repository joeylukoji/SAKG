"""Diff entre deux versions : ce qui change dans l'architecture, et seulement cela."""

from collections.abc import Callable

from sakg.analysis import GraphDiffer
from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType
from sakg.graph import GraphSnapshot, KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


def _graph(nodes: list[Node], edges: list[Edge] | None = None, version: int = 0) -> KnowledgeGraph:
    graph = KnowledgeGraph(version=version)
    for node in nodes:
        graph.add_node(node)
    for edge in edges or []:
        graph.add_edge(edge)
    return graph


def test_identical_graphs_have_an_empty_diff(make_node: MakeNode) -> None:
    node = make_node(NodeType.CLASS, "App")

    diff = GraphDiffer().diff_graphs(_graph([node]), _graph([node]))

    assert diff.is_empty()
    assert "Aucun changement" in diff.to_markdown()


def test_added_and_removed_nodes(make_node: MakeNode) -> None:
    kept, gone, new = (make_node(NodeType.CLASS, name) for name in ("Kept", "Gone", "New"))

    diff = GraphDiffer().diff_graphs(_graph([kept, gone]), _graph([kept, new]))

    assert [node.name for node in diff.added_nodes] == ["New"]
    assert [node.name for node in diff.removed_nodes] == ["Gone"]
    assert diff.modified_nodes == []


def test_a_changed_property_is_a_modification(make_node: MakeNode) -> None:
    before = make_node(NodeType.CLASS, "App")
    after = before.model_copy(update={"properties": {"module": "app.core"}})

    diff = GraphDiffer().diff_graphs(_graph([before]), _graph([after]))

    assert len(diff.modified_nodes) == 1
    assert diff.modified_nodes[0].changed_fields() == ["properties"]


def test_a_confidence_change_is_a_modification(make_node: MakeNode) -> None:
    """Passer d'une relation supposée à une relation observée change ce que l'on sait."""
    observed = make_node(NodeType.CLASS, "App")
    inferred = observed.model_copy(
        update={"provenance": Provenance(evidence_type=EvidenceType.INFERRED, confidence=0.6, detected_by="TEST")}
    )

    diff = GraphDiffer().diff_graphs(_graph([inferred]), _graph([observed]))

    assert diff.modified_nodes[0].changed_fields() == ["confidence", "evidence_type"]


def test_moving_a_class_within_its_file_is_not_a_change(make_node: MakeNode) -> None:
    """ADR-005 : la ligne de déclaration n'est pas l'architecture."""
    before = make_node(NodeType.CLASS, "App")
    moved = before.model_copy(
        update={
            "provenance": before.provenance.model_copy(update={"graph_version": 9, "commit_sha": "ffff"}),
        }
    )

    assert GraphDiffer().diff_graphs(_graph([before]), _graph([moved])).is_empty()


def test_added_and_removed_edges(make_node: MakeNode, make_edge: MakeEdge) -> None:
    parent, child, other = (make_node(NodeType.CLASS, name) for name in ("Parent", "Child", "Other"))
    old_edge = make_edge(child, RelationType.INHERITS, parent)
    new_edge = make_edge(child, RelationType.INHERITS, other)

    diff = GraphDiffer().diff_graphs(
        _graph([parent, child, other], [old_edge]), _graph([parent, child, other], [new_edge])
    )

    assert diff.added_edges == [new_edge]
    assert diff.removed_edges == [old_edge]


def test_an_edge_whose_nature_changed_is_modified_not_removed(make_node: MakeNode, make_edge: MakeEdge) -> None:
    """Un import de typage devenu import d'exécution : la relation existe toujours."""
    source, target = make_node(NodeType.FILE, "a.py"), make_node(NodeType.FILE, "b.py")
    runtime = make_edge(source, RelationType.DEPENDS_ON, target)
    typing_only = runtime.model_copy(update={"properties": {"type_only": True}})

    diff = GraphDiffer().diff_graphs(_graph([source, target], [typing_only]), _graph([source, target], [runtime]))

    assert diff.removed_edges == []
    assert diff.added_edges == []
    assert len(diff.modified_edges) == 1
    assert diff.modified_edges[0].describe() == ["properties.type_only : True → absent"]
    assert "relations modifiées : 1" in diff.to_markdown()
    assert "relations supprimées" not in diff.to_markdown()


def test_an_edge_confidence_change_is_a_modification(make_node: MakeNode, make_edge: MakeEdge) -> None:
    caller, callee = make_node(NodeType.METHOD, "run"), make_node(NodeType.METHOD, "save")
    observed = make_edge(caller, RelationType.CALLS, callee)
    inferred = observed.model_copy(
        update={"provenance": Provenance(evidence_type=EvidenceType.INFERRED, confidence=0.6, detected_by="TEST")}
    )

    diff = GraphDiffer().diff_graphs(_graph([caller, callee], [inferred]), _graph([caller, callee], [observed]))

    assert diff.modified_edges[0].describe() == ["confidence : 0.6 → 1.0", "evidence_type : INFERRED → OBSERVED"]


def test_edges_show_their_nature_in_the_report(make_node: MakeNode, make_edge: MakeEdge) -> None:
    source, target = make_node(NodeType.FILE, "a.py"), make_node(NodeType.FILE, "b.py")
    typing_only = make_edge(source, RelationType.DEPENDS_ON, target).model_copy(
        update={"properties": {"type_only": True}}
    )

    markdown = (
        GraphDiffer().diff_graphs(_graph([source, target]), _graph([source, target], [typing_only])).to_markdown()
    )

    assert "(typage seul)" in markdown


def test_diff_between_snapshots_carries_their_versions(make_node: MakeNode) -> None:
    before = GraphSnapshot.of(_graph([make_node(NodeType.CLASS, "A")], version=3))
    after = GraphSnapshot.of(_graph([make_node(NodeType.CLASS, "B")], version=5))

    diff = GraphDiffer().diff(before, after)

    assert (diff.before, diff.after) == (3, 5)
    assert diff.to_markdown().startswith("# Diff d'architecture : v3 → v5")


def test_markdown_reports_counts_and_changed_fields(make_node: MakeNode) -> None:
    before = make_node(NodeType.CLASS, "App")
    after = before.model_copy(update={"properties": {"module": "x"}})
    added = make_node(NodeType.FUNCTION, "helper")

    markdown = GraphDiffer().diff_graphs(_graph([before]), _graph([after, added])).to_markdown()

    assert "nœuds ajoutés : 1" in markdown
    assert "nœuds modifiés : 1" in markdown
    assert "— properties" in markdown


def test_by_type_ranks_the_most_affected_first(make_node: MakeNode) -> None:
    new = [make_node(NodeType.CLASS, "A"), make_node(NodeType.CLASS, "B"), make_node(NodeType.TABLE, "t")]

    diff = GraphDiffer().diff_graphs(_graph([]), _graph(new))

    assert list(diff.by_type().items()) == [(NodeType.CLASS, 2), (NodeType.TABLE, 1)]
