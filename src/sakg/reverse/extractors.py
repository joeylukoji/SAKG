"""Extracteurs : du ``ParsedModule`` aux nœuds et relations du graphe.

Principe de prudence : une relation n'est créée que si sa cible est **visible** depuis le
module analysé (définie sur place, ou importée depuis un module du projet). Un nom qui
désigne peut-être une bibliothèque tierce ne produit aucune relation, plutôt qu'une relation
vers un homonyme du projet.
"""

from dataclasses import dataclass, field
from typing import Protocol

from sakg.domain import EvidenceType, Node, NodeType, RelationType, make_node_id
from sakg.reverse.adapters import FastApiAdapter, FrameworkAdapter, NextJsAdapter, RouterContext, join_paths
from sakg.reverse.extraction import (
    CALLABLE_TYPES,
    NODE_KIND_TO_TYPE,
    edge,
    node_provenance,
    parse_modules,
    top_level_symbols,
)
from sakg.reverse.imports import import_bindings, module_aliases, rebound_names, resolve_import
from sakg.reverse.languages import detection_tag, is_package_file, module_name_of
from sakg.reverse.models import ExtractionResult, ImportRef, ParsedModule, ProjectContext, SourceFile, Symbol
from sakg.reverse.parser import ParserRegistry

CALL_CONFIDENCE = 0.6
"""Un appel est résolu par nom, sans analyse de types : relation INFERRED (ARCHITECTURE §3.4)."""

MAX_REEXPORT_DEPTH = 8
"""Garde-fou contre les ré-exportations circulaires entre paquets."""

MAX_BASE_DEPTH = 10
"""Garde-fou contre les hiérarchies d'héritage cycliques dans du code invalide."""


class Extractor(Protocol):
    """Étape indépendante du pipeline de reverse engineering."""

    @property
    def name(self) -> str:
        """Nom de l'extracteur, repris dans les avertissements."""
        ...

    @property
    def order(self) -> int:
        """Rang d'exécution ; les plus petits passent en premier."""
        ...

    def extract(self, context: ProjectContext, registry: ParserRegistry) -> ExtractionResult:
        """Analyse le projet et retourne ce qu'il a trouvé."""
        ...


@dataclass
class _ModuleEntry:
    """Ce que l'index retient d'un fichier analysé."""

    module: ParsedModule
    file_node_id: str
    symbol_ids: dict[str, str] = field(default_factory=dict)
    symbol_types: dict[str, NodeType] = field(default_factory=dict)
    bases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def module_name(self) -> str:
        return self.module.module_name

    @property
    def is_package(self) -> bool:
        return is_package_file(self.module.file)


