from collections.abc import Callable

import pytest

from sakg.domain import (
    Edge,
    Node,
    NodeNotFoundError,
    NodeType,
    OntologySchema,
    OntologyViolationError,
    RelationType,
)


class _Nodes:
    def __init__(self, *nodes: Node) -> None:
        self._nodes = {node.id: node for node in nodes}

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)


@pytest.mark.parametrize(
    ("source", "relation", "target"),
    [
        (NodeType.REQUIREMENT, RelationType.REALIZED_BY, NodeType.USE_CASE),
        (NodeType.FILE, RelationType.CONTAINS, NodeType.CLASS),
        (NodeType.CLASS, RelationType.IMPLEMENTS, NodeType.INTERFACE),
        (NodeType.ENDPOINT, RelationType.IMPLEMENTED_BY, NodeType.METHOD),
        (NodeType.TEST, RelationType.TESTS, NodeType.ENDPOINT),
        (NodeType.PACKAGE, RelationType.BELONGS_TO, NodeType.LAYER),
    ],
)
def test_default_schema_allows_documented_triples(source: NodeType, relation: RelationType, target: NodeType) -> None:
    assert OntologySchema.default().is_allowed(source, relation, target)


@pytest.mark.parametrize(
    ("source", "relation", "target"),
    [
        (NodeType.USE_CASE, RelationType.REALIZED_BY, NodeType.REQUIREMENT),  # sens inversé
        (NodeType.METHOD, RelationType.CONTAINS, NodeType.CLASS),
        (NodeType.TABLE, RelationType.CALLS, NodeType.TABLE),
    ],
)
def test_default_schema_rejects_undocumented_triples(
    source: NodeType, relation: RelationType, target: NodeType
) -> None:
    assert not OntologySchema.default().is_allowed(source, relation, target)


def test_every_relation_type_is_used_by_default_schema() -> None:
    used = {relation for _, relation, _ in OntologySchema.default().triples}
    assert used == set(RelationType)


def test_validate_edge_accepts_allowed_relation(
    make_node: Callable[..., Node], make_edge: Callable[[Node, RelationType, Node], Edge]
) -> None:
    child, parent = make_node(NodeType.CLASS, "Child"), make_node(NodeType.CLASS, "Parent")

    OntologySchema.default().validate_edge(make_edge(child, RelationType.INHERITS, parent), _Nodes(child, parent))


def test_validate_edge_rejects_forbidden_relation(
    make_node: Callable[..., Node], make_edge: Callable[[Node, RelationType, Node], Edge]
) -> None:
    table, cls = make_node(NodeType.TABLE, "users"), make_node(NodeType.CLASS, "User")

    with pytest.raises(OntologyViolationError, match="table -\\[maps_to\\]-> class"):
        OntologySchema.default().validate_edge(make_edge(table, RelationType.MAPS_TO, cls), _Nodes(table, cls))


def test_validate_edge_requires_existing_endpoints(
    make_node: Callable[..., Node], make_edge: Callable[[Node, RelationType, Node], Edge]
) -> None:
    child, parent = make_node(NodeType.CLASS, "Child"), make_node(NodeType.CLASS, "Parent")

    with pytest.raises(NodeNotFoundError, match="Parent"):
        OntologySchema.default().validate_edge(make_edge(child, RelationType.INHERITS, parent), _Nodes(child))


def test_custom_schema() -> None:
    schema = OntologySchema([(NodeType.TABLE, RelationType.CONTAINS, NodeType.COLUMN)])

    assert schema.is_allowed(NodeType.TABLE, RelationType.CONTAINS, NodeType.COLUMN)
    assert not schema.is_allowed(NodeType.FILE, RelationType.CONTAINS, NodeType.CLASS)
