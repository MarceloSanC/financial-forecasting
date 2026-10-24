"""Figuras do silver: sharpness diagram e fan chart (Stage 8.3, Task 08; A7, A8; D4, I6).

O silver sintético (`make_silver`) tem degenerados de propósito e o `mpiw` `model_full`
do gold recalculado pelo `CoverageMetrics` sobre as mesmas séries — a coerência que o
refresh real garante.
"""

from __future__ import annotations

import itertools
import math
import statistics

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    ReportSourceMismatchError,
    SeriesKind,
    SeriesSpec,
    fan_chart_seed_note,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    degenerate_key,
    fan_chart_figure,
    omitted_model_note,
    sharpness_figure,
)
from financial_forecasting.features.evaluation.application.use_cases.report_silver import (
    VerifiedSilver,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from tests.unit.features.evaluation._report_inputs import (
    CANDIDATE_SEEDS,
    DEGENERATE_POINTS,
    ReportWorld,
    make_silver,
    make_world,
)

_CANDIDATE = "tft_quantile"
_TOLERANCE = 1e-12


@pytest.fixture
def world() -> ReportWorld:
    return make_world()


@pytest.fixture
def silver(world: ReportWorld) -> VerifiedSilver:
    return make_silver(world)


def _full(
    world: ReportWorld, silver: VerifiedSilver, model: str, seed: int | None, h: int
) -> CoverageSeries:
    command = refresh_command_from(world.plan, world.reference)
    assembled = SeriesAssembly.assemble(
        silver.records,
        silver.runs,
        silver.realized,
        horizons=command.horizons,
        window_deficits=command.window_deficits,
        required_models=frozenset({_CANDIDATE}),
    )
    samples = next(s for s in assembled.horizons if s.horizon == h)
    return samples.full[model][samples.seeds[model].index(seed)]


def _panel(spec: object, panel_id: str) -> dict[str, SeriesSpec]:
    panel = next(p for p in spec.panels if p.panel_id == panel_id)  # type: ignore[attr-defined]
    return {s.series_id: s for s in panel.series}


# ---------------------------------------------------------------------------- sharpness


@pytest.mark.unit
def test_boxes_from_interval_widths_split_test_symmetric_pairs(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    box = _panel(sharpness_figure(world.inputs(), silver).spec, "h7")["gbm_quantile|0"]
    full = _full(world, silver, "gbm_quantile", 0, 7)
    widths = CoverageMetrics.interval_widths(full, tolerance=_TOLERANCE, pair=(0.25, 0.75))
    q1, median, q3 = statistics.quantiles(widths, n=4, method="inclusive")
    index = box.x.index("0,25-0,75")
    assert box.kind is SeriesKind.BOXES
    assert (box.whisker_low[index], box.low[index], box.y[index]) == (min(widths), q1, median)  # type: ignore[index]
    assert (box.high[index], box.whisker_high[index]) == (q3, max(widths))  # type: ignore[index]
    assert all(r.split == "test" for r in silver.records)


@pytest.mark.unit
def test_mean_of_drawn_widths_equals_gold_mpiw_model_full_exactly(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    full = _full(world, silver, _CANDIDATE, 1, 1)
    widths = CoverageMetrics.interval_widths(full, tolerance=_TOLERANCE, pair=(0.1, 0.9))
    gold = world.where(
        "gold_metrics_by_run",
        model=_CANDIDATE,
        seed=1,
        horizon=1,
        sample="model_full",
        metric="mpiw",
        level_low=0.1,
    )[0]["value"]
    assert math.fsum(widths) / len(widths) == gold
    assert sharpness_figure(world.inputs(), silver).spec.figure_id == "sharpness_diagram"


@pytest.mark.unit
def test_degenerate_rows_excluded_and_counted_in_legend(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    box = _panel(sharpness_figure(world.inputs(), silver).spec, "h1")[f"{_CANDIDATE}|stacked"]
    full = _full(world, silver, _CANDIDATE, 1, 1)
    widths = CoverageMetrics.interval_widths(full, tolerance=_TOLERANCE, pair=(0.1, 0.9))
    assert full.n_points - len(widths) == DEGENERATE_POINTS[(_CANDIDATE, 1, 1)]
    assert box.whisker_low[box.x.index("0,1-0,9")] > 0.0  # type: ignore[index]
    assert "0,1-0,9: 2" in (box.label.note or "")


@pytest.mark.unit
def test_candidate_seeds_stacked_with_legend(world: ReportWorld, silver: VerifiedSilver) -> None:
    # CC2-2 (concept D4): uma caixa por par sobre as larguras de todas as seeds empilhadas
    series = _panel(sharpness_figure(world.inputs(), silver).spec, "h7")
    assert not any(f"{_CANDIDATE}|{seed}" in series for seed in CANDIDATE_SEEDS)
    box = series[f"{_CANDIDATE}|stacked"]
    assert box.name == f"{_CANDIDATE} (larguras de 2 seeds empilhadas: seed 1, seed 2)"
    stacked: list[float] = []
    for seed in CANDIDATE_SEEDS:
        full = _full(world, silver, _CANDIDATE, seed, 7)
        stacked += CoverageMetrics.interval_widths(full, tolerance=_TOLERANCE, pair=(0.1, 0.9))
    q1, median, q3 = statistics.quantiles(stacked, n=4, method="inclusive")
    index = box.x.index("0,1-0,9")
    assert (box.whisker_low[index], box.low[index], box.y[index]) == (min(stacked), q1, median)  # type: ignore[index]
    assert (box.high[index], box.whisker_high[index]) == (q3, max(stacked))  # type: ignore[index]
    assert "0,1-0,9: 1" in (box.label.note or "")  # o degenerado da seed 2 em h+7
    assert series["gbm_quantile|0"].name == "gbm_quantile (seed 0)"


@pytest.mark.unit
def test_mpiw_mismatch_raises(world: ReportWorld, silver: VerifiedSilver) -> None:
    (row,) = world.where(
        "gold_metrics_by_run",
        model="gbm_quantile",
        seed=0,
        horizon=7,
        sample="model_full",
        metric="mpiw",
        level_low=0.25,
    )
    row["value"] = float(row["value"]) + 1e-15  # type: ignore[arg-type]
    with pytest.raises(ReportSourceMismatchError, match="gbm_quantile"):
        sharpness_figure(world.inputs(), silver)


@pytest.mark.unit
def test_sharpness_note(world: ReportWorld, silver: VerifiedSilver) -> None:
    spec = sharpness_figure(world.inputs(), silver).spec
    assert "sharpness só tem sentido sujeito à calibração" in spec.notes


@pytest.mark.unit
def test_sharpness_returns_excluded_degenerate_counts(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    excluded = sharpness_figure(world.inputs(), silver).excluded_degenerate
    for (model, seed, h), count in DEGENERATE_POINTS.items():
        for pair in ((0.1, 0.9), (0.25, 0.75)):
            assert excluded[degenerate_key(model, seed, h, pair)] == count
    assert excluded[degenerate_key("gbm_quantile", 0, 1, (0.1, 0.9))] == 0
    assert not any(key.startswith("baseline_zero_return|") for key in excluded)
    assert "tft_quantile|1|h1|0.1-0.9" in excluded


@pytest.mark.unit
def test_point_forecast_model_omitted_and_declared(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    """Baseline pontual do silver sem linha picp/mpiw no gold: fora das caixas, declarado
    na legenda (nota) e no registro (`omitted_models`)."""
    assert any(run.model == "baseline_zero_return" for run in silver.runs)
    assembly = sharpness_figure(world.inputs(), silver)
    for horizon in (1, 7):
        series = _panel(assembly.spec, f"h{horizon}")
        assert not any(sid.startswith("baseline_zero_return") for sid in series)
        assert "gbm_quantile|0" in series
    assert set(assembly.omitted_models) == {"baseline_historical_mean", "baseline_zero_return"}
    for model in assembly.omitted_models:
        assert omitted_model_note(model) in assembly.spec.notes


@pytest.mark.unit
def test_partial_interval_rows_still_raise(world: ReportWorld, silver: VerifiedSilver) -> None:
    """Modelo com alguma linha de intervalo e um par faltando: recusa (fail-closed)."""
    rows = world.rows["gold_metrics_by_run"]
    world.rows["gold_metrics_by_run"] = [
        row
        for row in rows
        if not (
            row["model"] == "gbm_quantile"
            and row["sample"] == "model_full"
            and row["metric"] == "mpiw"
            and row["horizon"] == 7  # noqa: PLR2004
            and row["level_low"] == 0.25  # noqa: PLR2004
        )
    ]
    with pytest.raises(ReportSourceMismatchError, match="gbm_quantile"):
        sharpness_figure(world.inputs(), silver)


# ---------------------------------------------------------------------------- fan chart


@pytest.mark.unit
def test_uses_first_seed_of_revision_only(world: ReportWorld, silver: VerifiedSilver) -> None:
    assembly = fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS)
    realized = _panel(assembly.spec, "h1")["realized"]
    full = _full(world, silver, _CANDIDATE, 1, 1)
    assert realized.x == full.target_timestamps


@pytest.mark.unit
def test_cohort_seeds_differ_from_revision_raises(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    with pytest.raises(ReportSourceMismatchError, match="seeds"):
        fan_chart_figure(world.inputs(), silver, (2, 1))


@pytest.mark.unit
def test_first_seed_without_predictions_raises_no_fallback(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    without = VerifiedSilver(
        runs=silver.runs,
        records=tuple(r for r in silver.records if not (r.model == _CANDIDATE and r.seed == 1)),
        realized=silver.realized,
        units=silver.units,
        split_fingerprints=silver.split_fingerprints,
    )
    with pytest.raises(ReportSourceMismatchError, match="seed 1"):
        fan_chart_figure(world.inputs(), without, CANDIDATE_SEEDS)


@pytest.mark.unit
def test_bands_are_value_guardrail_symmetric_pairs_and_median(
    world: ReportWorld, silver: VerifiedSilver
) -> None:
    series = _panel(fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).spec, "h7")
    full = _full(world, silver, _CANDIDATE, 1, 7)
    band = series["band|0,1-0,9"]
    assert band.kind is SeriesKind.BAND
    assert band.low == tuple(full.scored_values(i)[0] for i in range(full.n_points))
    assert band.high == tuple(full.scored_values(i)[4] for i in range(full.n_points))
    assert series["median"].y == tuple(full.scored_values(i)[2] for i in range(full.n_points))
    assert set(series) >= {"band|0,25-0,75", "realized"}


@pytest.mark.unit
def test_realized_from_series_realized(world: ReportWorld, silver: VerifiedSilver) -> None:
    series = _panel(fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).spec, "h1")
    assert series["realized"].y == _full(world, silver, _CANDIDATE, 1, 1).realized


@pytest.mark.unit
def test_fold_cuts_marked(world: ReportWorld, silver: VerifiedSilver) -> None:
    series = _panel(fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).spec, "h1")
    folds = {
        r.target_timestamp: r.fold
        for r in silver.records
        if r.model == _CANDIDATE and r.seed == 1 and r.horizon == 1
    }
    targets = sorted(folds)
    expected = tuple(t for prev, t in itertools.pairwise(targets) if folds[t] != folds[prev])
    assert expected
    assert series["fold_cuts"].x == expected


@pytest.mark.unit
def test_legend_names_the_seed(world: ReportWorld, silver: VerifiedSilver) -> None:
    spec = fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).spec
    note = fan_chart_seed_note(1)
    assert note == "seed 1, ilustrativa; as métricas usam a média entre seeds"
    assert note in spec.notes
    assert all(p.label.note == note for p in spec.panels)


@pytest.mark.unit
def test_never_mean_of_quantiles_across_seeds(world: ReportWorld, silver: VerifiedSilver) -> None:
    spec = fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).spec
    collapsed = 0.001  # o valor dos pontos colapsados de propósito, igual nas duas seeds
    seed_two = {
        r.value_guardrail
        for r in silver.records
        if r.model == _CANDIDATE and r.seed == 2  # noqa: PLR2004
    } - {collapsed}
    drawn = {
        value
        for panel in spec.panels
        for series in panel.series
        if series.series_id != "realized"
        for values in (series.y, series.low or (), series.high or ())
        for value in values
        if value is not None
    }
    assert drawn and not drawn & seed_two


@pytest.mark.unit
def test_silver_units_of_each_figure(world: ReportWorld, silver: VerifiedSilver) -> None:
    assert dict(sharpness_figure(world.inputs(), silver).silver_units) == dict(silver.units)
    fan = fan_chart_figure(world.inputs(), silver, CANDIDATE_SEEDS).silver_units
    seed_one = {r.run_id for r in silver.runs if r.model == _CANDIDATE and r.seed == 1}
    expected = {
        key
        for key in silver.units
        if key.startswith(("dim_run|", "realized|")) or key.split("|")[1] in seed_one
    }
    assert set(fan) == expected
    assert all(not key.startswith("fact_oos_predictions|gbm") for key in fan)