class _ProjectIndex:
    """Index des modules du projet, avec leurs symboles.

    Les entrées sont indexées par chemin relatif : deux fichiers peuvent porter le même nom
    de module (``src/conf.py`` et ``conf.py``). Un tel nom devient ambigu et ne résout plus
    rien, ce qui est signalé en avertissement.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _ModuleEntry] = {}
        self._by_module: dict[str, _ModuleEntry | None] = {}
        self._by_node_id: dict[str, tuple[_ModuleEntry, str]] = {}
        self._bindings: dict[str, tuple[dict[str, tuple[str, str]], frozenset[str]]] = {}
        self.warnings: list[str] = []

    def add(self, entry: _ModuleEntry) -> None:
        self._entries[entry.module.file.relative_path] = entry
        for qualified, node_id in entry.symbol_ids.items():
            self._by_node_id[node_id] = (entry, qualified)
        if entry.module_name in self._by_module:
            previous = self._by_module[entry.module_name]
            if previous is not None:
                self.warnings.append(
                    f"nom de module ambigu, résolution désactivée pour {entry.module_name!r} : "
                    f"{previous.module.file.relative_path} et {entry.module.file.relative_path}"
                )
            self._by_module[entry.module_name] = None
        else:
            self._by_module[entry.module_name] = entry

    def entries(self) -> list[_ModuleEntry]:
        return list(self._entries.values())

    def entry_of_module(self, module_name: str) -> _ModuleEntry | None:
        """Entrée d'un module du projet, ou ``None`` si inconnu ou ambigu."""
        return self._by_module.get(module_name)

    def knows_module(self, module_name: str) -> bool:
        return self._by_module.get(module_name) is not None

    def resolve_export(self, module_name: str, name: str) -> tuple[_ModuleEntry, str] | None:
        """Module qui définit réellement ``name`` tel qu'on l'importe depuis ``module_name``.

        ``from sakg.domain import SakgError`` vise un paquet qui ne fait que ré-exporter la
        classe, définie dans ``sakg.domain.errors``. Le ``__init__.py`` le dit en toutes lettres
        (``from sakg.domain.errors import SakgError``) : suivre cette chaîne n'invente rien.

        Un nom est ambigu — et rien n'est résolu — s'il est lié par des imports d'origines
        différentes (repli ``try/except ImportError``), ou à la fois défini et importé dans le
        même module : ce qui s'applique dépend de l'exécution.
        """
        for _ in range(MAX_REEXPORT_DEPTH):
            entry = self.entry_of_module(module_name)
            if entry is None:
                return None
            bindings, rebound = self._bindings_of(entry)
            defined = name in entry.symbol_ids
            if name in rebound or (defined and name in bindings):
                self._note_ambiguity(entry, name)
                return None
            if defined:
                return entry, name
            origin = bindings.get(name)
            if origin is None:
                return None
            module_name, name = origin
        return None

    def _bindings_of(self, entry: _ModuleEntry) -> tuple[dict[str, tuple[str, str]], frozenset[str]]:
        """Liaisons visibles depuis les autres fichiers : imports du niveau module seulement."""
        key = entry.module.file.relative_path
        if key not in self._bindings:
            self._bindings[key] = (
                import_bindings(entry.module, module_level_only=True),
                rebound_names(entry.module, module_level_only=True),
            )
        return self._bindings[key]

    def _note_ambiguity(self, entry: _ModuleEntry, name: str) -> None:
        message = (
            f"« {name} » est lié plusieurs fois dans {entry.module.file.relative_path} "
            "(repli d'import ou redéfinition) : aucune relation vers lui n'est créée"
        )
        if message not in self.warnings:
            self.warnings.append(message)

    def locate(self, node_id: str) -> tuple[_ModuleEntry, str] | None:
        """Module et nom qualifié d'un nœud déjà créé."""
        return self._by_node_id.get(node_id)


