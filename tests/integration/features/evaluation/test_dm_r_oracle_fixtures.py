"""Golden test do DM do domínio contra o oráculo R `forecast::dm.test` (A4 integração; I12).

Integração (lê `tests/fixtures/r_oracle/dm_test_cases.json`, gerado por
`dm_test_cases.R` na imagem `rocker/r-ver:4.4.1` com `forecast` 8.23.0 — proveniência
testada em `test_r_oracle_provenance.py`; ADR 6.2.0006). Para cada caso, as entradas vêm
da forma **hex** (`float.fromhex`, round-trip exato) e o primitivo `diebold_mariano` do
domínio reproduz o R: mesmo `horizon_used` (fallback), estatística sob
`math.isclose(rel_tol=1e-11, abs_tol=1e-14)` e p-valor sob `_assert_p_close`; os casos
de erro do R erguem `ValueError` no domínio. O `pt` do R é também oráculo isolado da t:
`student_t_cdf(S1*_R, T - 1)` contra o p do R (concept I12).

A tolerância da estatística supõe var̂ muito acima de ulp(d̄)² (technical 6.2 §7): nenhum
caso da fixture tem diferencial quase constante sem ser exatamente constante.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMarianoResult,
    DmVarianceEstimator,
    diebold_mariano,
)
from financial_forecasting.features.evaluation.domain.services.student_t import student_t_cdf

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "r_oracle" / "dm_test_cases.json"
_CASES: list[dict[str, Any]] = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]
_ESTIMATORS = {"acf": DmVarianceEstimator.RECTANGULAR, "bartlett": DmVarianceEstimator.BARTLETT}

# Tolerâncias declaradas (technical 6.2 §1).
_STAT_REL_TOL = 1e-11
_STAT_ABS_TOL = 1e-14
_P_ABS_TOL = 1e-12
_P_TAIL_REL_TOL = 1e-10
_HALF = 0.5
_SMALL_T = 10
_REQUIRED_HORIZONS = {1, 7}
# Mensagem do R -> padrão da mensagem do domínio, por categoria (os textos diferem; a
# categoria não). Mensagem do R nova → KeyError: o caso precisa de categoria declarada.
_DOMAIN_ERROR = {
    "h cannot be longer than the number of forecast errors": r"\(T > h\)",
    "Variance of DM statistic is zero": "^Variance of DM statistic is zero$",
}


def _assert_p_close(actual: float, expected: float) -> None:
    """|Δp| ≤ 1e-12 sempre e, na cauda (ref < 0,5), |Δp| ≤ 1e-10·ref."""
    assert abs(actual - expected) <= _P_ABS_TOL, (actual, expected)
    if expected < _HALF:
        assert abs(actual - expected) <= _P_TAIL_REL_TOL * expected, (actual, expected)


def _losses(case: dict[str, Any], key: str) -> list[float]:
    return [float.fromhex(value) for value in case["inputs"][key]["hex"]]


def _n_points(case: dict[str, Any]) -> int:
    return len(case["inputs"]["candidate_losses"]["hex"])


def _run(case: dict[str, Any]) -> DieboldMarianoResult:
    inputs = case["inputs"]
    assert (inputs["alternative"], inputs["power"]) == ("less", 1)
    return diebold_mariano(
        candidate_losses=_losses(case, "candidate_losses"),
        comparator_losses=_losses(case, "comparator_losses"),
        horizon=inputs["horizon"],
        variance_estimator=_ESTIMATORS[inputs["varestimator"]],
    )


_IDS = [case["id"] for case in _CASES]
_OK_CASES = [case for case in _CASES if "expected" in case]


@pytest.mark.integration
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_r_fixture_case_matches(case: dict[str, Any]) -> None:
    if "expected_error" in case:
        with pytest.raises(ValueError, match=_DOMAIN_ERROR[case["expected_error"]]):
            _run(case)
        return
    expected = case["expected"]
    result = _run(case)
    assert result.horizon_used == expected["horizon_used"]
    assert result.fallback_applied == (expected["horizon_used"] != case["inputs"]["horizon"])
    assert math.isclose(
        result.statistic, expected["statistic"], rel_tol=_STAT_REL_TOL, abs_tol=_STAT_ABS_TOL
    ), (result.statistic, expected["statistic"])
    _assert_p_close(result.p_value, expected["p_value"])


@pytest.mark.integration
@pytest.mark.parametrize("case", _OK_CASES, ids=[case["id"] for case in _OK_CASES])
def test_r_fixture_t_isolated(case: dict[str, Any]) -> None:
    """`student_t_cdf` sobre a estatística do próprio R contra o `pt` do R."""
    expected = case["expected"]
    actual = student_t_cdf(expected["statistic"], float(_n_points(case) - 1))
    _assert_p_close(actual, expected["p_value"])


@pytest.mark.integration
def test_r_fixture_covers_required_scenarios() -> None:
    ok = _OK_CASES
    errors = [case for case in _CASES if "expected_error" in case]
    horizons = {case["inputs"]["horizon"] for case in ok}
    assert horizons >= _REQUIRED_HORIZONS
    assert {case["inputs"]["varestimator"] for case in ok} == set(_ESTIMATORS)
    assert any(case["expected"]["statistic"] < 0 for case in ok)  # candidato melhor
    assert any(case["expected"]["statistic"] > 0 for case in ok)  # candidato pior
    assert any(_n_points(case) <= _SMALL_T for case in ok)  # T pequeno sem erro
    assert any(case["expected"]["horizon_used"] != case["inputs"]["horizon"] for case in ok)
    constant_h2 = [
        case
        for case in errors
        if case["inputs"]["horizon"] == 2  # noqa: PLR2004 — o caso constante com h = 2
        and case["expected_error"] == "Variance of DM statistic is zero"
    ]
    assert constant_h2, "missing: constant differential with h = 2 (fallback, then error)"
    assert any(case["inputs"]["horizon"] > _n_points(case) for case in errors)  # h > T
    assert any(
        case["inputs"]["horizon"] == 1
        and case["expected_error"] == "Variance of DM statistic is zero"
        for case in errors
    )
    assert all(case["inputs"]["horizon"] != _n_points(case) for case in _CASES)  # nunca h = T
