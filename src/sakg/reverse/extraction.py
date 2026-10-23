"""Briques communes aux extracteurs : analyse des fichiers, provenance et relations.

Quatre extracteurs (structure du code, API, données, infrastructure) partagent la même façon
de lire un projet et d'attester ce qu'ils y trouvent ; ces fonctions sont leur socle.
"""

from sakg.domain import Edge, Evidence, EvidenceType, NodeType, Provenance, RelationType
from sakg.reverse.models import ParsedModule, ProjectContext, SourceFile, Symbol
from sakg.reverse.parser import ParseError, ParserRegistry

NODE_KIND_TO_TYPE = {
    "class": NodeType.CLASS,
    "function": NodeType.FUNCTION,
    "method": NodeType.METHOD,
}

CALLABLE_TYPES = frozenset({NodeType.METHOD, NodeType.FUNCTION})

__all__ = [
    "CALLABLE_TYPES",
    "NODE_KIND_TO_TYPE",
    "edge",
    "node_provenance",
    "parse_modules",
    "top_level_symbols",
]


def parse_modules(
    context: ProjectContext,
    registry: ParserRegistry,
    extractor: str,
    *,
    report_missing_parsers: bool = True,
) -> tuple[list[ParsedModule], list[SourceFile], list[str]]:
    """Analyse les fichiers du projet.

    Un fichier illisible ou un langage sans parser devient un avertissement : un langage
    manquant n'est signalé qu'une fois, pas une fois par fichier.
    """
    modules: list[ParsedModule] = []
    unparsed: list[SourceFile] = []
    warnings: list[str] = []
    missing: dict[str, int] = {}
    for file in context.files:
        try:
            parsed = registry.parse(file)
        except ParseError as error:
            warnings.append(f"{extractor} : {error}")
            continue
        if parsed is None:
            missing[file.language] = missing.get(file.language, 0) + 1
            unparsed.append(file)
            continue
        modules.append(parsed)
    if report_missing_parsers:
        for language, count in sorted(missing.items()):
            files = "fichier" if count == 1 else "fichiers"
            warnings.append(f"{extractor} : aucun parser pour le langage {language} ({count} {files})")
    return modules, unparsed, warnings


def top_level_symbols(module: ParsedModule) -> list[Symbol]:
    """Classes et fonctions de premier niveau, et méthodes de ces classes.

    Les symboles plus profondément imbriqués (classe dans une classe, fonction dans une
    fonction, et leurs méthodes) sont écartés : ils alourdiraient le graphe sans servir les
    vues du MVP. Les appels qu'ils contiennent ne sont donc pas non plus rattachés.
    Un symbole déclaré deux fois (``@property`` puis ``@x.setter``) n'est retenu qu'une fois.
    """
    top_level_classes = {
        symbol.qualified_name
        for symbol in module.symbols
        if symbol.kind == "class" and "." not in symbol.qualified_name
    }

    def is_kept(symbol: Symbol) -> bool:
        if symbol.kind == "method":
            return symbol.qualified_name.rsplit(".", 1)[0] in top_level_classes
        return "." not in symbol.qualified_name

    seen: set[str] = set()
    kept: list[Symbol] = []
    for symbol in module.symbols:
        if is_kept(symbol) and symbol.qualified_name not in seen:
            seen.add(symbol.qualified_name)
            kept.append(symbol)
    return kept


def node_provenance(
    context: ProjectContext,
    file: str,
    *,
    detected_by: str,
    line: int | None = None,
    end_line: int | None = None,
    evidence_type: EvidenceType = EvidenceType.OBSERVED,
    confidence: float = 1.0,
) -> Provenance:
    return Provenance(
        evidence_type=evidence_type,
        confidence=confidence,
        detected_by=detected_by,
        evidence=Evidence(file=file, line=line, end_line=end_line if line is not None else None),
        commit_sha=context.commit_sha,
    )


def edge(
    source_id: str,
    relation: RelationType,
    target_id: str,
    context: ProjectContext,
    file: str,
    detected_by: str,
    line: int | None = None,
    *,
    evidence_type: EvidenceType = EvidenceType.OBSERVED,
    confidence: float = 1.0,
) -> Edge:
    return Edge(
        source_id=source_id,
        target_id=target_id,
        relation=relation,
        provenance=node_provenance(
            context,
            file,
            detected_by=detected_by,
            line=line,
            evidence_type=evidence_type,
            confidence=confidence,
        ),
    )
