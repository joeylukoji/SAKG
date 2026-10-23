"""Configuration du projet : ``.architect/project.yaml``."""

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sakg.infrastructure.json_graph_repository import ARCHITECT_DIR

PROJECT_FILE = "project.yaml"
ARCHITECT_SUBDIRECTORIES = ("graph", "versions", "decisions", "rules", "diagrams", "proposals", "audit")


class ProjectConfig(BaseModel):
    """Métadonnées du projet analysé.

    Attributes:
        name: Nom du projet.
        languages: Langages attendus dans le code source.
        source_roots: Dossiers analysés par ``sakg reverse``, relatifs à la racine.
        ignore: Dossiers ignorés en plus de la liste par défaut du scanner.
        rules: Règles d'architecture actives (utilisées à partir du sprint 9).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    languages: list[str] = Field(default_factory=lambda: ["python"])
    source_roots: list[str] = Field(default_factory=lambda: ["src"])
    ignore: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)

    @classmethod
    def default_for(cls, root: Path) -> "ProjectConfig":
        """Configuration déduite d'un projet : ``src/`` s'il existe, la racine sinon."""
        source_roots = ["src"] if (root / "src").is_dir() else ["."]
        return cls(name=root.resolve().name, source_roots=source_roots)

    @classmethod
    def load(cls, root: Path) -> "ProjectConfig":
        """Lit ``.architect/project.yaml``.

        Raises:
            ProjectNotInitializedError: Si le fichier n'existe pas.
        """
        path = config_path(root)
        if not path.exists():
            raise ProjectNotInitializedError(f"projet non initialisé : {path} est absent (lancer « sakg init »)")
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def save(self, root: Path) -> Path:
        """Écrit la configuration et retourne son chemin."""
        path = config_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return path


class ProjectNotInitializedError(FileNotFoundError):
    """Le dossier ``.architect/`` n'a pas encore été créé."""


def config_path(root: Path) -> Path:
    """Chemin du fichier de configuration d'un projet."""
    return Path(root) / ARCHITECT_DIR / PROJECT_FILE


def create_architect_layout(root: Path) -> Path:
    """Crée l'arborescence ``.architect/`` et retourne son chemin."""
    architect = Path(root) / ARCHITECT_DIR
    for name in ARCHITECT_SUBDIRECTORIES:
        (architect / name).mkdir(parents=True, exist_ok=True)
    return architect


def current_commit_sha(root: Path) -> str | None:
    """Commit courant du dépôt Git, ou ``None`` hors dépôt ou si Git est indisponible."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None
