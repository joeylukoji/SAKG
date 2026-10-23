from pathlib import Path

import pytest

from sakg.domain import EvidenceType, NodeType, RelationType
from sakg.reverse import CodeStructureExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.imports import resolve_import
from sakg.reverse.models import ExtractionResult, ImportRef

from .conftest import BROKEN


@pytest.fixture
def extraction(sample_project: Path) -> ExtractionResult:
    context = ProjectScanner().scan(sample_project, commit_sha="abc123")
    return CodeStructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))


def _edges(extraction: ExtractionResult, relation: RelationType) -> set[tuple[str, str]]:
    return {(edge.source_id, edge.target_id) for edge in extraction.edges if edge.relation == relation}


@pytest.mark.parametrize(
    ("module_name", "is_package", "import_ref", "expected"),
    [
        ("sakg.graph.snapshot", False, ImportRef(module="sakg.domain"), "sakg.domain"),
        ("sakg.domain", True, ImportRef(module="node", level=1), "sakg.domain.node"),
        ("sakg.domain.node", False, ImportRef(module="errors", level=1), "sakg.domain.errors"),
        ("sakg.graph.snapshot", False, ImportRef(module="domain", level=2), "sakg.domain"),
        ("sakg.domain", True, ImportRef(module="", level=1, names=("node",)), "sakg.domain"),
    ],
)
def test_resolve_import(module_name: str, is_package: bool, import_ref: ImportRef, expected: str) -> None:
    assert resolve_import(import_ref, module_name, is_package=is_package) == expected


def test_resolve_ecma_relative_import() -> None:
    assert (
        resolve_import(
            ImportRef(module="./base"),
            "app.service",
            is_package=False,
            language="typescript",
        )
        == "app.base"
    )
    assert (
        resolve_import(
            ImportRef(module="../core/base"),
            "app.service",
            is_package=False,
            language="typescript",
        )
        == "core.base"
    )


def test_nodes_cover_files_classes_methods_and_functions(extraction: ExtractionResult) -> None:
    by_type: dict[NodeType, set[str]] = {}
    for node in extraction.nodes:
        by_type.setdefault(node.type, set()).add(node.name)

    assert by_type[NodeType.FILE] == {"service.py", "__init__.py", "base.py", "helpers.py"}
    assert by_type[NodeType.CLASS] == {"PaymentService", "BaseService"}
    assert by_type[NodeType.METHOD] == {"pay", "refund", "charge"}
    assert by_type[NodeType.FUNCTION] == {"build_service", "audit"}


def test_nested_function_is_not_extracted(extraction: ExtractionResult) -> None:
    assert all(node.name != "inner" for node in extraction.nodes)


def test_node_ids_follow_the_convention(extraction: ExtractionResult) -> None:
    ids = {node.id for node in extraction.nodes}

    assert "class:payment/service.py::PaymentService" in ids
    assert "method:payment/service.py::PaymentService.pay" in ids
    assert "file:core/base.py::core.base" in ids


def test_provenance_is_observed_with_evidence(extraction: ExtractionResult) -> None:
    node = next(node for node in extraction.nodes if node.id == "class:payment/service.py::PaymentService")

    assert node.provenance.evidence_type == EvidenceType.OBSERVED
    assert node.provenance.confidence == 1.0
    assert node.provenance.detected_by == "PYTHON_AST_CLASS_DEF"
    assert node.provenance.evidence is not None
    assert node.provenance.evidence.file == "payment/service.py"
    assert node.provenance.commit_sha == "abc123"


def test_containment_edges(extraction: ExtractionResult) -> None:
    contains = _edges(extraction, RelationType.CONTAINS)

    assert ("file:payment/service.py::payment.service", "class:payment/service.py::PaymentService") in contains
    assert ("file:payment/service.py::payment.service", "function:payment/service.py::build_service") in contains
    assert ("class:payment/service.py::PaymentService", "method:payment/service.py::PaymentService.pay") in contains


def test_inheritance_edge_across_files(extraction: ExtractionResult) -> None:
    assert ("class:payment/service.py::PaymentService", "class:core/base.py::BaseService") in _edges(
        extraction, RelationType.INHERITS
    )


def test_import_edges_between_files(extraction: ExtractionResult) -> None:
    depends = _edges(extraction, RelationType.DEPENDS_ON)

    assert ("file:payment/service.py::payment.service", "file:core/base.py::core.base") in depends
    assert ("file:payment/service.py::payment.service", "file:core/__init__.py::core") in depends


def test_call_edges_are_inferred(extraction: ExtractionResult) -> None:
    calls = [edge for edge in extraction.edges if edge.relation == RelationType.CALLS]
    pairs = {(edge.source_id, edge.target_id) for edge in calls}

    assert ("method:payment/service.py::PaymentService.pay", "function:core/helpers.py::audit") in pairs
    assert ("method:payment/service.py::PaymentService.pay", "method:core/base.py::BaseService.charge") in pairs
    assert all(edge.provenance.evidence_type == EvidenceType.INFERRED for edge in calls)
    assert all(edge.provenance.confidence == 0.6 for edge in calls)


def test_calls_to_third_party_code_are_ignored(sample_project: Path) -> None:
    (sample_project / "core" / "helpers.py").write_text(
        "import json\n\n\ndef audit(amount):\n    return json.dumps(amount)\n", encoding="utf-8"
    )
    context = ProjectScanner().scan(sample_project)

    result = CodeStructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))

    assert all("json" not in node.id for node in result.nodes)
    assert all("dumps" not in edge.target_id for edge in result.edges)


def test_homonym_elsewhere_does_not_divert_the_call(sample_project: Path) -> None:
    """Une seconde fonction ``audit`` ailleurs : l'appel suit l'import, pas le nom."""
    (sample_project / "payment" / "audit.py").write_text("def audit(x):\n    pass\n", encoding="utf-8")
    context = ProjectScanner().scan(sample_project)

    result = CodeStructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))

    targets = {edge.target_id for edge in result.edges if edge.relation == RelationType.CALLS}
    assert "function:core/helpers.py::audit" in targets
    assert "function:payment/audit.py::audit" not in targets


def test_unparsable_file_is_reported_as_warning(sample_project: Path) -> None:
    (sample_project / "core" / "broken.py").write_text(BROKEN, encoding="utf-8")
    context = ProjectScanner().scan(sample_project)

    result = CodeStructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))

    assert any("syntaxe invalide" in warning for warning in result.warnings)
    assert any(node.name == "service.py" for node in result.nodes)


def test_file_without_parser_becomes_a_file_node(sample_project: Path) -> None:
    context = ProjectScanner().scan(sample_project)

    result = CodeStructureExtractor().extract(context, ParserRegistry())

    assert any("aucun parser pour le langage python" in warning for warning in result.warnings)
    assert {node.name for node in result.nodes if node.type is NodeType.FILE} == {
        "service.py",
        "__init__.py",
        "base.py",
        "helpers.py",
    }
    assert all(node.type is NodeType.FILE for node in result.nodes)
