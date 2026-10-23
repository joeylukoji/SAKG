"""Pipeline de reverse engineering : scan → extracteurs → graphe."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sakg.domain import OntologySchema
from sakg.graph import KnowledgeGraph
from sakg.reverse.database import DatabaseExtractor
from sakg.reverse.extractors import ApiExtractor, CodeStructureExtractor, Extractor
from sakg.reverse.graph_builder import GraphBuilder
from sakg.reverse.infrastructure import InfrastructureExtractor
from sakg.reverse.models import ProjectContext
from sakg.reverse.parser import ParserRegistry
from sakg.reverse.python_parser import PythonAstParser
from sakg.reverse.scanner import ProjectScanner
from sakg.reverse.typescript_parser import TypeScriptParser


@dataclass(frozen=True)
class ReverseResult:
    """Ce qu'un reverse a produit.

    Attributes:
        graph: Graphe extrait du code.
        warnings: Difficultés rencontrées, par exemple un fichier illisible.
    """

    graph: KnowledgeGraph
    warnings: tuple[str, ...] = ()


class ReverseEngineeringPipeline:
    """Exécute les extracteurs dans l'ordre et fusionne leurs résultats.

    Le résultat est retourné, jamais conservé : un même pipeline peut analyser plusieurs
    projets, y compris en parallèle.

    Example:
        >>> pipeline = ReverseEngineeringPipeline.default()
        >>> result = pipeline.run(ProjectScanner().scan(Path("src")))  # doctest: +SKIP
    """

    def __init__(
        self,
        registry: ParserRegistry,
        extractors: list[Extractor] | None = None,
        schema: OntologySchema | None = None,
    ) -> None:
        self._registry = registry
        self._extractors: list[Extractor] = list(extractors or [])
        self._schema = schema if schema is not None else OntologySchema.default()

    @classmethod
    def default(cls, schema: OntologySchema | None = None) -> "ReverseEngineeringPipeline":
        """Pipeline standard : structure du code, endpoints HTTP, tables et conteneurs."""
        return cls(
            ParserRegistry([PythonAstParser(), TypeScriptParser()]),
            [CodeStructureExtractor(), ApiExtractor(), DatabaseExtractor(), InfrastructureExtractor()],
            schema,
        )

    @property
    def extractors(self) -> list[Extractor]:
        """Extracteurs enregistrés, dans l'ordre d'exécution."""
        return sorted(self._extractors, key=lambda extractor: extractor.order)

    def add_extractor(self, extractor: Extractor) -> None:
        """Enregistre un extracteur supplémentaire (règle 6 d'AGENTS.md)."""
        self._extractors.append(extractor)

    def run(self, context: ProjectContext) -> ReverseResult:
        """Analyse le projet et retourne le graphe extrait avec ses avertissements."""
        builder = GraphBuilder(self._schema)
        try:
            for extractor in self.extractors:
                builder.add(extractor.extract(context, self._registry))
        finally:
            self._registry.clear_cache()  # le cache sert à un reverse, pas à la vie du processus
        graph = builder.build()
        return ReverseResult(graph=graph, warnings=tuple(builder.warnings))

    def run_on(
        self,
        root: Path,
        *,
        include: Sequence[str] | None = None,
        commit_sha: str | None = None,
        languages: Sequence[str] | None = None,
    ) -> ReverseResult:
        """Scanne puis analyse un projet, éventuellement restreint à certains sous-dossiers."""
        return self.run(
            ProjectScanner().scan(root, include=include, commit_sha=commit_sha, languages=languages)
        )