class _NameResolver:
    """Résout un nom pointé tel qu'il est visible depuis un module donné.

    Les noms visibles sont : les symboles définis dans le module, les noms importés depuis un
    module du projet, et les modules du projet importés. Tout le reste (bibliothèque tierce,
    variable locale, attribut d'instance) n'est pas résolu.
    """

    def __init__(self, index: _ProjectIndex, entry: _ModuleEntry) -> None:
        self._index = index
        self._entry = entry
        self._imported_names: dict[str, tuple[str, str]] = {}  # nom local -> (module, nom d'origine)
        self._imported_modules: dict[str, str] = {}  # alias local -> module
        self._build_bindings()

    def _build_bindings(self) -> None:
        for import_ref in self._entry.module.imports:  # import a.b.c [as d]
            if import_ref.names:
                continue
            target = resolve_import(
                import_ref,
                self._entry.module_name,
                is_package=self._entry.is_package,
                language=self._entry.module.file.language,
            )
            if target and self._index.knows_module(target):
                self._imported_modules[import_ref.alias or target] = target

        ambiguous = rebound_names(self._entry.module)
        for local, (target, name) in import_bindings(self._entry.module).items():  # from a.b import c [as d]
            if local in ambiguous:
                continue  # repli try/except : lequel s'exécute n'est pas observable
            submodule = f"{target}.{name}"
            if self._index.knows_module(submodule):
                self._imported_modules[local] = submodule
            elif self._index.knows_module(target):
                self._imported_names[local] = (target, name)

    def resolve(self, dotted_name: str, *, caller_class: str | None = None) -> tuple[str, NodeType] | None:
        """Nœud désigné par ``dotted_name``, avec son type ; ``None`` si le nom n'est pas visible."""
        if not dotted_name:
            return None
        if dotted_name.startswith(("self.", "this.")) and caller_class is not None:
            attribute = dotted_name.split(".", 1)[1]
            return self._resolve_attribute_on_class(self._entry, caller_class, attribute, 0)
        local = self._symbol_in(self._entry, dotted_name)
        if local is not None:
            return local
        head, _, rest = dotted_name.partition(".")
        if head in self._imported_names:
            module_name, original = self._imported_names[head]
            exported = self._index.resolve_export(module_name, original)
            if exported is None:
                return None
            entry, defined_as = exported
            qualified = f"{defined_as}.{rest}" if rest else defined_as
            return self._symbol_in(entry, qualified)
        binding = self._longest_imported_module(dotted_name)
        if binding is not None:
            alias, module_name = binding
            qualified = dotted_name[len(alias) + 1 :]
            if not qualified:
                return None
            head_name, _, remainder = qualified.partition(".")
            exported = self._index.resolve_export(module_name, head_name)
            if exported is None:
                return None
            entry, defined_as = exported
            return self._symbol_in(entry, f"{defined_as}.{remainder}" if remainder else defined_as)
        return None

    def _longest_imported_module(self, dotted_name: str) -> tuple[str, str] | None:
        """Alias de module le plus long qui préfixe le nom, par exemple ``core.base`` dans ``core.base.X``."""
        candidates = [alias for alias in self._imported_modules if dotted_name.startswith(f"{alias}.")]
        if not candidates:
            return None
        alias = max(candidates, key=len)
        return alias, self._imported_modules[alias]

    def _resolve_attribute_on_class(
        self, entry: _ModuleEntry | None, class_qualified: str, attribute: str, depth: int
    ) -> tuple[str, NodeType] | None:
        """Cherche ``attribute`` sur la classe, puis sur ses classes de base connues."""
        if entry is None or depth > MAX_BASE_DEPTH:
            return None
        found = self._symbol_in(entry, f"{class_qualified}.{attribute}")
        if found is not None:
            return found
        for base in entry.bases.get(class_qualified, ()):
            resolved = _NameResolver(self._index, entry).resolve(base)
            if resolved is None or resolved[1] is not NodeType.CLASS:
                continue
            located = self._index.locate(resolved[0])
            if located is not None:
                base_entry, base_qualified = located
                inherited = self._resolve_attribute_on_class(base_entry, base_qualified, attribute, depth + 1)
                if inherited is not None:
                    return inherited
        return None

    @staticmethod
    def _symbol_in(entry: _ModuleEntry | None, qualified_name: str) -> tuple[str, NodeType] | None:
        if entry is None or qualified_name not in entry.symbol_ids:
            return None
        return entry.symbol_ids[qualified_name], entry.symbol_types[qualified_name]


