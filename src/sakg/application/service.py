"""Façade unique utilisée par la CLI, le serveur MCP et l'API REST (règle 2 d'AGENTS.md)."""

from collections.abc import Sequence
from pathlib import Path

from sakg.analysis import (
    ArchitectureDiff,
    ChangeRequest,
    DriftDetector,
    DriftReport,
    GraphDiffer,
    ImpactAnalyzer,
    ImpactReport,
)
from sakg.application.command_bus import CommandBus
from sakg.application.commands import ReplaceObservedLayerCommand
from sakg.application.events import EventBus
from sakg.domain import Node, NodeType, SakgError
from sakg.generation import Diagram, DiagramGenerator, DiagramView, MermaidGenerator
from sakg.graph import GraphQueryEngine, GraphSnapshot, KnowledgeGraph, SnapshotMeta, compute_graph_hash
from sakg.infrastructure import JsonGraphRepository
from sakg.infrastructure.config import ProjectConfig, create_architect_layout, current_commit_sha
from sakg.reverse import ReverseEngineeringPipeline
from sakg.validation import ArchitectureValidator, RuleLoader, ValidationReport

DIAGRAMS_DIR = "diagrams"


class UnknownFocusError(SakgError):
    """Aucun des nœuds demandés en focus n'existe dans le graphe."""


