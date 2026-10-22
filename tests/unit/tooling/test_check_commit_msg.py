"""Unit de `scripts/check_commit_msg.py` — leitura do arquivo da mensagem (BOM)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_commit_msg.py"
_EXIT_OK, _EXIT_FAIL = 0, 1


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_msg", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccm = _load()


def test_message_with_utf8_bom_is_rejected_naming_the_bom(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # caso real (sessão da #78): PowerShell grava UTF-8 com BOM e o U+FEFF iria para o subject
    msg = tmp_path / "msg.txt"
    msg.write_bytes(b"\xef\xbb\xbfdocs(git): mensagem valida\n")
    assert ccm.main(["check_commit_msg.py", str(msg)]) == _EXIT_FAIL
    assert "BOM" in capsys.readouterr().err


def test_same_message_without_bom_passes(tmp_path: Path) -> None:
    msg = tmp_path / "msg.txt"
    msg.write_bytes(b"docs(git): mensagem valida\n")
    assert ccm.main(["check_commit_msg.py", str(msg)]) == _EXIT_OK


# --- aviso de hook pre-commit ausente (issue #199) ---------------------------

_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # O container de check exporta GIT_DIR/GIT_WORK_TREE da worktree real; o repo aqui é outro.
    for variable in _GIT_ENV:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    return root


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _install_hook(hooks_dir: Path) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")


def _message(tmp_path: Path, subject: str) -> str:
    msg = tmp_path / "msg.txt"
    msg.write_text(f"{subject}\n", encoding="utf-8")
    return str(msg)


def test_missing_pre_commit_hook_warns_naming_the_hooks(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ccm.warn_if_pre_commit_hook_missing(repo) is True
    err = capsys.readouterr().err
    assert "hook pre-commit não está instalado" in err
    assert "ruff-format, ruff e mypy" in err
    assert "não bloqueia" in err


def test_installed_pre_commit_hook_stays_silent(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _install_hook(repo / ".git" / "hooks")
    assert ccm.warn_if_pre_commit_hook_missing(repo) is False
    assert capsys.readouterr().err == ""


def test_sample_hook_does_not_count_as_installed(repo: Path) -> None:
    # `git init` deixa só `pre-commit.sample`, que o git não executa
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-commit.sample").write_text("#!/bin/sh\n", encoding="utf-8")
    assert ccm.warn_if_pre_commit_hook_missing(repo) is True


def test_hook_lookup_follows_core_hooks_path(repo: Path) -> None:
    _install_hook(repo / ".git" / "hooks")
    _git(repo, "config", "core.hooksPath", "custom-hooks")
    # com core.hooksPath o git ignora .git/hooks: o hook de lá não roda
    assert ccm.warn_if_pre_commit_hook_missing(repo) is True
    _install_hook(repo / "custom-hooks")
    assert ccm.warn_if_pre_commit_hook_missing(repo) is False


def test_linked_worktree_uses_the_hook_of_the_common_dir(repo: Path, tmp_path: Path) -> None:
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "other", str(linked))
    assert ccm.warn_if_pre_commit_hook_missing(linked) is True
    _install_hook(repo / ".git" / "hooks")
    assert ccm.warn_if_pre_commit_hook_missing(linked) is False


def test_outside_a_repo_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for variable in _GIT_ENV:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert ccm.pre_commit_hook_path(tmp_path) is None
    assert ccm.warn_if_pre_commit_hook_missing(tmp_path) is False
    assert capsys.readouterr().err == ""


def test_without_git_executable_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(ccm.subprocess, "run", _no_git)
    assert ccm.pre_commit_hook_path(tmp_path) is None
    assert ccm.warn_if_pre_commit_hook_missing(tmp_path) is False


def test_warning_does_not_change_the_verdict_of_a_valid_subject(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(repo)
    msg = _message(tmp_path, "chore(tooling): subject valido [#199/task-01]")
    assert ccm.main(["check_commit_msg.py", msg]) == _EXIT_OK
    assert "hook pre-commit não está instalado" in capsys.readouterr().err


def test_warning_does_not_rescue_an_invalid_subject(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(repo)
    assert ccm.main(["check_commit_msg.py", _message(tmp_path, "sem formato")]) == _EXIT_FAIL
    err = capsys.readouterr().err
    assert "rejected commit subject" in err
    assert "hook pre-commit não está instalado" in err


def test_main_with_hook_installed_prints_nothing(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_hook(repo / ".git" / "hooks")
    monkeypatch.chdir(repo)
    msg = _message(tmp_path, "chore(tooling): subject valido")
    assert ccm.main(["check_commit_msg.py", msg]) == _EXIT_OK
    assert capsys.readouterr().err == ""
