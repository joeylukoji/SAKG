"""Règles d'architecture vérifiables sur le graphe : couches et cycles d'imports."""

from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType, make_node_id
from sakg.graph import KnowledgeGraph
from sakg.validation import Finding, LayerDependencyRule, NoCycleRule, Severity

OBSERVED = Provenance(evidence_type=EvidenceType.OBSERVED, confidence=1.0, detected_by="TEST")


def _file(name: str, path: str, module: str) -> Node:
    return Node(
        id=make_node_id(NodeType.FILE, path, module),
        type=NodeType.FILE,
        name=name,
        properties={"module": module},
        provenance=OBSERVED,
    )


def _depends_on(source: Node, target: Node, *, type_only: bool = False) -> Edge:
    return Edge(
        source_id=source.id,
        target_id=target.id,
        relation=RelationType.DEPENDS_ON,
        properties={"type_only": type_only} if type_only else {},
        provenance=OBSERVED,
    )


class TestLayerDependencyRule:
    LAYERS = ("sakg.domain", "sakg.graph", "sakg.reverse")

    def test_an_outer_layer_depending_on_an_inner_one_is_allowed(self) -> None:
        graph = KnowledgeGraph()
        domain = _file("node.py", "src/sakg/domain/node.py", "sakg.domain.node")
        reverse = _file("pipeline.py", "src/sakg/reverse/pipeline.py", "sakg.reverse.pipeline")
        graph.add_node(domain)
        graph.add_node(reverse)
        graph.add_edge(_depends_on(reverse, domain))

        rule = LayerDependencyRule(id="layers", layers=self.LAYERS)
        assert rule.check(graph) == []

    def test_an_inner_layer_depending_on_an_outer_one_is_a_violation(self) -> None:
        graph = KnowledgeGraph()
        domain = _file("node.py", "src/sakg/domain/node.py", "sakg.domain.node")
        reverse = _file("pipeline.py", "src/sakg/reverse/pipeline.py", "sakg.reverse.pipeline")
        graph.add_node(domain)
        graph.add_node(reverse)
        edge = graph.add_edge(_depends_on(domain, reverse))

        rule = LayerDependencyRule(id="layers", layers=self.LAYERS, severity=Severity.ERROR)
        findings = rule.check(graph)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule_id == "layers"
        assert finding.severity is Severity.ERROR
        assert finding.node_ids == (domain.id, reverse.id)
        assert finding.edge_ids == (edge.id,)
        assert "sakg.domain" in finding.message and "sakg.reverse" in finding.message

    def test_same_layer_dependencies_are_allowed(self) -> None:
        graph = KnowledgeGraph()
        first = _file("a.py", "src/sakg/domain/a.py", "sakg.domain.a")
        second = _file("b.py", "src/sakg/domain/b.py", "sakg.domain.b")
        graph.add_node(first)
        graph.add_node(second)
        graph.add_edge(_depends_on(first, second))

        rule = LayerDependencyRule(id="layers", layers=self.LAYERS)
        assert rule.check(graph) == []

    def test_a_module_outside_any_known_layer_is_not_checked(self) -> None:
        graph = KnowledgeGraph()
        unknown = _file("main.py", "src/app/main.py", "app.main")
        domain = _file("node.py", "src/sakg/domain/node.py", "sakg.domain.node")
        graph.add_node(unknown)
        graph.add_node(domain)
        graph.add_edge(_depends_on(domain, unknown))

        rule = LayerDependencyRule(id="layers", layers=self.LAYERS)
        assert rule.check(graph) == []

    def test_non_depends_on_relations_are_ignored(self) -> None:
        """Une classe de ``reverse`` contenue par un fichier de ``domain`` n'est pas une dépendance."""
        graph = KnowledgeGraph()
        domain = _file("node.py", "src/sakg/domain/node.py", "sakg.domain.node")
        pipeline = Node(
            id=make_node_id(NodeType.CLASS, "src/sakg/reverse/pipeline.py", "Pipeline"),
            type=NodeType.CLASS,
            name="Pipeline",
            properties={"module": "sakg.reverse.pipeline"},
            provenance=OBSERVED,
        )
        graph.add_node(domain)
        graph.add_node(pipeline)
        graph.add_edge(
            Edge(source_id=domain.id, target_id=pipeline.id, relation=RelationType.CONTAINS, provenance=OBSERVED)
        )

        rule = LayerDependencyRule(id="layers", layers=self.LAYERS)
        assert rule.check(graph) == []

    def test_from_config_builds_an_equivalent_rule(self) -> None:
        rule = LayerDependencyRule.from_config(
            {"id": "layers", "layers": ["sakg.domain", "sakg.graph"], "severity": "warning"}
        )

        assert rule == LayerDependencyRule(id="layers", layers=("sakg.domain", "sakg.graph"), severity=Severity.WARNING)


class TestNoCycleRule:
    def test_a_cycle_of_runtime_imports_is_reported(self) -> None:
        graph = KnowledgeGraph()
        a = _file("a.py", "src/a.py", "a")
        b = _file("b.py", "src/b.py", "b")
        c = _file("c.py", "src/c.py", "c")
        for node in (a, b, c):
            graph.add_node(node)
        graph.add_edge(_depends_on(a, b))
        graph.add_edge(_depends_on(b, c))
        edge_c_a = graph.add_edge(_depends_on(c, a))

        findings = NoCycleRule().check(graph)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule_id == "no_cycle"
        assert set(finding.node_ids) == {a.id, b.id, c.id}
        assert edge_c_a.id in finding.edge_ids

    def test_a_type_only_import_does_not_close_a_cycle(self) -> None:
        graph = KnowledgeGraph()
        a = _file("a.py", "src/a.py", "a")
        b = _file("b.py", "src/b.py", "b")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_edge(_depends_on(a, b))
        graph.add_edge(_depends_on(b, a, type_only=True))

        assert NoCycleRule().check(graph) == []

    def test_no_cycle_is_silent(self) -> None:
        graph = KnowledgeGraph()
        a = _file("a.py", "src/a.py", "a")
        b = _file("b.py", "src/b.py", "b")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_edge(_depends_on(a, b))

        assert NoCycleRule().check(graph) == []

    def test_from_config_defaults_the_id(self) -> None:
        rule = NoCycleRule.from_config({})
        assert rule.id == "no_cycle"
        assert rule.relation is RelationType.DEPENDS_ON

    def test_default_severity_is_error(self) -> None:
        assert NoCycleRule().severity is Severity.ERROR


def test_finding_is_a_plain_dataclass() -> None:
    """La règle ne modifie jamais le graphe (règle 5 d'AGENTS.md) : un constat n'est pas un nœud."""
    finding = Finding(rule_id="r", severity=Severity.INFO, message="ok")
    assert finding.node_ids == ()
    assert finding.edge_ids == ()
