"""Modèles intermédiaires du reverse engineering (entre le code source et le graphe)."""

from dataclasses import dataclass, field
from pathlib import Path

from sakg.domain import Edge, Node


@dataclass(frozen=True)
class SourceFile:
    """Fichier source retenu par le scan.

    Attributes:
        path: Chemin absolu sur le disque.
        relative_path: Chemin relatif à la racine, en séparateurs ``/`` (utilisé dans les ids).
        language: Langage détecté, par exemple ``python``.
        content_hash: SHA-256 du contenu, pour détecter les changements.
    """

    path: Path
    relative_path: str
    language: str
    content_hash: str


@dataclass(frozen=True)
class ProjectContext:
    """Résultat du scan : ce que le pipeline doit analyser."""

    root: Path
    files: tuple[SourceFile, ...]
    languages: frozenset[str] = frozenset()
    frameworks: frozenset[str] = frozenset()
    commit_sha: str | None = None
    include: tuple[str, ...] = ()
    """Sous-dossiers demandés, relatifs à la racine ; vide si tout le projet est analysé."""

    def covers(self, relative_path: str) -> bool:
        """Indique si un chemin relatif entre dans le périmètre demandé."""
        return not self.include or any(
            relative_path == prefix or relative_path.startswith(f"{prefix}/") for prefix in self.include
        )

    def files_of_language(self, language: str) -> list[SourceFile]:
        """Fichiers d'un langage donné."""
        return [file for file in self.files if file.language == language]


@dataclass(frozen=True)
class Symbol:
    """Symbole déclaré dans un module.

    Attributes:
        kind: ``class``, ``function`` ou ``method``.
        name: Nom simple.
        qualified_name: Nom qualifié dans le module, par exemple ``PaymentService.pay``.
        line: Ligne de déclaration.
        end_line: Dernière ligne de la déclaration.
        bases: Noms des classes de base, pour ``kind == "class"``.
    """

    kind: str
    name: str
    qualified_name: str
    line: int
    end_line: int | None = None
    bases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportRef:
    """Import d'un module.

    Attributes:
        module: Module importé ; vide pour ``from . import x``.
        names: Noms importés ; vide pour ``import x``.
        level: Nombre de points d'un import relatif (0 si absolu).
        line: Ligne de l'import.
        alias: Nom local d'un ``import x as y`` ; ``None`` sans alias.
        aliases: Noms locaux des ``names``, seulement si au moins un alias est présent.
        type_only: Import placé sous ``if TYPE_CHECKING`` : présent à la vérification de
            types, absent à l'exécution.
        scoped: Import fait dans une fonction ou une classe : il ne rend rien visible au
            niveau du module, et ne peut donc pas servir de ré-exportation.
    """

    module: str
    names: tuple[str, ...] = ()
    level: int = 0
    line: int = 1
    alias: str | None = None
    aliases: tuple[str | None, ...] = ()
    type_only: bool = False
    scoped: bool = False

    def local_name_of(self, index: int) -> str:
        """Nom sous lequel ``names[index]`` est visible dans le module importateur."""
        if index < len(self.aliases) and self.aliases[index]:
            return str(self.aliases[index])
        return self.names[index]


@dataclass(frozen=True)
class CallRef:
    """Appel détecté dans le corps d'une fonction ou d'une méthode."""

    caller: str
    callee: str
    line: int


