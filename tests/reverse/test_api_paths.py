"""Cas où le chemin d'une route est difficile à établir.

Règle : soit SAKG produit le chemin exact, soit il n'enregistre rien et le signale. Un chemin
partiel ou deviné est pire que pas de route du tout.
"""

from pathlib import Path

import pytest

from sakg.reverse import ApiExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.models import ExtractionResult


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root)
    return ApiExtractor().extract(context, ParserRegistry([PythonAstParser()]))


def _paths(result: ExtractionResult) -> set[str]:
    return {node.name for node in result.nodes}


def test_prefix_from_a_variable_is_not_invented(tmp_path: Path) -> None:
    """Le préfixe est dans une variable : mieux vaut un chemin sans lui qu'un chemin faux."""
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nPREFIX = "/users"\nrouter = APIRouter(prefix=PREFIX)\n\n\n'
        '@router.get("/me")\ndef me():\n    pass\n',
    )

    result = _extract(tmp_path)

    assert _paths(result) == {"GET /me"}
    assert any("valeur inconnue statiquement" in warning for warning in result.warnings)


def test_prefix_from_an_f_string_is_not_invented(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nVERSION = "v1"\nrouter = APIRouter(prefix=f"/{VERSION}")\n\n\n'
        '@router.get("/me")\ndef me():\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /me"}


def test_router_imported_under_an_alias(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter as Router\n\nrouter = Router(prefix="/users")\n\n\n'
        '@router.get("/me")\ndef me():\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /users/me"}


def test_annotated_router_assignment(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nrouter: APIRouter = APIRouter(prefix="/users")\n\n\n'
        '@router.get("/me")\ndef me():\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /users/me"}


def test_nested_router_inclusions(tmp_path: Path) -> None:
    """main → v1 → items : les trois préfixes doivent se composer."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/items.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/items")\n\n\n'
        '@router.get("/{item_id}")\ndef read(item_id: int):\n    pass\n',
    )
    _write(
        tmp_path,
        "pkg/v1.py",
        "from fastapi import APIRouter\n\nfrom pkg.items import router as items_router\n\n"
        'router = APIRouter(prefix="/v1")\nrouter.include_router(items_router)\n',
    )
    _write(
        tmp_path,
        "main.py",
        "from fastapi import FastAPI\n\nfrom pkg.v1 import router as v1_router\n\n"
        'app = FastAPI()\napp.include_router(v1_router, prefix="/api")\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /api/v1/items/{item_id}"}


def test_a_router_mounted_twice_yields_both_routes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/list")\ndef listing():\n    pass\n',
    )
    _write(
        tmp_path,
        "main.py",
        "from fastapi import FastAPI\n\nfrom api import router\n\napp = FastAPI()\n"
        'app.include_router(router, prefix="/v1")\napp.include_router(router, prefix="/v2")\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /v1/list", "GET /v2/list"}


def test_router_reached_through_a_module_attribute(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/users.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/me")\ndef me():\n    pass\n',
    )
    _write(
        tmp_path,
        "main.py",
        "from fastapi import FastAPI\nfrom pkg import users\n\napp = FastAPI()\n"
        'app.include_router(users.router, prefix="/api")\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /api/me"}


def test_include_router_inside_a_factory_is_reported(tmp_path: Path) -> None:
    """Le patron ``create_app()`` n'est pas résolu : la route existe, le préfixe est signalé."""
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/me")\ndef me():\n    pass\n',
    )
    _write(
        tmp_path,
        "main.py",
        "from fastapi import FastAPI\n\nfrom api import router\n\n\ndef create_app():\n"
        '    app = FastAPI()\n    app.include_router(router, prefix="/api")\n    return app\n',
    )

    result = _extract(tmp_path)

    assert _paths(result) == {"GET /me"}
    assert any("include_router appelé dans" in warning for warning in result.warnings)


def test_a_non_router_object_does_not_declare_routes(tmp_path: Path) -> None:
    """``@cache.get("/oops")`` n'est pas une route, même dans un fichier qui importe FastAPI."""
    _write(
        tmp_path,
        "svc.py",
        'from fastapi import FastAPI\n\ncache = object()\napp = FastAPI()\n\n\n@cache.get("/oops")\n'
        'def cached():\n    pass\n\n\n@app.get("/real")\ndef real():\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /real"}


def test_an_empty_path_is_a_valid_route(tmp_path: Path) -> None:
    """``@router.post("")`` monte la route sur le préfixe du routeur, ce n'est pas une erreur."""
    _write(
        tmp_path,
        "api.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/items")\n\n\n@router.post("")\n'
        "def create():\n    pass\n",
    )

    result = _extract(tmp_path)

    assert _paths(result) == {"POST /items"}
    assert result.warnings == []


def test_api_route_declares_every_method(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.api_route("/thing", methods=["GET", "POST"])\n'
        "def thing():\n    pass\n",
    )

    assert _paths(_extract(tmp_path)) == {"GET /thing", "POST /thing"}


def test_websocket_route(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.websocket("/ws")\nasync def feed(socket):\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"WEBSOCKET /ws"}


def test_path_given_as_a_keyword(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get(path="/keyword")\ndef named():\n    pass\n',
    )

    assert _paths(_extract(tmp_path)) == {"GET /keyword"}


def test_a_non_literal_path_is_reported_not_guessed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        'from fastapi import FastAPI\n\nPATH = "/computed"\napp = FastAPI()\n\n\n@app.get(PATH)\n'
        "def computed():\n    pass\n",
    )

    result = _extract(tmp_path)

    assert result.nodes == []
    assert any("chemin non littéral" in warning for warning in result.warnings)


def test_two_routers_of_the_same_file_colliding_on_a_path(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        "from fastapi import APIRouter\n\nfirst = APIRouter()\nsecond = APIRouter()\n\n\n"
        '@first.get("/dup")\ndef one():\n    pass\n\n\n@second.get("/dup")\ndef two():\n    pass\n',
    )

    result = _extract(tmp_path)

    assert len(result.nodes) == 1
    assert any("une seule route est enregistrée" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    "source",
    [
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/a")\n@router.get("/x")\ndef f():\n    pass\n',
        'from fastapi import FastAPI\n\napp = FastAPI()\n@app.get("/a/x")\ndef f():\n    pass\n',
    ],
)
def test_equivalent_declarations_give_the_same_path(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "api.py", source)

    assert _paths(_extract(tmp_path)) == {"GET /a/x"}
