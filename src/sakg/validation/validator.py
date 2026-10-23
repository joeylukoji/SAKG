"""Orchestration des règles d'architecture (ARCHITECTURE.md §4.4)."""

from collections.abc import Sequence

from sakg.graph import KnowledgeGraph
from sakg.validation.findings import ValidationReport
from sakg.validation.rules import ArchitectureRule

__all__ = ["ArchitectureValidator"]


class ArchitectureValidator:
    """Applique un ensemble de règles au graphe et regroupe leurs constats."""

    def __init__(self, rules: Sequence[ArchitectureRule]) -> None:
        self._rules = list(rules)

    def validate(self, graph: KnowledgeGraph) -> ValidationReport:
        """Constats de toutes les règles enregistrées, règle par règle."""
        findings = [finding for rule in self._rules for finding in rule.check(graph)]
        return ValidationReport(findings=findings, rules_checked=tuple(rule.id for rule in self._rules))
