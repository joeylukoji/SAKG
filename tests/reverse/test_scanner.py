from pathlib import Path

import pytest

from sakg.reverse import ProjectScanner


def test_scan_collects_python_files(sample_project: Path) -> None:
    context = ProjectScanner().scan(sample_project)

    assert {file.relative_path for file in context.files} == {
        "payment/service.py",
        "core/__init__.py",
        "core/base.py",
        "core/helpers.py",
    }
    assert context.languages == frozenset({"python"})
    assert context.root == sample_project.resolve()


def test_scan_ignores_noise_directories(sample_project: Path) -> None:
    for ignored in (".venv", "__pycache__", ".architect"):
        (sample_project / ignored).mkdir()
        (sample_project / ignored / "junk.py").write_text("x = 1", encoding="utf-8")

    context = ProjectScanner().scan(sample_project)

    assert all("junk.py" not in file.relative_path for file in context.files)


def test_scan_accepts_extra_ignore_patterns(sample_project: Path) -> None:
    context = ProjectScanner(ignore_patterns={"core"}).scan(sample_project)

    assert {file.relative_path for file in context.files} == {"payment/service.py"}


def test_scan_ignores_unknown_suffixes(sample_project: Path) -> None:
    (sample_project / "README.md").write_text("# doc", encoding="utf-8")
    (sample_project / "types.d.ts").write_text("export type X = number;\n", encoding="utf-8")

    assert all(file.relative_path.endswith(".py") for file in ProjectScanner().scan(sample_project).files)


def test_scan_collects_typescript_files(sample_project: Path) -> None:
    (sample_project / "app.ts").write_text("export class App {}\n", encoding="utf-8")

    context = ProjectScanner().scan(sample_project)

    assert any(file.relative_path == "app.ts" and file.language == "typescript" for file in context.files)
    assert "typescript" in context.languages


def test_scan_can_restrict_languages(sample_project: Path) -> None:
    (sample_project / "app.ts").write_text("export class App {}\n", encoding="utf-8")

    context = ProjectScanner().scan(sample_project, languages=["python"])

    assert context.languages == frozenset({"python"})
    assert all(file.language == "python" for file in context.files)


def test_content_hash_changes_with_content(sample_project: Path, tmp_path: Path) -> None:
    before = ProjectScanner().scan(sample_project).files_of_language("python")
    (sample_project / "core" / "helpers.py").write_text("def audit(x): return x", encoding="utf-8")
    after = ProjectScanner().scan(sample_project).files_of_language("python")

    hashes_before = {file.relative_path: file.content_hash for file in before}
    hashes_after = {file.relative_path: file.content_hash for file in after}
    assert hashes_before["core/base.py"] == hashes_after["core/base.py"]
    assert hashes_before["core/helpers.py"] != hashes_after["core/helpers.py"]


def test_scan_missing_root(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ProjectScanner().scan(tmp_path / "absent")


def test_commit_sha_is_carried(sample_project: Path) -> None:
    assert ProjectScanner().scan(sample_project, commit_sha="abc123").commit_sha == "abc123"
