from collections.abc import Callable
from pathlib import Path

import pytest

from sakg.application import (
    AddEdgeCommand,
    AddNodeCommand,
    CommandBus,
    DomainEvent,
    EventBus,
    GraphChanged,
    NothingToUndoError,
    ValidationCompleted,
)
from sakg.domain import DuplicateNodeError, Edge, EvidenceType, Node, NodeType, Provenance, RelationType
from sakg.graph import KnowledgeGraph
from sakg.infrastructure import JsonGraphRepository

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def bus(tmp_path: Path) -> CommandBus:
    return CommandBus(KnowledgeGraph(), JsonGraphRepository(tmp_path), EventBus())


def test_execute_versions_and_persists(bus: CommandBus, make_node: MakeNode, tmp_path: Path) -> None:
    snapshot = bus.execute(AddNodeCommand(make_node(NodeType.CLASS, "App")))

    assert snapshot.version == 1
    assert snapshot.label == "AddNodeCommand"
    assert len(JsonGraphRepository(tmp_path).load()) == 1


def test_undo_last_restores_previous_state(bus: CommandBus, make_node: MakeNode, make_edge: MakeEdge) -> None:
    parent = make_node(NodeType.CLASS, "Parent")
    child = make_node(NodeType.CLASS, "Child")
    bus.execute(AddNodeCommand(parent))
    bus.execute(AddNodeCommand(child))
    bus.execute(AddEdgeCommand(make_edge(child, RelationType.INHERITS, parent)))

    snapshot = bus.undo_last()

    assert snapshot.version == 4  # chaque annulation crée elle aussi une version
    assert bus.graph.edges() == []
    assert len(bus.graph) == 2
    assert [type(command).__name__ for command in bus.history] == ["AddNodeCommand", "AddNodeCommand"]


def test_undo_without_history(bus: CommandBus) -> None:
    with pytest.raises(NothingToUndoError):
        bus.undo_last()


def test_failed_command_does_not_create_a_version(bus: CommandBus, make_node: MakeNode) -> None:
    node = make_node(NodeType.CLASS, "App")
    bus.execute(AddNodeCommand(node))

    with pytest.raises(DuplicateNodeError):
        bus.execute(AddNodeCommand(node))

    assert bus.graph.version == 1
    assert len(bus.history) == 1


def test_graph_changed_is_published(tmp_path: Path, make_node: MakeNode) -> None:
    events = EventBus()
    received: list[DomainEvent] = []
    events.subscribe(GraphChanged, received.append)
    bus = CommandBus(KnowledgeGraph(), JsonGraphRepository(tmp_path), events)

    bus.execute(AddNodeCommand(make_node(NodeType.CLASS, "App")))

    assert len(received) == 1
    assert isinstance(received[0], GraphChanged)
    assert (received[0].version, received[0].command) == (1, "AddNodeCommand")


def test_bus_without_event_bus_still_works(tmp_path: Path, make_node: MakeNode) -> None:
    bus = CommandBus(KnowledgeGraph(), JsonGraphRepository(tmp_path))

    assert bus.execute(AddNodeCommand(make_node(NodeType.CLASS, "App"))).version == 1


def test_commit_sha_is_recorded(tmp_path: Path, make_node: MakeNode) -> None:
    bus = CommandBus(KnowledgeGraph(), JsonGraphRepository(tmp_path), commit_sha="a1b2c3d")

    assert bus.execute(AddNodeCommand(make_node(NodeType.CLASS, "App"))).commit_sha == "a1b2c3d"


def test_user_defined_node_survives_reverse(tmp_path: Path, make_node: MakeNode) -> None:
    """Un reverse ne doit pas effacer les exigences saisies par l'utilisateur."""
    from sakg.application import ReplaceObservedLayerCommand

    graph = KnowledgeGraph()
    requirement = Node(
        id="requirement:REQ-001",
        type=NodeType.REQUIREMENT,
        name="REQ-001",
        provenance=Provenance(evidence_type=EvidenceType.USER_DEFINED, confidence=1.0, detected_by="USER"),
    )
    graph.add_node(requirement)
    graph.add_node(make_node(NodeType.CLASS, "Obsolete"))
    bus = CommandBus(graph, JsonGraphRepository(tmp_path))

    extracted = KnowledgeGraph()
    extracted.add_node(make_node(NodeType.CLASS, "Fresh"))
    bus.execute(ReplaceObservedLayerCommand(extracted))

    assert {node.name for node in bus.graph.nodes()} == {"REQ-001", "Fresh"}


def test_failing_handler_breaks_neither_the_command_nor_the_other_handlers(tmp_path: Path, make_node: MakeNode) -> None:
    events = EventBus()
    received: list[DomainEvent] = []

    def explode(event: DomainEvent) -> None:
        raise RuntimeError("régénération de diagramme en échec")

    events.subscribe(GraphChanged, explode)
    events.subscribe(GraphChanged, received.append)
    bus = CommandBus(KnowledgeGraph(), JsonGraphRepository(tmp_path), events)

    snapshot = bus.execute(AddNodeCommand(make_node(NodeType.CLASS, "App")))

    assert snapshot.version == 1
    assert len(received) == 1


def test_event_bus_dispatches_by_type() -> None:
    events = EventBus()
    graph_changes: list[DomainEvent] = []
    all_events: list[DomainEvent] = []
    events.subscribe(GraphChanged, graph_changes.append)
    events.subscribe(DomainEvent, all_events.append)

    events.publish(GraphChanged(version=1, command="X"))
    events.publish(ValidationCompleted(passed=True))

    assert len(graph_changes) == 1
    assert len(all_events) == 2
