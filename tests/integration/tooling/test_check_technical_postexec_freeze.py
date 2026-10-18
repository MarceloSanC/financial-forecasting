"""Integração de `scripts/check_technical_postexec.py` — freeze da §7 contra um repo git real.

Cada teste monta um repo descartável em `tmp_path` com `develop` e uma branch de Stage, e
roda o script com o cwd nele (o script chama `git` no cwd).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_technical_postexec.py"
_TECHNICAL = Path("docs/stages/9.9-demo/technical.md")
_APPROVED = "stage 9.9: technical approved"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_technical_postexec", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctp = _load()


def _git(*args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _doc(*, status: str = "done", plan: str = "plano", section: str = "") -> str:
    return (
        f"---\nstatus: {status}\n---\n\n# Technical\n\n{plan}\n\n## 7. Execução\n"
        f"<!-- BEGIN: post-execution -->\n{section}\n<!-- END: post-execution -->\n"
    )


def _commit(content: str, message: str) -> None:
    _TECHNICAL.parent.mkdir(parents=True, exist_ok=True)
    _TECHNICAL.write_text(content, encoding="utf-8")
    _git("add", _TECHNICAL.as_posix())
    _git("commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # O container de dev exporta GIT_DIR/GIT_WORK_TREE da worktree; o repo descartável
    # precisa do próprio .git.
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    _git("init", "-q", "-b", "develop")
    _git("commit", "-q", "--allow-empty", "-m", "base")
    _git("checkout", "-q", "-b", "feat/1-9-9-demo")
    return tmp_path


def test_edit_outside_the_window_is_refused_while_the_stage_runs(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    errors = ctp.check_file(_TECHNICAL)
    assert errors
    assert "fora dos marcadores post-execution" in errors[0]


def test_edit_inside_the_window_passes_while_the_stage_runs(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    section = "### 2026-10-17 — [measurement] task-01 — x — Claude\n**Medição:** y\n"
    _TECHNICAL.write_text(_doc(section=section), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_absolute_path_is_compared_against_the_same_baseline(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    assert ctp.check_file((repo / _TECHNICAL).resolve())


def test_freeze_lifts_once_the_stage_is_merged(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _git("checkout", "-q", "develop")
    _git("merge", "-q", "--no-ff", "-m", "merge", "feat/1-9-9-demo")
    _TECHNICAL.write_text(_doc(plan="plano alinhado pós-merge"), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_without_integration_branch_the_check_fails_open(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _git("branch", "-q", "-m", "develop", "trunk")
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_without_approval_commit_there_is_no_baseline(repo: Path) -> None:
    _commit(_doc(), "docs(technical): rascunho")
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_baseline_without_markers_is_accepted(repo: Path) -> None:
    _commit("---\nstatus: done\n---\n\n# Technical\n\nplano\n", _APPROVED)
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_draft_status_skips_the_diff(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _TECHNICAL.write_text(_doc(status="draft", plan="plano reescrito"), encoding="utf-8")
    assert ctp.check_file(_TECHNICAL) == []


def test_tag_and_freeze_errors_are_both_reported(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    section = "### 2026-10-17 — [nota] task-01 — x — Claude\n"
    _TECHNICAL.write_text(_doc(plan="plano reescrito", section=section), encoding="utf-8")
    errors = ctp.check_file(_TECHNICAL)
    assert "`[nota]`" in errors[0]
    assert any("fora dos marcadores post-execution" in e for e in errors[1:])


def test_main_discovers_stage_technicals_under_root(repo: Path) -> None:
    _commit(_doc(), _APPROVED)
    _TECHNICAL.write_text(_doc(plan="plano reescrito"), encoding="utf-8")
    assert ctp.main(["--root", str(repo)]) == 1
