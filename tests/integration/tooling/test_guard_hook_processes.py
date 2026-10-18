"""Integration dos hooks `git_guard` e `publish_guard` rodando como processo, como o Claude Code os
chama (`python .claude/hooks/<hook>.py` com o payload no stdin), contra um repositório git real em
`tmp_path`: prova que o import do helper vizinho `_shell_segments` resolve fora do pytest e que a
recusa sai ponta a ponta mesmo com o subcomando proibido numa linha seguinte.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_HOOKS = Path(__file__).resolve().parents[3] / ".claude" / "hooks"
# GIT_DIR/GIT_WORK_TREE do ambiente (docker run de worktree) apontariam o git para outro repo
_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


@pytest.fixture
def main_checkout(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True, env=_ENV)
    return tmp_path


def _run(hook: str, command: str, cwd: Path) -> str:
    payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
    out = subprocess.run(
        [sys.executable, str(_HOOKS / f"{hook}.py")],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=True,
        timeout=60,
        env=_ENV,
    )
    return out.stdout.decode("utf-8")


def _decision(stdout: str) -> str:
    return str(json.loads(stdout)["hookSpecificOutput"]["permissionDecision"])


@pytest.mark.parametrize(
    "command",
    ["git status\ngit checkout -b feat/99-x", "git status & git switch -c feat/99-x"],
)
def test_git_guard_process_denies_branch_creation_on_a_later_segment(
    main_checkout: Path, command: str
) -> None:
    assert _decision(_run("git_guard", command, main_checkout)) == "deny"


def test_publish_guard_process_denies_push_on_a_later_line(main_checkout: Path) -> None:
    assert _decision(_run("publish_guard", "git status\ngit push", main_checkout)) == "deny"


@pytest.mark.parametrize("hook", ["git_guard", "publish_guard"])
def test_guard_processes_stay_silent_on_safe_commands(main_checkout: Path, hook: str) -> None:
    assert _run(hook, "git status\ngit log -1", main_checkout) == ""


def test_git_guard_reads_worktree_and_branches_from_real_git(
    main_checkout: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)
    git = ["git", "-C", str(main_checkout), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path_factory.mktemp("wt") / "feat"
    subprocess.run([*git, "worktree", "add", "-q", "-b", "feat/1-x", str(worktree)], check=True)
    if str(_HOOKS) not in sys.path:
        sys.path.insert(0, str(_HOOKS))
    import git_guard  # noqa: PLC0415 — hook carregado do diretório dele, como no processo

    assert git_guard.is_main_worktree(main_checkout)
    assert not git_guard.is_main_worktree(worktree)
    assert not git_guard.is_main_worktree(tmp_path_factory.mktemp("not-a-repo"))
    assert git_guard.branch_exists(main_checkout, "feat/1-x")
    assert not git_guard.branch_exists(main_checkout, "feat/2-y")
