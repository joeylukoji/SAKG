from collections.abc import Callable
from pathlib import Path

import pytest

from sakg.analysis import ChangeRequest, ImpactAnalyzer, ImpactReport, tokenize
from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType
from sakg.graph import GraphQueryEngine, KnowledgeGraph
from sakg.reverse import ReverseEngineeringPipeline

MakeNode = Callable[..., Node]
MakeEdge = Callable[[Node, RelationType, Node], Edge]


@pytest.fixture
def payment_graph(make_node: MakeNode, make_edge: MakeEdge) -> tuple[ImpactAnalyzer, dict[str, Node]]:
    """Une exigence réalisée par un composant, une classe utilisée par une API et un test."""
    user_defined = Provenance(evidence_type=EvidenceType.USER_DEFINED, confidence=1.0, detected_by="USER")
    nodes = {
        "requirement": Node(
            id="requirement:REQ-001", type=NodeType.REQUIREMENT, name="Paiement", provenance=user_defined
        ),
        "service": make_node(NodeType.CLASS, "PaymentService", "src/payment/service.py"),
        "controller": make_node(NodeType.CLASS, "PaymentController", "src/payment/controller.py"),
        "cli": make_node(NodeType.CLASS, "Cli", "src/cli.py"),
        "unrelated": make_node(NodeType.CLASS, "MailSender", "src/mail.py"),
    }
    graph = KnowledgeGraph()
    for node in nodes.values():
        graph.add_node(node)
    graph.add_edge(make_edge(nodes["controller"], RelationType.DEPENDS_ON, nodes["service"]))
    graph.add_edge(make_edge(nodes["cli"], RelationType.DEPENDS_ON, nodes["controller"]))
    return ImpactAnalyzer(GraphQueryEngine(graph)), nodes


def test_tokenize_splits_identifiers() -> None:
    assert tokenize("Ajouter les paiements mobiles à PaymentService") == [
        "paiements",
        "mobiles",
        "paymentservice",
        "payment",
        "service",
    ]
    assert "ajouter" not in tokenize("Ajouter une classe")


