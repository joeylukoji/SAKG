"""Adaptateurs de frameworks : reconnaître une route derrière un décorateur.

Chaque framework a sa façon de déclarer une API. Un adaptateur traduit ces conventions en
``EndpointSpec``, que l'``ApiExtractor`` transforme ensuite en nœuds et relations : le reste
du pipeline ignore tout de FastAPI ou de Django (règle 6 d'AGENTS.md).

Règle de prudence : un chemin qui n'est pas écrit en clair dans le code n'est pas un fait.
Un préfixe rangé dans une variable, un routeur construit dynamiquement, un montage fait dans
une fonction : l'adaptateur produit un **avertissement** plutôt qu'un chemin deviné.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from sakg.reverse.imports import import_bindings
from sakg.reverse.models import ParsedModule

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
ROUTE_DECORATORS = (*HTTP_METHODS, "websocket", "api_route")
FASTAPI_FACTORIES = ("APIRouter", "FastAPI")

NEXTJS_ROUTE_FILENAMES = frozenset({"route.ts", "route.tsx"})
"""Nom de fichier qui, sous ``app/``, déclare des Route Handlers (App Router)."""

NEXTJS_HANDLER_NAMES = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
"""Verbes HTTP qu'un Route Handler exporte ; tout autre nom n'est pas une route."""

_OPTIONAL_CATCH_ALL_SEGMENT = re.compile(r"^\[\[\.\.\.([^.\[\]]+)\]\]$")
_CATCH_ALL_SEGMENT = re.compile(r"^\[\.\.\.([^.\[\]]+)\]$")
_DYNAMIC_SEGMENT = re.compile(r"^\[([^.\[\]]+)\]$")
_ROUTE_GROUP_SEGMENT = re.compile(r"^\(.+\)$")


@dataclass(frozen=True)
class EndpointSpec:
    """Route exposée par le code.

    Attributes:
        method: Verbe HTTP en majuscules, ou ``WEBSOCKET``.
        path: Chemin complet, préfixes connus inclus.
        handler: Nom qualifié de la fonction ou méthode qui l'implémente.
        line: Ligne du décorateur.
        router: Nom local du routeur ou de l'application qui porte la route.
        framework: Framework d'origine.
    """

    method: str
    path: str
    handler: str
    line: int
    router: str = ""
    framework: str = ""

    @property
    def name(self) -> str:
        """Nom lisible d'une route, par exemple ``GET /users/{id}``."""
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class RouterInclusion:
    """Montage d'un routeur dans un autre : ``app.include_router(users, prefix="/api")``.

    Attributes:
        router: Nom local du routeur monté.
        parent: Nom local de l'objet qui le monte.
        prefix: Préfixe appliqué, vide s'il n'y en a pas.
        line: Ligne du montage.
    """

    router: str
    parent: str
    prefix: str = ""
    line: int = 1


@dataclass(frozen=True)
class RouterContext:
    """Ce que l'extracteur sait et que l'adaptateur ignore, faute de voir les autres fichiers.

    Attributes:
        prefixes: Nom local de routeur → chemins de montage connus (plusieurs si le routeur
            est monté à plusieurs endroits).
        known_routers: Noms locaux importés qui désignent un routeur d'un module du projet.
    """

    prefixes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    known_routers: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RouteExtraction:
    """Routes trouvées dans un module, et ce que l'adaptateur n'a pas su résoudre."""

    endpoints: list[EndpointSpec] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FrameworkAdapter(Protocol):
    """Reconnaissance d'un framework et de ses routes."""

    @property
    def framework(self) -> str:
        """Nom du framework."""
        ...

    def detect(self, module: ParsedModule) -> bool:
        """Indique si ce module utilise le framework."""
        ...

    def routes(self, module: ParsedModule, context: RouterContext | None = None) -> RouteExtraction:
        """Routes déclarées dans le module, avec les avertissements rencontrés."""
        ...

    def routers(self, module: ParsedModule) -> dict[str, str]:
        """Routeurs déclarés dans le module : nom local → préfixe propre (souvent vide)."""
        ...

    def inclusions(self, module: ParsedModule) -> list[RouterInclusion]:
        """Montages d'un routeur dans un autre, à résoudre entre fichiers par l'extracteur."""
        ...


