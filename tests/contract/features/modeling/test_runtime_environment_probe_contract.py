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
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
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
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


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
def test_real_untracked_file_does_not_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "src/pkg/new_untracked.py").write_text("y = 1\n", encoding="utf-8")

    assert _real(repo).snapshot()["code_dirty"] == "false"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_uncommitted_cohort_file_is_an_explicit_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    probe = GitRuntimeEnvironmentProbe(
        repo_root=repo, cohort_file="config/cohorts/missing.toml", device="cpu"
    )

    with pytest.raises(RuntimeError, match="code identity"):
        probe.snapshot()
