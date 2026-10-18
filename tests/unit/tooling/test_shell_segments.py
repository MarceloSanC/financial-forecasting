"""Unit do helper `.claude/hooks/_shell_segments.py` (segmentação comum aos hooks — sem I/O)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_HELPER = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "_shell_segments.py"
HERE = Path("/repo").resolve()


def _load() -> ModuleType:
    # import pelo nome (não por arquivo): os hooks importam o mesmo objeto de módulo, e o teste
    # de regra comum do git_guard compara identidade das funções
    if str(_HELPER.parent) not in sys.path:
        sys.path.insert(0, str(_HELPER.parent))
    return importlib.import_module("_shell_segments")


ss = _load()


def _argv(command: str) -> list[list[str]]:
    return [toks for _here, toks in ss.commands(command, HERE)]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status && git push", [["git", "status"], ["git", "push"]]),
        ("git status || git push", [["git", "status"], ["git", "push"]]),
        ("git status; git push", [["git", "status"], ["git", "push"]]),
        ("git log | git push", [["git", "log"], ["git", "push"]]),
        ("git status & git push", [["git", "status"], ["git", "push"]]),
        ("git status\ngit push", [["git", "status"], ["git", "push"]]),
        ("& git push", [["git", "push"]]),
        ("& 'C:\\Git\\bin\\git.exe' push", [["C:\\Git\\bin\\git.exe", "push"]]),
    ],
)
def test_splits_on_every_separator(command: str, expected: list[list[str]]) -> None:
    assert _argv(command) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("(git push)", [["git", "push"]]),
        ("( git push )", [["git", "push"]]),
        ("{ git push; }", [["git", "push"]]),
        ("$(git push)", [["git", "push"]]),
        ("FOO=1 git push", [["git", "push"]]),
        ("env FOO=1 git push", [["git", "push"]]),
        ("sudo git push", [["git", "push"]]),
        ("if true; then git push; fi", [["true"], ["git", "push"], ["fi"]]),
        ("while x; do git push; done", [["x"], ["git", "push"], ["done"]]),
    ],
)
def test_strips_group_env_and_shell_words_before_the_executable(
    command: str, expected: list[list[str]]
) -> None:
    assert _argv(command) == expected


def test_group_close_is_removed_from_the_last_token() -> None:
    assert _argv("(git checkout -b feat/x)") == [["git", "checkout", "-b", "feat/x"]]
    assert _argv("{ git checkout -b feat/x;}") == [["git", "checkout", "-b", "feat/x"]]


def test_cd_updates_the_effective_directory_and_is_not_emitted() -> None:
    got = list(ss.commands("cd sub && git status\nSet-Location -Path ../other; git log", HERE))
    assert got == [
        ((HERE / "sub").resolve(), ["git", "status"]),
        ((HERE / "other").resolve(), ["git", "log"]),
    ]
    assert list(ss.commands("cd", HERE)) == []


def test_unbalanced_quotes_fall_back_to_whitespace_split() -> None:
    assert _argv('git commit -m "x') == [["git", "commit", "-m", '"x']]


@pytest.mark.parametrize("exe", ["git", "/usr/bin/git", "C:\\Git\\bin\\git.exe", "GIT"])
def test_executable_normalizes_path_and_extension(exe: str) -> None:
    assert ss.executable([exe, "status"]) == "git"


def test_git_invocation_reads_global_options() -> None:
    toks = ["git", "-C", "sub", "-c", "push.default=x", "--no-pager", "push", "origin"]
    assert ss.git_invocation(toks, HERE) == (
        (HERE / "sub").resolve(),
        ["push.default=x"],
        ["push", "origin"],
    )
    assert ss.git_invocation(["git", "status"], HERE) == (HERE, [], ["status"])
    assert ss.git_invocation(["git", "--git-dir", "-x", "log"], HERE) == (HERE, [], ["log"])
