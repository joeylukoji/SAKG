from collections.abc import Callable

import pytest

from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType, make_node_id


@pytest.fixture
def observed() -> Provenance:
    return Provenance(evidence_type=EvidenceType.OBSERVED, confidence=1.0, detected_by="TEST")


@pytest.fixture
def make_node(observed: Provenance) -> Callable[..., Node]:
    def factory(node_type: NodeType, name: str, path: str = "src/app.py") -> Node:
        return Node(id=make_node_id(node_type, path, name), type=node_type, name=name, provenance=observed)

    return factory


@pytest.fixture
def make_edge(observed: Provenance) -> Callable[[Node, RelationType, Node], Edge]:
    def factory(source: Node, relation: RelationType, target: Node) -> Edge:
        return Edge(source_id=source.id, target_id=target.id, relation=relation, provenance=observed)

    return factory