def join_paths(*parts: str) -> str:
    """Concatène des segments d'URL sans doubler ni perdre les barres obliques.

    Example:
        >>> join_paths("/api", "/users/", "{id}")
        '/api/users/{id}'
        >>> join_paths("", "/health")
        '/health'
    """
    segments = [part.strip("/") for part in parts if part and part.strip("/")]
    return "/" + "/".join(segments) if segments else "/"


class FastApiAdapter:
    """Routes FastAPI : décorateurs ``@app.get(...)``, ``@router.post(...)``, ``@app.websocket(...)``.

    Un décorateur n'est retenu que si son receveur est bien un routeur : une application ou un
    ``APIRouter`` construit sur place, ou un routeur importé d'un module du projet. Sans quoi
    un objet quelconque doté d'une méthode ``get`` produirait une fausse route.
    """

    @property
    def framework(self) -> str:
        """Nom du framework."""
        return "fastapi"

    def detect(self, module: ParsedModule) -> bool:
        """Vrai si le module importe FastAPI."""
        return module.imports_module("fastapi")

    def routers(self, module: ParsedModule) -> dict[str, str]:
        """Routeurs construits dans le module : ``router = APIRouter(prefix="/users")``."""
        factories = self._factory_names(module)
        return {
            site.assigned_to: site.keywords.get("prefix", "")
            for site in module.call_sites
            if site.assigned_to and site.callee in factories
        }

    def inclusions(self, module: ParsedModule) -> list[RouterInclusion]:
        """Montages déclarés : ``app.include_router(users_router, prefix="/api")``."""
        return [
            RouterInclusion(
                router=site.argument_names[0],
                parent=site.callee.rsplit(".", 1)[0] if "." in site.callee else "",
                prefix=site.keywords.get("prefix", ""),
                line=site.line,
            )
            for site in module.call_sites
            if site.callee.endswith("include_router") and site.argument_names
        ]

    def routes(self, module: ParsedModule, context: RouterContext | None = None) -> RouteExtraction:
        """Routes du module, préfixes connus appliqués, difficultés signalées."""
        known = context if context is not None else RouterContext()
        routers = self.routers(module)
        extraction = RouteExtraction(warnings=self._unresolved(module, routers))

        for decorator in module.decorators:
            receiver, _, verb = decorator.name.rpartition(".")
            if not receiver or verb.lower() not in ROUTE_DECORATORS:
                continue
            if receiver not in routers and receiver not in known.known_routers:
                continue
            path = self._declared_path(decorator.arguments, decorator.keywords)
            if path is None:
                extraction.warnings.append(
                    f"{module.file.relative_path}:{decorator.line} : chemin non littéral, route ignorée"
                )
                continue
            for method in self._methods(verb, decorator.list_keywords):
                for mounted in known.prefixes.get(receiver, ("",)):
                    extraction.endpoints.append(
                        EndpointSpec(
                            method=method,
                            path=join_paths(mounted, routers.get(receiver, ""), path),
                            handler=decorator.target,
                            line=decorator.line,
                            router=receiver,
                            framework=self.framework,
                        )
                    )
        return extraction

    def _unresolved(self, module: ParsedModule, routers: dict[str, str]) -> list[str]:
        """Signale les préfixes et montages que le code ne permet pas de connaître."""
        factories = self._factory_names(module)
        warnings = [
            f"{module.file.relative_path}:{site.line} : préfixe de {site.assigned_to} donné par "
            f"« {site.keyword_names['prefix']} », valeur inconnue statiquement"
            for site in module.call_sites
            if site.assigned_to and site.callee in factories and "prefix" in site.keyword_names
        ]
        warnings.extend(
            f"{module.file.relative_path}:{site.line} : préfixe d'inclusion donné par "
            f"« {site.keyword_names['prefix']} », valeur inconnue statiquement"
            for site in module.call_sites
            if site.callee.endswith("include_router") and "prefix" in site.keyword_names
        )
        warnings.extend(
            f"{module.file.relative_path}:{call.line} : include_router appelé dans « {call.caller} », "
            "préfixe non appliqué"
            for call in module.calls
            if call.callee.endswith("include_router")
        )
        if not routers and any(site.callee in factories for site in module.call_sites):
            warnings.append(f"{module.file.relative_path} : routeur construit sans être affecté à un nom")
        return warnings

    @staticmethod
    def _factory_names(module: ParsedModule) -> frozenset[str]:
        """Noms sous lesquels ``APIRouter`` et ``FastAPI`` sont visibles, alias compris."""
        names = {f"fastapi.{factory}" for factory in FASTAPI_FACTORIES}
        for local, (origin, original) in import_bindings(module).items():
            if origin == "fastapi" and original in FASTAPI_FACTORIES:
                names.add(local)
        return frozenset(names)

    @staticmethod
    def _declared_path(arguments: tuple[str, ...], keywords: dict[str, str]) -> str | None:
        """Chemin écrit en clair, positionnel ou en mot-clé ; ``None`` s'il n'est pas littéral."""
        if arguments:
            return arguments[0]
        return keywords.get("path")

    @staticmethod
    def _methods(verb: str, list_keywords: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
        """Verbes HTTP d'une route ; ``api_route`` peut en déclarer plusieurs."""
        if verb.lower() == "api_route":
            return tuple(method.upper() for method in list_keywords.get("methods", ())) or ("GET",)
        return (verb.upper(),)


class NextJsAdapter:
    """Route Handlers Next.js (App Router) : le chemin vient de l'arborescence, pas d'un décorateur.

    Sous ``app/`` (ou ``src/app/``), un fichier ``route.ts`` expose une route par fonction
    exportée au premier niveau nommée d'après un verbe HTTP (``GET``, ``POST``…) ; chaque
    fonction est son propre gestionnaire. Le chemin se lit dans les dossiers parents : segment
    dynamique (``[id]`` → ``{id}``), tout-venant (``[...slug]`` → ``{...slug}``), tout-venant
    optionnel (``[[...slug]]`` → ``{...slug?}``) et groupe de routage (``(marketing)``, ignoré
    dans l'URL). Un dossier privé (``_lib``) n'expose aucune route, comme dans Next.js.

    Sans routeur ni montage à résoudre entre fichiers, :meth:`routers` et :meth:`inclusions`
    ne retournent jamais rien.
    """

    @property
    def framework(self) -> str:
        """Nom du framework."""
        return "nextjs"

    def detect(self, module: ParsedModule) -> bool:
        """Vrai si le fichier est un Route Handler valide sous ``app/``."""
        return _route_path_segments(module.file.relative_path) is not None

    def routers(self, module: ParsedModule) -> dict[str, str]:
        """Aucun routeur à monter : chaque route vient directement de son chemin de fichier."""
        return {}

    def inclusions(self, module: ParsedModule) -> list[RouterInclusion]:
        """Aucun montage : rien à propager entre fichiers."""
        return []

    def routes(self, module: ParsedModule, context: RouterContext | None = None) -> RouteExtraction:
        """Une route par fonction exportée nommée d'après un verbe HTTP."""
        segments = _route_path_segments(module.file.relative_path)
        if segments is None:
            return RouteExtraction()
        path = join_paths(*segments)
        return RouteExtraction(
            endpoints=[
                EndpointSpec(
                    method=symbol.name,
                    path=path,
                    handler=symbol.qualified_name,
                    line=symbol.line,
                    framework=self.framework,
                )
                for symbol in module.symbols
                if symbol.kind == "function" and symbol.name in NEXTJS_HANDLER_NAMES
            ]
        )


def _route_path_segments(relative_path: str) -> list[str] | None:
    """Segments d'URL d'un Route Handler, ou ``None`` si ce fichier n'en déclare pas.

    ``None`` couvre aussi bien un fichier hors de ``app/`` qu'un dossier privé (``_lib``) :
    dans les deux cas, Next.js ne route rien ici, et aucune route ne doit être inventée.
    """
    parts = relative_path.replace("\\", "/").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts or parts[0] != "app":
        return None
    directories, filename = parts[1:-1], parts[-1]
    if filename not in NEXTJS_ROUTE_FILENAMES:
        return None
    segments: list[str] = []
    for part in directories:
        if part.startswith("_"):
            return None
        if _ROUTE_GROUP_SEGMENT.match(part):
            continue
        optional_catch_all = _OPTIONAL_CATCH_ALL_SEGMENT.match(part)
        if optional_catch_all:
            segments.append(f"{{...{optional_catch_all.group(1)}?}}")
            continue
        catch_all = _CATCH_ALL_SEGMENT.match(part)
        if catch_all:
            segments.append(f"{{...{catch_all.group(1)}}}")
            continue
        dynamic = _DYNAMIC_SEGMENT.match(part)
        segments.append(f"{{{dynamic.group(1)}}}" if dynamic else part)
    return segments
