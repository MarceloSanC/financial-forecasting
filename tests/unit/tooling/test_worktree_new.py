"""Unit de `scripts/worktree-new.py` — `--create-issue` exige BC e dependências no corpo.

O `gh issue create` do script roda por subprocess, fora do alcance do hook `issue_guard`; o
script aplica a mesma regra (`missing_fields` do hook). `gh` é substituído por fakes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "worktree-new.py"

NEW_ISSUE = 201
EXISTING_ISSUE = 42
EXIT_EXEC_ERROR = 2
FULL_BODY = "## O quê\n\nx\n\n### BC / camada\n\ntooling\n\n### Depende de\n\nnenhuma\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worktree_new", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wn = _load()


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake_create(title: str, body: str) -> int:
        calls.append((title, body))
        return NEW_ISSUE

    monkeypatch.setattr(wn, "gh_available", lambda: True)
    monkeypatch.setattr(wn, "gh_issue_create", fake_create)
    return calls


@pytest.mark.parametrize(
    ("body", "absent"),
    [
        (None, "`### BC / camada`, `### Depende de`"),
        ("## O quê\n\nx\n", "`### BC / camada`, `### Depende de`"),
        (FULL_BODY.replace("tooling", "_No response_"), "`### BC / camada`"),
        (FULL_BODY.replace("nenhuma", "<#N>"), "`### Depende de`"),
    ],
)
def test_create_issue_without_fields_fails_before_calling_gh(
    created: list[tuple[str, str]],
    capsys: pytest.CaptureFixture[str],
    body: str | None,
    absent: str,
) -> None:
    with pytest.raises(SystemExit) as exc:
        wn.ensure_issue(0, create_title="chore: x", create_body=body)
    assert exc.value.code == 1
    assert created == []
    assert f"--issue-body sem valor válido em {absent}." in capsys.readouterr().err


def test_create_issue_with_fields_creates(created: list[tuple[str, str]]) -> None:
    assert wn.ensure_issue(0, create_title="chore: x", create_body=FULL_BODY) == NEW_ISSUE
    assert created == [("chore: x", FULL_BODY)]


def test_existing_issue_number_skips_body_validation(
    monkeypatch: pytest.MonkeyPatch, created: list[tuple[str, str]]
) -> None:
    monkeypatch.setattr(wn, "gh_issue_exists", lambda num: num == EXISTING_ISSUE)
    assert (
        wn.ensure_issue(EXISTING_ISSUE, create_title="chore: x", create_body=None) == EXISTING_ISSUE
    )
    assert created == []


def test_rule_comes_from_the_hook() -> None:
    assert wn.ISSUE_GUARD.name == "issue_guard.py"
    assert wn.issue_body_missing_fields(FULL_BODY) == []
    assert wn.issue_body_missing_fields("") == ["BC / camada", "Depende de"]


def test_unloadable_guard_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        wn.issue_body_missing_fields(FULL_BODY, guard=tmp_path / "ausente.txt")
    assert exc.value.code == EXIT_EXEC_ERROR
