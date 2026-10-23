from pathlib import Path

from sakg.domain import NodeType, RelationType
from sakg.reverse import CodeStructureExtractor, ParserRegistry, ProjectScanner, TypeScriptParser
from sakg.reverse.languages import language_of, module_name_of


def test_module_name_of_typescript() -> None:
    assert module_name_of("src/app/users.ts", "typescript") == "app.users"
    assert module_name_of("src/app/index.ts", "typescript") == "app"
    assert module_name_of("src/app/page.tsx", "typescript") == "app.page"


def test_language_of_skips_declaration_files() -> None:
    assert language_of("src/app.ts") == "typescript"
    assert language_of("src/types.d.ts") is None
    assert language_of("bundle.min.js") is None


def _parse(root: Path, relative_path: str):
    context = ProjectScanner().scan(root)
    file = next(file for file in context.files if file.relative_path == relative_path)
    return TypeScriptParser().parse(file)


def test_typescript_parser_collects_symbols_imports_and_calls(tmp_path: Path) -> None:
    (tmp_path / "base.ts").write_text(
        "export class BaseService {\n  charge(amount: number): boolean {\n    return amount > 0;\n  }\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "service.ts").write_text(
        'import { BaseService } from "./base";\n'
        'import { audit } from "./helpers";\n\n'
        "export class PaymentService extends BaseService {\n"
        "  pay(amount: number): boolean {\n"
        "    audit(amount);\n"
        "    return this.charge(amount);\n"
        "  }\n"
        "}\n\n"
        "export function buildService(): PaymentService {\n"
        "  return new PaymentService();\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "helpers.ts").write_text("export function audit(amount: number): void {}\n", encoding="utf-8")

    module = _parse(tmp_path, "service.ts")

    assert module.module_name == "service"
    assert [(symbol.kind, symbol.qualified_name) for symbol in module.symbols] == [
        ("class", "PaymentService"),
        ("method", "PaymentService.pay"),
        ("function", "buildService"),
    ]
    assert any(
        import_ref.module == "./base" and import_ref.names == ("BaseService",) for import_ref in module.imports
    )
    calls = {(call.caller, call.callee) for call in module.calls}
    assert ("PaymentService.pay", "audit") in calls
    assert ("PaymentService.pay", "this.charge") in calls


def test_typescript_structure_resolves_inheritance_and_imports(tmp_path: Path) -> None:
    (tmp_path / "base.ts").write_text(
        "export class BaseService {\n  charge(amount: number): boolean {\n    return amount > 0;\n  }\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "service.ts").write_text(
        'import { BaseService } from "./base";\n\n'
        "export class PaymentService extends BaseService {\n"
        "  pay(amount: number): boolean {\n"
        "    return this.charge(amount);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    context = ProjectScanner().scan(tmp_path)
    result = CodeStructureExtractor().extract(context, ParserRegistry([TypeScriptParser()]))

    ids = {node.id for node in result.nodes}
    assert "class:service.ts::PaymentService" in ids
    assert "class:base.ts::BaseService" in ids
    pairs = {(edge.source_id, edge.target_id) for edge in result.edges if edge.relation is RelationType.INHERITS}
    assert ("class:service.ts::PaymentService", "class:base.ts::BaseService") in pairs
    depends = {(edge.source_id, edge.target_id) for edge in result.edges if edge.relation is RelationType.DEPENDS_ON}
    assert any("service.ts" in source and "base.ts" in target for source, target in depends)
    assert all(
        node.provenance.detected_by.startswith("TYPESCRIPT_")
        for node in result.nodes
        if node.type is NodeType.CLASS
    )
