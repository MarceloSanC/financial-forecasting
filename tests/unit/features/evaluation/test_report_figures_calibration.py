"""Figuras de calibração e cobertura (Stage 8.3, Task 06; A1 parcial, A5, A7, A16).

Reliability, quantile score, PICP x MPIW e nativo x conformal montados sobre o mundo
julgado sintético de `_report_inputs` (fakes discriminantes: ler a linha errada do mapa
do D13 muda o valor desenhado).
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    EMPIRICAL_COVERAGE_NOTE,
    FIGURE_CATALOG,
    FigureSpec,
    PanelScope,
    ReportSourceMismatchError,
    SeriesSpec,
    StatusLabel,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    FigureAssembly,
    native_vs_conformal_figure,
    picp_mpiw_figure,
    quantile_score_figure,
    reliability_figure,
)
from tests.unit.features.evaluation._report_inputs import (
    CANDIDATE_SEEDS,
    LEVELS,
    VARIANTS,
    ReportWorld,
    make_world,
)

_CANDIDATE = "tft_quantile"
_LOWER, _UPPER = 0.1, 0.9
_MEDIAN = 0.5


@pytest.fixture
def world() -> ReportWorld:
    return make_world()


def _panel_series(spec: FigureSpec, panel_id: str) -> dict[str, SeriesSpec]:
    panel = next(p for p in spec.panels if p.panel_id == panel_id)
    return {s.series_id: s for s in panel.series}


def _calibration(world: ReportWorld, **match: object) -> dict[str, object]:
    found = world.where("gold_calibration_table", **match)
    assert len(found) == 1, match
    return found[0]


def _gate(model: str, kind: str, level: float, **extra: object) -> dict[str, object]:
    return {
        "model": model,
        "sample": "model_full",
        "kind": kind,
        "level_low": level,
        "level_high": None,
        "includes_degenerate": False,
        "dgt_offset": None,
        "dgt_step": None,
        **extra,
    }


# --------------------------------------------------------------------------- reliability


@pytest.mark.unit
def test_confirmatory_tails_equal_verdict_h1_bands_and_profile_power(world: ReportWorld) -> None:
    spec = reliability_figure(world.inputs()).spec
    series = _panel_series(spec, "h1")
    h1 = world.horizon("verdict", 1)["h1"]
    lower, upper = h1["lower_band"], h1["upper_band"]  # type: ignore[index]
    gate_lower, gate_upper = series["gate_lower_tail"], series["gate_upper_tail"]
    assert gate_lower.x == (_LOWER,)
    assert gate_lower.y == (lower["estimate"],)
    assert (gate_lower.low, gate_lower.high) == ((lower["lower"],), (lower["upper"],))
    assert gate_upper.y == (1.0 - upper["estimate"],)
    power = world.horizon("profile", 1)["power"]
    note = gate_lower.label.note or ""
    assert "banda 0,975 do gate" in note
    for scenario in power:  # type: ignore[attr-defined]
        assert f"{scenario['label']} ({scenario['role']}): P(reprovar) = " in note
        assert f"{scenario['failure_probability']:.3f}" in note


@pytest.mark.unit
def test_gate_tails_confirmatory_in_every_horizon(world: ReportWorld) -> None:
    # CC2-1 (doc §2.3/§6.2): o gate H1 é confirmatório passe ou reprove; H1 passa em h+1
    # e reprova em h+7 no mundo padrão, e a nota diz o desfecho.
    spec = reliability_figure(world.inputs()).spec
    for kind in ("gate_lower_tail", "gate_upper_tail"):
        assert _panel_series(spec, "h1")[kind].label.status is StatusLabel.CONFIRMATORY
        assert _panel_series(spec, "h7")[kind].label.status is StatusLabel.CONFIRMATORY
        assert (_panel_series(spec, "h1")[kind].label.note or "").startswith("H1 passa em h+1")
        assert (_panel_series(spec, "h7")[kind].label.note or "").startswith("H1 reprova em h+7")
    confirmatory = [
        (p.panel_id, s.series_id)
        for p in spec.panels
        for s in p.series
        if s.label.status is StatusLabel.CONFIRMATORY
    ]
    assert confirmatory == [
        ("h1", "gate_lower_tail"),
        ("h1", "gate_upper_tail"),
        ("h7", "gate_lower_tail"),
        ("h7", "gate_upper_tail"),
    ]


@pytest.mark.unit
def test_candidate_descriptive_is_ratio_of_mean_counts_of_calibration_95(
    world: ReportWorld,
) -> None:
    spec = reliability_figure(world.inputs()).spec
    mean = _panel_series(spec, "h7")["candidate_seed_mean"]
    entries = world.horizon("profile", 7)["calibration_95"]
    expected = []
    for level in mean.x:
        kind = "lower_tail" if level < 0.5 else "upper_tail"  # type: ignore[operator]  # noqa: PLR2004
        entry = next(
            e
            for e in entries  # type: ignore[attr-defined]
            if all(e[k] == v for k, v in _gate(_CANDIDATE, kind, level).items())  # type: ignore[arg-type]
        )
        ratio = entry["mean_violations"] / entry["mean_observed"]
        expected.append(ratio if kind == "lower_tail" else 1.0 - ratio)
    assert mean.y == tuple(expected)
    assert mean.label.status is StatusLabel.DESCRIPTIVE_PROFILE


@pytest.mark.unit
def test_candidate_per_seed_points_from_calibration_table_95(world: ReportWorld) -> None:
    spec = reliability_figure(world.inputs()).spec
    points = _panel_series(spec, "h1")["candidate_per_seed"]
    expected = []
    for seed in CANDIDATE_SEEDS:
        for level in (0.1, 0.25, 0.75, 0.9):
            kind = "lower_tail" if level < 0.5 else "upper_tail"  # noqa: PLR2004
            row = _calibration(
                world, **_gate(_CANDIDATE, kind, level, seed=seed, horizon=1, band_level=0.95)
            )
            rate = row["violation_rate"]
            expected.append(rate if kind == "lower_tail" else 1.0 - rate)  # type: ignore[operator]
    assert points.y == tuple(expected)
    assert points.low is None and points.high is None  # banda do candidato por seed omitida


@pytest.mark.unit
def test_baseline_and_gbm_wilson_from_calibration_table_gate_filter_95(
    world: ReportWorld,
) -> None:
    series = _panel_series(reliability_figure(world.inputs()).spec, "h7")
    for model, seed in (("baseline_ar1", None), ("gbm_quantile", 0)):
        drawn = series[f"{model}|{seed}"]
        row = _calibration(
            world, **_gate(model, "lower_tail", 0.1, seed=seed, horizon=7, band_level=0.95)
        )
        assert drawn.y[0] == row["wilson_estimate"]
        assert (drawn.low[0], drawn.high[0]) == (row["wilson_lower"], row["wilson_upper"])  # type: ignore[index]


@pytest.mark.unit
def test_upper_tail_drawn_as_complement_with_swapped_band(world: ReportWorld) -> None:
    series = _panel_series(reliability_figure(world.inputs()).spec, "h1")
    drawn = series["gbm_quantile|0"]
    index = drawn.x.index(0.9)
    row = _calibration(
        world, **_gate("gbm_quantile", "upper_tail", 0.9, seed=0, horizon=1, band_level=0.95)
    )
    assert drawn.y[index] == 1.0 - row["wilson_estimate"]  # type: ignore[operator]
    assert drawn.low[index] == 1.0 - row["wilson_upper"]  # type: ignore[index, operator]
    assert drawn.high[index] == 1.0 - row["wilson_lower"]  # type: ignore[index, operator]


@pytest.mark.unit
def test_tau_half_absent(world: ReportWorld) -> None:
    spec = reliability_figure(world.inputs()).spec
    drawn = [s.x for p in spec.panels for s in p.series if s.kind.value != "reference"]
    assert all(_MEDIAN not in x for x in drawn)


@pytest.mark.unit
def test_gate_filter_bound_to_h1_mean_observed(world: ReportWorld) -> None:
    world.horizon("verdict", 7)["h1"]["mean_observed"] += 1.0  # type: ignore[index, operator]
    with pytest.raises(ReportSourceMismatchError, match="mean_observed"):
        reliability_figure(world.inputs())


@pytest.mark.unit
def test_reliability_note(world: ReportWorld) -> None:
    spec = reliability_figure(world.inputs()).spec
    assert "banda binomial anti-conservadora em h+7 e sob agrupamento" in spec.notes


@pytest.mark.unit
def test_missing_calibration_row_raises(world: ReportWorld) -> None:
    rows = world.rows["gold_calibration_table"]
    world.rows["gold_calibration_table"] = [
        r for r in rows if not (r["model"] == "baseline_ar1" and r["horizon"] == 1)
    ]
    with pytest.raises(ReportSourceMismatchError, match="gold_calibration_table"):
        reliability_figure(world.inputs())


# ------------------------------------------------------------------------ quantile score


@pytest.mark.unit
def test_points_from_metrics_by_run_common_pinball_per_seed(world: ReportWorld) -> None:
    series = _panel_series(quantile_score_figure(world.inputs()).spec, "h7")
    for model, seed in ((_CANDIDATE, 2), ("baseline_zero_return", None), ("gbm_quantile", 0)):
        drawn = series[f"{model}|{seed}"]
        assert drawn.x == LEVELS
        expected = tuple(
            world.where(
                "gold_metrics_by_run",
                model=model,
                seed=seed,
                horizon=7,
                sample="common",
                metric="pinball",
                level_low=level,
            )[0]["value"]
            for level in LEVELS
        )
        assert drawn.y == expected


@pytest.mark.unit
def test_candidate_mean_min_max_from_profile_descriptors(world: ReportWorld) -> None:
    drawn = _panel_series(quantile_score_figure(world.inputs()).spec, "h1")["candidate_seed_mean"]
    descriptors = world.horizon("profile", 1)["descriptors"]
    entry = next(
        d
        for d in descriptors  # type: ignore[attr-defined]
        if d["model"] == _CANDIDATE
        and d["sample"] == "common"
        and d["metric"] == "pinball"
        and d["level_low"] == 0.25  # noqa: PLR2004
    )
    index = drawn.x.index(0.25)
    assert (drawn.y[index], drawn.low[index], drawn.high[index]) == (  # type: ignore[index]
        entry["mean"],
        entry["minimum"],
        entry["maximum"],
    )


# ---------------------------------------------------------------------------- PICP x MPIW


@pytest.mark.unit
def test_one_point_per_model_pair_seed_common(world: ReportWorld) -> None:
    series = _panel_series(picp_mpiw_figure(world.inputs()).spec, "h1")
    candidate = series[_CANDIDATE]
    assert len(candidate.x) == len(CANDIDATE_SEEDS) * 2
    picp = world.where(
        "gold_metrics_by_run",
        model=_CANDIDATE,
        seed=2,
        horizon=1,
        sample="common",
        metric="picp",
        level_low=0.25,
    )[0]["value"]
    mpiw = world.where(
        "gold_metrics_by_run",
        model=_CANDIDATE,
        seed=2,
        horizon=1,
        sample="common",
        metric="mpiw",
        level_low=0.25,
    )[0]["value"]
    assert (mpiw, picp) in set(zip(candidate.x, candidate.y, strict=True))
    assert len(series["baseline_ar1"].x) == 2  # noqa: PLR2004 — sem seed, dois pares


@pytest.mark.unit
def test_candidate_dispersion_and_mean_from_descriptors(world: ReportWorld) -> None:
    series = _panel_series(picp_mpiw_figure(world.inputs()).spec, "h7")
    mean = series["candidate_seed_mean|0,1-0,9"]
    descriptors = world.horizon("profile", 7)["descriptors"]

    def entry(metric: str) -> dict[str, object]:
        return next(
            d
            for d in descriptors  # type: ignore[attr-defined]
            if d["model"] == _CANDIDATE
            and d["sample"] == "common"
            and d["metric"] == metric
            and d["level_low"] == 0.1  # noqa: PLR2004
        )

    assert mean.x == (entry("mpiw")["mean"],)
    assert (mean.y, mean.low, mean.high) == (
        (entry("picp")["mean"],),
        (entry("picp")["minimum"],),
        (entry("picp")["maximum"],),
    )


@pytest.mark.unit
def test_nominal_reference_line_1_minus_2_tau_low(world: ReportWorld) -> None:
    series = _panel_series(picp_mpiw_figure(world.inputs()).spec, "h1")
    assert series["nominal|0,1-0,9"].y == (pytest.approx(0.8),)
    assert series["nominal|0,25-0,75"].y == (0.5,)


@pytest.mark.unit
def test_picp_mpiw_note(world: ReportWorld) -> None:
    spec = picp_mpiw_figure(world.inputs()).spec
    assert (
        "o gráfico não ordena modelos — mais estreito só é melhor com cobertura igual" in spec.notes
    )


# ------------------------------------------------------------------- nativo vs. conformal


def _conformal(world: ReportWorld, **match: object) -> dict[str, object]:
    found = world.where("gold_conformal_coverage", **match)
    assert len(found) == 1, match
    return found[0]


@pytest.mark.unit
def test_conformal_rows_band_095_both_variants_seed_null_and_per_seed(world: ReportWorld) -> None:
    series = _panel_series(native_vs_conformal_figure(world.inputs()).spec, "h1_cobertura")
    for variant in VARIANTS:
        mean = series[f"conformal|{variant}|seed_mean"]
        row = _conformal(
            world,
            horizon=1,
            variant=variant,
            kind="upper_tail",
            lower_level=0.25,
            upper_level=0.75,
            seed=None,
            band_level=0.95,
        )
        index = mean.x.index("cauda 0,75")
        assert mean.y[index] == row["coverage"]
        assert (mean.low[index], mean.high[index]) == (row["wilson_lower"], row["wilson_upper"])  # type: ignore[index]
        per_seed = series[f"conformal|{variant}|per_seed"]
        seed_row = _conformal(
            world,
            horizon=1,
            variant=variant,
            kind="upper_tail",
            lower_level=0.25,
            upper_level=0.75,
            seed=2,
            band_level=0.95,
        )
        assert seed_row["coverage"] in per_seed.y


@pytest.mark.unit
def test_native_from_calibration_model_full_not_degenerate(world: ReportWorld) -> None:
    series = _panel_series(native_vs_conformal_figure(world.inputs()).spec, "h7_cobertura")
    native = series["native|per_seed"]
    row = _calibration(
        world, **_gate(_CANDIDATE, "upper_tail", 0.9, seed=1, horizon=7, band_level=0.95)
    )
    index = native.text.index("cauda 0,9, seed 1")  # type: ignore[union-attr]
    rate = row["n_violations"] / row["n_observed"]  # type: ignore[operator]
    assert native.y[index] == 1.0 - rate
    assert native.low[index] == 1.0 - row["wilson_upper"]  # type: ignore[index, operator]


@pytest.mark.unit
def test_native_seed_mean_ratio_from_calibration_95_profile(world: ReportWorld) -> None:
    series = _panel_series(native_vs_conformal_figure(world.inputs()).spec, "h1_cobertura")
    mean = series["native|seed_mean"]
    entry = next(
        e
        for e in world.horizon("profile", 1)["calibration_95"]  # type: ignore[attr-defined]
        if all(e[k] == v for k, v in _gate(_CANDIDATE, "lower_tail", 0.25).items())
    )
    assert mean.y[mean.x.index("cauda 0,25")] == entry["mean_violations"] / entry["mean_observed"]
    assert mean.low is None  # Wilson do nativo na média: omissão declarada


@pytest.mark.unit
def test_native_picp_mpiw_from_metrics_model_full(world: ReportWorld) -> None:
    spec = native_vs_conformal_figure(world.inputs()).spec
    width = _panel_series(spec, "h1_largura")["native|per_seed"]
    mpiw = world.where(
        "gold_metrics_by_run",
        model=_CANDIDATE,
        seed=1,
        horizon=1,
        sample="model_full",
        metric="mpiw",
        level_low=0.1,
    )[0]["value"]
    assert width.y[width.text.index("MPIW 0,1-0,9, seed 1")] == mpiw  # type: ignore[union-attr]
    coverage = _panel_series(spec, "h1_cobertura")["native|per_seed"]
    picp = world.where(
        "gold_metrics_by_run",
        model=_CANDIDATE,
        seed=2,
        horizon=1,
        sample="model_full",
        metric="picp",
        level_low=0.25,
    )[0]["value"]
    assert coverage.y[coverage.text.index("PICP 0,25-0,75, seed 2")] == picp  # type: ignore[union-attr]

    # CC2-3: a média nativa sai dos descritores model_full (a máscara do conformal), não
    # dos common — no fake os dois diferem, então ler a amostra errada muda o ponto.
    def descriptor(sample: str, metric: str, low: float) -> object:
        return next(
            d["mean"]
            for d in world.horizon("profile", 1)["descriptors"]  # type: ignore[attr-defined]
            if d["model"] == _CANDIDATE
            and d["sample"] == sample
            and d["metric"] == metric
            and d["level_low"] == low
        )

    width_mean = _panel_series(spec, "h1_largura")["native|seed_mean"]
    coverage_mean = _panel_series(spec, "h1_cobertura")["native|seed_mean"]
    mpiw_mean = width_mean.y[width_mean.x.index("MPIW 0,1-0,9")]
    picp_mean = coverage_mean.y[coverage_mean.x.index("PICP 0,25-0,75")]
    assert mpiw_mean == descriptor("model_full", "mpiw", 0.1)
    assert mpiw_mean != descriptor("common", "mpiw", 0.1)
    assert picp_mean == descriptor("model_full", "picp", 0.25)
    assert picp_mean != descriptor("common", "picp", 0.25)


@pytest.mark.unit
def test_n_evaluated_differs_from_n_observed_raises(world: ReportWorld) -> None:
    row = _conformal(
        world,
        horizon=7,
        variant=VARIANTS[0],
        kind="lower_tail",
        lower_level=0.1,
        upper_level=0.9,
        seed=1,
        band_level=0.95,
    )
    row["n_evaluated"] = int(row["n_evaluated"]) + 1  # type: ignore[call-overload]
    with pytest.raises(ReportSourceMismatchError, match="n_evaluated"):
        native_vs_conformal_figure(world.inputs())


@pytest.mark.unit
def test_every_panel_has_empirical_coverage_label(world: ReportWorld) -> None:
    spec = native_vs_conformal_figure(world.inputs()).spec
    assert len(spec.panels) == 4  # noqa: PLR2004 — cobertura e largura por horizonte
    assert all(p.label.note == EMPIRICAL_COVERAGE_NOTE for p in spec.panels)
    assert EMPIRICAL_COVERAGE_NOTE in spec.notes


# -------------------------------------------------------------------------------- comuns

_BUILDERS = (
    reliability_figure,
    quantile_score_figure,
    picp_mpiw_figure,
    native_vs_conformal_figure,
)


@pytest.mark.unit
@pytest.mark.parametrize("build", _BUILDERS)
def test_one_panel_per_horizon_never_mixed(build: object, world: ReportWorld) -> None:
    assembly: FigureAssembly = build(world.inputs())  # type: ignore[operator]
    assert all(p.scope is PanelScope.HORIZON for p in assembly.spec.panels)
    assert {p.horizon for p in assembly.spec.panels} == {1, 7}
    assert assembly.sources


@pytest.mark.unit
@pytest.mark.parametrize("build", _BUILDERS)
def test_omissions_equal_catalog_and_no_series_draws_omitted_element(
    build: object, world: ReportWorld
) -> None:
    spec = build(world.inputs()).spec  # type: ignore[operator]
    assert spec.omissions == FIGURE_CATALOG[spec.figure_id].omissions
    for panel in spec.panels:
        for series in panel.series:
            assert "beta" not in series.series_id.lower()
            if spec.figure_id == "reliability_diagram" and series.kind.value != "reference":
                assert 0.5 not in series.x  # noqa: PLR2004 — τ = 0,5 é omissão só aqui
            if (
                series.model == _CANDIDATE
                and series.series_id
                in {
                    "candidate_seed_mean",
                    "candidate_per_seed",
                }
                and spec.figure_id == "reliability_diagram"
            ):
                assert series.low is None and series.high is None
