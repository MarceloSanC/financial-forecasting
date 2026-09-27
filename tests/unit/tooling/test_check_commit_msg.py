"""Unit de `scripts/check_commit_msg.py` — leitura do arquivo da mensagem (BOM)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_commit_msg.py"
_EXIT_OK, _EXIT_FAIL = 0, 1


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_msg", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccm = _load()


def test_message_with_utf8_bom_is_rejected_naming_the_bom(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # caso real (sessão da #78): PowerShell grava UTF-8 com BOM e o U+FEFF iria para o subject
    msg = tmp_path / "msg.txt"
    msg.write_bytes(b"\xef\xbb\xbfdocs(git): mensagem valida\n")
    assert ccm.main(["check_commit_msg.py", str(msg)]) == _EXIT_FAIL
    assert "BOM" in capsys.readouterr().err


def test_same_message_without_bom_passes(tmp_path: Path) -> None:
    msg = tmp_path / "msg.txt"
    msg.write_bytes(b"docs(git): mensagem valida\n")
    assert ccm.main(["check_commit_msg.py", str(msg)]) == _EXIT_OK
