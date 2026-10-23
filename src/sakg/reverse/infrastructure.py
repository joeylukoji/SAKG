"""Extraction de la couche infrastructure : conteneurs déclarés par ``docker-compose``.

Un fichier compose décrit où le code tourne. Ces nœuds rattachent l'architecture applicative
à son déploiement, sans exécuter Docker ni résoudre les variables d'environnement.
"""

import os
from pathlib import Path
from typing import Any

import yaml

from sakg.domain import Node, NodeType, RelationType, make_node_id
from sakg.reverse.extraction import edge, node_provenance
from sakg.reverse.models import ExtractionResult, ProjectContext
from sakg.reverse.parser import ParserRegistry
from sakg.reverse.scanner import DEFAULT_IGNORED_DIRECTORIES

COMPOSE_PATTERNS = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
"""Noms exacts : un fichier d'override (``docker-compose.override.yml``) redéfinit des services
déjà déclarés, et le fusionner correctement demande la sémantique de Docker Compose. Hors
périmètre tant qu'on ne sait pas la reproduire fidèlement."""

UNRESOLVED_MARKER = "${"
"""Une image dont le tag vient d'une variable d'environnement n'est pas connue statiquement."""


class InfrastructureExtractor:
    """Services d'un ``docker-compose`` : conteneurs, images et dépendances entre eux.

    Le fichier compose n'est pas du code source : il est cherché directement sur le disque
    plutôt que dans les fichiers analysés par les parsers.
    """

    name = "infrastructure"
    order = 40

    def extract(self, context: ProjectContext, registry: ParserRegistry) -> ExtractionResult:
        """Construit les nœuds ``Container`` et ``Technology`` d'un projet conteneurisé."""
        result = ExtractionResult()
        for relative in self._compose_files(context):
            services = self._read_services(context.root / relative, relative, result)
            if services:
                self._add_services(services, relative, context, result)
        return result

    @staticmethod
    def _compose_files(context: ProjectContext) -> list[str]:
        """Chemins des fichiers compose, dossiers ignorés et périmètre demandé respectés.

        Le parcours élague les dossiers ignorés au lieu de les traverser : un ``.venv`` ou un
        ``node_modules`` coûterait plus cher à explorer que tout le reste du projet.
        """
        found: list[str] = []
        for directory, subdirectories, filenames in os.walk(context.root):
            subdirectories[:] = sorted(name for name in subdirectories if name not in DEFAULT_IGNORED_DIRECTORIES)
            for filename in sorted(filenames):
                if filename not in COMPOSE_PATTERNS:
                    continue
                relative = (Path(directory) / filename).relative_to(context.root).as_posix()
                if context.covers(relative):
                    found.append(relative)
        return found

    def _read_services(self, path: Path, relative: str, result: ExtractionResult) -> dict[str, Any]:
        """Section ``services`` du fichier, ou vide s'il est illisible."""
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            result.warnings.append(f"{self.name} : {relative} illisible ({error.__class__.__name__})")
            return {}
        if not isinstance(document, dict):
            return {}
        services = document.get("services")
        return services if isinstance(services, dict) else {}

    def _add_services(
        self, services: dict[str, Any], relative: str, context: ProjectContext, result: ExtractionResult
    ) -> None:
        file_node = Node(
            id=make_node_id(NodeType.FILE, relative, Path(relative).name),
            type=NodeType.FILE,
            name=Path(relative).name,
            properties={"language": "yaml", "kind": "docker-compose"},
            provenance=node_provenance(context, relative, detected_by="DOCKER_COMPOSE_FILE"),
        )
        result.nodes.append(file_node)
        containers = {name: make_node_id(NodeType.CONTAINER, relative, name) for name in services}

        for service_name, definition in services.items():
            settings = definition if isinstance(definition, dict) else {}
            container = Node(
                id=containers[service_name],
                type=NodeType.CONTAINER,
                name=service_name,
                properties=_service_properties(settings),
                provenance=node_provenance(context, relative, detected_by="DOCKER_COMPOSE_SERVICE"),
            )
            result.nodes.append(container)
            result.edges.append(
                edge(file_node.id, RelationType.CONTAINS, container.id, context, relative, "DOCKER_COMPOSE_SERVICE")
            )
            self._add_image(container, settings, relative, context, result)
            self._add_dependencies(container, settings, containers, relative, context, result)

    def _add_image(
        self,
        container: Node,
        settings: dict[str, Any],
        relative: str,
        context: ProjectContext,
        result: ExtractionResult,
    ) -> None:
        image = settings.get("image")
        if not isinstance(image, str) or not image:
            return
        if UNRESOLVED_MARKER in image:
            result.warnings.append(
                f"{self.name} : image « {image} » du service {container.name} dépend d'une variable "
                "d'environnement, technologie non enregistrée"
            )
            return
        technology = Node(
            # Sans le chemin du fichier : une technologie est la même partout dans le projet.
            id=make_node_id(NodeType.TECHNOLOGY, "", image),
            type=NodeType.TECHNOLOGY,
            name=image,
            properties={"kind": "image"},
            provenance=node_provenance(context, relative, detected_by="DOCKER_COMPOSE_IMAGE"),
        )
        result.nodes.append(technology)
        result.edges.append(
            edge(
                container.id,
                RelationType.USES_TECHNOLOGY,
                technology.id,
                context,
                relative,
                "DOCKER_COMPOSE_IMAGE",
            )
        )

    def _add_dependencies(
        self,
        container: Node,
        settings: dict[str, Any],
        containers: dict[str, str],
        relative: str,
        context: ProjectContext,
        result: ExtractionResult,
    ) -> None:
        for dependency in _declared_dependencies(settings):
            target = containers.get(dependency)
            if target is None or target == container.id:
                continue
            result.edges.append(
                edge(
                    container.id,
                    RelationType.DEPENDS_ON,
                    target,
                    context,
                    relative,
                    "DOCKER_COMPOSE_DEPENDS_ON",
                )
            )


def _declared_dependencies(settings: dict[str, Any]) -> list[str]:
    """Services dont celui-ci dépend, que la forme soit une liste ou un dictionnaire de conditions."""
    declared = settings.get("depends_on")
    if isinstance(declared, list):
        return [name for name in declared if isinstance(name, str)]
    if isinstance(declared, dict):
        return [name for name in declared if isinstance(name, str)]
    return []


def _service_properties(settings: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'on retient d'un service : image, ports exposés et contexte de construction."""
    properties: dict[str, Any] = {}
    image = settings.get("image")
    if isinstance(image, str):
        properties["image"] = image
    ports = settings.get("ports")
    if isinstance(ports, list):
        properties["ports"] = [str(port) for port in ports]
    build = settings.get("build")
    if isinstance(build, str):
        properties["build"] = build
    elif isinstance(build, dict) and isinstance(build.get("context"), str):
        properties["build"] = build["context"]
    return properties
