"""Unit test do `CrpsScore` e do `IntervalScore` (A3/A4/A1b/A10/C7).

Fixtures analíticas (ADR 0.0.0021): identidade CRPS_Q = 2·P̄_G, Dirac com grade
simétrica (CRPS_Q = |y - x|; IS_alpha = (2/alpha)|y - x|), os três casos do IS e a identidade
IS_alpha = (2/alpha)[rho_{alpha/2}(y - l) + rho_{1-alpha/2}(y - u)]
(Bracher et al. 2021, App. A). Os
valores de referência são escritos à parte, não com as funções do domínio.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services.crps_score import (
    CRPS_Q_LABEL,
    CrpsReport,
    CrpsScore,
    crps_quantile,
    mean_crps_quantile,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    IntervalScore,
    IntervalScoreReport,
    PairIntervalScore,
    interval_score,
    mean_interval_score,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

# Tolerâncias declaradas (ADR 0.0.0021; ADR 6.1.0001): ruído de soma float64.
_REL_TOL = 1e-12
_ABS_TOL = 1e-12
# Seed declarada da grade aleatória sem empate.
_SEED = 20260928
_RANDOM_POINTS = 200

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_WIDE_LEVELS = (0.02, 0.05, 0.1, 0.5, 0.9, 0.95, 0.98)
_DIRAC_MISCOVERAGE = 0.04
_DIRAC_FACTOR = 50.0  # 2/alpha com alpha = 0.04
_PAIR_05 = (0.05, 0.95)
_MISCOVERAGE_05 = 0.1
_NOMINAL_05 = 0.9
_HORIZON = 5
_A1B_RAW = (
    (0.03, -0.02, -0.01, 0.0, 0.01, 0.02, -0.03),  # extremos trocados
    (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03),
)
_A1B_REALIZED = (0.025, -0.001)


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _rho(u: float, tau: float) -> float:
    """rho_τ(u) na forma max, escrita à parte do domínio."""
    return tau * max(u, 0.0) + (1.0 - tau) * max(-u, 0.0)


def _pair(**overrides: float) -> PairIntervalScore:
    """Um `PairIntervalScore` coerente para (0.05, 0.95), com campos sobrescrevíveis."""
    fields = {
        "lower_level": 0.05,
        "upper_level": 0.95,
        "miscoverage": _MISCOVERAGE_05,
        "nominal": _NOMINAL_05,
        "mean_width": 0.02,
        "mean_lower_penalty": 0.0,
        "mean_upper_penalty": 0.0,
    }
    fields.update(overrides)
    return PairIntervalScore(**fields)


def _random_series(make_series: SeriesFactory, *, levels: tuple[float, ...]) -> CoverageSeries:
    """T = 200 pontos, grade ordenada sem empate, realizado sem empate com a grade."""
    rng = random.Random(_SEED)
    grids = [tuple(sorted(rng.gauss(0.0, 0.02) for _ in levels)) for _ in range(_RANDOM_POINTS)]
    realized = [rng.gauss(0.0, 0.02) for _ in range(_RANDOM_POINTS)]
    return make_series(grids, realized, levels=levels)


def _mixed_series(make_series: SeriesFactory) -> CoverageSeries:
    """Série mista: linhas com amplitude e linhas degeneradas (todos os quantis iguais)."""
    grids = [
        (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03),
        (0.004,) * 7,
        (-0.05, -0.02, -0.01, 0.002, 0.01, 0.015, 0.02),
        (-0.001,) * 7,
    ]
    return make_series(grids, [0.012, -0.02, 0.03, -0.001])


# --- A3 — CRPS_Q ---------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["random", "mixed"])
def test_crps_is_twice_pinball_grid_mean(make_series: SeriesFactory, kind: str) -> None:
    """A3: CRPS_Q = 2·P̄_G em série aleatória sem empate e em série mista."""
    series = (
        _random_series(make_series, levels=_LEVELS)
        if kind == "random"
        else _mixed_series(make_series)
    )

    crps = CrpsScore.score(series).crps_q

    assert _close(crps, 2 * PinballScore.score(series).grid_mean)


@pytest.mark.unit
@pytest.mark.parametrize(("y", "x"), [(0.03, -0.01), (-0.02, 0.01)], ids=["y>x", "y<x"])
def test_crps_on_symmetric_dirac_is_abs_error(
    make_series: SeriesFactory, y: float, x: float
) -> None:
    """A3: todos os quantis = x com grade simétrica → CRPS_Q = |y - x|."""
    series = make_series([(x,) * len(_LEVELS)], [y])

    assert _close(CrpsScore.score(series).crps_q, abs(y - x))


@pytest.mark.unit
def test_crps_report_carries_label(make_series: SeriesFactory) -> None:
    """A3/I4: o relatório sempre traz o rótulo da aproximação na grade."""
    report = CrpsScore.score(_mixed_series(make_series))

    assert report.label == CRPS_Q_LABEL


@pytest.mark.unit
def test_mean_of_crps_per_point_equals_crps_q(make_series: SeriesFactory) -> None:
    """A3: a média de `per_point` é `crps_q`; o ponto 0 confere à mão."""
    series = _mixed_series(make_series)

    per_point = CrpsScore.per_point(series)

    assert len(per_point) == series.n_points
    assert _close(sum(per_point) / len(per_point), CrpsScore.score(series).crps_q)
    values = series.scored_values(0)
    y = series.realized[0]
    expected = 2 * sum(_rho(y - q, t) for q, t in zip(values, _LEVELS, strict=True)) / 7
    assert _close(per_point[0], expected)


# --- A4 — IS_alpha -----------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("y", "expected"),
    [
        (-0.03, 0.02 + (2 / 0.1) * 0.02),  # y < l
        (-0.01, 0.02),  # y = l (dentro)
        (0.0, 0.02),  # l < y < u
        (0.01, 0.02),  # y = u (dentro)
        (0.04, 0.02 + (2 / 0.1) * 0.03),  # y > u
    ],
    ids=["below", "at-lower", "inside", "at-upper", "above"],
)
def test_interval_score_three_cases(y: float, expected: float) -> None:
    """A4: os três casos de GR 2007 Eq. (43), com y = l e y = u dentro."""
    value = interval_score(realized=y, lower=-0.01, upper=0.01, miscoverage=0.1)

    assert _close(value, expected)


@pytest.mark.unit
@pytest.mark.parametrize("y", [-0.05, -0.01, 0.003, 0.01, 0.07])
def test_interval_score_matches_pinball_identity(y: float) -> None:
    """A4: IS = (2/alpha)[rho_{alpha/2}(y - l) + rho_{1-alpha/2}(y - u)] (Bracher 2021)."""
    alpha, low, high = 0.2, -0.01, 0.01
    identity = (2 / alpha) * (_rho(y - low, alpha / 2) + _rho(y - high, 1 - alpha / 2))

    assert _close(interval_score(realized=y, lower=low, upper=high, miscoverage=alpha), identity)


@pytest.mark.unit
@pytest.mark.parametrize(("y", "x"), [(0.03, -0.01), (-0.02, 0.01)], ids=["y>x", "y<x"])
def test_interval_score_on_dirac_is_fifty_times_abs_error(
    make_series: SeriesFactory, y: float, x: float
) -> None:
    """A4: Dirac com alpha = 0.04 (par 0.02/0.98) → IS = 50·|y - x|."""
    series = make_series([(x,) * len(_WIDE_LEVELS)], [y], levels=_WIDE_LEVELS)

    pair = IntervalScore.score(series).per_pair[0]

    assert pair.miscoverage == _DIRAC_MISCOVERAGE
    assert _close(pair.mean_score, _DIRAC_FACTOR * abs(y - x))


def _a1b_series(make_series: SeriesFactory) -> CoverageSeries:
    """Fixture cruzada do A1b: extremos trocados no bruto (o guardrail reordena)."""
    return make_series(list(_A1B_RAW), list(_A1B_REALIZED))


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["random", "mixed-degenerate", "a1b-crossed"])
def test_pair_mean_score_matches_mean_interval_score(make_series: SeriesFactory, kind: str) -> None:
    """A4/I5: `mean_score` (soma dos termos, I5) ≈ `mean_interval_score` da mesma coluna.

    É a ponte entre a decomposição do `IntervalScore.score` e a função de série que o
    fake delega (ADR 6.1.0001 item 4): série aleatória sem empate, série mista com
    linhas degeneradas (largura 0) e a fixture cruzada do A1b.
    """
    builders = {
        "random": lambda: _random_series(make_series, levels=_LEVELS),
        "mixed-degenerate": lambda: _mixed_series(make_series),
        "a1b-crossed": lambda: _a1b_series(make_series),
    }
    series = builders[kind]()

    report = IntervalScore.score(series)

    for pair, (k_low, k_high) in zip(report.per_pair, series.symmetric_pair_indices, strict=True):
        expected = mean_interval_score(
            realized=series.realized,
            lower=[series.scored_values(i)[k_low] for i in range(series.n_points)],
            upper=[series.scored_values(i)[k_high] for i in range(series.n_points)],
            miscoverage=pair.miscoverage,
        )
        assert _close(pair.mean_score, expected)


@pytest.mark.unit
def test_one_pair_score_per_symmetric_pair(make_series: SeriesFactory) -> None:
    """A4: um `PairIntervalScore` por par, na ordem de `symmetric_pairs`."""
    series = _mixed_series(make_series)

    report = IntervalScore.score(series)

    assert tuple((p.lower_level, p.upper_level) for p in report.per_pair) == (
        series.symmetric_pairs
    )


@pytest.mark.unit
def test_miscoverage_and_nominal_are_exact_for_05_95(make_series: SeriesFactory) -> None:
    """A4/I5/I7: (0.05, 0.95) → alpha = 0.1 e nominal = 0.9 por igualdade EXATA de float."""
    series = _mixed_series(make_series)

    pair = IntervalScore.score(series).per_pair[0]

    assert (pair.lower_level, pair.upper_level) == _PAIR_05
    assert pair.miscoverage == _MISCOVERAGE_05
    assert pair.nominal == _NOMINAL_05


@pytest.mark.unit
def test_pair_interval_score_with_miscoverage_not_twice_lower_level_raises() -> None:
    """I5: `miscoverage` != 2·τ_l ergue (ex.: a forma `1 - (τ_u - τ_l)`)."""
    with pytest.raises(ValueError, match=r"miscoverage must be 2 \* lower_level"):
        _pair(miscoverage=1 - (0.95 - 0.05))


@pytest.mark.unit
def test_pair_interval_score_with_nominal_not_one_minus_miscoverage_raises() -> None:
    """I7: `nominal` != 1 - miscoverage ergue."""
    with pytest.raises(ValueError, match="nominal must be 1 - miscoverage"):
        _pair(nominal=0.95)


@pytest.mark.unit
def test_crps_report_with_zero_points_raises() -> None:
    """C4: `CrpsReport` com `n_points = 0` ergue."""
    with pytest.raises(ValueError, match="n_points >= 1"):
        CrpsReport(horizon=1, n_points=0, crps_q=0.1)


@pytest.mark.unit
def test_crps_report_without_the_label_raises() -> None:
    """I4 por construção: o rótulo não pode ser trocado nem omitido."""
    with pytest.raises(ValueError, match="must carry CRPS_Q_LABEL"):
        CrpsReport(horizon=1, n_points=2, crps_q=0.1, label="CRPS")


@pytest.mark.unit
def test_interval_score_report_without_pairs_raises() -> None:
    """C4: `per_pair = ()` ergue."""
    with pytest.raises(ValueError, match="at least one symmetric pair"):
        IntervalScoreReport(horizon=1, n_points=3, per_pair=())


@pytest.mark.unit
def test_interval_score_report_with_zero_points_raises() -> None:
    """C4: `n_points = 0` ergue."""
    with pytest.raises(ValueError, match="n_points >= 1"):
        IntervalScoreReport(horizon=1, n_points=0, per_pair=(_pair(),))


# --- A1b — pontua-se o rearranjado ----------------------------------------------------


@pytest.mark.unit
def test_interval_and_crps_score_guardrail_not_raw(make_series: SeriesFactory) -> None:
    """A1b: com raw cruzado no par extremo, IS (e CRPS_Q) conferem com o cálculo sobre
    `guardrail_values` e diferem do cálculo sobre `raw_values`."""
    raw = list(_A1B_RAW)
    realized = list(_A1B_REALIZED)
    series = _a1b_series(make_series)
    alpha = 2 * _LEVELS[0]

    pair = IntervalScore.score(series).per_pair[0]

    def hand_is(grids: list[tuple[float, ...]]) -> float:
        total = 0.0
        for grid, y in zip(grids, realized, strict=True):
            low, high = grid[0], grid[-1]
            total += (
                (high - low) + (2 / alpha) * max(low - y, 0.0) + (2 / alpha) * max(y - high, 0.0)
            )
        return total / len(realized)

    guardrail = [series.scored_values(i) for i in range(series.n_points)]
    assert _close(pair.mean_score, hand_is(guardrail))
    assert not _close(pair.mean_score, hand_is(raw))


# --- A10 (parte) ----------------------------------------------------------------------


@pytest.mark.unit
def test_crps_and_interval_reports_carry_horizon_and_all_points(
    make_series: SeriesFactory,
) -> None:
    """A10: os dois relatórios trazem `horizon` e `n_points = T`."""
    grids = [(0.0,) * 7, (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)]
    series = make_series(grids, [0.01, 0.0], horizon=_HORIZON)

    crps = CrpsScore.score(series)
    interval = IntervalScore.score(series)

    assert (crps.horizon, crps.n_points) == (series.horizon, series.n_points)
    assert (interval.horizon, interval.n_points) == (series.horizon, series.n_points)


# --- C7 — kernels por ponto e funções de série ----------------------------------------


@pytest.mark.unit
def test_crps_quantile_rejects_misaligned_grid() -> None:
    with pytest.raises(ValueError, match="must align"):
        crps_quantile(realized=0.0, quantiles=[0.0, 1.0], levels=[0.1, 0.5, 0.9])


@pytest.mark.unit
def test_crps_quantile_rejects_level_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="level must be"):
        crps_quantile(realized=0.0, quantiles=[0.0, 1.0], levels=[0.0, 0.9])


@pytest.mark.unit
@pytest.mark.parametrize("miscoverage", [0.0, 1.0, 1.5], ids=["zero", "one", "above-one"])
def test_interval_score_rejects_invalid_miscoverage(miscoverage: float) -> None:
    with pytest.raises(ValueError, match="miscoverage must be"):
        interval_score(realized=0.0, lower=-0.01, upper=0.01, miscoverage=miscoverage)


@pytest.mark.unit
def test_interval_score_rejects_crossed_bounds() -> None:
    with pytest.raises(ValueError, match="must not exceed upper"):
        interval_score(realized=0.0, lower=0.01, upper=-0.01, miscoverage=0.1)


@pytest.mark.unit
def test_mean_crps_quantile_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        mean_crps_quantile(realized=[], quantile_grid=[], levels=[0.25, 0.75])


@pytest.mark.unit
def test_mean_interval_score_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        mean_interval_score(realized=[], lower=[], upper=[], miscoverage=0.1)
