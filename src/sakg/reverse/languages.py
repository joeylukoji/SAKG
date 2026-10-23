"""Langages connus du reverse : suffixes, paquets, noms de modules.

Le scanner et les parseurs s'appuient sur cette table ; ajouter un langage commence ici,
puis par un ``LanguageParser`` enregistré (règle 6 d'AGENTS.md).
"""

from pathlib import Path

from sakg.reverse.models import SourceFile

LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".dart": "dart",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".php": "php",
    ".go": "go",
    ".rb": "ruby",
}

PACKAGE_INDEX_STEMS: dict[str, frozenset[str]] = {
    "python": frozenset({"__init__"}),
    "typescript": frozenset({"index"}),
    "javascript": frozenset({"index"}),
    "dart": frozenset({"index"}),
}

DEFAULT_SOURCE_ROOTS = ("src",)

_SKIP_SUFFIXES = (".d.ts", ".min.js", ".min.mjs", ".min.cjs")


def detection_tag(language: str, event: str) -> str:
    """Identifiant de méthode de détection, stable pour le hash du graphe.

    Python conserve le préfixe historique ``PYTHON_AST_`` (ADR-005) ; les autres langages
    utilisent ``<LANGAGE>_<événement>``.
    """
    if language == "python":
        return f"PYTHON_AST_{event}"
    return f"{language.upper()}_{event}"


def language_of(path: Path | str) -> str | None:
    """Langage déduit du suffixe, ou ``None`` pour un fichier hors reverse."""
    name = Path(path).name
    lowered = name.lower()
    if any(lowered.endswith(suffix) for suffix in _SKIP_SUFFIXES):
        return None
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def is_package_file(file: SourceFile) -> bool:
    """Indique si le fichier est l'index d'un paquet (``__init__.py``, ``index.ts``…)."""
    stem = Path(file.relative_path).stem
    return stem in PACKAGE_INDEX_STEMS.get(file.language, ())


def module_name_of(
    relative_path: str,
    language: str | None = None,
    source_roots: tuple[str, ...] = DEFAULT_SOURCE_ROOTS,
) -> str:
    """Nom de module pointé déduit d'un chemin relatif.

    Les racines de sources (``src`` par défaut) et le fichier d'index du paquet sont retirés
    pour que ``src/sakg/domain/__init__.py`` donne ``sakg.domain``, et ``src/app/index.ts``
    donne ``app``.

    Example:
        >>> module_name_of("src/sakg/domain/node.py")
        'sakg.domain.node'
        >>> module_name_of("src/app/users.ts", "typescript")
        'app.users'
    """
    posix = relative_path.replace("\\", "/")
    detected = language or language_of(posix) or "python"
    stem_path = posix
    for suffix in sorted(LANGUAGE_BY_SUFFIX, key=len, reverse=True):
        if stem_path.lower().endswith(suffix):
            stem_path = stem_path[: -len(suffix)]
            break
    parts = [part for part in stem_path.split("/") if part]
    while parts and parts[0] in source_roots:
        parts = parts[1:]
    if parts and parts[-1] in PACKAGE_INDEX_STEMS.get(detected, ()):
        parts = parts[:-1]
    return ".".join(parts)