class CodeStructureExtractor:
    """Fichiers, classes, fonctions, méthodes, héritage, imports et appels.

    Les relations dont la cible est extérieure au projet (bibliothèque tierce, classe de base
    inconnue) sont ignorées : le graphe ne contient que ce qui est observable dans le code.
    Les imports sous ``if TYPE_CHECKING`` produisent une dépendance comme les autres.
    """

    name = "code_structure"
    order = 10

    def extract(self, context: ProjectContext, registry: ParserRegistry) -> ExtractionResult:
        """Parse chaque fichier, crée les nœuds, puis résout les relations."""
        result = ExtractionResult()
        modules, unparsed, warnings = parse_modules(context, registry, self.name)
        result.warnings.extend(warnings)
        index = _ProjectIndex()
        for module in modules:
            self._add_nodes(module, context, result, index)
        for file in unparsed:
            self._add_unparsed_file(file, context, result)
        for entry in index.entries():
            self._add_edges(entry, context, result, index)
        # Après les relations : certaines ambiguïtés ne se découvrent qu'en les résolvant.
        result.warnings.extend(index.warnings)
        return result

    def _add_unparsed_file(self, file: SourceFile, context: ProjectContext, result: ExtractionResult) -> None:
        """Nœud fichier sans symboles : le langage est vu, pas encore analysé."""
        path = file.relative_path
        module = module_name_of(path, file.language)
        result.nodes.append(
            Node(
                id=make_node_id(NodeType.FILE, path, module),
                type=NodeType.FILE,
                name=file.path.name,
                properties={"module": module, "language": file.language},
                provenance=node_provenance(context, path, detected_by="FILE_SCAN"),
            )
        )

    def _add_nodes(
        self, module: ParsedModule, context: ProjectContext, result: ExtractionResult, index: _ProjectIndex
    ) -> None:
        path = module.file.relative_path
        file_node = Node(
            id=make_node_id(NodeType.FILE, path, module.module_name),
            type=NodeType.FILE,
            name=module.file.path.name,
            properties={"module": module.module_name, "language": module.file.language},
            provenance=node_provenance(context, path, detected_by=detection_tag(module.file.language, "FILE_SCAN")),
        )
        result.nodes.append(file_node)
        entry = _ModuleEntry(module=module, file_node_id=file_node.id)

        for symbol in top_level_symbols(module):
            node_type = NODE_KIND_TO_TYPE[symbol.kind]
            node = Node(
                id=make_node_id(node_type, path, symbol.qualified_name),
                type=node_type,
                name=symbol.name,
                properties={"qualified_name": symbol.qualified_name, "module": module.module_name},
                provenance=node_provenance(
                    context,
                    path,
                    detected_by=detection_tag(module.file.language, f"{symbol.kind.upper()}_DEF"),
                    line=symbol.line,
                    end_line=symbol.end_line,
                ),
            )
            result.nodes.append(node)
            entry.symbol_ids[symbol.qualified_name] = node.id
            entry.symbol_types[symbol.qualified_name] = node_type
            if symbol.kind == "class":
                entry.bases[symbol.qualified_name] = symbol.bases
        index.add(entry)

    def _add_edges(
        self, entry: _ModuleEntry, context: ProjectContext, result: ExtractionResult, index: _ProjectIndex
    ) -> None:
        resolver = _NameResolver(index, entry)
        path = entry.module.file.relative_path

        for symbol in top_level_symbols(entry.module):
            node_id = entry.symbol_ids[symbol.qualified_name]
            if symbol.kind == "method":
                owner_id = entry.symbol_ids[symbol.qualified_name.rsplit(".", 1)[0]]
                detected_by = detection_tag(entry.module.file.language, "CLASS_CONTAINS")
            else:
                owner_id, detected_by = (
                    entry.file_node_id,
                    detection_tag(entry.module.file.language, "FILE_CONTAINS"),
                )
            result.edges.append(edge(owner_id, RelationType.CONTAINS, node_id, context, path, detected_by, symbol.line))
            if symbol.kind == "class":
                self._add_inheritance_edges(symbol, node_id, entry, resolver, context, result)

        self._add_import_edges(entry, index, context, result)
        self._add_call_edges(entry, resolver, context, result)

    def _add_inheritance_edges(
        self,
        symbol: Symbol,
        node_id: str,
        entry: _ModuleEntry,
        resolver: _NameResolver,
        context: ProjectContext,
        result: ExtractionResult,
    ) -> None:
        for base in symbol.bases:
            resolved = resolver.resolve(base)
            if resolved is None or resolved[1] is not NodeType.CLASS or resolved[0] == node_id:
                continue
            result.edges.append(
                edge(
                    node_id,
                    RelationType.INHERITS,
                    resolved[0],
                    context,
                    entry.module.file.relative_path,
                    detection_tag(entry.module.file.language, "INHERITANCE"),
                    symbol.line,
                )
            )

    def _add_import_edges(
        self, entry: _ModuleEntry, index: _ProjectIndex, context: ProjectContext, result: ExtractionResult
    ) -> None:
        first_import: dict[str, ImportRef] = {}
        runtime_targets: set[str] = set()
        for import_ref in entry.module.imports:
            target = resolve_import(
                import_ref,
                entry.module_name,
                is_package=entry.is_package,
                language=entry.module.file.language,
            )
            if not target:
                continue
            # `from pkg import sub` désigne le sous-module quand il existe, pas seulement le paquet.
            for candidate in [target, *(f"{target}.{name}" for name in import_ref.names)]:
                target_entry = index.entry_of_module(candidate)
                if target_entry is None or target_entry.file_node_id == entry.file_node_id:
                    continue
                first_import.setdefault(target_entry.file_node_id, import_ref)
                if not import_ref.type_only:
                    runtime_targets.add(target_entry.file_node_id)

        self._add_symbol_import_edges(entry, index, context, result)

        for target_id, import_ref in first_import.items():
            dependency = edge(
                entry.file_node_id,
                RelationType.DEPENDS_ON,
                target_id,
                context,
                entry.module.file.relative_path,
                detection_tag(entry.module.file.language, "IMPORT_ANALYSIS"),
                import_ref.line,
            )
            if target_id not in runtime_targets:
                # Dépendance de typage seulement : elle ne pèse pas à l'exécution. Un même module
                # importé aussi à l'exécution reste une dépendance ordinaire.
                dependency = dependency.model_copy(update={"properties": {"type_only": True}})
            result.edges.append(dependency)

    def _add_symbol_import_edges(
        self, entry: _ModuleEntry, index: _ProjectIndex, context: ProjectContext, result: ExtractionResult
    ) -> None:
        """``from core.base import BaseService`` : ce fichier dépend de cette classe précise.

        Sans cette relation, demander « qui utilise cette classe ? » ne répondrait rien, les
        imports n'étant enregistrés qu'entre fichiers. ``import pkg`` puis ``pkg.Base`` ne
        crée pas cette relation : l'import désigne le module, qui a déjà sa relation fichier.

        Comme pour les fichiers, un symbole importé aussi à l'exécution reste une dépendance
        ordinaire, quel que soit l'ordre des imports ; un nom lié à des origines différentes
        n'est relié à rien.
        """
        ambiguous = rebound_names(entry.module)
        first_import: dict[str, ImportRef] = {}
        runtime_symbols: set[str] = set()
        for import_ref in entry.module.imports:
            module_name = resolve_import(
                import_ref,
                entry.module_name,
                is_package=entry.is_package,
                language=entry.module.file.language,
            )
            if not module_name:
                continue
            for position, name in enumerate(import_ref.names):
                if import_ref.local_name_of(position) in ambiguous:
                    continue
                exported = index.resolve_export(module_name, name)
                if exported is None:
                    continue
                target_entry, defined_as = exported
                if target_entry.symbol_types[defined_as] not in {NodeType.CLASS, NodeType.FUNCTION}:
                    continue
                symbol = target_entry.symbol_ids[defined_as]
                first_import.setdefault(symbol, import_ref)
                if not import_ref.type_only:
                    runtime_symbols.add(symbol)

        for symbol, import_ref in first_import.items():
            dependency = edge(
                entry.file_node_id,
                RelationType.DEPENDS_ON,
                symbol,
                context,
                entry.module.file.relative_path,
                detection_tag(entry.module.file.language, "SYMBOL_IMPORT"),
                import_ref.line,
            )
            if symbol not in runtime_symbols:
                dependency = dependency.model_copy(update={"properties": {"type_only": True}})
            result.edges.append(dependency)

    def _add_call_edges(
        self, entry: _ModuleEntry, resolver: _NameResolver, context: ProjectContext, result: ExtractionResult
    ) -> None:
        seen: set[tuple[str, str]] = set()
        for call in entry.module.calls:
            caller_qualified = _enclosing_symbol(entry, call.caller)
            if caller_qualified is None or entry.symbol_types[caller_qualified] not in CALLABLE_TYPES:
                continue
            caller_id = entry.symbol_ids[caller_qualified]
            caller_class = (
                caller_qualified.rsplit(".", 1)[0] if entry.symbol_types[caller_qualified] is NodeType.METHOD else None
            )
            resolved = resolver.resolve(call.callee, caller_class=caller_class)
            if resolved is None or resolved[1] not in CALLABLE_TYPES or (caller_id, resolved[0]) in seen:
                continue
            seen.add((caller_id, resolved[0]))
            result.edges.append(
                edge(
                    caller_id,
                    RelationType.CALLS,
                    resolved[0],
                    context,
                    entry.module.file.relative_path,
                    detection_tag(entry.module.file.language, "CALL_NAME_RESOLUTION"),
                    call.line,
                    evidence_type=EvidenceType.INFERRED,
                    confidence=CALL_CONFIDENCE,
                )
            )


