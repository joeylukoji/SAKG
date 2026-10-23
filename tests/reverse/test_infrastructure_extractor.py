"""Extraction de la couche infrastructure depuis un fichier docker-compose."""

from pathlib import Path

import pytest

from sakg.domain import NodeType, RelationType
from sakg.reverse import InfrastructureExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.models import ExtractionResult

COMPOSE = """
services:
  api:
    build:
      context: ./app
    ports:
      - "8000:8000"
    depends_on:
      - database
      - cache
  database:
    image: postgres:16
    ports:
      - "5432:5432"
  cache:
    image: redis:7
"""


@pytest.fixture
def compose_project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    return tmp_path


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root, commit_sha="abc123")
    return InfrastructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))


def _pairs(result: ExtractionResult, relation: RelationType) -> set[tuple[str, str]]:
    return {(edge.source_id, edge.target_id) for edge in result.edges if edge.relation == relation}


def test_services_become_containers(compose_project: Path) -> None:
    result = _extract(compose_project)

    assert {node.name for node in result.nodes if node.type == NodeType.CONTAINER} == {"api", "database", "cache"}


def test_container_properties(compose_project: Path) -> None:
    result = _extract(compose_project)
    api = next(node for node in result.nodes if node.name == "api")
    database = next(node for node in result.nodes if node.name == "database")

    assert api.properties == {"ports": ["8000:8000"], "build": "./app"}
    assert database.properties["image"] == "postgres:16"
    assert database.provenance.detected_by == "DOCKER_COMPOSE_SERVICE"
    assert database.provenance.commit_sha == "abc123"


def test_the_compose_file_declares_its_containers(compose_project: Path) -> None:
    contains = _pairs(_extract(compose_project), RelationType.CONTAINS)

    assert ("file:docker-compose.yml::docker-compose.yml", "container:docker-compose.yml::api") in contains


def test_dependencies_between_containers(compose_project: Path) -> None:
    depends = _pairs(_extract(compose_project), RelationType.DEPENDS_ON)

    assert depends == {
        ("container:docker-compose.yml::api", "container:docker-compose.yml::database"),
        ("container:docker-compose.yml::api", "container:docker-compose.yml::cache"),
    }


def test_images_become_technologies(compose_project: Path) -> None:
    result = _extract(compose_project)

    assert {node.name for node in result.nodes if node.type == NodeType.TECHNOLOGY} == {"postgres:16", "redis:7"}
    assert ("container:docker-compose.yml::database", "technology:postgres:16") in _pairs(
        result, RelationType.USES_TECHNOLOGY
    )


def test_depends_on_written_with_conditions(tmp_path: Path) -> None:
    """La forme longue de ``depends_on`` est un dictionnaire, pas une liste."""
    (tmp_path / "compose.yaml").write_text(
        "services:\n  api:\n    image: app\n    depends_on:\n      database:\n        condition: service_healthy\n"
        "  database:\n    image: postgres:16\n",
        encoding="utf-8",
    )

    assert ("container:compose.yaml::api", "container:compose.yaml::database") in _pairs(
        _extract(tmp_path), RelationType.DEPENDS_ON
    )


def test_a_dependency_on_an_unknown_service_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    image: app\n    depends_on:\n      - absent\n", encoding="utf-8"
    )

    assert _pairs(_extract(tmp_path), RelationType.DEPENDS_ON) == set()


def test_an_invalid_compose_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n   - broken\n  :\n", encoding="utf-8")

    result = _extract(tmp_path)

    assert result.nodes == []
    assert any("illisible" in warning for warning in result.warnings)


def test_an_image_built_from_an_environment_variable_is_not_a_technology(tmp_path: Path) -> None:
    """``myorg/api:${TAG}`` ne nomme aucune image existante : ne pas la matérialiser."""
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n    image: myorg/api:${TAG}\n", encoding="utf-8")

    result = _extract(tmp_path)

    assert all(node.type != NodeType.TECHNOLOGY for node in result.nodes)
    assert any("variable d'environnement" in warning for warning in result.warnings)
    api = next(node for node in result.nodes if node.type == NodeType.CONTAINER)
    assert api.properties["image"] == "myorg/api:${TAG}"  # la ligne du fichier reste consultable


def test_the_same_image_in_two_files_is_one_technology(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text("services:\n  a:\n    image: redis:7\n", encoding="utf-8")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "compose.yaml").write_text("services:\n  b:\n    image: redis:7\n", encoding="utf-8")

    result = _extract(tmp_path)

    assert len({node.id for node in result.nodes if node.type == NodeType.TECHNOLOGY}) == 1


def test_a_service_without_image_or_build(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text('services:\n  bare:\n    ports: ["1:1"]\n', encoding="utf-8")

    result = _extract(tmp_path)

    assert {node.name for node in result.nodes if node.type == NodeType.CONTAINER} == {"bare"}
    assert all(node.type != NodeType.TECHNOLOGY for node in result.nodes)


def test_compose_outside_the_requested_scope_is_skipped(tmp_path: Path) -> None:
    """``sakg reverse src`` ne doit pas ramener des conteneurs déclarés ailleurs."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n    image: app\n", encoding="utf-8")

    context = ProjectScanner().scan(tmp_path, include=["src"])
    result = InfrastructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))

    assert result.nodes == []


def test_a_project_without_compose_has_no_container(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    assert _extract(tmp_path).nodes == []


def test_compose_in_an_ignored_directory_is_skipped(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "docker-compose.yml").write_text("services:\n  ghost:\n    image: x\n", encoding="utf-8")

    assert _extract(tmp_path).nodes == []
