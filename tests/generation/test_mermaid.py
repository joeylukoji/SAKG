from collections.abc import Callable

import pytest

from sakg.domain import Edge, Node, NodeType, RelationType
from sakg.generation import DiagramView, MermaidGenerator, UnsupportedViewError, ViewProjection
from sakg.graph import KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def classes(make_node: MakeNode, make_edge: MakeEdge) -> tuple[KnowledgeGraph, dict[str, Node]]:
    nodes = {
        "base": make_node(NodeType.CLASS, "BaseService", "src/core/base.py"),
        "service": make_node(NodeType.CLASS, "PaymentService", "src/payment/service.py"),
        "pay": make_node(NodeType.METHOD, "pay", "src/payment/service.py"),
        "private": make_node(NodeType.METHOD, "_check", "src/payment/service.py"),
        "file": make_node(NodeType.FILE, "service.py", "src/payment/service.py"),
    }
    graph = KnowledgeGraph(version=7)
    for node in nodes.values():
        graph.add_node(node)
    graph.add_edge(make_edge(nodes["service"], RelationType.INHERITS, nodes["base"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.CONTAINS, nodes["pay"]))
    graph.add_edge(make_edge(nodes["service"], RelationType.CONTAINS, nodes["private"]))
    graph.add_edge(make_edge(nodes["file"], RelationType.CONTAINS, nodes["service"]))
    return graph, nodes


def test_projection_keeps_only_the_view_types(classes: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = classes

    projected = ViewProjection.for_view(DiagramView.CLASS).project(graph)

    assert {node.type for node in projected.nodes()} == {NodeType.CLASS, NodeType.METHOD}
    assert nodes["file"].id not in projected


def test_projection_restricted_to_a_focus(classes: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, nodes = classes

    projected = ViewProjection.for_view(DiagramView.CLASS).project(graph, focus=[nodes["base"].id])

    assert {node.id for node in projected.nodes()} >= {nodes["base"].id, nodes["service"].id}
    assert nodes["pay"].id in projected  # le contenu du voisin est conservé


def test_projection_of_an_unsupported_view() -> None:
    with pytest.raises(UnsupportedViewError):
        ViewProjection.for_view(DiagramView.ERD)


def test_class_diagram_source(classes: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, _ = classes

    diagram = MermaidGenerator().generate(graph, DiagramView.CLASS)

    assert diagram.source.startswith("classDiagram")
    assert "class PaymentService {" in diagram.source
    assert "+pay()" in diagram.source
    assert "PaymentService --|> BaseService" in diagram.source
    assert diagram.graph_version == 7


def test_private_methods_are_not_rendered(classes: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, _ = classes

    assert "_check" not in MermaidGenerator().generate(graph, DiagramView.CLASS).source


def test_homonym_classes_get_distinct_labels(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    first = make_node(NodeType.CLASS, "Config", "src/a.py").model_copy(update={"properties": {"module": "pkg.a"}})
    second = make_node(NodeType.CLASS, "Config", "src/b.py").model_copy(update={"properties": {"module": "pkg.b"}})
    graph.add_node(first)
    graph.add_node(second)

    source = MermaidGenerator().generate(graph, DiagramView.CLASS).source

    assert "class Config_pkg_a" in source
    assert "class Config_pkg_b" in source


def test_method_calls_become_dependencies_between_classes(make_node: MakeNode, make_edge: MakeEdge) -> None:
    """Le reverse produit des appels entre méthodes ; le diagramme les remonte aux classes."""
    graph = KnowledgeGraph()
    caller_class = graph.add_node(make_node(NodeType.CLASS, "Service", "src/service.py"))
    caller = graph.add_node(make_node(NodeType.METHOD, "handle", "src/service.py"))
    callee_class = graph.add_node(make_node(NodeType.CLASS, "Repository", "src/repo.py"))
    callee = graph.add_node(make_node(NodeType.METHOD, "save", "src/repo.py"))
    graph.add_edge(make_edge(caller_class, RelationType.CONTAINS, caller))
    graph.add_edge(make_edge(callee_class, RelationType.CONTAINS, callee))
    graph.add_edge(make_edge(caller, RelationType.CALLS, callee))

    source = MermaidGenerator().generate(graph, DiagramView.CLASS).source

    assert "Service ..> Repository" in source


def test_calls_inside_a_single_class_do_not_draw_a_self_arrow(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    owner = graph.add_node(make_node(NodeType.CLASS, "Service", "src/service.py"))
    first = graph.add_node(make_node(NodeType.METHOD, "handle", "src/service.py"))
    second = graph.add_node(make_node(NodeType.METHOD, "check", "src/service.py"))
    graph.add_edge(make_edge(owner, RelationType.CONTAINS, first))
    graph.add_edge(make_edge(owner, RelationType.CONTAINS, second))
    graph.add_edge(make_edge(first, RelationType.CALLS, second))

    assert "..>" not in MermaidGenerator().generate(graph, DiagramView.CLASS).source


def test_diagram_to_markdown(classes: tuple[KnowledgeGraph, dict[str, Node]]) -> None:
    graph, _ = classes

    markdown = MermaidGenerator().generate(graph, DiagramView.CLASS).to_markdown()

    assert markdown.startswith("```mermaid\n")
    assert markdown.endswith("```\n")


def test_use_case_view_renders_a_flowchart(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    actor = graph.add_node(make_node(NodeType.ACTOR, "Développeur", "docs/actors.md"))
    use_case = graph.add_node(make_node(NodeType.USE_CASE, "Interroger le graphe", "docs/uc.md"))
    graph.add_edge(make_edge(use_case, RelationType.USED_BY, actor))

    source = MermaidGenerator().generate(graph, DiagramView.USE_CASE).source

    assert source.startswith("flowchart LR")
    assert "used_by" in source
