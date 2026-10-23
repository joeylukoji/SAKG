"""Squelette Tree-sitter : un langage = grammaire + extraction vers ``ParsedModule``.

Python reste sur ``ast`` (ADR-003). Les autres langages héritent de cette classe et
n'implémentent que la collecte des symboles ; lecture du fichier, construction du parseur
et gestion des erreurs d'I/O sont communes.
"""

from abc import ABC, abstractmethod

from tree_sitter import Language, Node, Parser, Tree

from sakg.reverse.models import ParsedModule, SourceFile
from sakg.reverse.parser import ParseError


class TreeSitterParser(ABC):
    """Parser fondé sur Tree-sitter (Template Method).

    Example:
        >>> TypeScriptParser().language  # doctest: +SKIP
        'typescript'
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Langage pris en charge."""

    def supports(self, file: SourceFile) -> bool:
        """Accepte les fichiers du langage déclaré."""
        return file.language == self.language

    def parse(self, file: SourceFile) -> ParsedModule:
        """Analyse le fichier.

        Raises:
            ParseError: Si le fichier est illisible.
        """
        try:
            source = file.path.read_bytes()
        except OSError as error:
            raise ParseError(f"{file.relative_path} : lecture impossible ({error})") from error
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ParseError(f"{file.relative_path} : lecture impossible ({error})") from error
        tree = self._parser_for(file).parse(source)
        return self.collect(file, text, tree)

    def _parser_for(self, file: SourceFile) -> Parser:
        grammar = self.grammar_for(file)
        try:
            return Parser(grammar)
        except TypeError:
            parser = Parser()
            parser.language = grammar
            return parser

    def grammar_for(self, file: SourceFile) -> Language:
        """Grammaire Tree-sitter du fichier ; surchargeable (``.ts`` vs ``.tsx``)."""
        return self.grammar

    @property
    @abstractmethod
    def grammar(self) -> Language:
        """Grammaire par défaut du langage."""

    @abstractmethod
    def collect(self, file: SourceFile, source: str, tree: Tree) -> ParsedModule:
        """Remplit un ``ParsedModule`` depuis l'arbre Tree-sitter."""


def node_text(source: str, node: Node) -> str:
    """Texte source couvert par un nœud (offsets Tree-sitter en octets)."""
    encoded = source.encode("utf-8")
    return encoded[node.start_byte : node.end_byte].decode("utf-8")


def named_child(node: Node, field: str) -> Node | None:
    """Enfant nommé, ou ``None``."""
    return node.child_by_field_name(field)
