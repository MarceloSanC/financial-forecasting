"""Unit test do `DieboldMariano` contra casos calculados à mão (A4 unit, A1, C2, C3, C8).

Desvio de caminho declarado (concept 6.2 D7; ADR 6.2.0003 item 4): o nome do arquivo é o
do roadmap (`test_dm_vs_r_oracle.py`), mas o conteúdo é **só analítico** — casos que se
calculam à mão (sinal, variância com h = 1, retangular x Bartlett com h = 2, fator HLN,
fallback, erros). O oráculo R (`forecast::dm.test`) vive nas fixtures versionadas e no
teste de integração da Task 08 (`tests/integration/features/evaluation/`), porque unit
não lê arquivo; o cruzamento com `statsmodels` fica na suíte de contrato (Task 10).

Referências do p-valor pelas formas fechadas da t com df = 3 (T = 4).
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import diebold_mariano as dm
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DieboldMarianoResult,
    DmVarianceEstimator,
    diebold_mariano,
    validate_dm_request,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

# Tolerância declarada (technical 6.2 §1): igualdade exata onde a aritmética é exata;
# senão abs ≤ 1e-15 (estatística, variância) e abs ≤ 1e-14 no p-valor (forma fechada).
_ABS_TOL = 1e-15
_P_ABS_TOL = 1e-14
_HALF = 0.5

_RECT = DmVarianceEstimator.RECTANGULAR
_BART = DmVarianceEstimator.BARTLETT

# h = 1: d = (-1, 0, 1, 2), d̄ = 0,5, gamma_0 = 5/4, var̂ = gamma_0/T = 0,3125,
# HLN = ((4 + 1 - 2 + 0)/4)^½ = √0,75, S1* = √0,75·0,5/√0,3125 = √0,6.
_CAND_H1 = (1.0, 2.0, 3.0, 4.0)
_COMP_H1 = (2.0, 2.0, 2.0, 2.0)

# h = 2: d = (0, 0, 2, 2), d̄ = 1, desvios (-1, -1, 1, 1): gamma_0 = 1, gamma_1 = (1 - 1 + 1)/4 = ¼.
# Retangular (w = 1): var̂ = (1 + 2·¼)/4 = 0,375; Bartlett (w = ½): (1 + 2·½·¼)/4 = 0,3125.
# HLN(4, 2) = ((4 + 1 - 4 + 2/4)/4)^½ = √0,375 → S1* = 1 (retangular) e √1,2 (Bartlett).
_CAND_H2 = (1.0, 1.0, 3.0, 3.0)
_COMP_H2 = (1.0, 1.0, 1.0, 1.0)

# d = ±1 alternado (T = 10): d̄ = 0, gamma_0 = 1, gamma_1 = -0,9. Retangular h = 2:
# (1 - 1,8)/10 < 0 → fallback h = 1 (var̂ = 0,1); Bartlett h = 2: (1 - 0,9)/10 = 1/T² > 0.
_CAND_ALTERNATING = (3.0, 1.0) * 5
_COMP_FLAT = (2.0,) * 10


def _t3_cdf(x: float) -> float:
    """F_3(x) = ½ + (1/π)[(x/√3)/(1 + x²/3) + arctan(x/√3)]."""
    u = x / math.sqrt(3.0)
    return 0.5 + (u / (1.0 + u * u) + math.atan(u)) / math.pi


def _run(
    candidate: tuple[float, ...],
    comparator: tuple[float, ...],
    horizon: int,
    estimator: DmVarianceEstimator = _RECT,
) -> DieboldMarianoResult:
    return diebold_mariano(
        candidate_losses=candidate,
        comparator_losses=comparator,
        horizon=horizon,
        variance_estimator=estimator,
    )


@pytest.mark.unit
def test_dm_hand_h1() -> None:
    result = _run(_CAND_H1, _COMP_H1, 1)
    assert result.mean_differential == _HALF
    assert result.long_run_variance == 0.3125  # noqa: PLR2004 — valor à mão
    assert abs(result.statistic - math.sqrt(0.6)) <= _ABS_TOL
    assert abs(result.p_value - _t3_cdf(math.sqrt(0.6))) <= _P_ABS_TOL
    assert (result.horizon, result.horizon_used, result.fallback_applied) == (1, 1, False)
    assert (result.n_points, result.degrees_of_freedom) == (4, 3)
    assert result.variance_estimator is _RECT


@pytest.mark.unit
def test_dm_sign_swap() -> None:
    forward = _run(_CAND_H1, _COMP_H1, 1)
    backward = _run(_COMP_H1, _CAND_H1, 1)
    assert backward.mean_differential == -forward.mean_differential
    assert backward.statistic == -forward.statistic
    assert abs(backward.p_value - (1.0 - forward.p_value)) <= _ABS_TOL


@pytest.mark.unit
def test_dm_h2_rectangular() -> None:
    result = _run(_CAND_H2, _COMP_H2, 2, _RECT)
    assert result.long_run_variance == 0.375  # noqa: PLR2004 — valor à mão
    assert abs(result.statistic - 1.0) <= _ABS_TOL
    assert abs(result.p_value - _t3_cdf(1.0)) <= _P_ABS_TOL
    assert not result.fallback_applied


@pytest.mark.unit
def test_dm_h2_bartlett() -> None:
    result = _run(_CAND_H2, _COMP_H2, 2, _BART)
    assert result.long_run_variance == 0.3125  # noqa: PLR2004 — valor à mão
    assert abs(result.statistic - math.sqrt(1.2)) <= _ABS_TOL
    assert abs(result.p_value - _t3_cdf(math.sqrt(1.2))) <= _P_ABS_TOL
    assert result.variance_estimator is _BART


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n_points", "horizon", "expected"),
    [(10, 7, math.sqrt(0.12)), (4, 1, math.sqrt(0.75)), (4, 2, math.sqrt(0.375))],
)
def test_dm_hln_factor(n_points: int, horizon: int, expected: float) -> None:
    """((T + 1 - 2h + h(h - 1)/T)/T)^½ — T = 10, h = 7 → ((10 + 1 - 14 + 4,2)/10)^½ = √0,12."""
    assert abs(dm._hln_factor(n_points, horizon) - expected) <= _ABS_TOL


@pytest.mark.unit
def test_dm_fallback_alternating_rectangular() -> None:
    result = _run(_CAND_ALTERNATING, _COMP_FLAT, 2, _RECT)
    assert result.fallback_applied
    assert (result.horizon, result.horizon_used) == (2, 1)
    assert abs(result.long_run_variance - 0.1) <= _ABS_TOL
    assert result.statistic == 0.0
    assert result.p_value == _HALF


@pytest.mark.unit
def test_dm_fallback_alternating_not_under_bartlett() -> None:
    result = _run(_CAND_ALTERNATING, _COMP_FLAT, 2, _BART)
    assert not result.fallback_applied
    assert result.horizon_used == 2  # noqa: PLR2004 — h pedido
    assert abs(result.long_run_variance - 0.01) <= _ABS_TOL
    assert result.p_value == _HALF


@pytest.mark.unit
def test_dm_fallback_at_exactly_zero_variance_recomputes_hln() -> None:
    """var̂ = 0 exato com h = 2 também cai no fallback (≤ 0, não < 0), com HLN de h = 1.

    d = (1,5; -0,5; 0,5; 0,5): d̄ = 0,5, desvios (1, -1, 0, 0), gamma_0 = ½, gamma_1 = -¼ →
    retangular h = 2: (½ - ½)/4 = 0 → h = 1: var̂ = ½/4 = 0,125; HLN(4, 1) = √0,75 →
    S1* = √0,75·0,5/√0,125 = √1,5 (com o HLN de h = 2, √0,375, daria √0,75).
    """
    result = _run((2.5, 0.5, 1.5, 1.5), (1.0, 1.0, 1.0, 1.0), 2, _RECT)
    assert result.fallback_applied
    assert result.horizon_used == 1
    assert result.long_run_variance == 0.125  # noqa: PLR2004 — valor à mão
    assert abs(result.statistic - math.sqrt(1.5)) <= _ABS_TOL
    assert abs(result.p_value - _t3_cdf(math.sqrt(1.5))) <= _P_ABS_TOL


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [1, 2])
@pytest.mark.parametrize("estimator", [_RECT, _BART])
def test_dm_constant_differential_raises(horizon: int, estimator: DmVarianceEstimator) -> None:
    """d constante: var̂ = 0; h = 2 cai no fallback e, em h = 1, ergue a mensagem do R."""
    with pytest.raises(ValueError, match="Variance of DM statistic is zero"):
        _run((3.0, 4.0, 5.0, 6.0, 7.0), (1.0, 2.0, 3.0, 4.0, 5.0), horizon, estimator)


_C3_CASES = [
    pytest.param((1.0, 2.0, 3.0), (1.0, 2.0), 1, _RECT, "same length", id="length-mismatch"),
    pytest.param((1.0,), (2.0,), 1, _RECT, "T >= 2", id="single-point"),
    pytest.param((1.0, math.nan, 3.0), (1.0, 2.0, 3.0), 1, _RECT, "finite", id="nan"),
    pytest.param((1.0, 2.0, 3.0), (1.0, math.inf, 3.0), 1, _RECT, "finite", id="inf"),
    pytest.param((1.0, None, 3.0), (1.0, 2.0, 3.0), 1, _RECT, "finite", id="none"),
    pytest.param((1.0, True, 3.0), (1.0, 2.0, 3.0), 1, _RECT, "finite", id="bool-loss"),
    pytest.param((1.0, 2.0, 3.0), (1.0, -0.5, 3.0), 1, _RECT, ">= 0", id="negative-loss"),
    pytest.param((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 0, _RECT, "int >= 1", id="h-zero"),
    pytest.param((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), True, _RECT, "int >= 1", id="h-bool"),
    pytest.param((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 3, _RECT, "T > h", id="h-equals-t"),
    pytest.param((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 4, _RECT, "T > h", id="h-above-t"),
    pytest.param(
        (1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 1, "rectangular", "DmVarianceEstimator", id="raw-str"
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("cand", "comp", "horizon", "estimator", "message"), _C3_CASES)
def test_dm_c3_invalid_primitive(
    cand: tuple[object, ...],
    comp: tuple[object, ...],
    horizon: object,
    estimator: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        diebold_mariano(
            candidate_losses=cand,  # type: ignore[arg-type]
            comparator_losses=comp,  # type: ignore[arg-type]
            horizon=horizon,  # type: ignore[arg-type]
            variance_estimator=estimator,  # type: ignore[arg-type]
        )


@pytest.mark.unit
@pytest.mark.parametrize(("cand", "comp", "horizon", "estimator", "message"), _C3_CASES)
def test_dm_validate_request_rejects(
    cand: tuple[object, ...],
    comp: tuple[object, ...],
    horizon: object,
    estimator: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_dm_request(
            candidate_losses=cand,  # type: ignore[arg-type]
            comparator_losses=comp,  # type: ignore[arg-type]
            horizon=horizon,  # type: ignore[arg-type]
            variance_estimator=estimator,  # type: ignore[arg-type]
        )


@pytest.mark.unit
def test_dm_validate_request_accepts_valid_input() -> None:
    validate_dm_request(
        candidate_losses=_CAND_H2, comparator_losses=_COMP_H2, horizon=3, variance_estimator=_BART
    )


def _series() -> PairedLossSeries:
    """k = 3; "comp1" - "comp2" = 0,5 constante (par degenerado de comparadores)."""
    return PairedLossSeries(
        horizon=1,
        models=("cand", "comp1", "comp2"),
        target_timestamps=("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"),
        losses=(_CAND_H1, (2.5, 1.5, 0.5, 3.5), (2.0, 1.0, 0.0, 3.0)),
    )


@pytest.mark.unit
def test_dm_degenerate_comparator_pair_does_not_block() -> None:
    series = _series()
    for comparator in ("comp1", "comp2"):
        result = DieboldMariano.compare(series, candidate="cand", comparator=comparator)
        expected = _run(series.losses_of("cand"), series.losses_of(comparator), 1)
        assert result == expected


@pytest.mark.unit
def test_dm_compare_uses_series_horizon_and_estimator() -> None:
    series = PairedLossSeries(
        horizon=2,
        models=("cand", "comp"),
        target_timestamps=("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"),
        losses=(_CAND_H2, _COMP_H2),
    )
    result = DieboldMariano.compare(
        series, candidate="cand", comparator="comp", variance_estimator=_BART
    )
    assert result == _run(_CAND_H2, _COMP_H2, 2, _BART)


@pytest.mark.unit
@pytest.mark.parametrize(("candidate", "comparator"), [("zzz", "comp1"), ("cand", "zzz")])
def test_dm_unknown_name_raises(candidate: str, comparator: str) -> None:
    with pytest.raises(ValueError, match="unknown model 'zzz'"):
        DieboldMariano.compare(_series(), candidate=candidate, comparator=comparator)


@pytest.mark.unit
def test_dm_same_model_raises() -> None:
    with pytest.raises(ValueError, match="must differ"):
        DieboldMariano.compare(_series(), candidate="comp1", comparator="comp1")


def _valid_result() -> DieboldMarianoResult:
    return _run(_CAND_H1, _COMP_H1, 1)


_INCOHERENT: list[tuple[str, Callable[[DieboldMarianoResult], DieboldMarianoResult], str]] = [
    ("horizon-zero", lambda r: dataclasses.replace(r, horizon=0, horizon_used=0), "horizon"),
    ("horizon-bool", lambda r: dataclasses.replace(r, horizon=True), "horizon"),
    (
        "n-points-one",
        lambda r: dataclasses.replace(r, n_points=1, degrees_of_freedom=0),
        "T >= 2",
    ),
    (
        "n-points-not-above-horizon",
        lambda r: dataclasses.replace(r, horizon=4, horizon_used=4),
        r"T > h\), got T=4 and h=4",
    ),
    (
        "horizon-used-other",
        lambda r: dataclasses.replace(r, horizon=3, horizon_used=2),
        "horizon_used",
    ),
    (
        "fallback-without-change",
        lambda r: dataclasses.replace(r, fallback_applied=True),
        "fallback",
    ),
    (
        "change-without-fallback",
        lambda r: dataclasses.replace(r, horizon=2, horizon_used=1, fallback_applied=False),
        "fallback",
    ),
    ("raw-estimator", lambda r: dataclasses.replace(r, variance_estimator="bartlett"), "estimator"),
    ("df-mismatch", lambda r: dataclasses.replace(r, degrees_of_freedom=4), "degrees_of_freedom"),
    ("variance-zero", lambda r: dataclasses.replace(r, long_run_variance=0.0), "long_run_variance"),
    (
        "variance-nan",
        lambda r: dataclasses.replace(r, long_run_variance=math.nan),
        "long_run_variance",
    ),
    ("mean-inf", lambda r: dataclasses.replace(r, mean_differential=math.inf), "mean_differential"),
    ("statistic-nan", lambda r: dataclasses.replace(r, statistic=math.nan), "statistic"),
    ("p-above-one", lambda r: dataclasses.replace(r, p_value=1.5), "p_value"),
    ("p-negative", lambda r: dataclasses.replace(r, p_value=-0.1), "p_value"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build", "message"), [pytest.param(b, m, id=i) for i, b, m in _INCOHERENT]
)
def test_dm_result_incoherent_raises(
    build: Callable[[DieboldMarianoResult], DieboldMarianoResult], message: str
) -> None:
    valid = _valid_result()
    with pytest.raises(ValueError, match=message):
        build(valid)


@pytest.mark.unit
def test_dm_result_fallback_coherent_accepted() -> None:
    result = dataclasses.replace(_valid_result(), horizon=2, horizon_used=1, fallback_applied=True)
    assert result.fallback_applied
