from pathlib import Path

import pytest
import yaml

from sakg.application import ArchitectureService
from sakg.domain import EvidenceType, Node, NodeType, Provenance
from sakg.generation import DiagramView
from sakg.infrastructure import ProjectConfig, ProjectNotInitializedError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Projet jouet : ``src/app/service.py`` avec une classe et une méthode."""
    source = tmp_path / "src" / "app"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "base.py").write_text("class Base:\n    def run(self):\n        pass\n", encoding="utf-8")
    (source / "service.py").write_text(
        "from app.base import Base\n\n\nclass Service(Base):\n    def handle(self):\n        return self.run()\n",
        encoding="utf-8",
    )
    return tmp_path


def test_init_creates_the_architect_layout(project: Path) -> None:
    service = ArchitectureService.for_project(project)

    architect = service.init_project()

    assert (architect / "graph").is_dir()
    assert (architect / "versions").is_dir()
    config = yaml.safe_load((architect / "project.yaml").read_text(encoding="utf-8"))
    assert config["source_roots"] == ["src"]
    assert config["name"] == project.name


def test_init_does_not_overwrite_an_existing_configuration(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project(name="original")

    service.init_project(name="autre")

    assert ProjectConfig.load(project).name == "original"


def test_load_configuration_of_an_uninitialized_project(project: Path) -> None:
    with pytest.raises(ProjectNotInitializedError):
        ProjectConfig.load(project)


def test_reverse_persists_a_versioned_graph(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()

    snapshot = service.reverse()

    assert snapshot.version == 1
    assert {node.name for node in service.graph.nodes_of_type(NodeType.CLASS)} == {"Base", "Service"}
    assert (project / ".architect" / "graph" / "nodes.json").exists()
    assert ArchitectureService.for_project(project).graph.version == 1


def test_node_ids_do_not_depend_on_the_analysed_roots(project: Path) -> None:
    """Restreindre l'analyse ne doit pas renommer les nœuds déjà enregistrés."""
    ProjectConfig(name="p", source_roots=["src"]).save(project)
    whole = ArchitectureService.for_project(project)
    whole.reverse()
    from_whole = {node.id for node in whole.graph.nodes()}

    restricted = ArchitectureService.for_project(project)
    restricted.reverse(["src/app"])

    assert "class:src/app/base.py::Base" in from_whole
    assert {node.id for node in restricted.graph.nodes()} == from_whole


def test_reverse_of_a_missing_root_fails_clearly(project: Path) -> None:
    service = ArchitectureService.for_project(project)

    with pytest.raises(FileNotFoundError, match="introuvable"):
        service.reverse(["src/absent"])


def test_unchanged_code_creates_no_new_version(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    first = service.reverse()

    second = service.reverse()

    assert second.version == first.version
    assert second.graph_hash == first.graph_hash
    assert [snapshot.version for snapshot in service.snapshots()] == [1]
    assert any("inchangée" in warning for warning in service.warnings)


def test_provenance_dates_are_preserved_when_content_is_unchanged(project: Path) -> None:
    """Sans cela, chaque reverse réécrirait tout .architect/ et rendrait son diff illisible."""
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()
    before = {node.id: node.provenance.created_at for node in service.graph.nodes()}

    (project / "src" / "app" / "extra.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    service.reverse()

    after = {node.id: node.provenance.created_at for node in service.graph.nodes()}
    assert all(after[node_id] == created_at for node_id, created_at in before.items())
    assert "file:src/app/extra.py::app.extra" in after


def test_search_and_dependencies(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    found = service.search("Service")
    assert found and found[0].name == "Service"
    assert {node.name for node in service.dependencies(found[0].id)} == {"Base"}
    assert service.dependents("class:src/app/base.py::Base")[0].name == "Service"


def test_impact_report_from_the_service(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    report = service.impact("Modifier Base")

    assert any(node.name == "Base" for node in report.all_nodes())
    assert "# Impact" in report.to_markdown()


def test_write_diagram(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    path = service.write_diagram(DiagramView.CLASS)

    content = path.read_text(encoding="utf-8")
    assert path == project / ".architect" / "diagrams" / "class.md"
    assert "classDiagram" in content
    assert "Service --|> Base" in content


def test_validate_with_no_rules_declared_passes(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    report = service.validate()

    assert report.passed()
    assert report.rules_checked == ()


def test_validate_runs_declared_rules_against_the_graph(project: Path) -> None:
    """``app.service`` dépend de ``app.base`` ; classée « couche interne », c'est une violation."""
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()
    rules_dir = project / ".architect" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "layers.yaml").write_text(
        "- type: layer_dependency\n  id: reversed-layers\n  layers: [app.service, app.base]\n",
        encoding="utf-8",
    )

    report = service.validate()

    assert not report.passed()
    assert report.rules_checked == ("reversed-layers",)
    assert "app.service" in report.findings[0].message


def test_validate_filters_by_configured_rule_ids(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()
    rules_dir = project / ".architect" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "rules.yaml").write_text(
        "- type: no_cycle\n  id: cycles\n- type: layer_dependency\n  id: layers\n  layers: [app.base, app.service]\n",
        encoding="utf-8",
    )
    config = ProjectConfig.load(project).model_copy(update={"rules": ["cycles"]})
    config.save(project)

    report = service.validate()

    assert report.rules_checked == ("cycles",)


def test_detect_drift_of_an_unchanged_project_has_no_drift(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    report = service.detect_drift()

    assert not report.has_drifted()
    assert report.drift_score == 0.0


def test_detect_drift_reports_a_change_since_the_last_reverse(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()
    (project / "src" / "app" / "extra.py").write_text(
        "from app.base import Base\n\n\nclass Extra(Base):\n    pass\n", encoding="utf-8"
    )

    report = service.detect_drift()

    assert report.has_drifted()
    assert any("extra" in edge.source_id for edge in report.undocumented_in_code)


def test_detect_drift_ignores_a_user_defined_node(project: Path) -> None:
    """Un nœud ajouté à la main (règle 5 d'AGENTS.md : l'IA ne modifie jamais le graphe seule)."""
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()
    requirement = Node(
        id="requirement:manual::Facturation",
        type=NodeType.REQUIREMENT,
        name="Facturation",
        provenance=Provenance(evidence_type=EvidenceType.USER_DEFINED, confidence=1.0, detected_by="USER"),
    )
    service.graph.add_node(requirement)

    report = service.detect_drift()

    assert not report.has_drifted()


def test_detect_drift_of_a_missing_root_fails(tmp_path: Path) -> None:
    service = ArchitectureService.for_project(tmp_path / "absent")

    with pytest.raises(FileNotFoundError, match="introuvable"):
        service.detect_drift()


def test_second_reverse_creates_a_second_version(project: Path) -> None:
    service = ArchitectureService.for_project(project)
    service.init_project()
    service.reverse()

    (project / "src" / "app" / "service.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    snapshot = service.reverse()

    assert snapshot.version == 2
    assert [item.version for item in service.snapshots()] == [1, 2]
    assert all(node.name != "handle" for node in service.graph.nodes())
