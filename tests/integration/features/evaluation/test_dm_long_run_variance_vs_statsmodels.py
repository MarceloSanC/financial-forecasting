"""Integração: `dm_long_run_variance` x HAC do statsmodels (Stage 6.6 Task 02; ADR 6.6.0001).

Importa `statsmodels`/`numpy` (integração — o gate de pureza os proíbe no unit). Oráculo:
`OLS(d, 1).fit().get_robustcov_results(cov_type="HAC", kernel=..., maxlags=h-1,
use_correction=False).cov_params()[0, 0]` — já é var̂(d̄), com o divisor T aplicado (como
documenta o `statsmodels_hac.py`). `kernel="uniform"` ↔ retangular; `"bartlett"` ↔
pesos 1 - k/(m+1) = 1 - k/h com m = h - 1. Séries sem variância negativa (o fallback é
regra do domínio, testada no unit).
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import statsmodels.api as sm

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
    dm_long_run_variance,
)

_KERNELS = {DmVarianceEstimator.RECTANGULAR: "uniform", DmVarianceEstimator.BARTLETT: "bartlett"}


def _ma_series(n_points: int, horizon: int, seed: int) -> list[float]:
    """d_t = média móvel de h choques — dependência MA(h-1), variância positiva."""
    rng = random.Random(seed)
    shocks = [rng.gauss(0.05, 1.0) for _ in range(n_points + horizon)]
    return [sum(shocks[t : t + horizon]) / horizon for t in range(n_points)]


def _oracle(differences: list[float], horizon: int, estimator: DmVarianceEstimator) -> float:
    y = np.asarray(differences)
    fit = sm.OLS(y, np.ones_like(y)).fit()
    robust = fit.get_robustcov_results(
        cov_type="HAC", kernel=_KERNELS[estimator], maxlags=horizon - 1, use_correction=False
    )
    return float(robust.cov_params()[0, 0])


@pytest.mark.parametrize("estimator", list(DmVarianceEstimator))
@pytest.mark.parametrize(("horizon", "seed"), [(1, 3), (2, 5), (7, 11)])
def test_matches_statsmodels_hac(estimator: DmVarianceEstimator, horizon: int, seed: int) -> None:
    differences = _ma_series(300, horizon, seed)
    variance, horizon_used = dm_long_run_variance(
        differences, horizon=horizon, variance_estimator=estimator
    )
    assert horizon_used == horizon
    assert variance == pytest.approx(_oracle(differences, horizon, estimator), rel=1e-10)
