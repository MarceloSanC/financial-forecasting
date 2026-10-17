"""Unit do hook `.claude/hooks/publish_guard.py` (git e GitHub injetados — sem I/O)."""

from __future__ import annotations

import importlib.util
import json
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
COMPLETE_BODY = "Closes #1\n\n> **Auditoria:** `complete`\n>\n> Label de status.\n"


def _load() -> ModuleType:
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
    assert _reason("gh pr merge 7 --merge") is None
    assert _reason("gh pr merge 7 -m --delete-branch") is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 7",
        "gh pr merge 7 --squash",
        "gh pr merge 7 --rebase",
        "gh pr merge 7 --merge --admin",
        "gh pr merge 7 --merge --auto",
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
    ],
)
def test_blocks_merge_when_a_condition_fails(overrides: dict[str, Any], fragment: str) -> None:
    found = _reason("gh pr merge 7 --merge", pr=_pr(**overrides))
    assert found is not None
    assert fragment in found


def test_merge_fails_closed_when_github_query_fails() -> None:
    found = pg.reason(
        "gh pr merge 7 --merge",
        WORKTREE,
        is_main=lambda _p: False,
        branch=lambda _p: "feat/1-x",
        fetch=lambda *_: None,
    )
    assert found is not None


def test_merge_passes_selector_and_repo_to_fetch() -> None:
    seen: list[tuple[str | None, str | None]] = []

    def fetch(sel: str | None, _cwd: Path, repo: str | None) -> dict[str, Any]:
        seen.append((sel, repo))
        return _pr()

    pg.reason(
        "gh pr merge 7 -R owner/repo --merge",
        WORKTREE,
        is_main=lambda _p: False,
        branch=lambda _p: "feat/1-x",
        fetch=fetch,
    )
    assert seen == [("7", "owner/repo")]


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


class _Bytes:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    def read(self) -> bytes:
        return self._data
