"""Unit do hook `.claude/hooks/issue_guard.py` (leitura de arquivo e stdin injetados — sem I/O)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "issue_guard.py"
CWD = Path("/repo").resolve()

FULL_BODY = """## Contexto

Algo a fazer.

### BC / camada

tooling (`.claude/hooks`)

### Depende de

#145

## Escopo

1. fazer.
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("issue_guard", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ig = _load()


def _body(bc: str | None = "tooling", deps: str | None = "nenhuma") -> str:
    parts = ["## Contexto\n\nAlgo.\n"]
    if bc is not None:
        parts.append(f"### BC / camada\n\n{bc}\n")
    if deps is not None:
        parts.append(f"### Depende de\n\n{deps}\n")
    parts.append("## Escopo\n\n1. fazer.\n")
    return "\n".join(parts)


def _reason(
    command: str, files: dict[Path, str] | None = None, *, windows: bool = False
) -> str | None:
    store = files or {}
    result: str | None = ig.check(command, CWD, read_file=store.get, windows=windows)
    return result


def _heredoc(body: str) -> str:
    return f'gh issue create --title "chore: x" --body "$(cat <<\'EOF\'\n{body}EOF\n)"'


def _herestring(body: str) -> str:
    return f"gh issue create --title 'chore: x' --body @'\n{body}'@"


# --- corpo completo passa ------------------------------------------------------------------


@pytest.mark.parametrize("wrap", [_heredoc, _herestring], ids=["bash-heredoc", "ps-herestring"])
def test_full_inline_body_passes(wrap: Callable[[str], str]) -> None:
    assert _reason(wrap(FULL_BODY)) is None


def test_full_inline_quoted_body_passes() -> None:
    assert _reason(f'gh issue create --title "x" -b "{FULL_BODY}"') is None
    assert _reason(f'gh issue create --title "x" --body="{FULL_BODY}"') is None


def test_full_body_file_passes_relative_to_cwd_and_cd() -> None:
    files = {CWD / "body.md": FULL_BODY, (CWD / "sub" / "b.md").resolve(): FULL_BODY}
    assert _reason("gh issue create --title x --body-file body.md", files) is None
    assert _reason('gh issue create -t x -F "body.md"', files) is None
    assert _reason("cd sub && gh issue create -t x -F b.md", files) is None
    assert _reason("Set-Location sub; gh issue create -t x --body-file=b.md", files) is None


@pytest.mark.parametrize(
    ("windows", "expected"), [(True, "c:/tmp/body.md"), (False, "/c/tmp/body.md")]
)
def test_git_bash_drive_path_becomes_native_only_on_windows(windows: bool, expected: str) -> None:
    seen: list[Path] = []

    def read(path: Path) -> str:
        seen.append(path)
        return FULL_BODY

    command = "gh issue create -t x -F /c/tmp/body.md"
    assert ig.check(command, CWD, read_file=read, windows=windows) is None
    assert seen[0].as_posix().endswith(expected)
    assert windows is ("/c/tmp" not in seen[0].as_posix())


def test_nenhuma_is_a_valid_value() -> None:
    assert _reason(_heredoc(_body(bc="nenhuma", deps="nenhuma"))) is None


def test_multiline_value_passes() -> None:
    assert _reason(_heredoc(_body(deps="- #145\n- Stage 6.5"))) is None


def test_value_that_only_contains_angle_brackets_passes() -> None:
    assert _reason(_heredoc(_body(bc="modeling (<camada> = application)"))) is None


def test_unquoted_heredoc_delimiter_passes() -> None:
    assert _reason(f'gh issue create -t x --body "$(cat <<EOF\n{FULL_BODY}EOF\n)"') is None


# --- campo faltando ou sem valor recusa ---------------------------------------------------


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        (_body(bc=None), "### BC / camada"),
        (_body(deps=None), "### Depende de"),
        (_body(bc=""), "### BC / camada"),
        (_body(deps=""), "### Depende de"),
        (_body(bc="_No response_"), "### BC / camada"),
        (_body(deps="_No response_"), "### Depende de"),
        (_body(bc="<BC afetado>"), "### BC / camada"),
        (_body(deps="<#N ou Stage>"), "### Depende de"),
    ],
)
def test_missing_or_empty_field_is_denied(body: str, missing: str) -> None:
    expected = f"sem valor válido em `{missing}`:"
    for command in (_heredoc(body), _herestring(body)):
        reason = _reason(command)
        assert reason is not None
        assert expected in reason
    reason = _reason("gh issue create -t x -F body.md", {CWD / "body.md": body})
    assert reason is not None
    assert expected in reason


def test_both_fields_missing_lists_both() -> None:
    reason = _reason(_heredoc(_body(bc=None, deps=None)))
    assert reason is not None
    assert "sem valor válido em `### BC / camada`, `### Depende de`:" in reason


def test_value_does_not_leak_from_next_section() -> None:
    body = "### BC / camada\n\n### Depende de\n\nnenhuma\n"
    assert ig.missing_fields(body) == ["BC / camada"]


