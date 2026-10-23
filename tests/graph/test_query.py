from collections.abc import Callable

import pytest

from sakg.domain import Edge, Node, NodeNotFoundError, NodeType, RelationType
from sakg.graph import BoundedBfsStrategy, Direction, GraphQueryEngine, KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def layered(make_node: MakeNode, make_edge: MakeEdge) -> tuple[GraphQueryEngine, dict[str, Node]]:
    """``Cli`` dépend de ``Service``, qui dépend de ``Repository`` ; ``Service`` contient ``pay``."""
    nodes = {
        "cli": make_node(NodeType.CLASS, "Cli", "src/cli.py"),
        "service": make_node(NodeType.CLASS, "PaymentService", "src/service.py"),
        "repository": make_node(NodeType.CLASS, "Repository", "src/repository.py"),
        "pay": make_node(NodeType.METHOD, "pay", "src/service.py"),
        "table": make_node(NodeType.TABLE, "payments", "db/schema.sql"),
    }
    graph = KnowledgeGraph()
    for node in nodes.values():
        graph.add_node(node)
    graph.add_edge(make_edge(nodes["cli"], RelationType.DEPENDS_ON, nodes["service"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.DEPENDS_ON, nodes["repository"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.CONTAINS, nodes["pay"]))
    graph.add_edge(make_edge(nodes["repository"], RelationType.WRITES_TO, nodes["table"]))
    return GraphQueryEngine(graph), nodes


def test_find_ranks_exact_names_first(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    assert engine.find("PaymentService") == [nodes["service"]]
    assert nodes["service"] in engine.find("payment")
    assert engine.find("inexistant") == []


def test_find_filters_by_type_and_limit(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    assert engine.find("pay", types=[NodeType.TABLE]) == [nodes["table"]]
    assert len(engine.find("pay", limit=1)) == 1


def test_inventory_lists_every_node_of_a_type(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    assert engine.inventory([NodeType.TABLE]) == [nodes["table"]]
    assert len(engine.inventory([NodeType.CLASS, NodeType.METHOD])) == 4
    assert engine.inventory([NodeType.CONTAINER]) == []


def test_a_negative_limit_is_refused(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    """Une limite négative tronquerait la liste par la fin sans le dire."""
    engine, _ = layered

    with pytest.raises(ValueError, match="positif"):
        engine.inventory([NodeType.CLASS], limit=-1)
    with pytest.raises(ValueError, match="positif"):
        engine.find("Cli", limit=-1)


def test_dependencies_follow_dependency_relations(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    direct = engine.dependencies(nodes["cli"].id)
    transitive = engine.dependencies(nodes["cli"].id, depth=3)

    assert direct == [nodes["service"]]
    assert {node.id for node in transitive} == {nodes["service"].id, nodes["repository"].id, nodes["table"].id}


def test_dependencies_ignore_containment(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    """``contains`` est une hiérarchie, pas une dépendance."""
    engine, nodes = layered

    assert nodes["pay"] not in engine.dependencies(nodes["service"].id, depth=3)


def test_dependents_walk_the_other_way(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    assert engine.dependents(nodes["repository"].id) == [nodes["service"]]
    assert {node.id for node in engine.dependents(nodes["repository"].id, depth=2)} == {
        nodes["service"].id,
        nodes["cli"].id,
    }


def test_path_returns_the_shortest_edge_sequence(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    path = engine.path(nodes["cli"].id, nodes["table"].id)

    assert [edge.relation for edge in path] == [
        RelationType.DEPENDS_ON,
        RelationType.DEPENDS_ON,
        RelationType.WRITES_TO,
    ]
    assert path[0].source_id == nodes["cli"].id
    assert path[-1].target_id == nodes["table"].id


def test_path_without_route_or_to_itself(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    assert engine.path(nodes["table"].id, nodes["cli"].id) == []
    assert engine.path(nodes["cli"].id, nodes["cli"].id) == []
    with pytest.raises(NodeNotFoundError):
        engine.path("class:missing::X", nodes["cli"].id)


def test_bounded_bfs_stops_at_max_depth(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    result = engine.traverse([nodes["cli"].id], BoundedBfsStrategy(max_depth=1, direction=Direction.OUT))

    assert result.visited == {nodes["cli"].id: 0, nodes["service"].id: 1}
    assert result.scores[nodes["cli"].id] == 1.0
    assert result.scores[nodes["service"].id] == pytest.approx(0.5)


def test_bounded_bfs_depth_zero_returns_only_seeds(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    result = engine.traverse([nodes["cli"].id], BoundedBfsStrategy(max_depth=0))

    assert list(result.visited) == [nodes["cli"].id]


def test_bounded_bfs_filters_relations(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, nodes = layered

    result = engine.traverse(
        [nodes["service"].id],
        BoundedBfsStrategy(max_depth=2, relations=frozenset({RelationType.CONTAINS}), direction=Direction.OUT),
    )

    assert set(result.visited) == {nodes["service"].id, nodes["pay"].id}


def test_bounded_bfs_handles_cycles(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    first = graph.add_node(make_node(NodeType.CLASS, "A", "src/a.py"))
    second = graph.add_node(make_node(NodeType.CLASS, "B", "src/b.py"))
    graph.add_edge(make_edge(first, RelationType.DEPENDS_ON, second))
    graph.add_edge(make_edge(second, RelationType.DEPENDS_ON, first))

    result = BoundedBfsStrategy(max_depth=5, direction=Direction.OUT).traverse(graph, [first.id])

    assert result.visited == {first.id: 0, second.id: 1}


def test_traversal_rejects_unknown_seed(layered: tuple[GraphQueryEngine, dict[str, Node]]) -> None:
    engine, _ = layered

    with pytest.raises(NodeNotFoundError):
        engine.traverse(["class:missing::X"], BoundedBfsStrategy())
