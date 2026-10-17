"""Unit do hook `.claude/hooks/arch_feedback.py` (PostToolUse Edit|Write, issue #161).

A raiz de teste em `tmp_path` leva uma cópia dos gates de `scripts/` e do executor da
skill (o hook carrega o executor da raiz do arquivo editado, como numa worktree); nada
toca o `src/` real. O processo real do hook (stdin JSON → stderr + exit code) roda por
subprocess.
"""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_HOOK = _REPO / ".claude" / "hooks" / "arch_feedback.py"
_DOMAIN_FILE = "src/financial_forecasting/features/evaluation/domain/services/clocky.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("arch_feedback", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


af = _load()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Repo mínimo: gates + libs de `scripts/`, baseline vazio e o executor da skill."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for source in (_REPO / "scripts").glob("*.py"):
        if source.name.startswith(("check_", "arch_")):
            shutil.copy(source, scripts / source.name)
    (scripts / "arch_baseline.toml").write_text("", encoding="utf-8")
    runner = tmp_path / af.RUNNER_REL
    runner.parent.mkdir(parents=True)
    shutil.copy(_REPO / af.RUNNER_REL, runner)
    return tmp_path


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _payload(file_path: str, cwd: Path | None = None) -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path},
        "cwd": str(cwd or Path.cwd()),
    }


def _run(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_HOOK)], input=payload, capture_output=True, text=True, check=False
    )


def test_violation_in_edited_file_goes_to_stderr_with_exit_2(root: Path) -> None:
    edited = _write(root, _DOMAIN_FILE, "import time\nx = time.time()\n")

    result = _run(json.dumps(_payload(str(edited))))

    assert result.returncode == af.EXIT_FEEDBACK
    assert f"{_DOMAIN_FILE}::time.time: linhas L2" in result.stderr
    assert "reference/domain-purity.md" in result.stderr
    assert result.stdout == ""


def test_payload_with_utf8_bom_is_read(root: Path) -> None:
    """Pipe do Windows PowerShell 5.1 prefixa BOM; sem `utf-8-sig` o hook calava (fail open)."""
    edited = _write(root, _DOMAIN_FILE, "import time\nx = time.time()\n")

    result = _run("﻿" + json.dumps(_payload(str(edited))))

    assert result.returncode == af.EXIT_FEEDBACK


def test_clean_edit_is_silent(root: Path) -> None:
    edited = _write(root, _DOMAIN_FILE, "x = 1\n")

    result = _run(json.dumps(_payload(str(edited))))

    assert (result.returncode, result.stderr) == (0, "")


def test_fixing_baselined_debt_asks_to_remove_the_entry(root: Path) -> None:
    edited = _write(root, _DOMAIN_FILE, "x = 1\n")
    (root / "scripts" / "arch_baseline.toml").write_text(
        f"[[domain_determinism.allow]]\nkey = '{_DOMAIN_FILE}::time.time'\n"
        'motivo = "débito"\nissue = 1\n',
        encoding="utf-8",
    )

    message = af.feedback(_payload(str(edited)))

    assert message is not None
    assert "baseline morto" in message


def test_relative_path_resolves_against_the_payload_cwd(root: Path) -> None:
    _write(root, _DOMAIN_FILE, "import time\nx = time.time()\n")

    assert af.feedback(_payload(_DOMAIN_FILE, cwd=root)) is not None


@pytest.mark.parametrize(
    "rel",
    [
        pytest.param("src/financial_forecasting/notes.md", id="nao-python"),
        pytest.param("scripts/tool.py", id="fora-de-src"),
        pytest.param("src/financial_forecasting/missing.py", id="arquivo-inexistente"),
    ],
)
def test_out_of_scope_edits_are_ignored(root: Path, rel: str) -> None:
    if not rel.endswith("missing.py"):
        _write(root, rel, "import time\nx = time.time()\n")

    assert af.feedback(_payload(str(root / rel))) is None


def test_file_outside_any_repo_is_ignored(tmp_path: Path) -> None:
    edited = _write(tmp_path, _DOMAIN_FILE, "import time\nx = time.time()\n")

    assert af.find_root(edited) is None
    assert af.feedback(_payload(str(edited))) is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json", id="json-invalido"),
        pytest.param("[1, 2]", id="json-nao-objeto"),
        pytest.param(json.dumps({"tool_input": {}}), id="sem-file-path"),
    ],
)
def test_unexpected_input_fails_open(payload: str) -> None:
    assert _run(payload).returncode == 0


def test_malformed_baseline_fails_open(root: Path) -> None:
    """O gate sai com exit 2 em baseline malformado; o hook não repassa (fail open)."""
    edited = _write(root, _DOMAIN_FILE, "import time\nx = time.time()\n")
    (root / "scripts" / "arch_baseline.toml").write_text(
        "[[domain_determinism.allow]]\nkey = 'x'\n", encoding="utf-8"
    )

    result = _run(json.dumps(_payload(str(edited))))

    # exit 0: o Claude Code não mostra ao agente o stderr (o aviso do gate) de hook que sai 0
    assert result.returncode == 0
    assert "arch_feedback:" not in result.stderr


def _main(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> int:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    return int(af.main())


def test_main_in_process_follows_feedback(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mesmo contrato do processo, medido em processo (o subprocess não entra na cobertura)."""
    dirty = _write(root, _DOMAIN_FILE, "import time\nx = time.time()\n")
    assert _main(monkeypatch, json.dumps(_payload(str(dirty))).encode()) == af.EXIT_FEEDBACK
    assert "time.time" in capsys.readouterr().err

    dirty.write_text("x = 1\n", encoding="utf-8")
    assert _main(monkeypatch, json.dumps(_payload(str(dirty))).encode()) == 0
    assert _main(monkeypatch, b"not json") == 0
    assert _main(monkeypatch, b"[1]") == 0
    assert capsys.readouterr().err == ""


def test_hook_is_registered_on_post_tool_use_for_edit_and_write() -> None:
    settings = json.loads((_REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PostToolUse"]

    commands = [
        (entry["matcher"], hook["args"])
        for entry in entries
        for hook in entry["hooks"]
        if hook.get("type") == "command"
    ]

    assert ("Edit|Write", ["${CLAUDE_PROJECT_DIR}/.claude/hooks/arch_feedback.py"]) in commands
