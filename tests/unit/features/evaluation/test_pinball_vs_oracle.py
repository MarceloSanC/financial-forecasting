"""Unit test do `PinballScore` contra fixtures analíticas e oficiais (A2/A1b/A7/A10/C7).

O "oráculo" aqui são **constantes**: os dois exemplos oficiais da documentação do
`sklearn.metrics.mean_pinball_loss` (sklearn 1.9) — os testes unit não importam a lib
(ADR 6.1.0001 item 4; a checagem contra a biblioteca é a suíte de contrato). Os
demais valores são analíticos (Dirac simétrico, empate, pesos iguais) ou calculados
à mão sobre `guardrail_values` x `raw_values` (A1b).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballReport,
    PinballScore,
    mean_pinball,
    pinball_loss,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

# Tolerâncias declaradas (ADR 0.0.0021; ADR 6.1.0001 Implementation notes): ruído de
# soma float64 da ordem de 1e-12.
_REL_TOL = 1e-12
_ABS_TOL = 1e-12

# Fixtures oficiais do docstring de `sklearn.metrics.mean_pinball_loss`:
# y_true = [1, 2, 3]; y_pred = [0, 2, 3] -> 0.03333...; y_pred = [1, 2, 4] -> 0.3
# (ambos com alpha = 0.1).
_SKLEARN_Y = (1.0, 2.0, 3.0)
_SKLEARN_LEVEL = 0.1
_SKLEARN_LOW_PRED = (0.0, 2.0, 3.0)
_SKLEARN_LOW_EXPECTED = 0.1 / 3
_SKLEARN_HIGH_PRED = (1.0, 2.0, 4.0)
_SKLEARN_HIGH_EXPECTED = 0.3

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_HORIZON = 3


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _hand_pinball(y: float, q: float, tau: float) -> float:
    """rho_τ(y - q) escrito à parte, na forma max (a do sklearn) — não a do domínio."""
    return tau * max(y - q, 0.0) + (1.0 - tau) * max(q - y, 0.0)


def _hand_grid_mean(
    grids: Sequence[Sequence[float]], realized: Sequence[float], levels: Sequence[float]
) -> float:
    per_level = [
        sum(_hand_pinball(y, grid[k], tau) for grid, y in zip(grids, realized, strict=True))
        / len(realized)
        for k, tau in enumerate(levels)
    ]
    return sum(per_level) / len(per_level)


# --- A2 — fixtures oficiais e analíticas ----------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("quantiles", "expected"),
    [(_SKLEARN_LOW_PRED, _SKLEARN_LOW_EXPECTED), (_SKLEARN_HIGH_PRED, _SKLEARN_HIGH_EXPECTED)],
    ids=["sklearn-doc-0.0333", "sklearn-doc-0.3"],
)
def test_mean_pinball_matches_official_sklearn_fixtures(
    quantiles: tuple[float, ...], expected: float
) -> None:
    """A2: `mean_pinball` reproduz os dois exemplos oficiais do sklearn."""
    value = mean_pinball(realized=_SKLEARN_Y, quantiles=quantiles, level=_SKLEARN_LEVEL)

    assert _close(value, expected)


@pytest.mark.unit
@pytest.mark.parametrize("level", [0.05, 0.5, 0.95])
def test_pinball_loss_is_zero_on_tie(level: float) -> None:
    """A2/I6: empate y = q → perda 0 (qualquer nível)."""
    assert pinball_loss(realized=0.013, quantile=0.013, level=level) == 0.0


@pytest.mark.unit
def test_pinball_loss_scale_has_no_factor_two() -> None:
    """I4: rho_τ(u) = τ·u acima e (τ - 1)·u abaixo — sem fator 2."""
    tau = 0.25
    above = pinball_loss(realized=1.0, quantile=0.0, level=tau)
    below = pinball_loss(realized=0.0, quantile=1.0, level=tau)

    assert _close(above, tau)
    assert _close(below, 1.0 - tau)


@pytest.mark.unit
@pytest.mark.parametrize(("y", "x"), [(0.03, -0.01), (-0.02, 0.01)], ids=["y>x", "y<x"])
def test_grid_mean_on_symmetric_dirac_is_half_abs_error(
    make_series: SeriesFactory, y: float, x: float
) -> None:
    """A2: grade simétrica com todos os quantis = x → P̄_G = |y - x|/2."""
    series = make_series([(x,) * len(_LEVELS)], [y])

    report = PinballScore.score(series)

    assert _close(report.grid_mean, abs(y - x) / 2)


@pytest.mark.unit
def test_grid_mean_is_equal_weight_average_of_per_level(make_series: SeriesFactory) -> None:
    """A2: P̄_G é a média aritmética dos P̄_τ (pesos iguais), conferida à mão."""
    grids = [
        (-0.04, -0.03, -0.01, 0.0, 0.012, 0.025, 0.05),
        (-0.02, -0.015, -0.005, 0.001, 0.004, 0.02, 0.03),
        (-0.05, -0.02, -0.01, 0.002, 0.01, 0.015, 0.02),
    ]
    realized = [0.018, -0.03, 0.001]
    series = make_series(grids, realized)

    report = PinballScore.score(series)

    per_level_values = [value for _, value in report.per_level]
    assert _close(report.grid_mean, sum(per_level_values) / len(per_level_values))
    assert _close(report.grid_mean, _hand_grid_mean(grids, realized, _LEVELS))
    assert tuple(level for level, _ in report.per_level) == _LEVELS


@pytest.mark.unit
def test_mean_of_per_point_losses_equals_grid_mean(make_series: SeriesFactory) -> None:
    """A2: a média dos L_t (insumo da 6.2) é P̄_G, sob tolerância declarada."""
    grids = [
        (-0.04, -0.03, -0.01, 0.0, 0.012, 0.025, 0.05),
        (-0.02, -0.015, -0.005, 0.001, 0.004, 0.02, 0.03),
        (-0.05, -0.02, -0.01, 0.002, 0.01, 0.015, 0.02),
        (-0.01, -0.008, -0.002, 0.0, 0.003, 0.006, 0.011),
    ]
    realized = [0.018, -0.03, 0.001, 0.0]
    series = make_series(grids, realized)

    losses = PinballScore.per_point_losses(series)

    assert len(losses) == series.n_points
    assert _close(sum(losses) / len(losses), PinballScore.score(series).grid_mean)
    # L_t do ponto 0, à mão: média dos K rho_τ.
    expected_first = sum(
        _hand_pinball(realized[0], q, tau) for q, tau in zip(grids[0], _LEVELS, strict=True)
    ) / len(_LEVELS)
    assert _close(losses[0], expected_first)


# --- A1b — pontua-se o rearranjado ----------------------------------------------------


@pytest.mark.unit
def test_pinball_scores_guardrail_not_raw(make_series: SeriesFactory) -> None:
    """A1b: com raw cruzado, `score` bate com o cálculo sobre `guardrail_values`
    e difere do cálculo sobre `raw_values`."""
    raw = [
        (0.02, -0.03, -0.01, 0.0, 0.01, -0.02, 0.03),  # cruzado → guardrail reordena
        (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03),
    ]
    realized = [0.015, -0.025]
    series = make_series(raw, realized)
    guardrail = [series.scored_values(i) for i in range(series.n_points)]
    assert guardrail[0] != raw[0]  # premissa do caso

    grid_mean = PinballScore.score(series).grid_mean

    assert _close(grid_mean, _hand_grid_mean(guardrail, realized, _LEVELS))
    assert not _close(grid_mean, _hand_grid_mean(raw, realized, _LEVELS))


# --- A7 (parte) — PinballReport mal-formado ------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("per_level", [(), ((0.5, 0.1),)], ids=["zero-levels", "one-level"])
def test_pinball_report_with_fewer_than_two_levels_raises(
    per_level: tuple[tuple[float, float], ...],
) -> None:
    with pytest.raises(ValueError, match="K >= 2"):
        PinballReport(horizon=1, n_points=3, per_level=per_level, grid_mean=0.1)


@pytest.mark.unit
def test_pinball_report_with_zero_points_raises() -> None:
    with pytest.raises(ValueError, match="n_points >= 1"):
        PinballReport(horizon=1, n_points=0, per_level=((0.1, 0.1), (0.9, 0.1)), grid_mean=0.1)


# --- A10 (parte) — horizonte e T ------------------------------------------------------


@pytest.mark.unit
def test_report_carries_series_horizon_and_all_points(make_series: SeriesFactory) -> None:
    """A10: `horizon` e `n_points = T` da série — nenhuma linha excluída."""
    grids = [(0.0,) * len(_LEVELS), (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)]
    series = make_series(grids, [0.01, 0.0], horizon=_HORIZON)

    report = PinballScore.score(series)

    assert report.horizon == series.horizon
    assert report.n_points == series.n_points


# --- C7 (domínio) — kernels -----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("level", [0.0, 1.5], ids=["zero", "above-one"])
def test_pinball_loss_rejects_invalid_level(level: float) -> None:
    """C7: o kernel por ponto valida o nível (não só a função de série)."""
    with pytest.raises(ValueError, match="level must be"):
        pinball_loss(realized=1.0, quantile=0.0, level=level)


@pytest.mark.unit
def test_mean_pinball_rejects_empty_sequences() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        mean_pinball(realized=[], quantiles=[], level=0.5)


@pytest.mark.unit
def test_mean_pinball_rejects_different_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        mean_pinball(realized=[1.0, 2.0], quantiles=[1.0], level=0.5)
