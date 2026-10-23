import pytest
from pydantic import ValidationError

from sakg.domain import Edge, Node, NodeType, Provenance, RelationType, make_edge_id, make_node_id


def test_make_node_id_follows_convention() -> None:
    assert make_node_id(NodeType.CLASS, "src/payment/service.py", "PaymentService") == (
        "class:src/payment/service.py::PaymentService"
    )


def test_make_node_id_without_a_file() -> None:
    """Une exigence ou une technologie n'appartient à aucun fichier."""
    assert make_node_id(NodeType.REQUIREMENT, "", "REQ-001") == "requirement:REQ-001"
    assert make_node_id(NodeType.TECHNOLOGY, "", "postgres:16") == "technology:postgres:16"


def test_make_node_id_normalizes_windows_paths() -> None:
    assert make_node_id(NodeType.FILE, "src\\payment\\service.py", "service") == "file:src/payment/service.py::service"


def test_node_id_must_start_with_its_type(observed: Provenance) -> None:
    with pytest.raises(ValidationError, match="doit commencer par 'class:'"):
        Node(id="method:src/app.py::run", type=NodeType.CLASS, name="run", provenance=observed)


def test_node_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        Node(id="class:src/app.py::App", type=NodeType.CLASS, name="App")  # type: ignore[call-arg]


def test_qualified_name(observed: Provenance) -> None:
    method = Node(id="method:src/app.py::App.run", type=NodeType.METHOD, name="run", provenance=observed)
    requirement = Node(id="requirement:REQ-001", type=NodeType.REQUIREMENT, name="REQ-001", provenance=observed)

    assert method.qualified_name() == "App.run"
    assert requirement.qualified_name() == "REQ-001"


def test_node_rejects_unknown_fields(observed: Provenance) -> None:
    with pytest.raises(ValidationError):
        Node(id="class:a::A", type=NodeType.CLASS, name="A", provenance=observed, color="red")  # type: ignore[call-arg]


def test_edge_id_is_derived_when_missing(observed: Provenance) -> None:
    edge = Edge(source_id="class:a::A", target_id="class:b::B", relation=RelationType.INHERITS, provenance=observed)

    assert edge.id == make_edge_id("class:a::A", RelationType.INHERITS, "class:b::B")
    assert edge.id == "class:a::A-[inherits]->class:b::B"


def test_edge_keeps_explicit_id(observed: Provenance) -> None:
    edge = Edge(id="e1", source_id="a", target_id="b", relation=RelationType.CALLS, provenance=observed)

    assert edge.id == "e1"


def test_edge_with_invalid_relation_is_rejected(observed: Provenance) -> None:
    with pytest.raises(ValidationError):
        Edge(source_id="a", target_id="b", relation="unknown", provenance=observed)
