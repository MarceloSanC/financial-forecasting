"""Integração: diagnóstico de d_t x statsmodels/scipy (Stage 6.6 Task 09; CA7; ADR 6.6.0001).

Importa `statsmodels`/`scipy`/`numpy` (integração — o gate de pureza os proíbe no unit):

- ACF x `statsmodels.tsa.stattools.acf(adjusted=False, fft=False, nlags=L)[1:]`;
- em h = 1, estatística e p-valor x `breaks_cusumolsresid(d - mean, ddof=0)` (`sup_b`,
  `pval`): mesma escala sqrt(soma dos quadrados dos desvios) = T * sqrt(var(d̄));
- em h = 7, composição no teste: B = max|cumsum(d - mean)| / (T * sqrt(v)), v =
  `cov_params()[0, 0]` do HAC uniforme `maxlags=6`, `use_correction=False` (já é var(d̄));
- fallback: série alternada em h = 2 (variância retangular negativa) -> `horizon_used = 1`
  e a escala do h = 1;
- `kolmogorov_sf` x `scipy.stats.kstwobign.sf` numa grade que inclui x pequeno.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import statsmodels.api as sm
from scipy.stats import kstwobign
from statsmodels.stats.diagnostic import breaks_cusumolsresid
from statsmodels.tsa.stattools import acf

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.differential_stationarity import (
    acf_max_lag,
    cusum_mean_break,
    kolmogorov_sf,
    sample_acf,
)

_RECT = DmVarianceEstimator.RECTANGULAR


def _series(n_points: int, horizon: int, seed: int, shift_at: int | None = None) -> list[float]:
    rng = random.Random(seed)
    shocks = [rng.gauss(0.0, 1.0) for _ in range(n_points + horizon)]
    values = [sum(shocks[t : t + horizon]) / horizon for t in range(n_points)]
    if shift_at is not None:
        values = [v + (0.8 if t >= shift_at else 0.0) for t, v in enumerate(values)]
    return values


@pytest.mark.parametrize(("n_points", "seed"), [(30, 1), (250, 2), (1500, 3)])
def test_acf_matches_statsmodels(n_points: int, seed: int) -> None:
    values = _series(n_points, 3, seed)
    lags = acf_max_lag(n_points)
    expected = acf(np.asarray(values), adjusted=False, fft=False, nlags=lags)[1:]
    assert sample_acf(values, lags) == pytest.approx(tuple(expected), abs=1e-12)


@pytest.mark.parametrize(("seed", "shift_at"), [(4, None), (5, 120), (6, 40)])
def test_h1_cusum_matches_breaks_cusumolsresid(seed: int, shift_at: int | None) -> None:
    values = _series(200, 1, seed, shift_at)
    found = cusum_mean_break(values, horizon=1, variance_estimator=_RECT)
    assert found is not None
    resid = np.asarray(values) - np.mean(values)
    sup_b, pval, _ = breaks_cusumolsresid(resid, ddof=0)
    assert found.statistic == pytest.approx(float(sup_b), rel=1e-10)
    assert found.p_value == pytest.approx(float(pval), rel=1e-9, abs=1e-15)


def _composed(values: list[float], maxlags: int) -> tuple[float, int]:
    y = np.asarray(values)
    robust = (
        sm.OLS(y, np.ones_like(y))
        .fit()
        .get_robustcov_results(
            cov_type="HAC", kernel="uniform", maxlags=maxlags, use_correction=False
        )
    )
    variance = float(robust.cov_params()[0, 0])
    partial = np.cumsum(y - y.mean())
    return float(np.max(np.abs(partial)) / (len(values) * np.sqrt(variance))), int(
        np.argmax(np.abs(partial))
    )


@pytest.mark.parametrize(("seed", "shift_at"), [(7, None), (8, 300)])
def test_h7_cusum_matches_the_composition(seed: int, shift_at: int | None) -> None:
    values = _series(600, 7, seed, shift_at)
    found = cusum_mean_break(values, horizon=7, variance_estimator=_RECT)
    assert found is not None
    assert found.horizon_used == 7  # noqa: PLR2004
    statistic, index = _composed(values, maxlags=6)
    assert found.statistic == pytest.approx(statistic, rel=1e-9)
    assert found.break_index == index
    assert found.p_value == pytest.approx(float(kstwobign.sf(statistic)), rel=1e-8, abs=1e-15)


def test_fallback_uses_the_h1_scale() -> None:
    values = [1.0 if t % 2 == 0 else -1.0 for t in range(40)]
    values[5] += 0.3  # não constante, retangular em h = 2 ainda negativa
    found = cusum_mean_break(values, horizon=2, variance_estimator=_RECT)
    assert found is not None
    assert found.horizon_used == 1
    statistic, _ = _composed(values, maxlags=0)
    assert found.statistic == pytest.approx(statistic, rel=1e-9)


@pytest.mark.parametrize("x", [0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 1.18, 1.3580986, 1.63, 2.0, 3.0])
def test_kolmogorov_sf_matches_scipy(x: float) -> None:
    assert kolmogorov_sf(x) == pytest.approx(float(kstwobign.sf(x)), rel=1e-12, abs=1e-12)


def test_h7_fallback_uses_the_h1_scale() -> None:
    """Checkpoint C bloco 3 (L2): série sobrediferenciada (e_t - e_{t-1}, seed 0) com
    variância retangular até o lag 6 negativa -> fallback para h = 1."""
    rng = random.Random(0)
    shocks = [rng.gauss(0.0, 1.0) for _ in range(201)]
    values = [shocks[t] - shocks[t - 1] for t in range(1, 201)]
    found = cusum_mean_break(values, horizon=7, variance_estimator=_RECT)
    assert found is not None
    assert found.horizon_used == 1
    statistic, _ = _composed(values, maxlags=0)
    assert found.statistic == pytest.approx(statistic, rel=1e-9)
