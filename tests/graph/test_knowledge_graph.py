from collections.abc import Callable

import pytest

from sakg.domain import (
    DuplicateEdgeError,
    DuplicateNodeError,
    Edge,
    EdgeNotFoundError,
    Node,
    NodeNotFoundError,
    NodeType,
    OntologyViolationError,
    RelationType,
)
from sakg.graph import KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def payment(make_node: MakeNode, make_edge: MakeEdge) -> tuple[KnowledgeGraph, dict[str, Node]]:
    """``service.py`` contient ``PaymentService`` (hérite de ``BaseService``) qui contient ``pay``."""
    nodes = {
        "file": make_node(NodeType.FILE, "service", "src/payment/service.py"),
        "service": make_node(NodeType.CLASS, "PaymentService", "src/payment/service.py"),
        "base": make_node(NodeType.CLASS, "BaseService", "src/core/base.py"),
        "pay": make_node(NodeType.METHOD, "PaymentService.pay", "src/payment/service.py"),
    }
    graph = KnowledgeGraph()
    for node in nodes.values():
        graph.add_node(node)
    graph.add_edge(make_edge(nodes["file"], RelationType.CONTAINS, nodes["service"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.INHERITS, nodes["base"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.CONTAINS, nodes["pay"]))
    return graph, nodes


def test_add_and_get_node(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    node = graph.add_node(make_node(NodeType.CLASS, "App"))

    assert graph.get_node(node.id) == node
    assert node.id in graph
    assert len(graph) == 1
    assert graph.get_node("class:missing::X") is None


def test_duplicate_node_is_rejected(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    graph.add_node(make_node(NodeType.CLASS, "App"))

    with pytest.raises(DuplicateNodeError):
        graph.add_node(make_node(NodeType.CLASS, "App"))


def test_duplicate_edge_is_rejected(payment: tuple[KnowledgeGraph, dict[str, Node]], make_edge: MakeEdge) -> None:
    graph, nodes = payment

    with pytest.raises(DuplicateEdgeError):
        graph.add_edge(make_edge(nodes["service"], RelationType.INHERITS, nodes["base"]))


def test_edge_to_missing_node_is_rejected(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    child = graph.add_node(make_node(NodeType.CLASS, "Child"))

    with pytest.raises(NodeNotFoundError):
        graph.add_edge(make_edge(child, RelationType.INHERITS, make_node(NodeType.CLASS, "Ghost")))
    assert graph.edges() == []


def test_edge_outside_ontology_is_rejected(
    payment: tuple[KnowledgeGraph, dict[str, Node]], make_edge: MakeEdge
) -> None:
    graph, nodes = payment

    with pytest.raises(OntologyViolationError):
        graph.add_edge(make_edge(nodes["pay"], RelationType.CONTAINS, nodes["service"]))
    assert len(graph.edges()) == 3


def test_in_and_out_edges(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment

    assert [e.relation for e in graph.out_edges(nodes["service"].id)] == [RelationType.INHERITS, RelationType.CONTAINS]
    assert [e.source_id for e in graph.in_edges(nodes["service"].id)] == [nodes["file"].id]
    with pytest.raises(NodeNotFoundError):
        graph.out_edges("class:missing::X")


def test_nodes_of_type(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment

    assert graph.nodes_of_type(NodeType.CLASS) == [nodes["service"], nodes["base"]]
    assert graph.nodes_of_type(NodeType.TABLE) == []


def test_remove_edge(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment
    edge = graph.out_edges(nodes["service"].id)[0]

    assert graph.remove_edge(edge.id) == edge
    assert graph.get_edge(edge.id) is None
    assert graph.in_edges(nodes["base"].id) == []
    with pytest.raises(EdgeNotFoundError):
        graph.remove_edge(edge.id)


def test_remove_node_removes_incident_edges(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment

    graph.remove_node(nodes["service"].id)

    assert nodes["service"].id not in graph
    assert graph.edges() == []
    assert graph.out_edges(nodes["file"].id) == []
    with pytest.raises(NodeNotFoundError):
        graph.remove_node(nodes["service"].id)


def test_remove_node_with_self_loop(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    node = graph.add_node(make_node(NodeType.CLASS, "Recursive"))
    graph.add_edge(make_edge(node, RelationType.DEPENDS_ON, node))

    graph.remove_node(node.id)

    assert len(graph) == 0
    assert graph.edges() == []


def test_subgraph_keeps_only_internal_edges(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment

    sub = graph.subgraph([nodes["service"].id, nodes["pay"].id])

    assert {n.id for n in sub.nodes()} == {nodes["service"].id, nodes["pay"].id}
    assert [e.relation for e in sub.edges()] == [RelationType.CONTAINS]
    assert len(graph) == 4  # l'original n'est pas modifié
    with pytest.raises(NodeNotFoundError):
        graph.subgraph(["class:missing::X"])


def test_to_networkx(payment: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = payment

    nx_graph = graph.to_networkx()

    assert nx_graph.number_of_nodes() == 4
    assert nx_graph.number_of_edges() == 3
    assert nx_graph.nodes[nodes["base"].id]["type"] == "class"
    edge_data = nx_graph.get_edge_data(nodes["service"].id, nodes["base"].id)
    assert [data["relation"] for data in edge_data.values()] == ["inherits"]
