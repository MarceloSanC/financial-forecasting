"""Unit do hook `.claude/hooks/git_guard.py` (git e sistema de arquivos injetados — sem I/O)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "git_guard.py"
MAIN = Path("/repo").resolve()
WORKTREE = Path("/repo-worktrees/feat-1").resolve()
_REPO = _HOOK.parents[2]
# GIT_DIR/GIT_WORK_TREE do container de check de worktree apontariam o git para o repo real
_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
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


# --- main --------------------------------------------------------------------------------


class _Bytes:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    def read(self) -> bytes:
        return self._data


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": _Bytes(text)})())


def test_main_emits_deny_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gg, "blocked", lambda _cmd, _cwd: True)
    _stdin(monkeypatch, json.dumps({"tool_input": {"command": "git switch -c x"}, "cwd": "."}))
    assert gg.main() == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"] == gg.REASON


@pytest.mark.parametrize(
    "stdin",
    [json.dumps({"tool_input": {"command": "git status"}, "cwd": "."}), "{nao json", "{}"],
)
def test_main_is_silent_when_allowed_or_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin: str
) -> None:
    monkeypatch.setattr(gg, "blocked", lambda _cmd, _cwd: False)
    _stdin(monkeypatch, stdin)
    assert gg.main() == 0
    assert capsys.readouterr().out == ""


# --- processo real e registro -------------------------------------------------------------


@pytest.fixture
def main_checkout(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True, env=_ENV)
    return tmp_path


def _run(payload: str) -> subprocess.CompletedProcess[str]:
    """Como o Claude Code chama: `python <hook>.py` com o payload no stdin (o helper vizinho
    `_shell_segments` resolve pelo diretório do script, sem o sys.path do pytest)."""
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=60,
        env=_ENV,
    )


@pytest.mark.parametrize(
    "command",
    ["git status\ngit checkout -b feat/99-x", "git status & git switch -c feat/99-x"],
)
def test_process_denies_branch_creation_on_a_later_segment(
    main_checkout: Path, command: str
) -> None:
    result = _run(json.dumps({"tool_input": {"command": command}, "cwd": str(main_checkout)}))
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_process_is_silent_on_safe_commands(main_checkout: Path) -> None:
    payload = {"tool_input": {"command": "git status\ngit log -1"}, "cwd": str(main_checkout)}
    assert _run(json.dumps(payload)).stdout == ""


def test_reads_worktree_and_branches_from_real_git(
    main_checkout: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)
    git = ["git", "-C", str(main_checkout), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path_factory.mktemp("wt") / "feat"
    subprocess.run([*git, "worktree", "add", "-q", "-b", "feat/1-x", str(worktree)], check=True)

    assert gg.is_main_worktree(main_checkout)
    assert not gg.is_main_worktree(worktree)
    assert not gg.is_main_worktree(tmp_path_factory.mktemp("not-a-repo"))
    assert gg.branch_exists(main_checkout, "feat/1-x")
    assert not gg.branch_exists(main_checkout, "feat/2-y")


def test_hook_is_registered_on_pre_tool_use_for_bash_and_powershell() -> None:
    settings = json.loads((_REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = [
        (entry["matcher"], hook.get("if"), hook["args"])
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if hook.get("type") == "command"
    ]
    args = ["${CLAUDE_PROJECT_DIR}/.claude/hooks/git_guard.py"]
    assert ("Bash|PowerShell", "Bash(git *)", args) in hooks
    assert ("Bash|PowerShell", "PowerShell(git *)", args) in hooks
