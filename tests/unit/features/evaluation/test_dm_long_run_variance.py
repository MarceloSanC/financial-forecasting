"""Unit test da `dm_long_run_variance` (Stage 6.6 Task 02; ADR 6.6.0001 ST3).

Casos analíticos (sem oráculo — o de statsmodels mora em
`tests/integration/features/evaluation/test_dm_long_run_variance_vs_statsmodels.py`,
porque o gate de pureza proíbe statsmodels em `tests/unit/features/evaluation/**`):

- série alternada 1, -1, ...: gamma_0 = 1, gamma_1 = -(T-1)/T, então a retangular em h = 2
  é negativa e o fallback devolve gamma_0/T com `horizon_used = 1`;
- série constante -> `(0.0, 1)` em qualquer h (o fallback do `dm.test`);
- a variância é a mesma que o primitivo `diebold_mariano` usa (uma escrita só).
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
    diebold_mariano,
    dm_long_run_variance,
)

_ALTERNATING = tuple(1.0 if t % 2 == 0 else -1.0 for t in range(10))
_H_TWO = 2
_BARTLETT_WEIGHT_LAG_1_H_2 = 0.5  # 1 - k/h com k = 1, h = 2


def test_negative_rectangular_variance_falls_back_to_h_1() -> None:
    variance, horizon_used = dm_long_run_variance(
        _ALTERNATING, horizon=_H_TWO, variance_estimator=DmVarianceEstimator.RECTANGULAR
    )
    assert horizon_used == 1
    assert variance == pytest.approx(1.0 / len(_ALTERNATING))


def test_positive_variance_keeps_the_horizon() -> None:
    differences = (0.3, -0.1, 0.4, 0.2, -0.5, 0.1, 0.0, 0.6, -0.2, 0.3, 0.1, -0.4)
    variance, horizon_used = dm_long_run_variance(
        differences, horizon=_H_TWO, variance_estimator=DmVarianceEstimator.BARTLETT
    )
    n_points = len(differences)
    mean = math.fsum(differences) / n_points
    deviations = [d - mean for d in differences]
    gamma0 = math.fsum(x * x for x in deviations) / n_points
    gamma1 = math.fsum(deviations[t] * deviations[t - 1] for t in range(1, n_points)) / n_points
    expected = (gamma0 + 2 * _BARTLETT_WEIGHT_LAG_1_H_2 * gamma1) / n_points
    assert horizon_used == _H_TWO
    assert variance == pytest.approx(expected)


@pytest.mark.parametrize("horizon", [1, 7])
def test_constant_differential_gives_zero_with_h_1(horizon: int) -> None:
    assert dm_long_run_variance(
        (0.1,) * 12, horizon=horizon, variance_estimator=DmVarianceEstimator.RECTANGULAR
    ) == (0.0, 1)


def test_the_dm_primitive_uses_the_same_variance() -> None:
    candidate = (1.0, 2.0, 0.5, 1.5, 2.5, 0.2, 1.1, 0.9, 1.7, 0.4, 1.3, 2.2)
    comparator = (1.2, 1.8, 0.9, 1.0, 2.9, 0.1, 1.5, 0.8, 1.6, 0.9, 1.0, 2.0)
    result = diebold_mariano(candidate_losses=candidate, comparator_losses=comparator, horizon=3)
    variance, horizon_used = dm_long_run_variance(
        [a - b for a, b in zip(candidate, comparator, strict=True)],
        horizon=3,
        variance_estimator=DmVarianceEstimator.RECTANGULAR,
    )
    assert (result.long_run_variance, result.horizon_used) == (variance, horizon_used)


@pytest.mark.parametrize(
    ("differences", "horizon", "estimator", "message"),
    [
        ((0.1, 0.2), 2, DmVarianceEstimator.RECTANGULAR, "T > h"),
        ((0.1,), 1, DmVarianceEstimator.RECTANGULAR, "T >= 2"),
        ((0.1, 0.2, 0.3), 0, DmVarianceEstimator.RECTANGULAR, "horizon"),
        ((0.1, 0.2, 0.3), 1, "rectangular", "variance_estimator"),
    ],
)
def test_invalid_requests(
    differences: tuple[float, ...], horizon: int, estimator: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        dm_long_run_variance(
            differences,
            horizon=horizon,
            variance_estimator=estimator,  # type: ignore[arg-type]
        )
