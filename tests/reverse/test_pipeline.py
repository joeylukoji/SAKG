from pathlib import Path

from sakg.application import CommandBus, ReplaceObservedLayerCommand
from sakg.domain import Edge, EvidenceType, Node, NodeType, Provenance, RelationType
from sakg.graph import KnowledgeGraph
from sakg.infrastructure import JsonGraphRepository
from sakg.reverse import (
    ApiExtractor,
    CodeStructureExtractor,
    DatabaseExtractor,
    ExtractionResult,
    GraphBuilder,
    InfrastructureExtractor,
    ParserRegistry,
    ProjectContext,
    ProjectScanner,
    PythonAstParser,
    ReverseEngineeringPipeline,
)


def test_pipeline_builds_a_valid_graph(sample_project: Path) -> None:
    graph = ReverseEngineeringPipeline.default().run_on(sample_project).graph

    assert {node.name for node in graph.nodes_of_type(NodeType.CLASS)} == {"PaymentService", "BaseService"}
    assert len(graph.nodes_of_type(NodeType.FILE)) == 4
    assert any(edge.relation == RelationType.INHERITS for edge in graph.edges())


def test_pipeline_runs_extractors_in_order(sample_project: Path) -> None:
    calls: list[str] = []

    class _Recorder:
        name = "recorder"
        order = 5

        def extract(self, context: ProjectContext, registry: object) -> ExtractionResult:
            calls.append(self.name)
            return ExtractionResult()

    pipeline = ReverseEngineeringPipeline.default()
    pipeline.add_extractor(_Recorder())

    pipeline.run(ProjectScanner().scan(sample_project))

    assert [extractor.name for extractor in pipeline.extractors] == [
        "recorder",
        CodeStructureExtractor().name,
        ApiExtractor().name,
        DatabaseExtractor().name,
        InfrastructureExtractor().name,
    ]
    assert calls == ["recorder"]


def test_pipeline_returns_its_warnings_instead_of_keeping_them(sample_project: Path) -> None:
    """Un même pipeline doit pouvoir analyser deux projets sans mélanger leurs avertissements."""
    (sample_project / "core" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    pipeline = ReverseEngineeringPipeline.default()

    with_warning = pipeline.run_on(sample_project)
    other = pipeline.run_on(sample_project / "payment")

    assert any("syntaxe invalide" in warning for warning in with_warning.warnings)
    assert other.warnings == ()


def test_parsing_is_shared_between_extractors(sample_project: Path) -> None:
    """Le registre mémorise les fichiers analysés : deux extracteurs ne parsent pas deux fois."""
    registry = ParserRegistry([PythonAstParser()])
    file = ProjectScanner().scan(sample_project).files[0]

    assert registry.parse(file) is registry.parse(file)
    registry.clear_cache()
    assert registry.parse(file) is not None


def test_an_unreadable_file_is_reported_once(sample_project: Path) -> None:
    """Deux extracteurs butent sur le même fichier : l'utilisateur ne doit le lire qu'une fois."""
    (sample_project / "core" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    warnings = ReverseEngineeringPipeline.default().run_on(sample_project).warnings

    assert len([warning for warning in warnings if "broken.py" in warning]) == 1


def test_builder_drops_edges_with_missing_endpoints() -> None:
    provenance = Provenance(evidence_type=EvidenceType.OBSERVED, confidence=1.0, detected_by="TEST")
    known = Node(id="class:a.py::A", type=NodeType.CLASS, name="A", provenance=provenance)
    result = ExtractionResult(
        nodes=[known],
        edges=[
            Edge(
                source_id=known.id,
                target_id="class:ghost.py::Ghost",
                relation=RelationType.INHERITS,
                provenance=provenance,
            )
        ],
    )

    builder = GraphBuilder().add(result)
    graph = builder.build()

    assert graph.edges() == []
    assert any("extrémité absente" in warning for warning in builder.warnings)


def test_builder_deduplicates_nodes() -> None:
    provenance = Provenance(evidence_type=EvidenceType.OBSERVED, confidence=1.0, detected_by="TEST")
    node = Node(id="class:a.py::A", type=NodeType.CLASS, name="A", provenance=provenance)

    graph = GraphBuilder().add(ExtractionResult(nodes=[node])).add(ExtractionResult(nodes=[node])).build()

    assert len(graph) == 1


def test_merge_into_preserves_existing_nodes(sample_project: Path) -> None:
    existing = KnowledgeGraph()
    requirement = existing.add_node(
        Node(
            id="requirement:REQ-001",
            type=NodeType.REQUIREMENT,
            name="REQ-001",
            provenance=Provenance(evidence_type=EvidenceType.USER_DEFINED, confidence=1.0, detected_by="USER"),
        )
    )
    context = ProjectScanner().scan(sample_project)
    registry = ParserRegistry([PythonAstParser()])
    builder = GraphBuilder().add(CodeStructureExtractor().extract(context, registry))

    merged = builder.merge_into(existing)

    assert requirement.id in merged
    assert len(merged) > 1


def test_reverse_is_persisted_through_the_command_bus(sample_project: Path, tmp_path: Path) -> None:
    """Chaîne complète du sprint 2 + 3 : reverse → commande → snapshot sur disque."""
    repository = JsonGraphRepository(tmp_path / "project")
    bus = CommandBus(KnowledgeGraph(), repository)
    extracted = ReverseEngineeringPipeline.default().run_on(sample_project).graph

    snapshot = bus.execute(ReplaceObservedLayerCommand(extracted))

    reloaded = repository.load()
    assert snapshot.version == 1
    assert len(reloaded) == len(extracted)
    assert {node.id for node in reloaded.nodes()} == {node.id for node in extracted.nodes()}


def test_second_reverse_replaces_the_observed_layer(sample_project: Path, tmp_path: Path) -> None:
    repository = JsonGraphRepository(tmp_path / "project")
    bus = CommandBus(KnowledgeGraph(), repository)
    bus.execute(ReplaceObservedLayerCommand(ReverseEngineeringPipeline.default().run_on(sample_project).graph))

    (sample_project / "payment" / "service.py").write_text(
        "class PaymentService:\n    def pay(self):\n        return True\n", encoding="utf-8"
    )
    bus.execute(ReplaceObservedLayerCommand(ReverseEngineeringPipeline.default().run_on(sample_project).graph))

    assert all(node.name != "refund" for node in bus.graph.nodes())
    assert bus.graph.version == 2
