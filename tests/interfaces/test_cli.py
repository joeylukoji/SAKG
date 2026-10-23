import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sakg.interfaces.cli import app, main

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    source = tmp_path / "src" / "app"
    source.mkdir(parents=True)
    (source / "base.py").write_text("class Base:\n    def run(self):\n        pass\n", encoding="utf-8")
    (source / "service.py").write_text(
        "from app.base import Base\n\n\nclass Service(Base):\n    def handle(self):\n        return self.run()\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(*arguments: str) -> tuple[int, str]:
    result = runner.invoke(app, list(arguments))
    return result.exit_code, result.stdout


def test_init_then_reverse(project: Path) -> None:
    code, output = _run("init", "--root", str(project))
    assert code == 0
    assert (project / ".architect" / "project.yaml").exists()

    code, output = _run("reverse", "--root", str(project))
    assert code == 0
    assert "Version 1" in output
    assert "nœuds" in output


def test_query_lists_matching_nodes(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "Service", "--root", str(project))

    assert code == 0
    assert "class:src/app/service.py::Service" in output


def test_query_without_match_exits_with_an_error(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "Inexistant", "--root", str(project))

    assert code == 1
    assert "Aucun nœud" in output


def test_query_dependencies(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "Service", "--dependencies", "--root", str(project))

    assert code == 0
    assert "dépend de (1)" in output
    assert "class:src/app/base.py::Base" in output


def test_impact_prints_a_markdown_report(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("impact", "Modifier Base", "--root", str(project))

    assert code == 0
    assert output.startswith("# Impact : Modifier Base")


def test_impact_without_match_exits_with_an_error(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("impact", "Refondre la facturation", "--root", str(project))

    assert code == 1
    assert "Aucun élément" in output


def test_uml_writes_the_default_file(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("uml", "--root", str(project))

    assert code == 0
    assert (project / ".architect" / "diagrams" / "class.md").exists()
    assert "class.md" in output


def test_uml_with_an_explicit_output(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    target = project / "docs" / "generated" / "classes.md"

    code, _ = _run("uml", "--root", str(project), "--output", str(target))

    assert code == 0
    assert "classDiagram" in target.read_text(encoding="utf-8")


def test_uml_of_an_unsupported_view(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, _ = _run("uml", "--root", str(project), "--view", "erd")

    assert code == 2


def test_uml_with_focus_does_not_overwrite_the_full_diagram(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    _run("uml", "--root", str(project))
    full = (project / ".architect" / "diagrams" / "class.md").read_text(encoding="utf-8")

    code, _ = _run("uml", "--root", str(project), "--focus", "class:src/app/base.py::Base")

    assert code == 0
    assert (project / ".architect" / "diagrams" / "class-focus.md").exists()
    assert (project / ".architect" / "diagrams" / "class.md").read_text(encoding="utf-8") == full


def test_uml_with_an_unknown_focus_fails_loudly(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    result = runner.invoke(app, ["uml", "--root", str(project), "--focus", "class:nope::Nope"])

    assert result.exit_code != 0
    assert not (project / ".architect" / "diagrams" / "class-focus.md").exists()


def test_query_with_type_filter_and_limit(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "Service", "--type", "class", "--root", str(project))

    assert code == 0
    assert "class:src/app/service.py::Service" in output
    assert "file:" not in output


def test_query_by_type_alone_lists_the_inventory(project: Path) -> None:
    """« Quelles classes ce projet définit-il ? » ne demande aucun texte de recherche."""
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "--type", "class", "--root", str(project))

    assert code == 0
    assert "class:src/app/base.py::Base" in output
    assert "class:src/app/service.py::Service" in output


def test_query_without_text_or_type_is_refused(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    result = runner.invoke(app, ["query", "--root", str(project)])

    assert result.exit_code == 2


def test_query_dependents_with_depth(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("query", "Base", "--dependents", "--depth", "2", "--root", str(project))

    assert code == 0
    assert "class:src/app/service.py::Service" in output


def test_reverse_twice_reports_that_nothing_changed(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    result = runner.invoke(app, ["reverse", "--root", str(project)])

    assert result.exit_code == 0
    assert "Version 1" in result.stdout
    assert not (project / ".architect" / "versions" / "v0002").exists()


def test_reverse_of_a_missing_root_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["reverse", "--root", str(tmp_path / "absent")])

    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)
    assert not (tmp_path / "absent").exists()  # la racine n'est pas créée au passage


def test_entry_point_turns_expected_errors_into_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un utilisateur en ligne de commande, ou un journal de CI, ne doit pas voir de traceback."""
    monkeypatch.setattr(sys, "argv", ["sakg", "reverse", "--root", str(tmp_path / "absent")])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Erreur :" in captured.err
    assert "Traceback" not in captured.err


def test_history_lists_versions(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("history", "--root", str(project))

    assert code == 0
    assert "v0001" in output


def test_diff_between_two_versions(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    (project / "src" / "app" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    _run("reverse", "--root", str(project))

    code, output = _run("diff", "1", "2", "--root", str(project))

    assert code == 0
    assert output.startswith("# Diff d'architecture : v1 → v2")
    assert "class:src/app/extra.py::Extra" in output


def test_diff_of_an_unknown_version_fails_clearly(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Par le vrai point d'entrée : un message, pas une trace Python."""
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    monkeypatch.setattr(sys, "argv", ["sakg", "diff", "1", "42", "--root", str(project)])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    error = capsys.readouterr().err
    assert "version introuvable : 42" in error
    assert "Traceback" not in error


def test_history_shows_the_size_of_each_version(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("history", "--root", str(project))

    assert code == 0
    assert "nœuds" in output and "relations" in output


def test_validate_with_no_rules_passes(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("validate", "--root", str(project))

    assert code == 0
    assert "conforme" in output


def test_validate_fails_on_a_violated_rule(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    rules_dir = project / ".architect" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "layers.yaml").write_text(
        "- type: layer_dependency\n  id: reversed-layers\n  layers: [app.service, app.base]\n",
        encoding="utf-8",
    )

    code, output = _run("validate", "--root", str(project))

    assert code == 1
    assert "reversed-layers" in output


def test_drift_of_an_unchanged_project_reports_none(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))

    code, output = _run("drift", "--root", str(project))

    assert code == 0
    assert "décrit encore le code" in output


def test_drift_after_a_code_change_fails(project: Path) -> None:
    _run("init", "--root", str(project))
    _run("reverse", "--root", str(project))
    (project / "src" / "app" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")

    code, output = _run("drift", "--root", str(project))

    assert code == 1
    assert "Dérive" in output


def test_history_of_a_fresh_project(project: Path) -> None:
    code, output = _run("history", "--root", str(project))

    assert code == 0
    assert "Aucune version" in output
