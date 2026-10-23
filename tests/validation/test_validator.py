"""Orchestration des règles : un rapport unique, toutes règles confondues."""

from dataclasses import dataclass

from sakg.graph import KnowledgeGraph
from sakg.validation import ArchitectureValidator, Finding, Severity


@dataclass(frozen=True)
class _AlwaysFinds:
    id: str
    severity: Severity = Severity.ERROR

    def check(self, graph: KnowledgeGraph) -> list[Finding]:
        return [Finding(rule_id=self.id, severity=self.severity, message=f"{self.id} déclenchée")]


@dataclass(frozen=True)
class _NeverFinds:
    id: str
    severity: Severity = Severity.ERROR

    def check(self, graph: KnowledgeGraph) -> list[Finding]:
        return []


def test_findings_from_every_rule_are_aggregated() -> None:
    report = ArchitectureValidator([_AlwaysFinds("a"), _AlwaysFinds("b")]).validate(KnowledgeGraph())

    assert [finding.rule_id for finding in report.findings] == ["a", "b"]
    assert report.rules_checked == ("a", "b")
    assert not report.passed()


def test_a_clean_rule_is_still_listed_as_checked() -> None:
    report = ArchitectureValidator([_NeverFinds("clean")]).validate(KnowledgeGraph())

    assert report.findings == []
    assert report.rules_checked == ("clean",)
    assert report.passed()


def test_no_rules_at_all_still_produces_a_report() -> None:
    report = ArchitectureValidator([]).validate(KnowledgeGraph())

    assert report.passed()
    assert report.rules_checked == ()
