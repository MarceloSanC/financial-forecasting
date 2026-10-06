"""Unit test do `DifferentialStationarity` (Stage 6.6 Task 09; CA7 analítico; ADR 6.6.0001).

Casos analíticos (os oráculos statsmodels/scipy moram em
`tests/integration/features/evaluation/test_differential_stationarity_vs_statsmodels.py`):

- `acf_max_lag`: T = 3 -> 2, T = 2 -> 1, T = 1500 -> 31;
- `sample_acf` de (1, 2, 3, 4): rho_1 = 0,25, rho_2 = -0,3 (desvios -1,5..1,5, soma 5);
- `kolmogorov_sf`: 1 em x <= 0, em [0, 1], decrescente, contínua na troca de série,
  ~0,05 no crítico 1,3581;
- CUSUM de um degrau de média (dez 0 e dez 1): quebra no último ponto do primeiro bloco,
  B = 5 / (20 * sqrt(0,25 / 20)) em h = 1;
- d_t constante -> relatório `undefined`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.differential_stationarity import (
    CONSTANT_DIFFERENTIAL,
    DifferentialStationarity,
    StationarityStatus,
    acf_max_lag,
    cusum_mean_break,
    kolmogorov_sf,
    sample_acf,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    PROFILE_RULE_CATALOG,
    StationarityParameters,
)

_RECT = DmVarianceEstimator.RECTANGULAR
_ALPHA = 0.05
_PARAMETERS = StationarityParameters(
    acf_max_lag=PROFILE_RULE_CATALOG["stationarity.acf_max_lag"],
    break_test=PROFILE_RULE_CATALOG["stationarity.break_test"],
    break_alpha=_ALPHA,
)
_STEP = tuple([0.0] * 10 + [1.0] * 10)
_STEP_BREAK_INDEX = 9
_KOLMOGOROV_CRITICAL_5PCT = 1.3580986


def _timestamps(n_points: int) -> tuple[str, ...]:
    start = datetime(2024, 1, 2, tzinfo=UTC)
    return tuple((start + timedelta(days=i)).isoformat() for i in range(n_points))


def _paired(differences: tuple[float, ...], horizon: int = 1) -> PairedLossSeries:
    base = tuple(2.0 + 0.1 * (i % 3) for i in range(len(differences)))
    return PairedLossSeries(
        horizon=horizon,
        models=("a", "b", "c"),
        target_timestamps=_timestamps(len(differences)),
        losses=(
            tuple(b + d for b, d in zip(base, differences, strict=True)),
            base,
            tuple(b + 0.5 for b in base),
        ),
    )


@pytest.mark.parametrize(("n_points", "expected"), [(2, 1), (3, 2), (11, 10), (1500, 31)])
def test_acf_max_lag(n_points: int, expected: int) -> None:
    assert acf_max_lag(n_points) == expected


@pytest.mark.parametrize("n_points", [1, 0, True, 2.0])
def test_acf_max_lag_invalid(n_points: object) -> None:
    with pytest.raises(ValueError, match="n_points"):
        acf_max_lag(n_points)  # type: ignore[arg-type]


def test_sample_acf_by_hand() -> None:
    assert sample_acf((1.0, 2.0, 3.0, 4.0), 2) == pytest.approx((0.25, -0.3))


@pytest.mark.parametrize("max_lag", [0, 4, True])
def test_sample_acf_invalid_lag(max_lag: object) -> None:
    with pytest.raises(ValueError, match="max_lag"):
        sample_acf((1.0, 2.0, 3.0, 4.0), max_lag)  # type: ignore[arg-type]


def test_sample_acf_constant_series() -> None:
    with pytest.raises(ValueError, match="constant"):
        sample_acf((0.2,) * 5, 2)


def test_kolmogorov_sf_shape() -> None:
    assert kolmogorov_sf(0.0) == 1.0
    assert kolmogorov_sf(-1.0) == 1.0
    grid = [0.01 * i for i in range(1, 500)]
    values = [kolmogorov_sf(x) for x in grid]
    assert all(0.0 <= v <= 1.0 for v in values)
    assert all(a >= b for a, b in pairwise(values))
    assert kolmogorov_sf(1.18 - 1e-9) == pytest.approx(kolmogorov_sf(1.18 + 1e-9), abs=1e-8)
    assert kolmogorov_sf(_KOLMOGOROV_CRITICAL_5PCT) == pytest.approx(_ALPHA, abs=1e-6)


def test_cusum_step_in_the_mean() -> None:
    found = cusum_mean_break(_STEP, horizon=1, variance_estimator=_RECT)
    assert found is not None
    assert found.break_index == _STEP_BREAK_INDEX
    expected = 5.0 / (20 * math.sqrt(0.25 / 20))
    assert found.statistic == pytest.approx(expected)
    assert found.p_value == pytest.approx(kolmogorov_sf(expected))
    assert found.horizon_used == 1


def test_cusum_constant_series_is_none() -> None:
    assert cusum_mean_break((0.3,) * 8, horizon=1, variance_estimator=_RECT) is None


def test_evaluate_one_report_per_pair() -> None:
    series = _paired(_STEP)
    reports = DifferentialStationarity.evaluate(
        series, parameters=_PARAMETERS, variance_estimator=_RECT
    )
    assert [r.pair for r in reports] == list(series.model_pairs())
    first = reports[0]
    assert first.differential == series.differential("a", "b")
    assert first.status is StationarityStatus.COMPUTED
    assert first.break_target_timestamp == series.target_timestamps[_STEP_BREAK_INDEX]
    assert first.max_lag == acf_max_lag(len(_STEP))
    assert len(first.acf) == first.max_lag
    assert first.rejected is (first.p_value is not None and first.p_value <= _ALPHA)
    assert first.rejected is True


def test_evaluate_constant_differential_is_undefined() -> None:
    series = _paired(_STEP)
    reports = DifferentialStationarity.evaluate(
        series, parameters=_PARAMETERS, variance_estimator=_RECT
    )
    constant = next(r for r in reports if r.pair == ("b", "c"))  # c = b + 0,5
    assert constant.status is StationarityStatus.UNDEFINED
    assert constant.undefined_reason == CONSTANT_DIFFERENTIAL
    assert constant.acf == ()
    assert constant.statistic is None
    assert constant.rejected is None
    assert constant.break_target_timestamp is None


def test_evaluate_refuses_untyped_parameters() -> None:
    with pytest.raises(ValueError, match="StationarityParameters"):
        DifferentialStationarity.evaluate(
            _paired(_STEP),
            parameters={"break_alpha": 0.05},  # type: ignore[arg-type]
            variance_estimator=_RECT,
        )
