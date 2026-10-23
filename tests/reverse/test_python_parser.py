from pathlib import Path

import pytest

from sakg.reverse import ParsedModule, ParseError, ProjectScanner, PythonAstParser
from sakg.reverse.models import ImportRef
from sakg.reverse.python_parser import module_name_of

from .conftest import BROKEN


def _parse(root: Path, relative_path: str) -> ParsedModule:
    context = ProjectScanner().scan(root)
    file = next(file for file in context.files if file.relative_path == relative_path)
    return PythonAstParser().parse(file)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/sakg/domain/node.py", "sakg.domain.node"),
        ("src/sakg/domain/__init__.py", "sakg.domain"),
        ("payment/service.py", "payment.service"),
        ("main.py", "main"),
    ],
)
def test_module_name_of(path: str, expected: str) -> None:
    assert module_name_of(path) == expected


def test_parse_collects_symbols(sample_project: Path) -> None:
    module = _parse(sample_project, "payment/service.py")

    assert module.module_name == "payment.service"
    assert [(symbol.kind, symbol.qualified_name) for symbol in module.symbols] == [
        ("class", "PaymentService"),
        ("method", "PaymentService.pay"),
        ("method", "PaymentService.refund"),
        ("function", "build_service"),
        ("function", "build_service.inner"),
    ]


def test_parse_collects_bases_and_lines(sample_project: Path) -> None:
    module = _parse(sample_project, "payment/service.py")
    payment_service = module.symbols_of_kind("class")[0]

    assert payment_service.bases == ("BaseService",)
    assert payment_service.line > 0
    assert payment_service.end_line is not None and payment_service.end_line > payment_service.line


def test_parse_collects_imports(sample_project: Path) -> None:
    module = _parse(sample_project, "payment/service.py")

    assert ImportRef(module="core.base", names=("BaseService",), level=0, line=4) in module.imports
    assert any(import_ref.names == ("helpers",) for import_ref in module.imports)


def test_parse_collects_calls_with_their_caller(sample_project: Path) -> None:
    module = _parse(sample_project, "payment/service.py")

    calls = {(call.caller, call.callee) for call in module.calls}
    assert ("PaymentService.pay", "helpers.audit") in calls
    assert ("PaymentService.pay", "self.charge") in calls
    assert ("build_service", "PaymentService") in calls


def test_parse_collects_decorators(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        '@app.post("/pay")\ndef pay() -> None:\n    pass\n',
        encoding="utf-8",
    )

    module = _parse(tmp_path, "api.py")

    assert [(decorator.target, decorator.name, decorator.arguments) for decorator in module.decorators] == [
        ("pay", "app.post", ("/pay",))
    ]


def test_parse_invalid_syntax(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text(BROKEN, encoding="utf-8")

    with pytest.raises(ParseError, match="syntaxe invalide"):
        _parse(tmp_path, "broken.py")
