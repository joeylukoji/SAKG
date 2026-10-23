"""Parser TypeScript / TSX fondé sur Tree-sitter."""

import tree_sitter_typescript
from tree_sitter import Language, Node, Tree

from sakg.reverse.languages import module_name_of
from sakg.reverse.models import CallRef, ImportRef, ParsedModule, SourceFile, Symbol
from sakg.reverse.tree_sitter_parser import TreeSitterParser, named_child, node_text

TYPESCRIPT = "typescript"


def _language(raw: Language | object) -> Language:
    if isinstance(raw, Language):
        return raw
    return Language(raw)


_TS_LANGUAGE = _language(tree_sitter_typescript.language_typescript())
_TSX_LANGUAGE = _language(tree_sitter_typescript.language_tsx())

_CLASS_TYPES = frozenset({"class_declaration", "abstract_class_declaration"})
_FUNCTION_TYPES = frozenset({"function_declaration", "generator_function_declaration"})


class TypeScriptParser(TreeSitterParser):
    """Parser TypeScript : classes, fonctions, méthodes, imports et appels.

    ``.tsx`` utilise la grammaire TSX ; le reste du pipeline voit le même langage
    ``typescript``.
    """

    @property
    def language(self) -> str:
        """Langage pris en charge."""
        return TYPESCRIPT

    @property
    def grammar(self) -> Language:
        """Grammaire TypeScript (sans JSX)."""
        return _TS_LANGUAGE

    def grammar_for(self, file: SourceFile) -> Language:
        """Grammaire TSX pour les fichiers ``.tsx``."""
        return _TSX_LANGUAGE if file.relative_path.endswith(".tsx") else _TS_LANGUAGE

    def collect(self, file: SourceFile, source: str, tree: Tree) -> ParsedModule:
        """Remplit un ``ParsedModule`` depuis l'arbre TypeScript."""
        visitor = _TypeScriptVisitor(source)
        visitor.visit(tree.root_node)
        return ParsedModule(
            file=file,
            module_name=module_name_of(file.relative_path, TYPESCRIPT),
            symbols=tuple(visitor.symbols),
            imports=tuple(visitor.imports),
            calls=tuple(visitor.calls),
        )


class _TypeScriptVisitor:
    """Parcourt l'arbre en suivant la portée courante (Visitor)."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []
        self.calls: list[CallRef] = []
        self._scope: list[str] = []
        self._current_class: str | None = None
        self._function_depth = 0

    def visit(self, node: Node) -> None:
        if node.type in _CLASS_TYPES:
            self._visit_class(node)
            return
        if node.type in _FUNCTION_TYPES:
            kind = "method" if self._current_class and self._function_depth == 0 else "function"
            self._visit_function(node, kind=kind)
            return
        if node.type == "method_definition":
            self._visit_function(node, kind="method" if self._current_class else "function")
            return
        if node.type == "import_statement":
            self._visit_import(node)
            return
        if node.type == "call_expression":
            self._visit_call(node)
            return
        for child in node.children:
            self.visit(child)

    def _visit_class(self, node: Node) -> None:
        name = self._field_name(node) or "default"
        qualified = self._qualify(name)
        self.symbols.append(
            Symbol(
                kind="class",
                name=name,
                qualified_name=qualified,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                bases=self._bases(node),
            )
        )
        previous = self._current_class
        self._current_class = qualified
        self._scope.append(name)
        body = named_child(node, "body")
        self.visit(body) if body is not None else self._visit_children(node)
        self._scope.pop()
        self._current_class = previous

    def _visit_function(self, node: Node, *, kind: str) -> None:
        name = self._field_name(node)
        if not name or name in {"constructor", "get", "set"}:
            self._visit_children(node)
            return
        qualified = self._qualify(name)
        self.symbols.append(
            Symbol(
                kind=kind,
                name=name,
                qualified_name=qualified,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            )
        )
        previous = self._current_class
        if kind == "function":
            self._current_class = None
        self._scope.append(name)
        self._function_depth += 1
        body = named_child(node, "body")
        self.visit(body) if body is not None else self._visit_children(node)
        self._function_depth -= 1
        self._scope.pop()
        self._current_class = previous

    def _visit_import(self, node: Node) -> None:
        specifier = ""
        names: list[str] = []
        aliases: list[str | None] = []
        alias: str | None = None
        type_only = any(child.type == "type" for child in node.children)
        for child in node.children:
            if child.type == "string":
                specifier = node_text(self.source, child).strip("'\"`")
            elif child.type == "import_clause":
                names, aliases, alias = self._import_clause(child)
        if not specifier:
            return
        self.imports.append(
            ImportRef(
                module=specifier,
                names=tuple(names),
                line=node.start_point[0] + 1,
                alias=alias,
                aliases=tuple(aliases) if any(aliases) else (),
                type_only=type_only,
            )
        )

    def _import_clause(self, node: Node) -> tuple[list[str], list[str | None], str | None]:
        names: list[str] = []
        aliases: list[str | None] = []
        default_alias: str | None = None
        for child in node.children:
            if child.type == "identifier":
                default_alias = node_text(self.source, child)
                names.append(default_alias)
                aliases.append(None)
            elif child.type == "named_imports":
                for specifier in child.children:
                    if specifier.type != "import_specifier":
                        continue
                    imported = self._field_name(specifier) or node_text(self.source, specifier)
                    local_node = named_child(specifier, "alias")
                    local = node_text(self.source, local_node) if local_node is not None else None
                    names.append(imported)
                    aliases.append(local)
            elif child.type == "namespace_import":
                identifier = next((item for item in child.children if item.type == "identifier"), None)
                if identifier is not None:
                    default_alias = node_text(self.source, identifier)
        return names, aliases, default_alias if not names else None

    def _visit_call(self, node: Node) -> None:
        if self._function_depth:
            callee = named_child(node, "function")
            name = self._dotted(callee) if callee is not None else ""
            if name:
                self.calls.append(CallRef(caller=self._qualify(""), callee=name, line=node.start_point[0] + 1))
        for child in node.children:
            self.visit(child)

    def _bases(self, node: Node) -> tuple[str, ...]:
        heritage = next((child for child in node.children if child.type == "class_heritage"), None)
        if heritage is None:
            return ()
        names = []
        for clause in heritage.children:
            if clause.type != "extends_clause":
                continue
            for child in clause.children:
                dotted = self._dotted(child)
                if dotted:
                    names.append(dotted)
        return tuple(names)

    def _dotted(self, node: Node) -> str:
        if node.type in {"identifier", "type_identifier", "property_identifier"}:
            return node_text(self.source, node)
        if node.type == "this":
            return "this"
        if node.type in {"member_expression", "nested_identifier"}:
            obj = named_child(node, "object")
            prop = named_child(node, "property")
            if obj is not None and prop is not None:
                prefix = self._dotted(obj)
                name = self._dotted(prop)
                return f"{prefix}.{name}" if prefix and name else prefix or name
        if node.type == "call_expression":
            func = named_child(node, "function")
            return self._dotted(func) if func is not None else ""
        return ""

    def _field_name(self, node: Node) -> str:
        name = named_child(node, "name")
        return self._dotted(name) if name is not None else ""

    def _qualify(self, name: str) -> str:
        parts = [*self._scope, name] if name else list(self._scope)
        return ".".join(parts)

    def _visit_children(self, node: Node) -> None:
        for child in node.children:
            self.visit(child)
