"""Interface de parsing et registre (extensible par langage, règle 6 d'AGENTS.md)."""

from typing import Protocol

from sakg.domain import SakgError
from sakg.reverse.models import ParsedModule, SourceFile


class ParseError(SakgError):
    """Le fichier n'a pas pu être analysé."""


class LanguageParser(Protocol):
    """Parser d'un langage : transforme un fichier en ``ParsedModule``."""

    @property
    def language(self) -> str:
        """Langage pris en charge."""
        ...

    def supports(self, file: SourceFile) -> bool:
        """Indique si ce parser sait analyser le fichier."""
        ...

    def parse(self, file: SourceFile) -> ParsedModule:
        """Analyse le fichier.

        Raises:
            ParseError: Si le fichier est illisible ou syntaxiquement invalide.
        """
        ...


class ParserRegistry:
    """Registre des parsers disponibles ; le premier qui accepte le fichier l'emporte."""

    def __init__(self, parsers: list[LanguageParser] | None = None) -> None:
        self._parsers: list[LanguageParser] = list(parsers or [])
        self._cache: dict[tuple[str, str], ParsedModule | SakgError] = {}

    def parse(self, file: SourceFile) -> ParsedModule | None:
        """Analyse le fichier, ou ``None`` si aucun parser ne le prend en charge.

        Le résultat est mémorisé par contenu, succès comme échec : plusieurs extracteurs
        analysent le même projet sans le reparser, et un fichier invalide n'est pas réanalysé
        à chaque passage.

        Raises:
            ParseError: Si le fichier est illisible ou syntaxiquement invalide.
        """
        parser = self.for_file(file)
        if parser is None:
            return None
        key = (file.relative_path, file.content_hash)
        if key not in self._cache:
            try:
                self._cache[key] = parser.parse(file)
            except SakgError as error:
                self._cache[key] = error
        cached = self._cache[key]
        if isinstance(cached, SakgError):
            raise cached
        return cached

    def clear_cache(self) -> None:
        """Vide la mémoire d'analyse, à la fin d'un reverse."""
        self._cache.clear()

    def register(self, parser: LanguageParser) -> None:
        """Ajoute un parser."""
        self._parsers.append(parser)

    def for_file(self, file: SourceFile) -> LanguageParser | None:
        """Parser capable d'analyser le fichier, ou ``None``."""
        return next((parser for parser in self._parsers if parser.supports(file)), None)

    @property
    def languages(self) -> set[str]:
        """Langages couverts par le registre."""
        return {parser.language for parser in self._parsers}
