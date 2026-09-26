"""Unit do hook `.claude/hooks/git_guard.py` (git e sistema de arquivos injetados — sem I/O)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "git_guard.py"
MAIN = Path("/repo").resolve()
WORKTREE = Path("/repo-worktrees/feat-1").resolve()
LOCAL_BRANCHES = {"develop", "feat/77-6-1-scoring", "feat/80-remote-only"}  # local ou remota


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("git_guard", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gg = _load()


def _blocked(command: str, cwd: Path = MAIN) -> bool:
    return bool(
        gg.blocked(
            command,
            cwd,
            is_main=lambda p: p == MAIN,
            exists=lambda _p, name: name in LOCAL_BRANCHES,
        )
    )


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b feat/99-x",
        "git switch -c feat/99-x",
        "git switch --create feat/99-x",
        "git switch feat/77-6-1-scoring",
        "git checkout feat/77-6-1-scoring",
        "git worktree add ../x feat/99-x",
        "git checkout feat/80-remote-only",
        "git checkout --track origin/feat/80-remote-only",
        "git checkout -t origin/feat/80-remote-only",
        "git switch -",
        "git checkout -",
        "git status && git checkout -b feat/99-x",
        f"git -C {MAIN} switch -c feat/99-x",
    ],
)
def test_blocks_branch_changes_in_main_checkout(command: str) -> None:
    assert _blocked(command)


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git checkout develop",
        "git switch develop",
        "git checkout -- src/app.py",
        "git checkout src/app.py",
        "git log --oneline -5",
        "python scripts/worktree-new.py feat/99-x --no-setup --no-vscode",
    ],
)
def test_allows_safe_commands_in_main_checkout(command: str) -> None:
    assert not _blocked(command)


def test_allows_branch_work_inside_a_worktree() -> None:
    assert not _blocked("git checkout -b feat/99-x", cwd=WORKTREE)
    assert not _blocked(f"git -C {WORKTREE} switch -c feat/99-x")
    assert not _blocked(f"cd {WORKTREE} && git switch -c feat/99-x")
