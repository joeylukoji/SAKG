"""Chargement des règles déclarées dans .architect/rules/*.yaml."""

from pathlib import Path

import pytest

from sakg.validation import LayerDependencyRule, NoCycleRule, RuleLoader, Severity, UnknownRuleTypeError


def _write(root: Path, name: str, content: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(content, encoding="utf-8")


def test_a_missing_directory_yields_no_rule(tmp_path: Path) -> None:
    assert RuleLoader().load(tmp_path / "rules") == []


def test_loads_a_layer_dependency_and_a_no_cycle_rule(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    _write(
        rules_dir,
        "agents-md.yaml",
        "- type: layer_dependency\n"
        "  id: layers\n"
        "  layers: [sakg.domain, sakg.graph]\n"
        "- type: no_cycle\n"
        "  id: cycles\n"
        "  severity: warning\n",
    )

    rules = RuleLoader().load(rules_dir)

    assert rules == [
        LayerDependencyRule(id="layers", layers=("sakg.domain", "sakg.graph")),
        NoCycleRule(id="cycles", severity=Severity.WARNING),
    ]


def test_a_single_rule_entry_not_wrapped_in_a_list_is_accepted(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    _write(rules_dir, "single.yaml", "type: no_cycle\nid: cycles\n")

    assert RuleLoader().load(rules_dir) == [NoCycleRule(id="cycles")]


def test_an_unknown_rule_type_is_reported_not_ignored(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    _write(rules_dir, "bogus.yaml", "- type: does_not_exist\n  id: x\n")

    with pytest.raises(UnknownRuleTypeError):
        RuleLoader().load(rules_dir)


def test_files_are_loaded_in_name_order(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    _write(rules_dir, "b.yaml", "type: no_cycle\nid: second\n")
    _write(rules_dir, "a.yaml", "type: no_cycle\nid: first\n")

    rules = RuleLoader().load(rules_dir)

    assert [rule.id for rule in rules] == ["first", "second"]
