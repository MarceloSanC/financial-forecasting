"""Unit das partes puras de `scripts/verify_citations.py` (sem rede)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_EXIT_OK, _EXIT_FAIL, _EXIT_INCONCLUSIVE = 0, 1, 2
_UNRELATED_MAX = 0.5

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "verify_citations.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_citations", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass resolve o módulo pelo nome
    spec.loader.exec_module(module)
    return module


vc = _load()


def test_extract_dois_strips_trailing_punctuation_and_dedups() -> None:
    text = (
        "Walters (2023), doi:10.1038/s41598-023-41032-5. De novo "
        "(https://doi.org/10.1038/s41598-023-41032-5) e 10.1287/mnsc.34.6.679;"
    )
    assert vc.extract_dois(text) == ["10.1038/s41598-023-41032-5", "10.1287/mnsc.34.6.679"]


def test_extract_arxiv_ids_from_prefix_and_url() -> None:
    text = "arXiv:2309.11495 e https://arxiv.org/abs/2104.08542v2, não 12.34"
    assert vc.extract_arxiv_ids(text) == ["2309.11495", "2104.08542"]


def test_title_similarity_ignores_case_and_punctuation() -> None:
    title = "Specification curve analysis"
    assert vc.title_similarity(title, "Specification Curve Analysis.") == 1.0
    assert vc.title_similarity(title, "Deep residual learning") < _UNRELATED_MAX


def test_main_without_citations_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("sem referências aqui", encoding="utf-8")
    assert vc.main([str(empty)]) == _EXIT_FAIL


def test_main_exit_codes_follow_worst_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(status: str) -> object:
        return lambda ident: vc.Result(status, ident)

    monkeypatch.setattr(vc, "check_doi", fake("OK"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_OK
    monkeypatch.setattr(vc, "check_doi", fake("ERROR"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_INCONCLUSIVE
    monkeypatch.setattr(vc, "check_doi", fake("NOT_FOUND"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_FAIL
