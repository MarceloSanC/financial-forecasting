"""Contrato do port `RuntimeEnvironmentProbe` (Stage 5.5, A4 / I5).

Nas duas pernas (a `real` entra na Task 23): a foto traz todas as
`REQUIRED_KEYS` como texto e `code_dirty` é `"true"`/`"false"`; duas fotos do
mesmo estado são iguais.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import (  # noqa: E501
    GitRuntimeEnvironmentProbe,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    REQUIRED_KEYS,
    RuntimeEnvironmentProbe,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)

_COHORT_FILE = "config/cohorts/test.toml"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    """Repositório git descartável com `src/`, `uv.lock`, o arquivo do cohort e `docs/`."""
    repo = tmp_path / "repo"
    for rel, text in {
        "src/pkg/module.py": "x = 1\n",
        "uv.lock": "lock\n",
        _COHORT_FILE: "name = 'test'\n",
        "docs/notes.md": "notes\n",
    }.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo do teste é outro."""
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(params=["fake", "real"])
def probe(
    request: pytest.FixtureRequest, tmp_path: Path, isolated_git: None
) -> RuntimeEnvironmentProbe:
    if request.param == "fake":
        return InMemoryRuntimeEnvironmentProbe()
    return GitRuntimeEnvironmentProbe(
        repo_root=_repo(tmp_path), cohort_file=_COHORT_FILE, device="cpu"
    )


@pytest.mark.contract
def test_snapshot_has_every_required_key_as_text(probe: RuntimeEnvironmentProbe) -> None:
    snapshot = probe.snapshot()

    assert set(REQUIRED_KEYS) <= set(snapshot)
    assert all(isinstance(value, str) and value for value in snapshot.values())
    assert snapshot[DIRTY_KEY] in {"true", "false"}


@pytest.mark.contract
def test_two_snapshots_of_the_same_state_are_equal(probe: RuntimeEnvironmentProbe) -> None:
    assert probe.snapshot() == probe.snapshot()


# -- só o adapter real: identidade do código ---------------------------------------


def _real(repo: Path) -> GitRuntimeEnvironmentProbe:
    return GitRuntimeEnvironmentProbe(repo_root=repo, cohort_file=_COHORT_FILE, device="cpu")


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_docs_only_commit_does_not_change_the_snapshot(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _real(repo).snapshot()

    (repo / "docs/notes.md").write_text("more notes\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "docs")

    assert _real(repo).snapshot() == before


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_tracked_change_in_src_marks_dirty_then_changes_identity(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _real(repo).snapshot()

    (repo / "src/pkg/module.py").write_text("x = 2\n", encoding="utf-8")
    dirty = _real(repo).snapshot()
    _git(repo, "commit", "-q", "-am", "code")
    after = _real(repo).snapshot()

    assert dirty["code_dirty"] == "true"
    assert after["code_dirty"] == "false"
    assert after["code.src"] != before["code.src"]


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_untracked_file_in_src_counts_as_dirty(tmp_path: Path) -> None:
    """Módulo novo não ignorado em `src/` seria importado: conta (decisão do Checkpoint C)."""
    repo = _repo(tmp_path)
    (repo / "src/pkg/new_untracked.py").write_text("y = 1" + chr(10), encoding="utf-8")

    assert _real(repo).snapshot()["code_dirty"] == "true"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_untracked_file_outside_tracked_paths_does_not_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/new_untracked.md").write_text("z" + chr(10), encoding="utf-8")

    assert _real(repo).snapshot()["code_dirty"] == "false"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_staged_uncommitted_change_counts_as_dirty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "uv.lock").write_text("lock v2" + chr(10), encoding="utf-8")
    _git(repo, "add", "uv.lock")

    assert _real(repo).snapshot()["code_dirty"] == "true"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_cohort_file_outside_the_repo_is_an_explicit_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(RuntimeError, match="outside the repository"):
        GitRuntimeEnvironmentProbe(
            repo_root=repo, cohort_file=tmp_path / "elsewhere.toml", device="cpu"
        )


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_uncommitted_cohort_file_is_an_explicit_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    probe = GitRuntimeEnvironmentProbe(
        repo_root=repo, cohort_file="config/cohorts/missing.toml", device="cpu"
    )

    with pytest.raises(RuntimeError, match="code identity"):
        probe.snapshot()


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_repo_root_below_the_repository_root_is_an_explicit_error(tmp_path: Path) -> None:
    """F1/G2 (Checkpoint C 24-31): num subdiretório, os pathspecs do `git status`
    não casariam `src` e `code_dirty` sairia sempre "false" — recusa em vez disso."""
    repo = _repo(tmp_path)
    (repo / "src/pkg/module.py").write_text("x = 2" + chr(10), encoding="utf-8")
    probe = GitRuntimeEnvironmentProbe(
        repo_root=repo / "docs", cohort_file="../" + _COHORT_FILE, device="cpu"
    )

    with pytest.raises(RuntimeError, match="not the repository root"):
        probe.snapshot()
