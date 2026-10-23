from collections.abc import Callable

import pytest

from sakg.application import AddEdgeCommand, AddNodeCommand, ReplaceObservedLayerCommand
from sakg.domain import (
    Edge,
    EvidenceType,
    Node,
    NodeNotFoundError,
    NodeType,
    Provenance,
    RelationType,
)
from sakg.graph import KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


def _user_defined(node_id: str, name: str, node_type: NodeType = NodeType.REQUIREMENT) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        name=name,
        provenance=Provenance(evidence_type=EvidenceType.USER_DEFINED, confidence=1.0, detected_by="USER"),
    )


def test_add_node_command_undo(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    command = AddNodeCommand(make_node(NodeType.CLASS, "App"))

    command.execute(graph)
    command.undo(graph)

    assert len(graph) == 0


def test_add_edge_command_undo(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    parent = graph.add_node(make_node(NodeType.CLASS, "Parent"))
    child = graph.add_node(make_node(NodeType.CLASS, "Child"))
    command = AddEdgeCommand(make_edge(child, RelationType.INHERITS, parent))

    command.execute(graph)
    command.undo(graph)

    assert graph.edges() == []
    assert len(graph) == 2


def test_replace_observed_layer_keeps_user_defined(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    requirement = graph.add_node(_user_defined("requirement:REQ-001", "REQ-001"))
    use_case = graph.add_node(_user_defined("use_case:UC01", "UC01", NodeType.USE_CASE))
    graph.add_edge(
        Edge(
            source_id=requirement.id,
            target_id=use_case.id,
            relation=RelationType.REALIZED_BY,
            provenance=requirement.provenance,
        )
    )
    old_class = graph.add_node(make_node(NodeType.CLASS, "OldService"))
    graph.add_edge(make_edge(old_class, RelationType.DEPENDS_ON, old_class))

    extracted = KnowledgeGraph()
    extracted.add_node(make_node(NodeType.CLASS, "NewService"))

    ReplaceObservedLayerCommand(extracted).execute(graph)

    assert {node.name for node in graph.nodes()} == {"REQ-001", "UC01", "NewService"}
    assert [edge.relation for edge in graph.edges()] == [RelationType.REALIZED_BY]


def test_replace_observed_layer_relinks_curated_edges(make_node: MakeNode) -> None:
    """Une relation saisie par l'utilisateur survit si le nœud observé est re-extrait (§5.1)."""
    graph = KnowledgeGraph()
    test_node = graph.add_node(_user_defined("test:tests/test_app.py::test_run", "test_run", NodeType.TEST))
    observed = graph.add_node(make_node(NodeType.CLASS, "App"))
    curated = graph.add_edge(
        Edge(
            source_id=test_node.id,
            target_id=observed.id,
            relation=RelationType.TESTS,
            provenance=test_node.provenance,
        )
    )

    extracted = KnowledgeGraph()
    extracted.add_node(make_node(NodeType.CLASS, "App"))  # même id : le code n'a pas changé
    ReplaceObservedLayerCommand(extracted).execute(graph)

    assert graph.get_edge(curated.id) is not None


def test_replace_observed_layer_undo_after_relink(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    test_node = graph.add_node(_user_defined("test:tests/test_app.py::test_run", "test_run", NodeType.TEST))
    observed = graph.add_node(make_node(NodeType.CLASS, "App"))
    curated = graph.add_edge(
        Edge(
            source_id=test_node.id,
            target_id=observed.id,
            relation=RelationType.TESTS,
            provenance=test_node.provenance,
        )
    )
    extracted = KnowledgeGraph()
    extracted.add_node(make_node(NodeType.CLASS, "App"))
    command = ReplaceObservedLayerCommand(extracted)

    command.execute(graph)
    command.undo(graph)

    assert {node.id for node in graph.nodes()} == {test_node.id, observed.id}
    assert [edge.id for edge in graph.edges()] == [curated.id]


def test_replace_observed_layer_undo_restores_everything(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    parent = graph.add_node(make_node(NodeType.CLASS, "Parent"))
    child = graph.add_node(make_node(NodeType.CLASS, "Child"))
    graph.add_edge(make_edge(child, RelationType.INHERITS, parent))
    before = ({node.id for node in graph.nodes()}, {edge.id for edge in graph.edges()})

    extracted = KnowledgeGraph()
    extracted.add_node(make_node(NodeType.CLASS, "Fresh"))
    command = ReplaceObservedLayerCommand(extracted)
    command.execute(graph)
    command.undo(graph)

    assert ({node.id for node in graph.nodes()}, {edge.id for edge in graph.edges()}) == before


def test_replace_observed_layer_removes_edges_pointing_to_removed_nodes(
    make_node: MakeNode, make_edge: MakeEdge
) -> None:
    """Une relation USER_DEFINED vers une classe disparue ne doit pas laisser de relation orpheline."""
    graph = KnowledgeGraph()
    test_node = graph.add_node(_user_defined("test:tests/test_app.py::test_run", "test_run", NodeType.TEST))
    observed_class = graph.add_node(make_node(NodeType.CLASS, "App"))
    graph.add_edge(
        Edge(
            source_id=test_node.id,
            target_id=observed_class.id,
            relation=RelationType.TESTS,
            provenance=test_node.provenance,
        )
    )

    ReplaceObservedLayerCommand(KnowledgeGraph()).execute(graph)

    assert [node.id for node in graph.nodes()] == [test_node.id]
    assert graph.edges() == []


class _BrokenExtraction(KnowledgeGraph):
    """Extraction incohérente : une relation vise un nœud qui n'a pas été extrait."""

    def edges(self) -> list[Edge]:
        dangling = super().nodes()[0]
        return [
            Edge(
                source_id=dangling.id,
                target_id="class:src/ghost.py::Ghost",
                relation=RelationType.DEPENDS_ON,
                provenance=dangling.provenance,
            )
        ]


def test_replace_observed_layer_rolls_back_on_failure(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    old = graph.add_node(make_node(NodeType.CLASS, "Old"))
    graph.add_edge(make_edge(old, RelationType.DEPENDS_ON, old))

    extracted = _BrokenExtraction()
    extracted.add_node(make_node(NodeType.CLASS, "Fresh"))

    with pytest.raises(NodeNotFoundError):
        ReplaceObservedLayerCommand(extracted).execute(graph)

    assert [node.name for node in graph.nodes()] == ["Old"]
    assert len(graph.edges()) == 1
