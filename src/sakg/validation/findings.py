"""Constats de validation : ce qu'une règle a trouvé, et ce que cela implique."""

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """Gravité d'un constat ; seule ``ERROR`` fait échouer une validation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """Violation d'une règle, vérifiable en une lecture.

    Attributes:
        rule_id: Règle qui l'a produite.
        severity: Gravité.
        message: Description lisible, qui cite ce qui est en cause.
        node_ids: Nœuds concernés.
        edge_ids: Relations concernées, quand la violation porte sur une dépendance.
    """

    rule_id: str
    severity: Severity
    message: str
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    """Résultat d'une validation.

    Attributes:
        findings: Constats, toutes règles confondues.
        rules_checked: Identifiants des règles évaluées, y compris celles sans constat.
    """

    findings: list[Finding] = field(default_factory=list)
    rules_checked: tuple[str, ...] = ()

    def passed(self) -> bool:
        """Vrai si aucun constat n'est une erreur."""
        return not self.errors()

    def errors(self) -> list[Finding]:
        """Constats bloquants."""
        return [finding for finding in self.findings if finding.severity is Severity.ERROR]

    def by_rule(self) -> dict[str, list[Finding]]:
        """Constats groupés par règle, dans l'ordre d'évaluation des règles."""
        grouped: dict[str, list[Finding]] = {rule_id: [] for rule_id in self.rules_checked}
        for finding in self.findings:
            grouped.setdefault(finding.rule_id, []).append(finding)
        return grouped

    def to_markdown(self) -> str:
        """Rapport lisible : une section par règle, conforme ou non."""
        verdict = "conforme" if self.passed() else f"{len(self.errors())} erreur(s)"
        lines = [f"# Validation d'architecture : {verdict}", ""]
        if not self.rules_checked:
            lines.append("Aucune règle définie (ajouter des fichiers dans `.architect/rules/`).")
        for rule_id, findings in self.by_rule().items():
            status = "✓ conforme" if not findings else f"{len(findings)} constat(s)"
            lines.append(f"## {rule_id} — {status}")
            for finding in findings:
                lines.append(f"- **{finding.severity.value}** : {finding.message}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
