"""Résolution des imports : ce qu'un module voit sous quel nom.

Chaque langage a ses conventions (``from . import x``, ``from "./x"``, packages JVM…).
``ImportResolver`` isole cette règle ; les extracteurs n'ont pas à la connaître.
"""

from typing import Protocol

from sakg.reverse.languages import is_package_file
from sakg.reverse.models import ImportRef, ParsedModule

_ESM_EXTENSIONS = (".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js")


class ImportResolver(Protocol):
    """Traduit une référence d'import en nom de module, relatif compris."""

    def resolve(self, import_ref: ImportRef, module_name: str, *, is_package: bool) -> str:
        """Module visé, ou chaîne vide si l'import ne désigne rien dans le projet."""
        ...


class PythonImportResolver:
    """Imports Python, relatifs (``from .. import x``) compris."""

    def resolve(self, import_ref: ImportRef, module_name: str, *, is_package: bool) -> str:
        """Module visé par un import, imports relatifs compris.

        Dans un ``__init__.py``, le paquet courant est le module lui-même ; ailleurs, c'est son
        paquet parent. Un import relatif qui remonte au-delà de la racine retourne une chaîne
        vide : il ne désigne rien dans le projet.

        Example:
            >>> PythonImportResolver().resolve(ImportRef(module="sakg.domain"), "sakg.graph", is_package=False)
            'sakg.domain'
            >>> PythonImportResolver().resolve(ImportRef(module="node", level=1), "sakg.domain", is_package=True)
            'sakg.domain.node'
        """
        if import_ref.level == 0:
            return import_ref.module
        package = module_name.split(".") if is_package else module_name.split(".")[:-1]
        keep = len(package) - (import_ref.level - 1)
        if keep < 0:
            return ""
        ancestors = package[:keep]
        if not ancestors and import_ref.level > 1:
            return ""
        return ".".join([*ancestors, import_ref.module]) if import_ref.module else ".".join(ancestors)


class EcmaImportResolver:
    """Imports ESM / CommonJS : ``from "./base"``, ``require("../core")``.

    Un spécificateur relatif est résolu par rapport au module courant. Un spécificateur nu
    (``react``, ``@/lib``) est renvoyé tel quel, sans inventer d'alias de bundler.
    """

    def resolve(self, import_ref: ImportRef, module_name: str, *, is_package: bool) -> str:
        """Module visé par un import ESM, chemins ``./`` et ``../`` compris."""
        specifier = _strip_esm_extension(import_ref.module.replace("\\", "/"))
        if not specifier:
            return ""
        if specifier.startswith("./") or specifier.startswith("../") or specifier in {".", ".."}:
            return _resolve_relative_specifier(specifier, module_name, is_package=is_package)
        return specifier.replace("/", ".")


def resolver_for(language: str) -> ImportResolver:
    """Résolveur adapté au langage du fichier."""
    if language in {"typescript", "javascript"}:
        return EcmaImportResolver()
    return PythonImportResolver()


def resolve_import(
    import_ref: ImportRef,
    module_name: str,
    *,
    is_package: bool,
    language: str = "python",
) -> str:
    """Module visé par un import, selon le langage du fichier.

    Example:
        >>> resolve_import(ImportRef(module="sakg.domain"), "sakg.graph", is_package=False)
        'sakg.domain'
        >>> resolve_import(ImportRef(module="./base"), "app.service", is_package=False, language="typescript")
        'app.base'
    """
    return resolver_for(language).resolve(import_ref, module_name, is_package=is_package)


def import_bindings(module: ParsedModule, *, module_level_only: bool = False) -> dict[str, tuple[str, str]]:
    """Noms importés : nom local → (module visé, nom d'origine).

    Couvre ``from a.b import c`` et ``from a.b import c as d``, imports relatifs compris. Un
    nom lié plusieurs fois (voir :func:`rebound_names`) garde ici sa dernière liaison : aux
    appelants de l'écarter quand l'ambiguïté compte.

    Args:
        module: Module analysé.
        module_level_only: N'utiliser que les imports du niveau module, les seuls qu'un autre
            fichier puisse voir à travers une ré-exportation.
    """
    package = is_package_file(module.file)
    resolver = resolver_for(module.file.language)
    bindings: dict[str, tuple[str, str]] = {}
    for reference in module.imports:
        if module_level_only and reference.scoped:
            continue
        target = resolver.resolve(reference, module.module_name, is_package=package)
        if not target:
            continue
        for position, name in enumerate(reference.names):
            bindings[reference.local_name_of(position)] = (target, name)
    return bindings


def rebound_names(module: ParsedModule, *, module_level_only: bool = False) -> frozenset[str]:
    """Noms que plusieurs imports lient, par exemple un repli ``try/except ImportError``.

    Lequel s'applique dépend de l'exécution : aucun des deux n'est un fait observable, et
    choisir le dernier reviendrait à relier l'implémentation de repli plutôt que la vraie.
    Un même nom importé deux fois depuis la même origine (bloc ``TYPE_CHECKING`` puis import
    d'exécution) n'est pas ambigu : seules des origines différentes le sont.
    """
    package = is_package_file(module.file)
    resolver = resolver_for(module.file.language)
    origins: dict[str, set[tuple[str, str]]] = {}
    for reference in module.imports:
        if module_level_only and reference.scoped:
            continue
        target = resolver.resolve(reference, module.module_name, is_package=package)
        for position, name in enumerate(reference.names):
            origins.setdefault(reference.local_name_of(position), set()).add((target, name))
    return frozenset(local for local, sources in origins.items() if len(sources) > 1)


def module_aliases(module: ParsedModule) -> dict[str, str]:
    """Modules importés en tant que tels : nom local → module, pour ``import a.b [as c]``."""
    package = is_package_file(module.file)
    resolver = resolver_for(module.file.language)
    aliases: dict[str, str] = {}
    for reference in module.imports:
        if reference.names:
            continue
        target = resolver.resolve(reference, module.module_name, is_package=package)
        if target:
            aliases[reference.alias or target] = target
    return aliases


def _strip_esm_extension(specifier: str) -> str:
    lowered = specifier.lower()
    for extension in _ESM_EXTENSIONS:
        if lowered.endswith(extension):
            return specifier[: -len(extension)]
    return specifier


def _resolve_relative_specifier(specifier: str, module_name: str, *, is_package: bool) -> str:
    current = module_name.split(".") if is_package else module_name.split(".")[:-1]
    for part in specifier.split("/"):
        if part in {".", ""}:
            continue
        if part == "..":
            if not current:
                return ""
            current = current[:-1]
            continue
        current.append(part)
    return ".".join(part for part in current if part)
