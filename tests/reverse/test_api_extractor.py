"""Extraction des endpoints HTTP : une route du graphe doit exister dans le code."""

from pathlib import Path

import pytest

from sakg.domain import EvidenceType, NodeType, RelationType
from sakg.reverse import ApiExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.adapters import FastApiAdapter, join_paths
from sakg.reverse.models import ExtractionResult

ROUTES = '''
"""Routeur des utilisateurs."""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}")
async def read_user(user_id: int) -> dict:
    return {"id": user_id}


@router.post("/")
async def create_user(payload: dict) -> dict:
    return payload
'''

MAIN = """
from fastapi import FastAPI

from api.routes import router

app = FastAPI()
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
"""

PLAIN = """
def helper(value):
    return value
"""


@pytest.fixture
def api_project(tmp_path: Path) -> Path:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "routes.py").write_text(ROUTES, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN, encoding="utf-8")
    (tmp_path / "helpers.py").write_text(PLAIN, encoding="utf-8")
    return tmp_path


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root, commit_sha="abc123")
    return ApiExtractor().extract(context, ParserRegistry([PythonAstParser()]))


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("/api", "/users/", "{id}"), "/api/users/{id}"),
        (("", "/health"), "/health"),
        (("/api/v1", "", "/"), "/api/v1"),
        ((), "/"),
    ],
)
def test_join_paths(parts: tuple[str, ...], expected: str) -> None:
    assert join_paths(*parts) == expected


def test_endpoints_are_extracted_with_their_prefixes(api_project: Path) -> None:
    """Le préfixe local du routeur et celui posé par include_router s'additionnent."""
    result = _extract(api_project)

    routes = {node.name for node in result.nodes}
    assert routes == {"GET /api/v1/users/{user_id}", "POST /api/v1/users", "GET /health"}


def test_endpoint_properties_and_provenance(api_project: Path) -> None:
    result = _extract(api_project)
    endpoint = next(node for node in result.nodes if node.name == "GET /health")

    assert endpoint.type == NodeType.ENDPOINT
    assert endpoint.properties["method"] == "GET"
    assert endpoint.properties["framework"] == "fastapi"
    assert endpoint.properties["handler"] == "health"
    assert endpoint.provenance.evidence_type == EvidenceType.OBSERVED
    assert endpoint.provenance.evidence is not None
    assert endpoint.provenance.evidence.file == "main.py"
    assert endpoint.provenance.commit_sha == "abc123"


def test_file_exposes_and_endpoint_is_implemented(api_project: Path) -> None:
    result = _extract(api_project)
    pairs = {(edge.relation, edge.source_id, edge.target_id) for edge in result.edges}

    assert (
        RelationType.EXPOSES,
        "file:main.py::main",
        "endpoint:main.py::GET /health",
    ) in pairs
    assert (
        RelationType.IMPLEMENTED_BY,
        "endpoint:main.py::GET /health",
        "function:main.py::health",
    ) in pairs


def test_a_project_without_fastapi_has_no_endpoint(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text(PLAIN, encoding="utf-8")

    assert _extract(tmp_path).nodes == []


def test_a_decorator_that_is_not_a_route_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "svc.py").write_text(
        "from fastapi import FastAPI\nimport functools\n\n\n@functools.cache\ndef compute():\n    pass\n",
        encoding="utf-8",
    )

    assert _extract(tmp_path).nodes == []


def test_router_without_prefix_keeps_the_declared_path(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.delete("/items/{item_id}")\n'
        "def drop(item_id: int):\n    pass\n",
        encoding="utf-8",
    )

    assert {node.name for node in _extract(tmp_path).nodes} == {"DELETE /items/{item_id}"}


def test_prefix_from_an_unknown_router_is_not_invented(tmp_path: Path) -> None:
    """``include_router`` d'un routeur venant d'une bibliothèque : aucun préfixe supposé."""
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\nfrom third_party import router\n\napp = FastAPI()\n"
        'app.include_router(router, prefix="/ext")\n\n\n@app.get("/ping")\ndef ping():\n    pass\n',
        encoding="utf-8",
    )

    assert {node.name for node in _extract(tmp_path).nodes} == {"GET /ping"}


def test_changing_a_handler_impacts_its_route(api_project: Path) -> None:
    """La question « quelles routes ce changement touche-t-il ? » doit avoir une réponse."""
    from sakg.analysis import ChangeRequest, ImpactAnalyzer
    from sakg.graph import GraphQueryEngine
    from sakg.reverse import ReverseEngineeringPipeline

    graph = ReverseEngineeringPipeline.default().run_on(api_project).graph
    report = ImpactAnalyzer(GraphQueryEngine(graph)).analyze(ChangeRequest(description="Modifier read_user"))

    assert [node.name for node in report.by_type(NodeType.ENDPOINT)] == ["GET /api/v1/users/{user_id}"]


def test_adapter_detects_fastapi_modules(api_project: Path) -> None:
    context = ProjectScanner().scan(api_project)
    registry = ParserRegistry([PythonAstParser()])
    modules = {file.relative_path: registry.parse(file) for file in context.files}
    adapter = FastApiAdapter()

    assert adapter.detect(modules["main.py"])  # type: ignore[arg-type]
    assert not adapter.detect(modules["helpers.py"])  # type: ignore[arg-type]


def test_local_prefixes_and_included_routers(api_project: Path) -> None:
    context = ProjectScanner().scan(api_project)
    registry = ParserRegistry([PythonAstParser()])
    routes = next(registry.parse(file) for file in context.files if file.relative_path == "api/routes.py")
    main = next(registry.parse(file) for file in context.files if file.relative_path == "main.py")
    adapter = FastApiAdapter()

    assert routes is not None and main is not None
    assert adapter.routers(routes) == {"router": "/users"}
    inclusion = adapter.inclusions(main)[0]
    assert (inclusion.router, inclusion.parent, inclusion.prefix) == ("router", "app", "/api/v1")