class ArchitectureService:
    """Opérations d'architecture d'un projet, du reverse engineering aux diagrammes.

    Le graphe est chargé depuis ``.architect/`` à la construction, et toute modification passe
    par le ``CommandBus`` (règle 4 d'AGENTS.md).

    Example:
        >>> service = ArchitectureService.for_project(Path("."))  # doctest: +SKIP
        >>> service.reverse()  # doctest: +SKIP
    """

    def __init__(
        self,
        root: Path,
        repository: JsonGraphRepository,
        graph: KnowledgeGraph,
        pipeline: ReverseEngineeringPipeline | None = None,
        events: EventBus | None = None,
        generator: DiagramGenerator | None = None,
    ) -> None:
        self.root = Path(root)
        self._repository = repository
        self._pipeline = pipeline if pipeline is not None else ReverseEngineeringPipeline.default()
        self._commands = CommandBus(graph, repository, events)
        self._query = GraphQueryEngine(graph)
        self._impact = ImpactAnalyzer(self._query)
        self._diagrams = generator if generator is not None else MermaidGenerator()
        self._differ = GraphDiffer()
        self.warnings: list[str] = []

    @classmethod
    def for_project(cls, root: Path, events: EventBus | None = None) -> "ArchitectureService":
        """Ouvre un projet et charge son graphe courant (vide s'il n'a jamais été analysé)."""
        repository = JsonGraphRepository(Path(root))
        return cls(root=Path(root), repository=repository, graph=repository.load(), events=events)

    @property
    def graph(self) -> KnowledgeGraph:
        """Graphe courant du projet."""
        return self._commands.graph

    def init_project(self, name: str | None = None) -> Path:
        """Crée ``.architect/`` et son ``project.yaml``, sans écraser une configuration existante."""
        create_architect_layout(self.root)
        config = ProjectConfig.default_for(self.root)
        if name:
            config = config.model_copy(update={"name": name})
        if not (self.root / ".architect" / "project.yaml").exists():
            config.save(self.root)
        return self.root / ".architect"

    def reverse(self, source_roots: Sequence[str] | None = None) -> GraphSnapshot:
        """Reconstruit la couche observée du graphe depuis le code et enregistre une version.

        Les chemins des identifiants sont toujours relatifs à la racine du projet : restreindre
        l'analyse à certains dossiers ne change pas les identifiants déjà enregistrés.
        Si l'architecture est inchangée, aucune version n'est créée.

        Args:
            source_roots: Dossiers à analyser ; ceux de ``project.yaml`` par défaut.

        Raises:
            FileNotFoundError: Si un dossier demandé n'existe pas.
        """
        if not self.root.is_dir():
            raise FileNotFoundError(f"racine de projet introuvable : {self.root}")
        create_architect_layout(self.root)
        roots = list(source_roots) if source_roots else self._configured_source_roots()
        self._commands.commit_sha = current_commit_sha(self.root)
        self.warnings = []
        reversed_project = self._pipeline.run_on(
            self.root,
            include=roots,
            commit_sha=self._commands.commit_sha,
            languages=self._configured_languages(),
        )
        extracted = reversed_project.graph
        self.warnings.extend(reversed_project.warnings)

        preview = self.graph.copy()
        ReplaceObservedLayerCommand(extracted).execute(preview)
        if compute_graph_hash(preview) == compute_graph_hash(self.graph):
            self.warnings.append("architecture inchangée : aucune nouvelle version enregistrée")
            return GraphSnapshot.of(self.graph)
        return self._commands.execute(ReplaceObservedLayerCommand(extracted))

    def search(self, text: str, types: Sequence[NodeType] | None = None, limit: int | None = None) -> list[Node]:
        """Nœuds dont le nom correspond au texte.

        Sans texte mais avec des types, retourne tous les nœuds de ces types : c'est ainsi
        qu'on demande l'inventaire des routes, des tables ou des conteneurs d'un projet.
        """
        if not text.strip() and types:
            return self._query.inventory(list(types), limit)
        return self._query.find(text, list(types) if types else None, limit)

    def dependencies(self, node_id: str, depth: int = 1) -> list[Node]:
        """Ce dont un nœud dépend."""
        return self._query.dependencies(node_id, depth)

    def dependents(self, node_id: str, depth: int = 1) -> list[Node]:
        """Ce qui dépend d'un nœud."""
        return self._query.dependents(node_id, depth)

    def impact(self, change: str, node_ids: Sequence[str] | None = None) -> ImpactReport:
        """Analyse l'impact d'un changement décrit en langage naturel."""
        return self._impact.analyze(ChangeRequest(description=change, target_node_ids=tuple(node_ids or ())))

    def diagram(self, view: DiagramView, focus: Sequence[str] | None = None) -> Diagram:
        """Génère un diagramme depuis le graphe courant.

        Raises:
            UnknownFocusError: Si aucun des nœuds demandés en focus n'existe ; sans quoi un
                identifiant mal saisi produirait un diagramme vide sans rien signaler.
        """
        return self._diagrams.generate(self.graph, view, self._checked_focus(focus))

    def write_diagram(self, view: DiagramView, focus: Sequence[str] | None = None, path: Path | None = None) -> Path:
        """Génère un diagramme et l'écrit sur disque, avec son en-tête.

        Par défaut dans ``.architect/diagrams/`` ; un diagramme restreint par ``focus`` est
        écrit à part, pour ne pas remplacer la vue complète par une vue partielle.
        """
        diagram = self.diagram(view, focus)
        if path is None:
            name = f"{view.value}-focus.md" if focus else f"{view.value}.md"
            path = self.root / ".architect" / DIAGRAMS_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Diagramme {view.value} — version {diagram.graph_version} du graphe\n\n"
        path.write_text(header + diagram.to_markdown(), encoding="utf-8")
        return path

    def snapshots(self) -> list[SnapshotMeta]:
        """Fiches des versions archivées du graphe."""
        return self._repository.list_snapshots()

    def validate(self) -> ValidationReport:
        """Vérifie les règles déclarées dans ``.architect/rules/*.yaml`` (UC08).

        Sans filtre configuré, toutes les règles trouvées s'appliquent ; ``rules`` dans
        ``project.yaml`` restreint l'exécution à un sous-ensemble d'identifiants, pour
        désactiver une règle sans supprimer son fichier.
        """
        rules = RuleLoader().load(self.root / ".architect" / "rules")
        active = set(self._configured_rule_ids())
        if active:
            rules = [rule for rule in rules if rule.id in active]
        return ArchitectureValidator(rules).validate(self.graph)

    def detect_drift(self) -> DriftReport:
        """Compare le graphe enregistré au code actuel, sans rien enregistrer (UC09).

        Seule la couche observée d'une copie du graphe est recalculée : un nœud ajouté à la
        main (``USER_DEFINED``) qui n'existe pas dans le code ne compte jamais comme une dérive.

        Raises:
            FileNotFoundError: Si la racine du projet n'existe pas.
        """
        if not self.root.is_dir():
            raise FileNotFoundError(f"racine de projet introuvable : {self.root}")
        reversed_project = self._pipeline.run_on(
            self.root,
            include=self._configured_source_roots(),
            commit_sha=current_commit_sha(self.root),
            languages=self._configured_languages(),
        )
        actual = self.graph.copy()
        ReplaceObservedLayerCommand(reversed_project.graph).execute(actual)
        return DriftDetector().detect(self.graph, actual)

    def diff(self, before: int, after: int) -> ArchitectureDiff:
        """Compare deux versions archivées du graphe.

        Raises:
            SnapshotNotFoundError: Si l'une des versions n'existe pas.
        """
        return self._differ.diff(self._repository.load_snapshot(before), self._repository.load_snapshot(after))

    def _checked_focus(self, focus: Sequence[str] | None) -> Sequence[str] | None:
        if not focus:
            return focus
        known = [node_id for node_id in focus if self._query.get_node(node_id) is not None]
        unknown = [node_id for node_id in focus if node_id not in known]
        self.warnings.extend(f"nœud de focus introuvable : {node_id}" for node_id in unknown)
        if not known:
            raise UnknownFocusError(f"aucun nœud ne correspond au focus demandé : {', '.join(focus)}")
        return known

    def _configured_source_roots(self) -> list[str]:
        try:
            return ProjectConfig.load(self.root).source_roots
        except FileNotFoundError:
            return ProjectConfig.default_for(self.root).source_roots

    def _configured_languages(self) -> list[str]:
        try:
            return ProjectConfig.load(self.root).languages
        except FileNotFoundError:
            return ProjectConfig.default_for(self.root).languages

    def _configured_rule_ids(self) -> list[str]:
        try:
            return ProjectConfig.load(self.root).rules
        except FileNotFoundError:
            return []
