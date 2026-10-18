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
    if str(_HOOK.parent) not in sys.path:  # o hook importa o helper vizinho `_shell_segments`
        sys.path.insert(0, str(_HOOK.parent))
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
        "git status && git checkout -b feat/99-x",
        "git status || git checkout -b feat/99-x",
        "git status; git checkout -b feat/99-x",
        "git log | git checkout -b feat/99-x",
        "git status\ngit checkout -b feat/99-x",
        "git status\r\ngit checkout -b feat/99-x",
        "git status & git checkout -b feat/99-x",
        "& git checkout -b feat/99-x",
        "& 'C:\\Program Files\\Git\\bin\\git.exe' checkout -b feat/99-x",
        "(git checkout -b feat/99-x)",
        "( git checkout -b feat/99-x )",
        "{ git checkout -b feat/99-x; }",
        "$(git switch -c feat/99-x)",
        "FOO=1 git switch -c feat/99-x",
        "if true; then git switch -c feat/99-x; fi",
        "git status\n(git switch feat/77-6-1-scoring)",
        # checkout de branch existente casa pelo nome exato: `)` colado ou solto não pode vazar
        "(git checkout feat/77-6-1-scoring)",
        "( git checkout feat/77-6-1-scoring )",
        "{ git checkout feat/77-6-1-scoring;}",
    ],
)
def test_blocks_branch_change_after_any_separator(command: str) -> None:
    assert _blocked(command)


@pytest.mark.parametrize(
    "command",
    [
        "(git checkout develop)",
        "( git switch develop )",
        "git status\ngit log -1 & git diff",
        "{ git checkout -- src/app.py; }",
    ],
)
def test_groups_and_new_separators_do_not_create_false_positives(command: str) -> None:
    assert not _blocked(command)


def test_cd_to_worktree_on_a_previous_line_is_honored() -> None:
    assert not _blocked(f"cd {WORKTREE}\ngit switch -c feat/99-x")
    assert _blocked(f"cd {WORKTREE}\ncd {MAIN}\ngit switch -c feat/99-x")


def test_shares_the_segmentation_rule_with_publish_guard() -> None:
    import publish_guard  # noqa: PLC0415 — carregado do mesmo diretório que o git_guard

    assert gg.commands is publish_guard.commands
    assert gg.git_invocation is publish_guard.git_invocation


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
