"""Parser Python fondé sur le module ``ast`` de la bibliothèque standard (ADR-003)."""

import ast

from sakg.reverse.languages import module_name_of as _module_name_of
from sakg.reverse.models import (
    AttributeRef,
    CallRef,
    CallSite,
    DecoratorRef,
    ImportRef,
    ParsedModule,
    SourceFile,
    Symbol,
)
from sakg.reverse.parser import ParseError

PYTHON = "python"

__all__ = ["PYTHON", "ParseError", "PythonAstParser", "module_name_of"]


def module_name_of(relative_path: str, source_roots: tuple[str, ...] = ("src",)) -> str:
    """Nom de module pointé déduit d'un chemin relatif Python.

    Example:
        >>> module_name_of("src/sakg/domain/node.py")
        'sakg.domain.node'
        >>> module_name_of("src/sakg/domain/__init__.py")
        'sakg.domain'
    """
    return _module_name_of(relative_path, "python", source_roots)


def _is_string_literal(node: ast.expr) -> bool:
    """Vrai pour une chaîne écrite en clair, y compris la chaîne vide.

    Une f-string ou une variable n'en sont pas : leur valeur n'est pas un fait observable, et
    la deviner reviendrait à inventer un chemin d'URL. La chaîne vide, elle, est un chemin
    valide (``@router.post("")``), d'où la distinction entre « littéral » et « non vide ».
    """
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _string_literal(node: ast.expr) -> str:
    """Valeur d'une chaîne littérale, ou chaîne vide si ce n'en est pas une."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _string_mapping(node: ast.expr) -> dict[str, str]:
    """Dictionnaire littéral dont clés et valeurs sont des chaînes, par exemple ``__table_args__``."""
    if not isinstance(node, ast.Dict):
        return {}
    pairs = zip(node.keys, node.values, strict=True)
    return {
        _string_literal(key): _string_literal(value)
        for key, value in pairs
        if key is not None and _is_string_literal(key) and _is_string_literal(value)
    }


def _string_list(node: ast.expr) -> tuple[str, ...]:
    """Liste de chaînes littérales, par exemple ``methods=["GET", "POST"]``."""
    if not isinstance(node, ast.List | ast.Tuple | ast.Set):
        return ()
    return tuple(filter(None, (_string_literal(element) for element in node.elts)))


def _dotted_name(node: ast.expr) -> str:
    """Nom pointé d'une expression ``a.b.c``, ou chaîne vide si ce n'est pas un nom."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    if isinstance(node, ast.Subscript):  # class Repository(Base[T])
        return _dotted_name(node.value)
    return ""


