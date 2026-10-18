"""Prova sintética da cobertura do CQR sob permutabilidade (Stage 7.2, Task 10; concept CA7).

Dados i.i.d.: por ponto, mu ~ N(0, 1) conhecido pelo modelo base, y = mu + eps com
eps ~ N(0, 1), e a grade do modelo base q_tau = mu + sigma_m * z_tau nos sete níveis do
candidato. Por réplica: n = 252 pontos de calib e m = 252 de teste. Tudo passa pelo
código de registro: `CalibrateConformal` (inference) calcula as correções e os limites,
e `ConformalCoverage` (evaluation) mede ĉ e PICP sobre a `CoverageSeries` nativa do
teste.

Sob permutabilidade, a cobertura marginal da cauda inferior é (n + 1 - k)/(n + 1), com
k = ceil((n + 1)(1 - alpha)), e fica em [alpha - 1/(n + 1), alpha]; a da superior fica em
[tau_hi, tau_hi + 1/(n + 1)]. A média de ĉ sobre as réplicas é conferida contra essa faixa,
com +-3 erros-padrão de Monte Carlo. O NexCP (rho = 0,99) só garante o lado
conservador.
"""

from __future__ import annotations

import math
import random
import statistics
from datetime import UTC, datetime, timedelta
from statistics import NormalDist

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    ConformalCoverage,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
)

pytestmark = pytest.mark.integration

_SEED = 20261017
_N = 252
_M = 252
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_PAIRS = ((0.02, 0.98), (0.1, 0.9), (0.25, 0.75))
_Z = {level: NormalDist().inv_cdf(level) for level in _LEVELS}
_SPLIT = "split_cqr_asymmetric_unweighted_v1"
_NEXCP = "nexcp_fixed_geometric_weights_v1"
_START = datetime(2000, 1, 3, 21, tzinfo=UTC)
_STAMPS = tuple((_START + timedelta(days=d)).isoformat() for d in range(_N + _M + 2))
_TOLERANCE = 1e-12
_MC_SIGMAS = 3.0


def _point(rng: random.Random, sigma_model: float) -> tuple[dict[float, float], float]:
    mu = rng.gauss(0.0, 1.0)
    grid = {level: mu + sigma_model * _Z[level] for level in _LEVELS}
    return grid, mu + rng.gauss(0.0, 1.0)


def _replica(
    rng: random.Random, *, variant: str, sigma_model: float
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Uma réplica: (ĉ(L), ĉ(U)) por par e (Q_lo, Q_hi) por par."""
    calib = []
    for i in range(_N):
        grid, y = _point(rng, sigma_model)
        calib.append(ConformalPointInput(_STAMPS[i], _STAMPS[i + 1], grid, y))
    test_grids, test_y = [], []
    for _ in range(_M):
        grid, y = _point(rng, sigma_model)
        test_grids.append(grid)
        test_y.append(y)
    test = tuple(
        ConformalPointInput(_STAMPS[_N + 1 + j], _STAMPS[_N + 2 + j], grid, None)
        for j, grid in enumerate(test_grids)
    )
    result = CalibrateConformal()(
        CalibrateConformalCommand(
            units=(ConformalUnitInput(0, 1, 1, tuple(calib), test),),
            pairs=_PAIRS,
            variants=(variant,),
            nexcp_rho=0.99 if variant == _NEXCP else None,
        )
    )
    native = CoverageSeries(
        horizon=1,
        levels=_LEVELS,
        target_timestamps=tuple(_STAMPS[_N + 2 + j] for j in range(_M)),
        forecasts=tuple(
            QuantileForecast.from_raw(
                levels=_LEVELS, raw_values=tuple(grid[level] for level in _LEVELS)
            )
            for grid in test_grids
        ),
        realized=tuple(test_y),
    )
    limits = []
    corrections = []
    for unit in result.units:
        assert unit.test_lower is not None
        assert unit.test_upper is not None
        assert unit.lower is not None
        assert unit.upper is not None
        limits.append(
            ConformalPairLimits(
                unit.lower_level, unit.upper_level, unit.test_lower, unit.test_upper
            )
        )
        corrections.append((unit.lower.correction, unit.upper.correction))
    report = ConformalCoverage.evaluate(
        ConformalCoverageSeries(seed=1, native=native, variant=variant, pairs=tuple(limits)),
        tolerance=_TOLERANCE,
        band_levels=(0.95,),
    )
    assert report.n_evaluated == _M
    tails = [(p.lower_tail.coverage, p.upper_tail.coverage) for p in report.per_pair]
    return tails, corrections


def _simulate(
    *, variant: str, replicas: int, sigma_model: float
) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    rng = random.Random(_SEED)
    runs = [_replica(rng, variant=variant, sigma_model=sigma_model) for _ in range(replicas)]
    return [r[0] for r in runs], [r[1] for r in runs]


def _mean_se(values: list[float]) -> tuple[float, float]:
    return statistics.fmean(values), statistics.stdev(values) / math.sqrt(len(values))


@pytest.fixture(scope="module")
def split_runs() -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    return _simulate(variant=_SPLIT, replicas=1000, sigma_model=1.0)


def test_split_cqr_tail_coverage_in_the_theoretical_band(
    split_runs: tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]],
) -> None:
    tails, _ = split_runs
    slack = 1 / (_N + 1)
    for k, (low, high) in enumerate(_PAIRS):
        mean_lo, se_lo = _mean_se([run[k][0] for run in tails])
        mean_hi, se_hi = _mean_se([run[k][1] for run in tails])
        alpha = low
        assert alpha - slack - _MC_SIGMAS * se_lo <= mean_lo <= alpha + _MC_SIGMAS * se_lo, (
            low,
            mean_lo,
            se_lo,
        )
        assert high - _MC_SIGMAS * se_hi <= mean_hi <= high + slack + _MC_SIGMAS * se_hi, (
            high,
            mean_hi,
            se_hi,
        )


def test_nexcp_guarantee_side() -> None:
    tails, _ = _simulate(variant=_NEXCP, replicas=200, sigma_model=1.0)
    for k, (low, high) in enumerate(_PAIRS):
        mean_lo, se_lo = _mean_se([run[k][0] for run in tails])
        mean_hi, se_hi = _mean_se([run[k][1] for run in tails])
        assert mean_lo <= low + _MC_SIGMAS * se_lo, (low, mean_lo, se_lo)
        assert mean_hi >= high - _MC_SIGMAS * se_hi, (high, mean_hi, se_hi)


def test_narrow_base_model_is_widened_and_wide_is_shrunk() -> None:
    _, narrow = _simulate(variant=_SPLIT, replicas=50, sigma_model=0.5)
    _, wide = _simulate(variant=_SPLIT, replicas=50, sigma_model=2.0)
    for k in range(len(_PAIRS)):
        for side in (0, 1):
            assert statistics.fmean(run[k][side] for run in narrow) > 0
            assert statistics.fmean(run[k][side] for run in wide) < 0