def test_repeated_heading_passes_when_one_has_value() -> None:
    body = "### BC / camada\n\n### BC / camada\n\ntooling\n\n### Depende de\n\nnenhuma\n"
    assert ig.missing_fields(body) == []


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        (_body(bc="<!-- módulo afetado -->"), ["BC / camada"]),
        (_body(deps="<!--\n#145\n-->"), ["Depende de"]),
        ("<!--\n### BC / camada\n\ntooling\n-->\n" + _body(bc=None), ["BC / camada"]),
    ],
)
def test_html_comment_does_not_count_as_value(body: str, missing: list[str]) -> None:
    assert ig.missing_fields(body) == missing


def test_value_next_to_html_comment_still_counts() -> None:
    assert ig.missing_fields(_body(bc="<!-- dica -->\ntooling")) == []


def test_heading_level_must_be_three() -> None:
    body = "## BC / camada\n\ntooling\n\n### Depende de\n\nnenhuma\n"
    assert _reason(_heredoc(body)) is not None


def test_issue_reference_is_a_value_not_a_heading() -> None:
    assert _reason(_heredoc(_body(deps="#145"))) is None


# --- origens especiais do corpo -----------------------------------------------------------


@pytest.mark.parametrize("flag", ["--web", "-w"])
def test_web_passes(flag: str) -> None:
    assert _reason(f"gh issue create {flag}") is None
    assert _reason(f'gh issue create --title "x" --body "" {flag}') is None


def test_body_file_stdin_is_denied_with_reason() -> None:
    reason = _reason(f"gh issue create -t x -F - <<'EOF'\n{FULL_BODY}EOF")
    assert reason is not None
    assert "stdin" in reason
    assert _reason("gh issue create -t x --body-file -") == reason


def test_default_reader_reads_real_file_with_bom(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(FULL_BODY, encoding="utf-8-sig")
    assert ig.check("gh issue create -t x -F body.md", tmp_path) is None
    assert ig.check("gh issue create -t x -F ausente.md", tmp_path) is not None


def test_missing_body_file_is_denied() -> None:
    reason = _reason("gh issue create -t x -F nope.md")
    assert reason is not None
    assert "nope.md" in reason


def test_no_body_at_all_is_denied() -> None:
    assert _reason('gh issue create --title "x"') == ig.REASON_NO_BODY


@pytest.mark.parametrize("verb", ["create", "new"])
def test_unbalanced_quotes_in_issue_create_are_denied(verb: str) -> None:
    assert _reason(f'gh issue {verb} --title "x --body y') == ig.REASON_UNPARSEABLE


# --- comandos fora do escopo do hook --------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "gh issue view 147 --comments",
        "gh issue list --search x",
        'gh pr create --base develop --title "x" --body "y"',
        "git status",
        'echo "unbalanced',
        "echo gh issue create",
    ],
)
def test_other_commands_pass(command: str) -> None:
    assert _reason(command) is None


def test_create_on_a_later_line_is_checked() -> None:
    assert _reason('git status\ngh issue create --title "y" --body "sem campos"') is not None


@pytest.mark.parametrize(
    "command",
    [
        'echo $(date); gh issue create -t x -b "sem"',
        '$d = (Get-Date); gh issue create -t x -b "sem"',
        'echo $(date)\ngh issue create -t x -b "sem"',
        '(gh issue create -t x -b "sem")',
        'ls 2>&1; gh issue create -t x -b "sem"',
    ],
)
def test_create_after_fused_punctuation_is_checked(command: str) -> None:
    """O shlex funde `);`, `)\\n` e `>&;` num token só; o `create` seguinte ainda é checado."""
    assert _reason(command) is not None


def test_redirect_does_not_split_the_create_command() -> None:
    files = {CWD / "body.md": FULL_BODY}
    assert _reason("gh issue create -t x -F body.md > out.txt 2>&1", files) is None


def test_issue_new_alias_is_checked() -> None:
    assert _reason('gh issue new --title "y" --body "sem campos"') is not None
    assert _reason(_heredoc(FULL_BODY).replace("issue create", "issue new")) is None
    assert _reason("gh issue new --web") is None


def test_second_create_in_chain_is_checked() -> None:
    command = _heredoc(FULL_BODY) + ' && gh issue create --title "y" --body "sem campos"'
    assert _reason(command) is not None


# --- main (stdin/stdout) -------------------------------------------------------------------


def _run_main(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> int:
    stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    code: int = ig.main()
    return code


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_main_denies_with_hook_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool: str
) -> None:
    payload = {
        "tool_name": tool,
        "tool_input": {"command": 'gh issue create --title "x" --body "sem campos"'},
        "cwd": str(CWD),
    }
    assert _run_main(monkeypatch, json.dumps(payload).encode()) == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert "### BC / camada" in out["permissionDecisionReason"]


def test_main_is_silent_when_command_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"command": "gh issue create --web"}, "cwd": str(CWD)}
    assert _run_main(monkeypatch, json.dumps(payload).encode()) == 0
    assert capsys.readouterr().out == ""


def test_main_ignores_invalid_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(monkeypatch, b"{not json") == 0
    assert capsys.readouterr().out == ""