class _ModuleVisitor(ast.NodeVisitor):
    """Parcourt l'AST en suivant la portée courante (Visitor)."""

    def __init__(self) -> None:
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []
        self.calls: list[CallRef] = []
        self.decorators: list[DecoratorRef] = []
        self.call_sites: list[CallSite] = []
        self.attributes: list[AttributeRef] = []
        self._scope: list[str] = []
        self._current_class: str | None = None
        self._type_only = False

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        """Un bloc ``if TYPE_CHECKING:`` ne s'exécute pas : ses imports sont marqués."""
        previous = self._type_only
        self._type_only = previous or _dotted_name(node.test).endswith("TYPE_CHECKING")
        for statement in node.body:
            self.visit(statement)
        self._type_only = previous
        for statement in node.orelse:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 (nom imposé par ast)
        for alias in node.names:
            self.imports.append(
                ImportRef(
                    module=alias.name,
                    line=node.lineno,
                    alias=alias.asname,
                    type_only=self._type_only,
                    scoped=bool(self._scope),
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        aliases = tuple(alias.asname for alias in node.names)
        self.imports.append(
            ImportRef(
                module=node.module or "",
                names=tuple(alias.name for alias in node.names),
                level=node.level,
                line=node.lineno,
                aliases=aliases if any(aliases) else (),
                type_only=self._type_only,
                scoped=bool(self._scope),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        qualified_name = self._qualify(node.name)
        self.symbols.append(
            Symbol(
                kind="class",
                name=node.name,
                qualified_name=qualified_name,
                line=node.lineno,
                end_line=node.end_lineno,
                bases=tuple(filter(None, (_dotted_name(base) for base in node.bases))),
            )
        )
        self._record_decorators(node, qualified_name)
        previous_class = self._current_class
        self._current_class = qualified_name
        self._scope.append(node.name)
        self._visit_body(node.body)
        self._scope.pop()
        self._current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        callee = _dotted_name(node.func)
        if callee and self._scope:
            self.calls.append(CallRef(caller=self._qualify(""), callee=callee, line=node.lineno))
        elif callee:
            self.call_sites.append(self._call_site(node, callee, assigned_to=None))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """``router: APIRouter = APIRouter(prefix="/users")`` est une affectation comme une autre."""
        if node.value is not None:
            self._record_assignment(_dotted_name(node.target), node.value)
        else:
            self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Retient ``router = APIRouter(prefix="/users")`` avec le nom auquel il est affecté."""
        target = _dotted_name(node.targets[0]) if len(node.targets) == 1 else ""
        self._record_assignment(target, node.value)

    def _record_assignment(self, target: str, value: ast.expr) -> None:
        callee = _dotted_name(value.func) if isinstance(value, ast.Call) else ""
        if isinstance(value, ast.Call) and callee and target and not self._scope:
            self.call_sites.append(self._call_site(value, callee, assigned_to=target))
            for argument in [*value.args, *(keyword.value for keyword in value.keywords)]:
                self.visit(argument)
            return
        if target and self._current_class is not None and self._scope == self._current_class.split("."):
            self.attributes.append(self._attribute(self._current_class, target, value))
        self.visit(value)

    def _attribute(self, owner: str, name: str, value: ast.expr) -> AttributeRef:
        """Décrit un attribut de classe, qu'il soit une constante ou un appel de colonne."""
        if not isinstance(value, ast.Call):
            return AttributeRef(
                owner=owner,
                name=name,
                value=_string_literal(value),
                mapping=_string_mapping(value),
                line=getattr(value, "lineno", 1),
            )
        return AttributeRef(
            owner=owner,
            name=name,
            callee=_dotted_name(value.func),
            arguments=tuple(_string_literal(argument) for argument in value.args if _is_string_literal(argument)),
            argument_names=tuple(
                _dotted_name(argument)
                for argument in value.args
                if not isinstance(argument, ast.Call) and _dotted_name(argument)
            ),
            keywords={
                keyword.arg: _string_literal(keyword.value)
                for keyword in value.keywords
                if keyword.arg and _is_string_literal(keyword.value)
            },
            booleans={
                keyword.arg: bool(keyword.value.value)
                for keyword in value.keywords
                if keyword.arg and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool)
            },
            nested={
                _dotted_name(argument.func): tuple(
                    _string_literal(inner) for inner in argument.args if _is_string_literal(inner)
                )
                for argument in [*value.args, *(keyword.value for keyword in value.keywords)]
                if isinstance(argument, ast.Call) and _dotted_name(argument.func)
            },
            line=value.lineno,
        )

    def _call_site(self, node: ast.Call, callee: str, *, assigned_to: str | None) -> CallSite:
        return CallSite(
            callee=callee,
            assigned_to=assigned_to,
            arguments=tuple(_string_literal(argument) for argument in node.args if _is_string_literal(argument)),
            argument_names=tuple(filter(None, (_dotted_name(argument) for argument in node.args))),
            keywords={
                keyword.arg: _string_literal(keyword.value)
                for keyword in node.keywords
                if keyword.arg and _is_string_literal(keyword.value)
            },
            keyword_names={
                keyword.arg: _dotted_name(keyword.value)
                for keyword in node.keywords
                if keyword.arg and not _is_string_literal(keyword.value) and _dotted_name(keyword.value)
            },
            line=node.lineno,
        )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = self._qualify(node.name)
        self.symbols.append(
            Symbol(
                kind="method" if self._current_class is not None else "function",
                name=node.name,
                qualified_name=qualified_name,
                line=node.lineno,
                end_line=node.end_lineno,
            )
        )
        self._record_decorators(node, qualified_name)
        previous_class = self._current_class
        self._current_class = None  # une fonction imbriquée n'est pas une méthode
        self._scope.append(node.name)
        self._visit_body(node.body)
        self._scope.pop()
        self._current_class = previous_class

    def _visit_body(self, body: list[ast.stmt]) -> None:
        """Ne parcourt que le corps : un décorateur n'est pas un appel fait *par* la fonction."""
        for statement in body:
            self.visit(statement)

    def _record_decorators(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, target: str) -> None:
        for decorator in node.decorator_list:
            name = _dotted_name(decorator)
            if not name:
                continue
            arguments: tuple[str, ...] = ()
            keywords: dict[str, str] = {}
            list_keywords: dict[str, tuple[str, ...]] = {}
            if isinstance(decorator, ast.Call):
                arguments = tuple(
                    _string_literal(argument) for argument in decorator.args if _is_string_literal(argument)
                )
                keywords = {
                    keyword.arg: _string_literal(keyword.value)
                    for keyword in decorator.keywords
                    if keyword.arg and _is_string_literal(keyword.value)
                }
                list_keywords = {
                    keyword.arg: _string_list(keyword.value)
                    for keyword in decorator.keywords
                    if keyword.arg and _string_list(keyword.value)
                }
            self.decorators.append(
                DecoratorRef(
                    target=target,
                    name=name,
                    line=decorator.lineno,
                    arguments=arguments,
                    keywords=keywords,
                    list_keywords=list_keywords,
                )
            )

    def _qualify(self, name: str) -> str:
        parts = [*self._scope, name] if name else list(self._scope)
        return ".".join(parts)


class PythonAstParser:
    """Parser Python : symboles, imports, appels et décorateurs.

    Example:
        >>> parser = PythonAstParser()
        >>> parser.language
        'python'
    """

    @property
    def language(self) -> str:
        """Langage pris en charge."""
        return PYTHON

    def supports(self, file: SourceFile) -> bool:
        """Accepte les fichiers détectés comme Python."""
        return file.language == PYTHON

    def parse(self, file: SourceFile) -> ParsedModule:
        """Analyse le fichier.

        Raises:
            ParseError: Si le fichier est illisible ou syntaxiquement invalide.
        """
        try:
            source = file.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ParseError(f"{file.relative_path} : lecture impossible ({error})") from error
        try:
            tree = ast.parse(source, filename=str(file.path))
        except SyntaxError as error:
            raise ParseError(f"{file.relative_path} : syntaxe invalide ligne {error.lineno}") from error

        visitor = _ModuleVisitor()
        visitor.visit(tree)
        return ParsedModule(
            file=file,
            module_name=module_name_of(file.relative_path),
            symbols=tuple(visitor.symbols),
            imports=tuple(visitor.imports),
            calls=tuple(visitor.calls),
            decorators=tuple(visitor.decorators),
            call_sites=tuple(visitor.call_sites),
            attributes=tuple(visitor.attributes),
        )
