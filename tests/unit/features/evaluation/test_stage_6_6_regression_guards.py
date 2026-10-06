"""Guardas de regressão textuais da Stage 6.6 (CA13 e CA14; Auditoria de Testes).

CA13: nenhum `type: ignore` nos três use cases que leem o gold pelos acessores tipados.
CA14: nenhum teste lê o cohort real — o `cohort_id` do r0 só aparece nos testes de
consistência do plano (arquivos versionados, nenhum dado).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_USE_CASES = _REPO / "src/financial_forecasting/features/evaluation/application/use_cases"
_REAL_COHORT = "aapl_confirmatory-r0-" + "665f45d9169a"  # partido: este arquivo não casa
_ALLOWED = {"test_preregistration_consistency.py"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "module", ["scorecard_evidence.py", "scorecard_profile.py", "build_confirmatory_scorecard.py"]
)
def test_gold_readers_have_no_type_ignore(module: str) -> None:
    text = (_USE_CASES / module).read_text(encoding="utf-8")
    assert "type: ignore" not in text


@pytest.mark.unit
def test_no_test_reads_the_real_cohort() -> None:
    hits = [
        path.relative_to(_REPO).as_posix()
        for path in (_REPO / "tests").rglob("*.py")
        if path.name not in _ALLOWED and _REAL_COHORT in path.read_text(encoding="utf-8")
    ]
    assert hits == []
