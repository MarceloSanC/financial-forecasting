"""Testes do `HorizonReports` (Stage 6.4 Task 06; A5, I1, I12, C8; ADR 6.4.0007).

Os relatórios são **iguais** (`==`) aos das chamadas diretas aos serviços 6.1-6.3
sobre as mesmas séries, nas duas amostras.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import CrpsScore
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    HolmCorrection,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
    HorizonReports,
    SampleKind,
    SeriesReports,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    IntervalScore,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import WilsonBand
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from tests.unit.features.evaluation.gold.conftest import (
    Cohort,
    make_cohort,
    replace_records,
)

_TOLERANCE = 1e-9
_BANDS = (0.9, 0.95)
_MIN_VIOLATIONS = 5
_ALPHA = 0.05
_ESTIMATORS = (DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT)
_CANDIDATE = "tft"
_TAIL_LEVELS = (0.05, 0.1, 0.25, 0.75, 0.9, 0.95)
_H2 = 2


def _samples(
    cohort: Cohort, deficits: Mapping[str, int] | None = None
) -> tuple[HorizonSamples, ...]:
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 2),
        window_deficits=deficits or {},
        required_models=frozenset({_CANDIDATE}),
    )
    assert assembled.alignment.findings == ()
    return assembled.horizons


def _paired(samples: HorizonSamples) -> PairedLossSeries:
    return paired_pinball_losses({model: samples.common[model] for model in samples.models})


def _evaluate(samples: HorizonSamples, **changes: object) -> HorizonReport:
    kwargs: dict[str, object] = {
        "paired": _paired(samples),
        "tolerance": _TOLERANCE,
        "band_levels": _BANDS,
        "min_violations": _MIN_VIOLATIONS,
        "candidate": _CANDIDATE,
        "dm_alpha": _ALPHA,
        "dm_variance_estimators": _ESTIMATORS,
    }
    kwargs.update(changes)
    return HorizonReports.evaluate(samples, **kwargs)  # type: ignore[arg-type]


def _report_of(
    report: HorizonReport, model: str, seed: int | None, sample: SampleKind
) -> SeriesReports:
    [match] = [s for s in report.series if (s.model, s.seed, s.sample) == (model, seed, sample)]
    return match


@pytest.fixture(scope="module")
def reports() -> tuple[tuple[HorizonSamples, HorizonReport], ...]:
    return tuple(
        (samples, _evaluate(samples))
        for samples in _samples(make_cohort(prefixes={"tft": 2}), {"tft": 2})
    )


@pytest.mark.unit
def test_reports_equal_direct_calls(
    reports: tuple[tuple[HorizonSamples, HorizonReport], ...],
) -> None:
    for samples, report in reports:
        for model in samples.models:
            for index, seed in enumerate(samples.seeds[model]):
                for sample, series in (
                    (SampleKind.MODEL_FULL, samples.full[model][index]),
                    (SampleKind.COMMON, samples.common[model][index]),
                ):
                    got = _report_of(report, model, seed, sample)
                    assert got.pinball == PinballScore.score(series)
                    assert got.crps == CrpsScore.score(series)
                    assert got.interval == IntervalScore.score(series)
                    assert got.coverage == CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
                    assert got.n_points == series.n_points
                    assert (got.first_target_timestamp, got.last_target_timestamp) == (
                        series.target_timestamps[0],
                        series.target_timestamps[-1],
                    )
                    first = got.calibration[0]
                    direct = HitSequences.interval(
                        series, pair=series.symmetric_pairs[0], tolerance=_TOLERANCE
                    )
                    assert first.christoffersen == ChristoffersenTest.evaluate(
                        direct, min_violations=_MIN_VIOLATIONS
                    )
        for estimator, family in zip(_ESTIMATORS, report.dm_families, strict=True):
            assert family == HolmCorrection.family(
                report.paired, candidate=_CANDIDATE, alpha=_ALPHA, variance_estimator=estimator
            )


@pytest.mark.unit
def test_both_samples(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    """Uma entrada por (modelo, seed, amostra); a `full` do GBM é mais longa que a comum."""
    for samples, report in reports:
        keys = [(s.model, s.seed, s.sample) for s in report.series]
        assert keys == [
            (model, seed, sample)
            for model in samples.models
            for seed in samples.seeds[model]
            for sample in (SampleKind.MODEL_FULL, SampleKind.COMMON)
        ]
        full = _report_of(report, "gbm", None, SampleKind.MODEL_FULL)
        common = _report_of(report, "gbm", None, SampleKind.COMMON)
        assert full.n_points == common.n_points + 2
        assert common.n_points == report.n_common == samples.n_common
        assert (report.common_first_target_timestamp, report.common_last_target_timestamp) == (
            samples.common_first_target_timestamp,
            samples.common_last_target_timestamp,
        )


@pytest.mark.unit
def test_with_and_without_gaps(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    """Toda sequência sai com e sem as linhas degeneradas (`include_degenerate`)."""
    for _, report in reports:
        for series in report.series:
            flags = [row.christoffersen.includes_degenerate for row in series.calibration]
            assert flags.count(False) == flags.count(True) > 0


@pytest.mark.unit
def test_band_per_level(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    samples, report = reports[0]
    series = samples.full["tft"][0]
    got = _report_of(report, "tft", 1, SampleKind.MODEL_FULL)
    row = got.calibration[0]
    assert [band.band_level for band in row.wilson] == list(_BANDS)
    sequence = HitSequences.interval(series, pair=series.symmetric_pairs[0], tolerance=_TOLERANCE)
    for band, level in zip(row.wilson, _BANDS, strict=True):
        assert band == WilsonBand.evaluate(
            horizon=sequence.horizon,
            count=sequence.n_violations,
            n=sequence.n_observed,
            nominal=sequence.violation_rate,
            band_level=level,
        )
    assert all(len(r.wilson) == len(_BANDS) for s in report.series for r in s.calibration)


@pytest.mark.unit
def test_dm_per_estimator(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    samples, _ = reports[0]
    report = _evaluate(samples, dm_variance_estimators=(DmVarianceEstimator.BARTLETT,))
    assert len(report.dm_families) == 1
    assert report.dm_families[0].variance_estimator is DmVarianceEstimator.BARTLETT
    assert [f.variance_estimator for f in reports[0][1].dm_families] == list(_ESTIMATORS)


@pytest.mark.unit
def test_dgt_only_multistep(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    """h = 1: nenhuma linha DGT; h = 2: sub-séries com `dgt_step == 2` (2 por sequência)."""
    by_horizon = {report.horizon: report for _, report in reports}
    h1_rows = [r for s in by_horizon[1].series for r in s.calibration]
    assert all(r.christoffersen.dgt_step is None for r in h1_rows)
    h2_rows = [r for s in by_horizon[_H2].series for r in s.calibration]
    dgt = [r for r in h2_rows if r.christoffersen.dgt_step is not None]
    assert dgt
    assert {r.christoffersen.dgt_step for r in dgt} == {_H2}
    assert len(dgt) == _H2 * (len(h2_rows) - len(dgt))
    assert len(h1_rows) == len(h2_rows) - len(dgt)


@pytest.mark.unit
def test_var_level_tails(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    """`var_level` só nas caudas: 0,95 para τ = 0,05 e 0,95 (e 1 - τ / τ nas demais)."""
    _, report = reports[0]
    rows = [r for r in report.series[0].calibration if not r.christoffersen.includes_degenerate]
    interval_rows = [r for r in rows if len(r.christoffersen.levels) == _H2]
    tail_rows = [r for r in rows if len(r.christoffersen.levels) == 1]
    assert all(r.var_level is None for r in interval_rows)
    assert [r.christoffersen.levels[0] for r in tail_rows] == list(_TAIL_LEVELS)
    expected = [max(level, 1.0 - level) for level in _TAIL_LEVELS]
    assert [r.var_level for r in tail_rows] == pytest.approx(expected, abs=1e-12)
    assert tail_rows[0].var_level == tail_rows[-1].var_level == pytest.approx(0.95, abs=1e-12)


@pytest.mark.unit
def test_degenerate_not_applicable() -> None:
    """Série 100 % degenerada (baseline pontual): relatórios "não aplicável" (C8)."""
    cohort = replace_records(
        make_cohort(),
        lambda r: r.model == "gbm",
        lambda r: dataclasses.replace(r, value_raw=0.002, value_guardrail=0.002),
    )
    samples = _samples(cohort)[0]
    report = _evaluate(samples)
    gbm = _report_of(report, "gbm", None, SampleKind.MODEL_FULL)
    series = samples.full["gbm"][0]
    assert gbm.coverage == CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    excluded = [r for r in gbm.calibration if not r.christoffersen.includes_degenerate]
    assert excluded
    assert all(r.christoffersen.statistics.n_observed == 0 for r in excluded)
    assert all(not band.applicable for r in excluded for band in r.wilson)


@pytest.mark.unit
def test_seed_mean_by_factory(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    """O `paired` (2 seeds do tft) é o da fábrica: média de L_t entre seeds (I12)."""
    samples, report = reports[0]
    assert report.paired == paired_pinball_losses(
        {model: samples.common[model] for model in samples.models}
    )
    per_seed = [PinballScore.per_point_losses(series) for series in samples.common["tft"]]
    mean = tuple((a + b) / 2 for a, b in zip(*per_seed, strict=True))
    assert report.paired.losses_of("tft") == pytest.approx(mean, abs=1e-15)


@pytest.mark.unit
def test_guardrail_rate_copied(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    samples, report = reports[0]
    series = samples.full["tft"][0]
    got = _report_of(report, "tft", 1, SampleKind.MODEL_FULL)
    assert got.guardrail_applied_rate == series.guardrail_applied_rate


@pytest.mark.unit
def test_horizon_mismatch_raises(reports: tuple[tuple[HorizonSamples, HorizonReport], ...]) -> None:
    (h1, _), (h2, _) = reports
    with pytest.raises(ValueError, match="paired series is for horizon 2"):
        _evaluate(h1, paired=_paired(h2))
    other_models = dataclasses.replace(_paired(h1), models=("gbm", "xgb"))
    with pytest.raises(ValueError, match="paired models"):
        _evaluate(h1, paired=other_models)
    shifted = PairedLossSeries(
        horizon=1,
        models=h1.models,
        target_timestamps=h1.full["gbm"][0].target_timestamps[: h1.n_common],
        losses=_paired(h1).losses,
    )
    with pytest.raises(ValueError, match="common sample"):
        _evaluate(h1, paired=shifted)
    with pytest.raises(ValueError, match="band_levels"):
        _evaluate(h1, band_levels=())
    with pytest.raises(ValueError, match="dm_variance_estimators"):
        _evaluate(h1, dm_variance_estimators=())
