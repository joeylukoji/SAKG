"""Scan du projet : quels fichiers analyser."""

import hashlib
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from sakg.reverse.languages import language_of
from sakg.reverse.models import ProjectContext, SourceFile

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".architect",
        ".claude",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        ".tox",
        ".idea",
        ".vscode",
        "site-packages",
    }
)


class ProjectScanner:
    """Parcourt un projet et retient les fichiers sources connus.

    Attributes:
        ignore_patterns: Noms de dossiers ignorés, en plus de la liste par défaut.

    Example:
        >>> context = ProjectScanner().scan(Path("src"))  # doctest: +SKIP
    """

    def __init__(self, ignore_patterns: Iterable[str] = ()) -> None:
        self.ignore_patterns = DEFAULT_IGNORED_DIRECTORIES | set(ignore_patterns)

    def scan(
        self,
        root: Path,
        *,
        include: Sequence[str] | None = None,
        commit_sha: str | None = None,
        languages: Sequence[str] | None = None,
    ) -> ProjectContext:
        """Construit le contexte du projet.

        Args:
            root: Racine du projet ; les chemins des identifiants lui sont relatifs.
            include: Sous-dossiers à analyser ; tout le projet si vide. Les chemins restent
                relatifs à ``root``, de sorte que restreindre l'analyse ne change pas les
                identifiants des nœuds (convention d'AGENTS.md).
            commit_sha: Commit analysé, repris dans la provenance.
            languages: Langages à retenir ; tous les suffixes connus si ``None``.

        Raises:
            FileNotFoundError: Si la racine ou un sous-dossier demandé n'existe pas.
        """
        root = Path(root).resolve()
        if not root.exists():
            raise FileNotFoundError(f"racine introuvable : {root}")
        prefixes = self._prefixes(root, include)
        allowed = set(languages) if languages is not None else None
        files = tuple(
            file
            for file in self._collect(root)
            if self._is_included(file.relative_path, prefixes) and (allowed is None or file.language in allowed)
        )
        return ProjectContext(
            root=root,
            files=files,
            languages=frozenset(file.language for file in files),
            commit_sha=commit_sha,
            include=prefixes,
        )

    @staticmethod
    def _prefixes(root: Path, include: Sequence[str] | None) -> tuple[str, ...]:
        prefixes: list[str] = []
        for name in include or ():
            directory = (root / name).resolve()
            if not directory.exists():
                raise FileNotFoundError(f"dossier à analyser introuvable : {directory}")
            relative = directory.relative_to(root).as_posix()
            prefixes.append("" if relative == "." else relative)
        return tuple(prefixes)

    @staticmethod
    def _is_included(relative_path: str, prefixes: tuple[str, ...]) -> bool:
        return not prefixes or any(
            prefix == "" or relative_path == prefix or relative_path.startswith(f"{prefix}/") for prefix in prefixes
        )

    def _collect(self, root: Path) -> Iterable[SourceFile]:
        for directory, subdirectories, filenames in os.walk(root):
            # Élagage en place : les dossiers ignorés ne sont pas parcourus du tout.
            subdirectories[:] = sorted(name for name in subdirectories if name not in self.ignore_patterns)
            for filename in sorted(filenames):
                path = Path(directory) / filename
                language = language_of(path)
                if language is None:
                    continue
                yield SourceFile(
                    path=path,
                    relative_path=path.relative_to(root).as_posix(),
                    language=language,
                    content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
