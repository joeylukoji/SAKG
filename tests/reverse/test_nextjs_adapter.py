"""Route Handlers Next.js (App Router) : le chemin vient de l'arborescence, pas d'un décorateur."""

from pathlib import Path

from sakg.domain import EvidenceType, NodeType, RelationType
from sakg.reverse import ApiExtractor, ParserRegistry, ProjectScanner, TypeScriptParser
from sakg.reverse.adapters import NextJsAdapter
from sakg.reverse.models import ExtractionResult

ROUTE_HANDLER = """export async function GET(request: Request) {
  return Response.json({ ok: true });
}

export async function POST(request: Request) {
  return Response.json({ created: true });
}

function helper(value: number): number {
  return value * 2;
}
"""


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root)
    return ApiExtractor().extract(context, ParserRegistry([TypeScriptParser()]))


def _paths(result: ExtractionResult) -> set[str]:
    return {node.name for node in result.nodes}


def test_route_handler_exposes_its_http_verbs(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)

    assert _paths(_extract(tmp_path)) == {"GET /api/users", "POST /api/users"}


def test_endpoint_properties_and_provenance(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)
    endpoint = next(node for node in _extract(tmp_path).nodes if node.name == "GET /api/users")

    assert endpoint.type == NodeType.ENDPOINT
    assert endpoint.properties["method"] == "GET"
    assert endpoint.properties["framework"] == "nextjs"
    assert endpoint.properties["handler"] == "GET"
    assert endpoint.provenance.detected_by == "NEXTJS_ROUTE_DECLARATION"
    assert endpoint.provenance.evidence_type == EvidenceType.OBSERVED
    assert endpoint.provenance.evidence is not None
    assert endpoint.provenance.evidence.file == "app/api/users/route.ts"


def test_file_exposes_and_endpoint_is_implemented(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)
    result = _extract(tmp_path)
    pairs = {(edge.relation, edge.source_id, edge.target_id, edge.provenance.detected_by) for edge in result.edges}

    assert (
        RelationType.EXPOSES,
        "file:app/api/users/route.ts::app.api.users.route",
        "endpoint:app/api/users/route.ts::GET /api/users",
        "TYPESCRIPT_ROUTE_DECLARATION",
    ) in pairs
    assert (
        RelationType.IMPLEMENTED_BY,
        "endpoint:app/api/users/route.ts::GET /api/users",
        "function:app/api/users/route.ts::GET",
        "TYPESCRIPT_ROUTE_HANDLER",
    ) in pairs


def test_a_helper_function_is_not_mistaken_for_a_route(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)

    handlers = {node.properties["handler"] for node in _extract(tmp_path).nodes}
    assert handlers == {"GET", "POST"}


def test_root_route(tmp_path: Path) -> None:
    _write(tmp_path, "app/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _paths(_extract(tmp_path)) == {"GET /"}


def test_dynamic_segment(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "app/api/users/[id]/route.ts",
        "export function GET(request: Request, { params }: { params: { id: string } }) {\n  return null;\n}\n",
    )

    assert _paths(_extract(tmp_path)) == {"GET /api/users/{id}"}


def test_catch_all_segment(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/files/[...slug]/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _paths(_extract(tmp_path)) == {"GET /api/files/{...slug}"}


def test_optional_catch_all_segment(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/files/[[...slug]]/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _paths(_extract(tmp_path)) == {"GET /api/files/{...slug?}"}


def test_route_group_does_not_appear_in_the_path(tmp_path: Path) -> None:
    _write(tmp_path, "app/(marketing)/api/ping/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _paths(_extract(tmp_path)) == {"GET /api/ping"}


def test_a_private_folder_exposes_no_route(tmp_path: Path) -> None:
    """Next.js exclut du routage les dossiers préfixés par ``_`` : ne rien inventer non plus."""
    _write(tmp_path, "app/_internal/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _extract(tmp_path).nodes == []


def test_a_file_outside_app_is_not_a_route_handler(tmp_path: Path) -> None:
    _write(tmp_path, "lib/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _extract(tmp_path).nodes == []


def test_a_page_is_not_a_route_handler(tmp_path: Path) -> None:
    _write(tmp_path, "app/about/page.tsx", "export default function Page() {\n  return null;\n}\n")

    assert _extract(tmp_path).nodes == []


def test_src_app_layout_is_supported(tmp_path: Path) -> None:
    _write(tmp_path, "src/app/api/ping/route.ts", "export function GET() {\n  return null;\n}\n")

    assert _paths(_extract(tmp_path)) == {"GET /api/ping"}


def test_adapter_detects_route_handler_files(tmp_path: Path) -> None:
    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)
    _write(tmp_path, "app/about/page.tsx", "export default function Page() {\n  return null;\n}\n")
    context = ProjectScanner().scan(tmp_path)
    registry = ParserRegistry([TypeScriptParser()])
    modules = {file.relative_path: registry.parse(file) for file in context.files}
    adapter = NextJsAdapter()

    assert adapter.detect(modules["app/api/users/route.ts"])  # type: ignore[arg-type]
    assert not adapter.detect(modules["app/about/page.tsx"])  # type: ignore[arg-type]


def test_changing_a_handler_impacts_its_route(tmp_path: Path) -> None:
    """La question « quelles routes ce changement touche-t-il ? » doit avoir une réponse."""
    from sakg.analysis import ChangeRequest, ImpactAnalyzer
    from sakg.graph import GraphQueryEngine
    from sakg.reverse import ReverseEngineeringPipeline

    _write(tmp_path, "app/api/users/route.ts", ROUTE_HANDLER)
    graph = ReverseEngineeringPipeline.default().run_on(tmp_path).graph
    report = ImpactAnalyzer(GraphQueryEngine(graph)).analyze(ChangeRequest(description="Modifier GET"))

    assert [node.name for node in report.by_type(NodeType.ENDPOINT)] == ["GET /api/users"]
