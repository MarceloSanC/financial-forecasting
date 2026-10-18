"""Unit do `ConformalCoverage` (Stage 7.2, Task 09) — concept §5 I8, I9, §6 C6; ADR 7.2.0004.

Contagens à mão sobre séries pequenas (grade de 7 níveis do conftest): a cobertura
conformal reusa os predicados, o gate e a banda do evaluation, e com correção zero
reproduz o `CoverageMetrics` da mesma série.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
    ConformalCoverage,
    ConformalCoverageReport,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]
pytestmark = pytest.mark.unit

_TOL = 1e-9
_BANDS = (0.9, 0.95)
_SPREAD = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_WIDE = (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06)
_DIRAC = (0.004,) * 7
_PAIR_INDEX = {(0.05, 0.95): (0, 6), (0.1, 0.9): (1, 5), (0.25, 0.75): (2, 4)}
_V = "split_cqr_asymmetric_unweighted_v1"


def _conformal(
    native: CoverageSeries,
    *,
    corrections: dict[tuple[float, float], tuple[float, float]] | None = None,
    seed: int = 7,
    variant: str = _V,
) -> ConformalCoverageSeries:
    """Limites = quantis nativos do par corrigidos por (Q_lo, Q_hi) (zero por padrão)."""
    pairs = []
    for pair, (k_lo, k_hi) in _PAIR_INDEX.items():
        q_lo, q_hi = (corrections or {}).get(pair, (0.0, 0.0))
        lower = tuple(native.scored_values(i)[k_lo] - q_lo for i in range(native.n_points))
        upper = tuple(native.scored_values(i)[k_hi] + q_hi for i in range(native.n_points))
        pairs.append(ConformalPairLimits(pair[0], pair[1], lower, upper))
    return ConformalCoverageSeries(seed=seed, native=native, variant=variant, pairs=tuple(pairs))


def _explicit(
    native: CoverageSeries, lower: Sequence[float], upper: Sequence[float], *, seed: int = 7
) -> ConformalCoverageSeries:
    return ConformalCoverageSeries(
        seed=seed,
        native=native,
        variant=_V,
        pairs=(ConformalPairLimits(0.1, 0.9, tuple(lower), tuple(upper)),),
    )


def _mixed(make_series: SeriesFactory) -> CoverageSeries:
    """T = 5, linhas 1 e 3 degeneradas, realizados sem empate com a grade."""
    grids = [_SPREAD, _DIRAC, _WIDE, _DIRAC, _SPREAD]
    return make_series(grids, [0.015, 0.1, -0.05, -0.2, 0.035])


def test_zero_corrections_equal_the_native_coverage_metrics(make_series: SeriesFactory) -> None:
    native = _mixed(make_series)
    report = ConformalCoverage.evaluate(_conformal(native), tolerance=_TOL, band_levels=_BANDS)
    metrics = CoverageMetrics.evaluate(native, tolerance=_TOL)
    assert report.n_evaluated == metrics.n_evaluated == 3  # noqa: PLR2004
    per_level = dict(metrics.per_level)
    for pair, metric_pair in zip(report.per_pair, metrics.per_pair, strict=True):
        assert pair.lower_tail.coverage == per_level[pair.lower_level]
        assert pair.upper_tail.coverage == per_level[pair.upper_level]
        assert pair.picp == metric_pair.picp
        assert math.isclose(pair.mpiw, metric_pair.mpiw, rel_tol=1e-12)
        assert pair.nominal == metric_pair.nominal
    assert report.degeneracy == metrics.degeneracy


def test_mask_is_the_native_series_mask(make_series: SeriesFactory) -> None:
    # linha 1 degenerada com y abaixo de L: fora do denominador e da contagem
    native = make_series([_SPREAD, _DIRAC, _SPREAD], [0.0, -1.0, 0.0])
    report = ConformalCoverage.evaluate(
        _explicit(native, (-0.02, -0.02, -0.02), (0.02, 0.02, 0.02)),
        tolerance=_TOL,
        band_levels=_BANDS,
    )
    assert report.degeneracy.degenerate == (False, True, False)
    assert report.n_evaluated == 2  # noqa: PLR2004
    assert report.per_pair[0].lower_tail.count_at_or_below == 0
    assert report.per_pair[0].picp == 1.0


def test_tolerance_changes_the_mask(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [0.0, 0.0])
    series = _explicit(native, (-0.02, -0.02), (0.02, 0.02))
    assert ConformalCoverage.evaluate(series, tolerance=_TOL, band_levels=_BANDS).n_evaluated == 2  # noqa: PLR2004
    wide = ConformalCoverage.evaluate(series, tolerance=0.1, band_levels=_BANDS)
    assert wide.n_evaluated == 0
    assert wide.applicable is False


def test_tail_tie_counts_at_or_below(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [-0.02, 0.02])
    report = ConformalCoverage.evaluate(
        _explicit(native, (-0.02, -0.03), (0.01, 0.02)), tolerance=_TOL, band_levels=_BANDS
    )
    pair = report.per_pair[0]
    assert pair.lower_tail.count_at_or_below == 1  # y == L na linha 0
    # linha 0: y = -0,02 abaixo de U = 0,01; linha 1: y == U = 0,02 também conta
    assert pair.upper_tail.count_at_or_below == 2  # noqa: PLR2004


def test_picp_closed_ties(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [-0.02, 0.02])
    report = ConformalCoverage.evaluate(
        _explicit(native, (-0.02, -0.02), (0.02, 0.02)), tolerance=_TOL, band_levels=_BANDS
    )
    assert report.per_pair[0].picp == 1.0  # y == L e y == U contam dentro
    assert report.per_pair[0].covered_count == 2  # noqa: PLR2004


def test_crossed_interval_not_covered_and_counted(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [0.0, 0.0])
    # linha 0 cruzada (L = 0,01 > U = -0,01), y = 0 entre os dois: não cobre
    report = ConformalCoverage.evaluate(
        _explicit(native, (0.01, -0.02), (-0.01, 0.02)), tolerance=_TOL, band_levels=_BANDS
    )
    pair = report.per_pair[0]
    assert pair.picp == 0.5  # noqa: PLR2004
    assert pair.crossed_rate == 0.5  # noqa: PLR2004
    assert pair.crossed_count == 1
    assert math.isclose(pair.mpiw, ((-0.01 - 0.01) + 0.04) / 2, rel_tol=1e-12)  # U - L como está
    assert report.nesting_violation_rate == 0.5  # noqa: PLR2004
    assert report.nesting_violation_count == 1


def test_nesting_across_pairs(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [0.0, 0.0])
    # par interno (0,25) com L abaixo do L do par (0,1) na linha 1: viola o aninhamento
    nested = _conformal(native)
    report = ConformalCoverage.evaluate(nested, tolerance=_TOL, band_levels=_BANDS)
    assert report.nesting_violation_rate == 0.0
    pairs = list(nested.pairs)
    inner = pairs[2]
    pairs[2] = ConformalPairLimits(
        inner.lower_level, inner.upper_level, (inner.lower[0], -0.025), inner.upper
    )
    broken = dataclasses.replace(nested, pairs=tuple(pairs))
    report = ConformalCoverage.evaluate(broken, tolerance=_TOL, band_levels=_BANDS)
    assert report.nesting_violation_rate == 0.5  # noqa: PLR2004
    assert report.per_pair[2].crossed_rate == 0.0  # o par sozinho não cruza


def test_infinite_limits_cover_and_flag_mpiw(make_series: SeriesFactory) -> None:
    native = make_series([_SPREAD, _SPREAD], [0.5, -0.5])
    report = ConformalCoverage.evaluate(
        _explicit(native, (-math.inf, -math.inf), (math.inf, math.inf)),
        tolerance=_TOL,
        band_levels=_BANDS,
    )
    pair = report.per_pair[0]
    assert pair.picp == 1.0
    assert pair.mpiw == math.inf
    assert pair.mpiw_infinite is True
    assert pair.lower_tail.count_at_or_below == 0
    assert pair.upper_tail.count_at_or_below == 2  # noqa: PLR2004
    finite = ConformalCoverage.evaluate(
        _explicit(native, (-1.0, -1.0), (1.0, 1.0)), tolerance=_TOL, band_levels=_BANDS
    )
    assert finite.per_pair[0].mpiw_infinite is False


def test_wilson_nominal_is_the_tail_level(make_series: SeriesFactory) -> None:
    native = _mixed(make_series)
    report = ConformalCoverage.evaluate(_conformal(native), tolerance=_TOL, band_levels=_BANDS)
    for pair in report.per_pair:
        assert [b.nominal for b in pair.lower_tail.bands] == [pair.lower_level] * 2
        assert [b.nominal for b in pair.upper_tail.bands] == [pair.upper_level] * 2
        assert [b.band_level for b in pair.lower_tail.bands] == list(_BANDS)
        assert pair.lower_tail.bands[0].count == pair.lower_tail.count_at_or_below
        assert pair.lower_tail.bands[0].n == report.n_evaluated


def test_label_is_exact_and_validated(make_series: SeriesFactory) -> None:
    report = ConformalCoverage.evaluate(
        _conformal(_mixed(make_series)), tolerance=_TOL, band_levels=_BANDS
    )
    assert report.label == EMPIRICAL_COVERAGE_LABEL == "cobertura empírica (não garantida)"
    with pytest.raises(ValueError, match="EMPIRICAL_COVERAGE_LABEL"):
        dataclasses.replace(report, label="cobertura garantida")


def test_fully_degenerate_native_is_not_applicable(make_series: SeriesFactory) -> None:
    native = make_series([_DIRAC, _DIRAC], [0.0, 0.1])
    report = ConformalCoverage.evaluate(_conformal(native), tolerance=_TOL, band_levels=_BANDS)
    assert (report.applicable, report.n_evaluated, report.per_pair) == (False, 0, ())
    assert report.nesting_violation_rate is None
    assert report.label == EMPIRICAL_COVERAGE_LABEL


def _report(
    make_series: SeriesFactory, *, seed: int, below: int, n: int, horizon: int = 1
) -> ConformalCoverageReport:
    """n linhas não degeneradas; `below` delas com y ≤ L (y = -1), as outras dentro."""
    realized = [-1.0] * below + [0.0] * (n - below)
    native = make_series([_SPREAD] * n, realized, horizon=horizon)
    series = _explicit(native, (-0.02,) * n, (0.02,) * n, seed=seed)
    return ConformalCoverage.evaluate(series, tolerance=_TOL, band_levels=_BANDS)


def test_seed_mean_coverage_is_mean_count_over_mean_n(make_series: SeriesFactory) -> None:
    reports = [
        _report(make_series, seed=1, below=1, n=2),  # ĉ = 1/2
        _report(make_series, seed=2, below=1, n=8),  # ĉ = 1/8
    ]
    mean = ConformalCoverage.seed_mean(
        reports, horizon=1, variant=_V, expected_seeds=(1, 2), band_levels=_BANDS
    )
    tail = mean.per_pair[0].lower_tail
    assert mean.n_mean == 5.0  # noqa: PLR2004
    assert tail.mean_count == 1.0
    assert tail.coverage == 1.0 / 5.0  # c̄/n̄
    assert tail.mean_of_seed_coverages == (0.5 + 0.125) / 2  # média das coberturas
    assert tail.coverage != tail.mean_of_seed_coverages
    assert tail.sd_of_seed_coverages == pytest.approx(math.sqrt(2) * (0.5 - 0.125) / 2)
    assert [b.count for b in tail.bands] == [1.0, 1.0]
    assert [b.n for b in tail.bands] == [5.0, 5.0]
    assert [b.nominal for b in tail.bands] == [0.1, 0.1]
    pair = mean.per_pair[0]
    assert pair.picp == (1 + 7) / 2 / 5.0  # c̄_dentro / n̄
    assert pair.mean_of_seed_picps == (0.5 + 0.875) / 2
    assert math.isclose(pair.mpiw, 0.04, rel_tol=1e-12)
    assert mean.label == EMPIRICAL_COVERAGE_LABEL


def test_seed_mean_reports_used_and_excluded_seeds(make_series: SeriesFactory) -> None:
    reports = [
        _report(make_series, seed=3, below=0, n=2),
        _report(make_series, seed=1, below=1, n=2),
    ]
    mean = ConformalCoverage.seed_mean(
        reports, horizon=1, variant=_V, expected_seeds=(1, 2, 3, 4), band_levels=_BANDS
    )
    assert mean.seeds_used == (1, 3)
    assert mean.seeds_excluded == (2, 4)
    assert mean.applicable is True


def test_seed_mean_with_one_seed_has_no_dispersion(make_series: SeriesFactory) -> None:
    mean = ConformalCoverage.seed_mean(
        [_report(make_series, seed=1, below=1, n=4)],
        horizon=1,
        variant=_V,
        expected_seeds=(1,),
        band_levels=_BANDS,
    )
    pair = mean.per_pair[0]
    assert pair.lower_tail.sd_of_seed_coverages is None
    assert pair.sd_of_seed_picps is None
    assert pair.lower_tail.coverage == pair.lower_tail.mean_of_seed_coverages == 0.25  # noqa: PLR2004


def test_seed_mean_without_reports_is_undefined() -> None:
    mean = ConformalCoverage.seed_mean(
        [], horizon=1, variant=_V, expected_seeds=(1, 2), band_levels=_BANDS
    )
    assert (mean.applicable, mean.seeds_used, mean.seeds_excluded) == (False, (), (1, 2))
    assert (mean.n_mean, mean.per_pair, mean.nesting_violation_rate) == (None, (), None)


def test_seed_mean_skips_a_not_applicable_seed(make_series: SeriesFactory) -> None:
    degenerate = ConformalCoverage.evaluate(
        _conformal(make_series([_DIRAC], [0.0]), seed=2), tolerance=_TOL, band_levels=_BANDS
    )
    mean = ConformalCoverage.seed_mean(
        [_report(make_series, seed=1, below=1, n=2), degenerate],
        horizon=1,
        variant=_V,
        expected_seeds=(1, 2),
        band_levels=_BANDS,
    )
    assert (mean.seeds_used, mean.seeds_excluded, mean.n_mean) == ((1,), (2,), 2.0)


def test_seed_mean_refuses_mixed_horizon_variant_and_bad_seeds(
    make_series: SeriesFactory,
) -> None:
    one = _report(make_series, seed=1, below=1, n=2)
    other_h = _report(make_series, seed=2, below=1, n=2, horizon=7)
    other_v = dataclasses.replace(_report(make_series, seed=2, below=1, n=2), variant="other")
    for reports, message in (
        ([one, other_h], "horizon"),
        ([one, other_v], "variant"),
        ([one, one], "repeated"),
        ([_report(make_series, seed=9, below=0, n=2)], "not in expected_seeds"),
    ):
        with pytest.raises(ValueError, match=message):
            ConformalCoverage.seed_mean(
                reports, horizon=1, variant=_V, expected_seeds=(1, 2), band_levels=_BANDS
            )
    with pytest.raises(ValueError, match="expected_seeds"):
        ConformalCoverage.seed_mean(
            [one], horizon=1, variant=_V, expected_seeds=(1, 1), band_levels=_BANDS
        )
