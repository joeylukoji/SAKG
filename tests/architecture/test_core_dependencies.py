"""Règle 1 d'AGENTS.md : le cœur (domain, graph) n'importe que stdlib, Pydantic et NetworkX."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "sakg"

THIRD_PARTY_ALLOWED = {"pydantic", "networkx"}

# Le domaine ne dépend d'aucun autre module SAKG ; le graphe peut dépendre du domaine.
INTERNAL_ALLOWED = {
    "domain": {"sakg.domain"},
    "graph": {"sakg.domain", "sakg.graph"},
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _is_allowed(module: str, package: str) -> bool:
    root = module.split(".")[0]
    if root in sys.stdlib_module_names or root in THIRD_PARTY_ALLOWED or root == "__future__":
        return True
    return any(module == allowed or module.startswith(allowed + ".") for allowed in INTERNAL_ALLOWED[package])


@pytest.mark.parametrize("package", sorted(INTERNAL_ALLOWED))
def test_core_package_has_no_forbidden_imports(package: str) -> None:
    violations = [
        f"{path.relative_to(SRC)}: {module}"
        for path in sorted((SRC / package).rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if not _is_allowed(module, package)
    ]
    assert not violations, "Imports interdits dans le cœur :\n" + "\n".join(violations)


# Les flèches pointent vers le cœur (ARCHITECTURE.md §2) : ces couches ne remontent jamais.
FORBIDDEN_UPWARD = {
    "reverse": {"sakg.application", "sakg.infrastructure", "sakg.interfaces"},
    "analysis": {"sakg.application", "sakg.infrastructure", "sakg.interfaces"},
    "validation": {"sakg.application", "sakg.infrastructure", "sakg.interfaces"},
    "generation": {"sakg.application", "sakg.infrastructure", "sakg.interfaces"},
    "ai": {"sakg.application", "sakg.infrastructure", "sakg.interfaces"},
    "infrastructure": {"sakg.application", "sakg.interfaces"},
    "application": {"sakg.interfaces"},
}


@pytest.mark.parametrize("package", sorted(FORBIDDEN_UPWARD))
def test_layer_does_not_import_an_outer_layer(package: str) -> None:
    forbidden = FORBIDDEN_UPWARD[package]
    violations = [
        f"{path.relative_to(SRC)}: {module}"
        for path in sorted((SRC / package).rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if any(module == name or module.startswith(name + ".") for name in forbidden)
    ]
    assert not violations, f"La couche {package} remonte vers une couche externe :\n" + "\n".join(violations)