@dataclass(frozen=True)
class DecoratorRef:
    """Décorateur appliqué à un symbole, par exemple ``app.post`` (utilisé par l'ApiExtractor).

    Attributes:
        target: Nom qualifié du symbole décoré.
        name: Nom pointé du décorateur.
        line: Ligne du décorateur.
        arguments: Arguments positionnels littéraux.
        keywords: Arguments nommés littéraux, par exemple ``path="/x"``.
        list_keywords: Arguments nommés valant une liste de chaînes, par exemple ``methods``.
    """

    target: str
    name: str
    line: int
    arguments: tuple[str, ...] = ()
    keywords: dict[str, str] = field(default_factory=dict)
    list_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class CallSite:
    """Appel exécuté au chargement du module, hors de toute fonction.

    C'est là que les frameworks se configurent : ``router = APIRouter(prefix="/users")``,
    ``app.include_router(router, prefix="/api")``.

    Les valeurs littérales et les identifiants sont séparés : un préfixe écrit en clair est un
    fait, un préfixe rangé dans une variable ne l'est pas. Les confondre ferait produire un
    chemin d'URL inventé.

    Attributes:
        callee: Nom pointé appelé, par exemple ``APIRouter``.
        assigned_to: Nom auquel le résultat est affecté, s'il y en a un.
        arguments: Arguments positionnels littéraux (chaînes écrites en clair).
        argument_names: Arguments positionnels donnés par un identifiant.
        keywords: Arguments nommés dont la valeur est une chaîne littérale.
        keyword_names: Arguments nommés dont la valeur est un identifiant, donc non résolue.
        line: Ligne de l'appel.
    """

    callee: str
    assigned_to: str | None = None
    arguments: tuple[str, ...] = ()
    argument_names: tuple[str, ...] = ()
    keywords: dict[str, str] = field(default_factory=dict)
    keyword_names: dict[str, str] = field(default_factory=dict)
    line: int = 1


@dataclass(frozen=True)
class AttributeRef:
    """Attribut déclaré dans le corps d'une classe.

    C'est ainsi que les ORM décrivent une table : ``__tablename__ = "users"`` puis
    ``id = Column(Integer, primary_key=True)``.

    Attributes:
        owner: Nom qualifié de la classe qui déclare l'attribut.
        name: Nom de l'attribut.
        value: Valeur, si c'est une chaîne littérale.
        callee: Fonction appelée à droite, par exemple ``Column`` ou ``mapped_column``.
        arguments: Arguments positionnels littéraux de cet appel.
        argument_names: Arguments positionnels donnés par un identifiant, par exemple ``Integer``.
        keywords: Arguments nommés littéraux.
        booleans: Arguments nommés valant ``True`` ou ``False``, par exemple ``primary_key``.
        nested: Appels imbriqués et leurs arguments littéraux, par exemple ``ForeignKey``.
        mapping: Dictionnaire littéral affecté, par exemple ``__table_args__ = {"schema": "billing"}``.
        line: Ligne de la déclaration.
    """

    owner: str
    name: str
    value: str = ""
    callee: str = ""
    arguments: tuple[str, ...] = ()
    argument_names: tuple[str, ...] = ()
    keywords: dict[str, str] = field(default_factory=dict)
    booleans: dict[str, bool] = field(default_factory=dict)
    nested: dict[str, tuple[str, ...]] = field(default_factory=dict)
    mapping: dict[str, str] = field(default_factory=dict)
    line: int = 1


@dataclass(frozen=True)
class ParsedModule:
    """Vue structurée d'un fichier source, indépendante du langage."""

    file: SourceFile
    module_name: str
    symbols: tuple[Symbol, ...] = ()
    imports: tuple[ImportRef, ...] = ()
    calls: tuple[CallRef, ...] = ()
    decorators: tuple[DecoratorRef, ...] = ()
    call_sites: tuple[CallSite, ...] = ()
    attributes: tuple[AttributeRef, ...] = ()

    def attributes_of(self, owner: str) -> list[AttributeRef]:
        """Attributs déclarés par une classe donnée."""
        return [attribute for attribute in self.attributes if attribute.owner == owner]

    def imports_module(self, prefix: str) -> bool:
        """Indique si le module importe ``prefix`` ou l'un de ses sous-modules."""
        return any(
            reference.module == prefix or reference.module.startswith(f"{prefix}.") for reference in self.imports
        )

    def symbols_of_kind(self, kind: str) -> list[Symbol]:
        """Symboles d'un type donné."""
        return [symbol for symbol in self.symbols if symbol.kind == kind]


@dataclass
class ExtractionResult:
    """Ce qu'un extracteur a trouvé, avant fusion dans le graphe."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
