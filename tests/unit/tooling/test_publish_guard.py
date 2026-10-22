"""Unit do hook `.claude/hooks/publish_guard.py` (git e GitHub injetados — sem I/O)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "publish_guard.py"
MAIN = Path("/repo").resolve()
WORKTREE = Path("/repo-worktrees/feat-1").resolve()
BRANCHES = {MAIN: "develop", WORKTREE: "feat/1-x"}
HEAD = "abc123"
MERGE = f"gh pr merge 7 --merge --match-head-commit {HEAD}"
COMPLETE_BODY = "Closes #1\n\n> **Auditoria:** `complete`\n>\n> Label de status.\n"


def _load() -> ModuleType:
    if str(_HOOK.parent) not in sys.path:  # o hook importa o helper vizinho `_shell_segments`
        sys.path.insert(0, str(_HOOK.parent))
    spec = importlib.util.spec_from_file_location("publish_guard", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pg = _load()


def _pr(**overrides: object) -> dict[str, Any]:
    pr: dict[str, Any] = {
        "number": 7,
        "headRefOid": HEAD,
        "baseRefName": "develop",
        "isDraft": False,
        "body": COMPLETE_BODY,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [
            {"name": "lint-and-test", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "audit-status", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "guard-main-source", "status": "COMPLETED", "conclusion": "SKIPPED"},
        ],
        "unresolvedThreads": 0,
    }
    pr.update(overrides)
    return pr


def _reason(command: str, cwd: Path = WORKTREE, pr: dict[str, Any] | None = None) -> str | None:
    state = _pr() if pr is None else pr
    found: str | None = pg.reason(
        command,
        cwd,
        is_main=lambda p: p == MAIN,
        branch=BRANCHES.get,
        fetch=lambda _sel, _cwd, _repo: state,
    )
    return found


# --- git push ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git push origin develop",
        "git push origin main",
        "git push origin feat/1-x:develop",
        "git push origin HEAD:refs/heads/main",
        "git push origin :develop",
        "git push --delete origin develop",
        "git push --force",
        "git push -f origin feat/1-x",
        "git push origin +feat/1-x",
        "git push --all origin",
        "git push --mirror",
        "git status && git push --force",
        "GIT_TRACE=1 git push origin develop",
        "git status\ngit push origin develop",
        "echo x & git push origin develop",
        "& git push origin develop",
        "(git push origin develop)",
        "{ git push origin develop; }",
        "env git push origin develop",
        "nohup git push origin develop",
        "if true; then git push origin develop; fi",
        "while true; do git push origin develop; done",
        "git push origin heads/develop",
        "git push origin @:develop",
        "git push origin 'refs/heads/*:refs/heads/*'",
        "git push origin '*:*'",
        "git push origin :",
        "git push --prune origin feat/1-x",
        "git push -fu origin feat/1-x",
        "git -c push.default=matching push",
        "git -c remote.origin.push=HEAD:develop push",
    ],
)
def test_blocks_unsafe_push_from_worktree(command: str) -> None:
    assert _reason(command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -q",
        "git push -u origin feat/1-x",
        "git push origin HEAD",
        "git push --force-with-lease",
        "git push --force-with-lease=feat/1-x origin feat/1-x",
        "git push origin --delete feat/1-x",
        "git push --force-with-lease --force-if-includes origin feat/1-x",
        "git push origin feat/1-x 2>&1",
        "git -c core.quotepath=off push",
    ],
)
def test_allows_feature_branch_push_from_worktree(command: str) -> None:
    assert _reason(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin feat/1-x",
        f"git -C {WORKTREE} status && git push origin feat/1-x",
    ],
)
def test_blocks_any_push_from_main_checkout(command: str) -> None:
    assert _reason(command, cwd=MAIN) is not None


def test_git_dash_c_redirects_to_worktree() -> None:
    assert _reason(f"git -C {WORKTREE} push", cwd=MAIN) is None


def test_cd_into_worktree_redirects() -> None:
    assert _reason(f"cd {WORKTREE} && git push", cwd=MAIN) is None


def test_set_location_path_redirects() -> None:
    assert _reason(f"Set-Location -Path {WORKTREE}; git push", cwd=MAIN) is None


def test_push_without_refspec_on_protected_branch_is_blocked() -> None:
    other = Path("/repo-worktrees/odd").resolve()
    found = pg.reason(
        "git push",
        other,
        is_main=lambda _p: False,
        branch=lambda _p: "main",
        fetch=lambda *_: None,
    )
    assert found is not None


# --- gh pr merge -------------------------------------------------------------------------


def test_allows_merge_when_every_condition_holds() -> None:
    assert _reason(MERGE) is None
    assert _reason(f"gh pr merge 7 -m --delete-branch --match-head-commit={HEAD}") is None
    assert _reason(f"gh pr merge --merge --match-head-commit {HEAD} 7") is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 7",
        "gh pr merge 7 --squash",
        "gh pr merge 7 --rebase",
        "gh pr merge 7 --merge --admin",
        "gh pr merge 7 --merge --auto",
        "gh pr merge 7 --merge",
        "gh pr merge 7 --merge --match-head-commit outro",
    ],
)
def test_blocks_merge_with_wrong_strategy(command: str) -> None:
    assert _reason(command) is not None


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"baseRefName": "main"}, "base `main`"),
        ({"isDraft": True}, "draft"),
        ({"body": "> **Auditoria:** `review`"}, "Auditoria"),
        ({"body": ""}, "Auditoria"),
        ({"mergeStateStatus": "UNSTABLE"}, "UNSTABLE"),
        ({"mergeStateStatus": "UNKNOWN"}, "UNKNOWN"),
        ({"unresolvedThreads": 2}, "2 conversa"),
        (
            {"statusCheckRollup": [{"name": "lint-and-test", "status": "IN_PROGRESS"}]},
            "lint-and-test",
        ),
        (
            {"statusCheckRollup": [{"name": "audit-status", "conclusion": "FAILURE"}]},
            "audit-status",
        ),
        ({"statusCheckRollup": [{"context": "ext", "state": "PENDING"}]}, "ext"),
        ({"statusCheckRollup": []}, "lint-and-test"),
        (
            {"statusCheckRollup": [{"name": "lint-and-test", "conclusion": "SUCCESS"}]},
            "audit-status",
        ),
        ({"body": "> **Auditoria:** `completeness`"}, "Auditoria"),
    ],
)
def test_blocks_merge_when_a_condition_fails(overrides: dict[str, Any], fragment: str) -> None:
    found = _reason(MERGE, pr=_pr(**overrides))
    assert found is not None
    assert fragment in found


def test_merge_fails_closed_when_github_query_fails() -> None:
    found = pg.reason(
        MERGE,
        WORKTREE,
        is_main=lambda _p: False,
        branch=lambda _p: "feat/1-x",
        fetch=lambda *_: None,
    )
    assert found is not None


@pytest.mark.parametrize(
    "command",
    [
        f"gh pr merge 7 -R o/r --merge --match-head-commit {HEAD}",
        f"gh -R o/r pr merge 7 --merge --match-head-commit {HEAD}",
        f"gh --repo=o/r pr merge 7 --merge --match-head-commit {HEAD}",
        f"gh pr --repo o/r merge 7 --merge --match-head-commit {HEAD}",
        f"gh pr merge -Ro/r 7 --merge --match-head-commit {HEAD}",
    ],
)
def test_merge_finds_repo_flag_in_any_position(command: str) -> None:
    seen: list[tuple[str | None, str | None]] = []

    def fetch(sel: str | None, _cwd: Path, repo: str | None) -> dict[str, Any]:
        seen.append((sel, repo))
        return _pr(isDraft=True)

    found = pg.reason(
        command,
        WORKTREE,
        is_main=lambda _p: False,
        branch=lambda _p: "feat/1-x",
        fetch=fetch,
    )
    assert seen == [("7", "o/r")]
    assert found is not None


def test_merge_split_by_newline_is_still_checked() -> None:
    assert _reason(f"git fetch\n{MERGE}", pr=_pr(isDraft=True)) is not None


# --- gh edit / issue / api ---------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "gh pr edit 7 --base main",
        "gh pr edit 7 -B main",
        "gh pr edit 7 --add-label bug",
        "gh issue edit 9 --add-assignee someone",
        "gh issue edit 9 --milestone v1",
        "gh issue edit 9 --remove-label bug",
        "gh issue edit 9 --add-project Roadmap",
        "gh pr edit 7 --remove-project Roadmap",
        "gh pr edit 7 -Bmain",
        "gh pr edit 7 -mv1",
        "gh issue -R o/r close 9",
        "gh api -XPUT repos/o/r/pulls/7/merge",
        "gh api -X=PUT repos/o/r/pulls/7/merge",
        "gh api repos/o/r/pulls/7/merge -fmerge_method=merge",
        "gh issue close 9",
        "gh issue reopen 9",
        "gh issue delete 9",
        "gh issue transfer 9 other/repo",
        "gh api -X PUT repos/o/r/pulls/7/merge",
        "gh api --method=DELETE repos/o/r/git/refs/heads/develop",
        "gh api repos/o/r/issues/9/comments -f body=x",
        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
    ],
)
def test_blocks_out_of_scope_github_writes(command: str) -> None:
    assert _reason(command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr edit 7 --body-file corpo.md",
        "gh pr edit 7 --title novo",
        "gh issue edit 9 --body-file corpo.md",
        "gh pr comment 7 --body-file veredito.md",
        "gh issue comment 9 --body texto",
        "gh pr view 7 --json state",
        "gh pr checks 7 --watch --fail-fast",
        "gh api repos/o/r/pulls/7",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh issue view 9",
    ],
)
def test_allows_routine_github_commands(command: str) -> None:
    assert _reason(command) is None


# --- main --------------------------------------------------------------------------------


def test_main_emits_deny_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pg, "reason", lambda _cmd, _cwd: "motivo")
    payload = json.dumps({"tool_input": {"command": "git push"}, "cwd": str(WORKTREE)})
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": _Bytes(payload)})())
    assert pg.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "motivo" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_main_is_silent_when_allowed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pg, "reason", lambda _cmd, _cwd: None)
    payload = json.dumps({"tool_input": {"command": "git status"}, "cwd": str(WORKTREE)})
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": _Bytes(payload)})())
    assert pg.main() == 0
    assert capsys.readouterr().out == ""


def test_process_denies_push_on_a_later_line(tmp_path: Path) -> None:
    """Processo real (`python publish_guard.py`), contra repo git em tmp_path: o import do helper
    vizinho resolve fora do pytest e a recusa sai mesmo com o push numa linha seguinte."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True, env=env)
    for command, denied in (("git status\ngit push", True), ("git status\ngit log -1", False)):
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(tmp_path)})
        result = subprocess.run(
            [sys.executable, str(_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=60,
            env=env,
        )
        assert ('"deny"' in result.stdout) is denied


def test_payload_with_utf8_bom_is_read(tmp_path: Path) -> None:
    """Pipe do Windows PowerShell 5.1 prefixa BOM; sem `utf-8-sig` o hook calava (fail open)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True, env=env)
    payload = json.dumps({"tool_input": {"command": "git push"}, "cwd": str(tmp_path)})
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=("﻿" + payload).encode("utf-8"),
        capture_output=True,
        check=True,
        timeout=60,
        env=env,
    )
    out = json.loads(result.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_hook_is_registered_on_pre_tool_use_for_bash_and_powershell() -> None:
    settings_path = _HOOK.parents[1] / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = [
        (entry["matcher"], hook.get("if"), hook["args"])
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if hook.get("type") == "command"
    ]
    args = ["${CLAUDE_PROJECT_DIR}/.claude/hooks/publish_guard.py"]
    assert ("Bash|PowerShell", None, args) in hooks


class _Bytes:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    def read(self) -> bytes:
        return self._data