def _enclosing_symbol(entry: _ModuleEntry, qualified_name: str) -> str | None:
    """Symbole extrait qui englobe ``qualified_name``, ou ``None``.

    Une fonction imbriquée n'est pas un nœud : ses appels sont rattachés à la fonction ou à
    la méthode de premier niveau qui la contient, où ils s'exécutent.
    """
    candidate = qualified_name
    while candidate:
        if candidate in entry.symbol_ids:
            return candidate
        candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
    return None


class ApiExtractor:
    """Endpoints HTTP exposés par le code, via les adaptateurs de frameworks.

    Une route est rattachée au fichier qui la déclare (``exposes``) et à la fonction qui la
    traite (``implemented_by``). Les préfixes posés dans un autre fichier par
    ``include_router`` sont appliqués quand le routeur vient d'un module du projet ; sinon la
    route garde le chemin écrit sur place, sans préfixe inventé.
    """

    name = "api"
    order = 20

    def __init__(self, adapters: list[FrameworkAdapter] | None = None) -> None:
        self._adapters: list[FrameworkAdapter] = (
            list(adapters) if adapters is not None else [FastApiAdapter(), NextJsAdapter()]
        )

    @property
    def adapters(self) -> list[FrameworkAdapter]:
        """Adaptateurs consultés, dans l'ordre d'enregistrement."""
        return list(self._adapters)

    def extract(self, context: ProjectContext, registry: ParserRegistry) -> ExtractionResult:
        """Construit les nœuds ``Endpoint`` et leurs relations."""
        result = ExtractionResult()
        modules, _unparsed, warnings = parse_modules(
            context, registry, self.name, report_missing_parsers=False
        )
        result.warnings.extend(warnings)
        by_module = {module.module_name: module for module in modules}

        for adapter in self._adapters:
            concerned = [module for module in modules if adapter.detect(module)]
            mounts = _RouterMounts.resolve(concerned, by_module, adapter)
            for module in concerned:
                self._add_endpoints(module, adapter, mounts.context_for(module, adapter), context, result)
            result.warnings.extend(f"{self.name} : {warning}" for warning in mounts.warnings)
        return result

    def _add_endpoints(
        self,
        module: ParsedModule,
        adapter: FrameworkAdapter,
        router_context: RouterContext,
        context: ProjectContext,
        result: ExtractionResult,
    ) -> None:
        path = module.file.relative_path
        file_id = make_node_id(NodeType.FILE, path, module.module_name)
        handlers = {symbol.qualified_name: NODE_KIND_TO_TYPE[symbol.kind] for symbol in top_level_symbols(module)}
        extraction = adapter.routes(module, router_context)
        result.warnings.extend(f"{self.name} : {warning}" for warning in extraction.warnings)
        declared: dict[str, str] = {}

        for endpoint in extraction.endpoints:
            if endpoint.name in declared and declared[endpoint.name] != endpoint.router:
                result.warnings.append(
                    f"{self.name} : {path}:{endpoint.line} : « {endpoint.name} » est déclarée par "
                    f"{declared[endpoint.name]} et {endpoint.router} ; une seule route est enregistrée"
                )
                continue
            declared[endpoint.name] = endpoint.router
            node = Node(
                id=make_node_id(NodeType.ENDPOINT, path, endpoint.name),
                type=NodeType.ENDPOINT,
                name=endpoint.name,
                properties={
                    "method": endpoint.method,
                    "path": endpoint.path,
                    "framework": endpoint.framework,
                    "handler": endpoint.handler,
                },
                provenance=node_provenance(
                    context, path, detected_by=f"{endpoint.framework.upper()}_ROUTE_DECLARATION", line=endpoint.line
                ),
            )
            result.nodes.append(node)
            result.edges.append(
                edge(
                    file_id,
                    RelationType.EXPOSES,
                    node.id,
                    context,
                    path,
                    detection_tag(module.file.language, "ROUTE_DECLARATION"),
                    endpoint.line,
                )
            )
            handler_type = handlers.get(endpoint.handler)
            if handler_type in CALLABLE_TYPES:
                handler_id = make_node_id(handler_type, path, endpoint.handler)
                result.edges.append(
                    edge(
                        node.id,
                        RelationType.IMPLEMENTED_BY,
                        handler_id,
                        context,
                        path,
                        detection_tag(module.file.language, "ROUTE_HANDLER"),
                        endpoint.line,
                    )
                )