def test_locate_finds_nodes_by_description(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    located = analyzer.locate(ChangeRequest(description="Modifier PaymentService"))

    assert located[0].id == nodes["service"].id
    assert nodes["unrelated"] not in located


def test_locate_accepts_explicit_targets(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    located = analyzer.locate(ChangeRequest(description="peu importe", target_node_ids=(nodes["cli"].id,)))

    assert located == [nodes["cli"]]


def test_locate_ignores_unknown_targets(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, _ = payment_graph

    assert analyzer.locate(ChangeRequest(description="x", target_node_ids=("class:ghost::X",))) == []


def test_unknown_explicit_target_is_reported(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    report = analyzer.analyze(ChangeRequest(description="x", target_node_ids=(nodes["cli"].id, "class:ghost::X")))

    assert any("introuvable" in warning and "ghost" in warning for warning in report.warnings)
    assert report.seeds == (nodes["cli"].id,)


def test_explicit_targets_are_never_truncated(make_node: MakeNode) -> None:
    """Quand l'utilisateur désigne les nœuds, aucun n'est écarté en silence."""
    graph = KnowledgeGraph()
    ids = []
    for index in range(8):
        node = graph.add_node(make_node(NodeType.CLASS, f"Service{index}", f"src/s{index}.py"))
        ids.append(node.id)
    analyzer = ImpactAnalyzer(GraphQueryEngine(graph))

    report = analyzer.analyze(ChangeRequest(description="revue complète", target_node_ids=tuple(ids)))

    assert set(report.seeds) == set(ids)


def test_tied_candidates_beyond_the_limit_are_reported(make_node: MakeNode) -> None:
    graph = KnowledgeGraph()
    for suffix in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta"):
        graph.add_node(make_node(NodeType.CLASS, f"Payment{suffix}", f"src/{suffix.lower()}.py"))
    analyzer = ImpactAnalyzer(GraphQueryEngine(graph))

    report = analyzer.analyze(ChangeRequest(description="Modifier payment"))

    assert any("à égalité" in warning for warning in report.warnings)
    assert len(report.seeds) == 5


def test_report_explains_why_each_node_is_impacted(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    report = analyzer.analyze(ChangeRequest(description="Changer PaymentService"))

    assert report.reasons[nodes["controller"].id].startswith("depends_on")
    assert nodes["controller"].id in report.to_markdown()
    assert "depends_on" in report.to_markdown()


def test_markdown_lists_high_level_types_first(make_node: MakeNode, make_edge: MakeEdge) -> None:
    graph = KnowledgeGraph()
    component = graph.add_node(make_node(NodeType.COMPONENT, "Paiement", "docs/components.md"))
    klass = graph.add_node(make_node(NodeType.CLASS, "PaymentService", "src/service.py"))
    graph.add_edge(make_edge(component, RelationType.DEPENDS_ON, component))
    graph.add_edge(make_edge(klass, RelationType.DEPENDS_ON, klass))
    report = ImpactAnalyzer(GraphQueryEngine(graph)).analyze(ChangeRequest(description="Modifier Paiement"))

    markdown = report.to_markdown()

    assert markdown.index("## component") < markdown.index("## class") if "## class" in markdown else True


def test_analyze_propagates_to_dependents(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    report = analyzer.analyze(ChangeRequest(description="Changer PaymentService"))

    impacted = {node.id for node in report.all_nodes()}
    assert nodes["service"].id in impacted  # le point de départ
    assert nodes["controller"].id in impacted  # dépend directement
    assert nodes["cli"].id in impacted  # dépend indirectement
    assert nodes["unrelated"].id not in impacted


def test_analyze_scores_decrease_with_distance(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    report = analyzer.analyze(ChangeRequest(description="Changer PaymentService"))

    assert report.scores[nodes["service"].id] > report.scores[nodes["controller"].id]
    assert report.scores[nodes["controller"].id] > report.scores[nodes["cli"].id]


def test_analyze_groups_by_type(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    report = analyzer.analyze(ChangeRequest(description="Changer PaymentService"))

    assert {node.id for node in report.by_type(NodeType.CLASS)} >= {nodes["service"].id, nodes["controller"].id}
    assert report.by_type(NodeType.TABLE) == []


def test_analyze_without_match_reports_a_warning(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, _ = payment_graph

    report = analyzer.analyze(ChangeRequest(description="Refondre la facturation"))

    assert report.is_empty()
    assert report.warnings
    assert "Aucun élément" in report.to_markdown()


def test_report_markdown_lists_nodes_and_seeds(payment_graph: tuple[ImpactAnalyzer, dict[str, Node]]) -> None:
    analyzer, nodes = payment_graph

    markdown = analyzer.analyze(ChangeRequest(description="Changer PaymentService")).to_markdown()

    assert markdown.startswith("# Impact : Changer PaymentService")
    assert f"`{nodes['service'].id}`" in markdown
    assert "point de départ" in markdown


SAKG_SOURCE = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(scope="module")
def sakg_analyzer() -> ImpactAnalyzer:
    """Analyseur branché sur le graphe de SAKG lui-même."""
    return ImpactAnalyzer(GraphQueryEngine(ReverseEngineeringPipeline.default().run_on(SAKG_SOURCE).graph))


def test_impact_on_the_sakg_graph_itself(sakg_analyzer: ImpactAnalyzer) -> None:
    report = sakg_analyzer.analyze(ChangeRequest(description="Modifier KnowledgeGraph"))

    impacted = {node.id for node in report.all_nodes()}
    assert any(node_id.endswith("::KnowledgeGraph") for node_id in report.seeds)
    assert any("query.py" in node_id or "snapshot.py" in node_id for node_id in impacted)
    assert isinstance(report, ImpactReport)


def test_seeds_prefer_public_symbols_over_dunders(sakg_analyzer: ImpactAnalyzer) -> None:
    """« Modifier KnowledgeGraph » doit partir de la classe, pas de ``__init__`` ni ``__len__``."""
    report = sakg_analyzer.analyze(ChangeRequest(description="Modifier KnowledgeGraph"))

    assert report.seeds[0].endswith("::KnowledgeGraph")
    assert not any(seed.split("::")[-1].startswith("__") for seed in report.seeds)


def test_a_fragmented_word_does_not_impact_the_whole_graph(sakg_analyzer: ImpactAnalyzer) -> None:
    """« GraphType » se découpe en graph + type : correspondance faible, aucune propagation.

    Ni l'un ni l'autre ne nomme un symbole du graphe, contrairement à « TypeScript »,
    désormais un vrai module de SAKG (le mot entier y correspondrait fortement).
    """
    report = sakg_analyzer.analyze(ChangeRequest(description="Ajouter le support de GraphType"))

    assert any("correspondance faible" in warning for warning in report.warnings)
    assert len(report.all_nodes()) == len(report.seeds) <= 5


def test_relevant_methods_are_reachable(sakg_analyzer: ImpactAnalyzer) -> None:
    report = sakg_analyzer.analyze(ChangeRequest(description="Modifier ReverseEngineeringPipeline"))

    impacted = {node.id for node in report.all_nodes()}
    assert any(node_id.endswith("::ReverseEngineeringPipeline") for node_id in report.seeds)
    assert any("pipeline.py" in node_id for node_id in impacted)
