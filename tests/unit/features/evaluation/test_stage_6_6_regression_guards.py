"""Guardas de regressão textuais da Stage 6.6 (CA13 e CA14; Auditoria de Testes).

CA13: nenhum `type: ignore` nos três use cases que leem o gold pelos acessores tipados.
CA14/I14: nenhum teste nem script lê o cohort real — o `cohort_id`, o hash do cohort e o
fingerprint do r0 só aparecem nos testes de consistência do plano (arquivos versionados).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_USE_CASES = _REPO / "src/financial_forecasting/features/evaluation/application/use_cases"
# literais do cohort real, partidos para este arquivo não casar consigo mesmo
_REAL_COHORT = (
    "aapl_confirmatory-r0-" + "665f45d9169a",
    "665f45d9169aba576d194e73d45c0508" + "f51f231f573c4de283c96fc5847365b1",
    "00e4406dcd96658d557f7d4d86face98" + "74fac42385e3cb182d54c5d2286695bd",
)
_ALLOWED = {"test_preregistration_consistency.py"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "module", ["scorecard_evidence.py", "scorecard_profile.py", "build_confirmatory_scorecard.py"]
)
def test_gold_readers_have_no_type_ignore(module: str) -> None:
    text = (_USE_CASES / module).read_text(encoding="utf-8")
    assert "type: ignore" not in text


@pytest.mark.unit
def test_no_test_or_script_reads_the_real_cohort() -> None:
    """I14: nenhum teste nem script cita o `cohort_id`, o hash do cohort ou o fingerprint."""
    paths = [*(_REPO / "tests").rglob("*.py"), *(_REPO / "scripts").rglob("*.py")]
    hits = [
        path.relative_to(_REPO).as_posix()
        for path in paths
        if path.name not in _ALLOWED
        and any(literal in path.read_text(encoding="utf-8") for literal in _REAL_COHORT)
    ]
    assert hits == []
