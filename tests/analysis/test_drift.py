"""Dérive entre le graphe enregistré et le code actuel : distance de Jaccard sur les relations."""

from collections.abc import Callable

from sakg.analysis import DriftDetector
from sakg.domain import Edge, Node, NodeType, RelationType
from sakg.graph import KnowledgeGraph

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


def _graph(nodes: list[Node], edges: list[Edge] | None = None) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for node in nodes:
        graph.add_node(node)
    for edge in edges or []:
        graph.add_edge(edge)
    return graph


def test_identical_graphs_have_no_drift(make_node: MakeNode, make_edge: MakeEdge) -> None:
    cli, service = make_node(NodeType.CLASS, "Cli"), make_node(NodeType.CLASS, "Service")
    edge = make_edge(cli, RelationType.DEPENDS_ON, service)
    graph = _graph([cli, service], [edge])

    report = DriftDetector().detect(graph, graph)

    assert report.drift_score == 0.0
    assert not report.has_drifted()
    assert report.missing_in_code == ()
    assert report.undocumented_in_code == ()
    assert "décrit encore le code" in report.to_markdown()


def test_a_relation_undocumented_in_code_is_reported(make_node: MakeNode, make_edge: MakeEdge) -> None:
    """Le code dépend maintenant de quelque chose que le graphe enregistré ignore."""
    cli, service = make_node(NodeType.CLASS, "Cli"), make_node(NodeType.CLASS, "Service")
    intended = _graph([cli, service])
    new_edge = make_edge(cli, RelationType.DEPENDS_ON, service)
    actual = _graph([cli, service], [new_edge])

    report = DriftDetector().detect(intended, actual)

    assert report.has_drifted()
    assert report.drift_score == 1.0
    assert [edge.id for edge in report.undocumented_in_code] == [new_edge.id]
    assert report.missing_in_code == ()


def test_a_relation_missing_in_code_is_reported(make_node: MakeNode, make_edge: MakeEdge) -> None:
    """Le graphe enregistré affirme une dépendance que le code n'a plus."""
    cli, service = make_node(NodeType.CLASS, "Cli"), make_node(NodeType.CLASS, "Service")
    old_edge = make_edge(cli, RelationType.DEPENDS_ON, service)
    intended = _graph([cli, service], [old_edge])
    actual = _graph([cli, service])

    report = DriftDetector().detect(intended, actual)

    assert report.has_drifted()
    assert report.drift_score == 1.0
    assert [edge.id for edge in report.missing_in_code] == [old_edge.id]
    assert report.undocumented_in_code == ()


def test_drift_score_is_the_jaccard_distance(make_node: MakeNode, make_edge: MakeEdge) -> None:
    cli, service, repository = (make_node(NodeType.CLASS, name) for name in ("Cli", "Service", "Repository"))
    kept = make_edge(cli, RelationType.DEPENDS_ON, service)
    removed = make_edge(service, RelationType.DEPENDS_ON, repository)
    added = make_edge(cli, RelationType.DEPENDS_ON, repository)
    intended = _graph([cli, service, repository], [kept, removed])
    actual = _graph([cli, service, repository], [kept, added])

    report = DriftDetector().detect(intended, actual)

    # 1 relation commune, 3 au total (1 gardée + 1 disparue + 1 apparue) : 1 − 1/3.
    assert report.drift_score == 1 - 1 / 3


def test_to_markdown_lists_what_drifted(make_node: MakeNode, make_edge: MakeEdge) -> None:
    cli, service = make_node(NodeType.CLASS, "Cli"), make_node(NodeType.CLASS, "Service")
    intended = _graph([cli, service])
    actual = _graph([cli, service], [make_edge(cli, RelationType.DEPENDS_ON, service)])

    report = DriftDetector().detect(intended, actual)
    markdown = report.to_markdown()

    assert markdown.startswith("# Dérive architecture ↔ code :")
    assert "Apparues dans le code" in markdown
    assert cli.id in markdown and service.id in markdown