MAX_MOUNT_ROUNDS = 10
"""Garde-fou : un montage circulaire de routeurs ne doit pas boucler indéfiniment."""


@dataclass
class _RouterMounts:
    """Où chaque routeur du projet est monté, une fois les fichiers recoupés.

    Un routeur peut être monté dans un autre, lui-même monté ailleurs : les chemins se
    composent par propagation jusqu'à stabilisation. Un routeur monté par une chaîne qu'on ne
    sait pas suivre garde son chemin local, et l'écart est signalé.
    """

    prefixes: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    routers_by_module: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def resolve(
        cls, modules: list[ParsedModule], by_module: dict[str, ParsedModule], adapter: FrameworkAdapter
    ) -> "_RouterMounts":
        """Calcule les chemins de montage de tous les routeurs du projet."""
        mounts = cls(routers_by_module={module.module_name: adapter.routers(module) for module in modules})
        edges = mounts._collect(modules, by_module, adapter)
        mounts._propagate(edges)
        return mounts

    def context_for(self, module: ParsedModule, adapter: FrameworkAdapter) -> RouterContext:
        """Ce que l'adaptateur doit savoir pour ce module : chemins de montage et routeurs importés."""
        local_prefixes = {
            name: tuple(sorted(self.prefixes[(module.module_name, name)]))
            for name in self.routers_by_module.get(module.module_name, {})
            if (module.module_name, name) in self.prefixes
        }
        known = {
            local
            for local, (origin, original) in import_bindings(module).items()
            if original in self.routers_by_module.get(origin, {})
        }
        return RouterContext(prefixes=local_prefixes, known_routers=frozenset(known))

    def _collect(
        self, modules: list[ParsedModule], by_module: dict[str, ParsedModule], adapter: FrameworkAdapter
    ) -> list[tuple[str, str, tuple[str, str], str]]:
        """Montages exploitables : (module, routeur parent, routeur monté, préfixe)."""
        collected: list[tuple[str, str, tuple[str, str], str]] = []
        for module in modules:
            bindings = import_bindings(module)
            aliases = module_aliases(module)
            for inclusion in adapter.inclusions(module):
                target = self._locate_router(inclusion.router, module, bindings, aliases, by_module)
                if target is None:
                    self.warnings.append(
                        f"{module.file.relative_path}:{inclusion.line} : routeur « {inclusion.router} » "
                        "hors du projet ou non résolu, préfixe non appliqué"
                    )
                    continue
                collected.append((module.module_name, inclusion.parent, target, inclusion.prefix))
        return collected

    def _locate_router(
        self,
        name: str,
        module: ParsedModule,
        bindings: dict[str, tuple[str, str]],
        aliases: dict[str, str],
        by_module: dict[str, ParsedModule],
    ) -> tuple[str, str] | None:
        """Module et nom d'origine d'un routeur désigné localement."""
        head, _, attribute = name.partition(".")
        if attribute:  # users.router, où « users » est un module
            origin = aliases.get(head)
            if origin is None and head in bindings:
                imported_module, imported_name = bindings[head]
                origin = f"{imported_module}.{imported_name}"
            if origin in by_module and attribute in self.routers_by_module.get(origin, {}):
                return origin, attribute
            return None
        if name in bindings:
            origin, original = bindings[name]
            return (origin, original) if original in self.routers_by_module.get(origin, {}) else None
        return (module.module_name, name) if name in self.routers_by_module.get(module.module_name, {}) else None

    def _propagate(self, edges: list[tuple[str, str, tuple[str, str], str]]) -> None:
        """Compose les préfixes parent → enfant jusqu'à stabilisation."""
        mounted = {child for _, _, child, _ in edges}
        for _ in range(MAX_MOUNT_ROUNDS):
            changed = False
            for module_name, parent, child, prefix in edges:
                parent_key = (module_name, parent)
                if parent_key in mounted:
                    parent_paths = self.prefixes.get(parent_key, set())
                    if not parent_paths:
                        continue  # le parent n'est pas encore résolu ; un tour de plus
                else:
                    parent_paths = {""}
                # Le parent apporte son propre préfixe en plus de là où il est monté.
                parent_prefix = self.routers_by_module.get(module_name, {}).get(parent, "")
                paths = {join_paths(parent_path, parent_prefix, prefix) for parent_path in parent_paths}
                known = self.prefixes.setdefault(child, set())
                if not paths <= known:
                    known |= paths
                    changed = True
            if not changed:
                return
        self.warnings.append("montage de routeurs trop imbriqué ou circulaire, préfixes partiellement résolus")
