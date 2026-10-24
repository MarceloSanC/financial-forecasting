"""Figuras de inferência e atribuição (Stage 8.3, Task 07; A1, A5, A6, A7, A16).

DM candidato x comparadores, d_t + ACF, importância por família de H3 e pesos da VSN,
montados sobre o mundo julgado sintético de `_report_inputs` (fakes discriminantes).
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGenerationCorruptError,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_CATALOG,
    FigureSpec,
    PanelScope,
    ReportSourceMismatchError,
    SeriesKind,
    SeriesSpec,
    StatusLabel,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    dm_figure,
    h3_figure,
    loss_differential_figure,
    vsn_figure,
)
from tests.unit.features.evaluation._report_inputs import (
    CANDIDATE_IS_MODEL_A,
    FOLDS,
    TARGETS,
    ReportWorld,
    make_world,
)

_CANDIDATE = "tft_quantile"
_FAMILIES = ("price", "technical", "sentiment", "fundamental")


@pytest.fixture
def world() -> ReportWorld:
    return make_world()


def _series(spec: FigureSpec, panel_id: str) -> dict[str, SeriesSpec]:
    panel = next(p for p in spec.panels if p.panel_id == panel_id)
    return {s.series_id: s for s in panel.series}


def _dm_row(world: ReportWorld, h: int, estimator: str, comparator: str) -> dict[str, object]:
    found = world.where(
        "gold_dm_results", horizon=h, variance_estimator=estimator, comparator=comparator
    )
    assert len(found) == 1
    return found[0]


# ---------------------------------------------------------------------------------- DM


@pytest.mark.unit
def test_cells_are_horizon_by_family_comparator_only(world: ReportWorld) -> None:
    spec = dm_figure(world.inputs()).spec
    assert [p.panel_id for p in spec.panels] == ["h1", "h7"]
    for panel in spec.panels:
        (cells,) = panel.series
        assert cells.kind is SeriesKind.CELLS
        assert cells.x == world.plan.comparators
        assert _CANDIDATE not in cells.x


@pytest.mark.unit
def test_raw_p_from_rectangular_row_not_bartlett(world: ReportWorld) -> None:
    cells = _series(dm_figure(world.inputs()).spec, "h7")["dm_cells"]
    for comparator, raw in zip(cells.x, cells.y, strict=True):
        assert raw == _dm_row(world, 7, "rectangular", str(comparator))["p_value"]
        assert raw != _dm_row(world, 7, "bartlett", str(comparator))["p_value"]


@pytest.mark.unit
def test_adjusted_and_rejected_divergent_from_scorecard_raises(world: ReportWorld) -> None:
    entry = next(
        e
        for e in world.horizon("profile", 1)["dm"]  # type: ignore[attr-defined]
        if e["comparator"] == "baseline_ar1" and e["estimator"] == "rectangular"
    )
    entry["rejected"] = not entry["rejected"]
    with pytest.raises(ReportSourceMismatchError, match="baseline_ar1"):
        dm_figure(world.inputs())
    entry["rejected"] = not entry["rejected"]
    entry["adjusted_p_value"] += 0.01
    with pytest.raises(ReportSourceMismatchError, match="scorecard"):
        dm_figure(world.inputs())


@pytest.mark.unit
def test_missing_scorecard_dm_entry_raises(world: ReportWorld) -> None:
    profile = world.horizon("profile", 7)
    profile["dm"] = [
        e
        for e in profile["dm"]  # type: ignore[attr-defined]
        if not (e["comparator"] == "gbm_quantile" and e["estimator"] == "rectangular")
    ]
    with pytest.raises(ReportSourceMismatchError, match="dm"):
        dm_figure(world.inputs())


@pytest.mark.unit
def test_row_label_h2_not_applicable_where_h1_fails(world: ReportWorld) -> None:
    spec = dm_figure(world.inputs()).spec
    assert _series(spec, "h1")["dm_cells"].label.status is StatusLabel.CONFIRMATORY
    assert (
        _series(spec, "h7")["dm_cells"].label.status
        is StatusLabel.DESCRIPTIVE_PROFILE_H2_NOT_APPLICABLE
    )
    assert spec.panels[1].label.status is StatusLabel.DESCRIPTIVE_PROFILE_H2_NOT_APPLICABLE


@pytest.mark.unit
def test_cell_text_has_raw_p_and_holm_decision(world: ReportWorld) -> None:
    cells = _series(dm_figure(world.inputs()).spec, "h1")["dm_cells"]
    for comparator, text in zip(cells.x, cells.text or (), strict=True):
        row = _dm_row(world, 1, "rectangular", str(comparator))
        decision = "rejeita" if row["rejected"] else "não rejeita"
        assert text == (
            f"p bruto = {row['p_value']:.3g}; Holm {decision} "
            f"(p ajustado = {row['adjusted_p_value']:.3g})"
        )


# --------------------------------------------------------------------------------- d_t


def _differentials(world: ReportWorld, h: int, comparator: str) -> list[float]:
    rows = [
        r
        for r in world.rows["gold_loss_differentials"]
        if r["horizon"] == h and comparator in (r["model_a"], r["model_b"])
    ]
    return [
        float(r["differential"]) for r in sorted(rows, key=lambda r: str(r["target_timestamp"]))
    ]  # type: ignore[arg-type]


@pytest.mark.unit
def test_sign_flipped_when_candidate_is_model_b(world: ReportWorld) -> None:
    comparator = "baseline_historical_mean"
    assert comparator not in CANDIDATE_IS_MODEL_A
    drawn = _series(loss_differential_figure(world.inputs()).spec, "h1_d_t")[f"d_t|{comparator}"]
    assert drawn.y == tuple(-d for d in _differentials(world, 1, comparator))
    assert drawn.x == TARGETS


@pytest.mark.unit
def test_sign_kept_when_candidate_is_model_a(world: ReportWorld) -> None:
    comparator = "baseline_ar1"
    assert comparator in CANDIDATE_IS_MODEL_A
    drawn = _series(loss_differential_figure(world.inputs()).spec, "h7_d_t")[f"d_t|{comparator}"]
    assert drawn.y == tuple(_differentials(world, 7, comparator))


@pytest.mark.unit
def test_only_candidate_family_pairs(world: ReportWorld) -> None:
    extra = dict(world.rows["gold_loss_differentials"][0])
    extra.update(model_a="baseline_ar1", model_b="gbm_quantile")
    world.rows["gold_loss_differentials"].append(extra)
    spec = loss_differential_figure(world.inputs()).spec
    ids = {s.series_id for s in spec.panels[0].series}
    assert ids == {f"d_t|{c}" for c in world.plan.comparators} | {"fold_cuts"}


@pytest.mark.unit
def test_missing_pair_raises(world: ReportWorld) -> None:
    world.rows["gold_differential_acf"] = [
        r
        for r in world.rows["gold_differential_acf"]
        if "gbm_quantile" not in (r["model_a"], r["model_b"])
    ]
    with pytest.raises(ReportSourceMismatchError, match="gbm_quantile"):
        loss_differential_figure(world.inputs())


@pytest.mark.unit
def test_acf_stems_from_gold_acf_by_lag(world: ReportWorld) -> None:
    stems = _series(loss_differential_figure(world.inputs()).spec, "h7_acf")[
        "acf|baseline_ewma_vol"
    ]
    rows = sorted(
        (
            r
            for r in world.rows["gold_differential_acf"]
            if r["horizon"] == 7  # noqa: PLR2004
            and "baseline_ewma_vol" in (r["model_a"], r["model_b"])
        ),
        key=lambda r: int(r["lag"]),  # type: ignore[call-overload]
    )
    assert stems.kind is SeriesKind.STEMS
    assert stems.x == (1.0, 2.0, 3.0)
    assert stems.y == tuple(r["acf"] for r in rows)


@pytest.mark.unit
def test_acf_band_absent(world: ReportWorld) -> None:
    spec = loss_differential_figure(world.inputs()).spec
    assert spec.omissions == ("faixa de confiança da ACF (±1,96/√n não persistida)",)
    for panel in spec.panels:
        for series in panel.series:
            assert series.low is None and series.high is None
            assert series.kind is not SeriesKind.BAND


@pytest.mark.unit
def test_fold_cuts_from_differential_fold(world: ReportWorld) -> None:
    cuts = _series(loss_differential_figure(world.inputs()).spec, "h1_d_t")["fold_cuts"]
    expected = tuple(TARGETS[i] for i in range(1, len(FOLDS)) if FOLDS[i] != FOLDS[i - 1])
    assert cuts.kind is SeriesKind.VLINES
    assert cuts.x == expected


# ---------------------------------------------------------------------------------- H3


@pytest.mark.unit
def test_if_h_is_aggregate_row_seed_and_permutation_null(world: ReportWorld) -> None:
    series = _series(h3_figure(world.inputs()).spec, "h7")
    for method in ("loco", "permutation"):
        bars = series[f"{method}|aggregate"]
        assert bars.x == _FAMILIES
        expected = tuple(
            world.where(
                "gold_h3_importance",
                method=method,
                family=family,
                horizon=7,
                seed=None,
                permutation_index=None,
            )[0]["importance"]
            for family in _FAMILIES
        )
        assert bars.y == expected


@pytest.mark.unit
def test_per_seed_profiles_both_methods_per_permutation_only_permutation(
    world: ReportWorld,
) -> None:
    series = _series(h3_figure(world.inputs()).spec, "h1")
    assert {"loco|per_seed", "permutation|per_seed", "permutation|per_permutation"} <= set(series)
    assert "loco|per_permutation" not in series
    per_perm = series["permutation|per_permutation"]
    row = world.where(
        "gold_h3_importance",
        method="permutation",
        family="sentiment",
        horizon=1,
        seed=None,
        permutation_index=1,
    )[0]
    assert row["importance"] in per_perm.y
    assert "permutação 1" in (per_perm.text or ())


@pytest.mark.unit
def test_shares_delta_interval_from_h3_shares(world: ReportWorld) -> None:
    delta = _series(h3_figure(world.inputs()).spec, "h1_vs_h7")["permutation|delta"]
    row = world.where("gold_h3_shares", method="permutation", family="technical")[0]
    index = delta.x.index("technical")
    assert (delta.y[index], delta.low[index], delta.high[index]) == (  # type: ignore[index]
        row["delta"],
        row["lower"],
        row["upper"],
    )


@pytest.mark.unit
def test_reading_label_status_from_h3_reading(world: ReportWorld) -> None:
    panel = next(p for p in h3_figure(world.inputs()).spec.panels if p.panel_id == "h1_vs_h7")
    note = panel.label.note or ""
    assert "leitura descritiva [ok]" in note
    assert "heterogênea na permutação = True, na ablação = False" in note


@pytest.mark.unit
def test_reading_note_names_no_agreeing_family_explicitly(world: ReportWorld) -> None:
    """`agreeing_families = ""` (nenhuma concorda) → "nenhuma", nunca "=" sem valor."""
    note = _reading_panel_note(world)
    assert note.endswith("famílias concordantes = nenhuma")


@pytest.mark.unit
def test_reading_note_lists_agreeing_families(world: ReportWorld) -> None:
    (row,) = world.rows["gold_h3_reading"]
    row["agreeing_families"] = "price,technical"
    assert _reading_panel_note(world).endswith("famílias concordantes = price, technical")


@pytest.mark.unit
def test_reading_note_rejects_null_agreeing_families(world: ReportWorld) -> None:
    """NULL não é "nenhuma": geração corrompida, falha explícita (só "" vira "nenhuma")."""
    (row,) = world.rows["gold_h3_reading"]
    row["agreeing_families"] = None
    with pytest.raises(GoldGenerationCorruptError, match="agreeing_families"):
        _reading_panel_note(world)


def _reading_panel_note(world: ReportWorld) -> str:
    panel = next(p for p in h3_figure(world.inputs()).spec.panels if p.panel_id == "h1_vs_h7")
    return panel.label.note or ""


@pytest.mark.unit
def test_h1_h7_side_by_side_and_comparison_panel(world: ReportWorld) -> None:
    spec = h3_figure(world.inputs()).spec
    assert [(p.panel_id, p.scope, p.horizon) for p in spec.panels] == [
        ("h1", PanelScope.HORIZON, 1),
        ("h7", PanelScope.HORIZON, 7),
        ("h1_vs_h7", PanelScope.HORIZON_COMPARISON, None),
    ]


@pytest.mark.unit
def test_h3_note(world: ReportWorld) -> None:
    assert (
        FIGURE_CATALOG["h3_family_importance"].required_notes[0]
        in h3_figure(world.inputs()).spec.notes
    )


@pytest.mark.unit
def test_no_if_or_sf_interval_drawn(world: ReportWorld) -> None:
    spec = h3_figure(world.inputs()).spec
    for panel in spec.panels:
        for series in panel.series:
            if series.series_id.endswith("|delta"):
                assert series.low is not None
            else:
                assert series.low is None and series.high is None, series.series_id


# --------------------------------------------------------------------------------- VSN


@pytest.mark.unit
def test_only_kind_family_rows(world: ReportWorld) -> None:
    (panel,) = vsn_figure(world.inputs()).spec.panels
    (series,) = panel.series
    assert set(series.x) == set(_FAMILIES)
    assert "log_return" not in series.x
    row = world.where("gold_h3_vsn", kind="family", name="price")[0]
    index = series.x.index("price")
    assert (series.y[index], series.low[index], series.high[index]) == (  # type: ignore[index]
        row["p50"],
        row["p10"],
        row["p90"],
    )


@pytest.mark.unit
def test_single_horizon_invariant_panel_with_note(world: ReportWorld) -> None:
    spec = vsn_figure(world.inputs()).spec
    (panel,) = spec.panels
    assert panel.scope is PanelScope.HORIZON_INVARIANT and panel.horizon is None
    assert panel.label.note == "horizonte-invariante"
    assert "horizonte-invariante" in spec.notes


@pytest.mark.unit
@pytest.mark.parametrize("build", [dm_figure, loss_differential_figure, h3_figure, vsn_figure])
def test_omissions_equal_catalog_and_sources_listed(build: object, world: ReportWorld) -> None:
    assembly = build(world.inputs())  # type: ignore[operator]
    assert assembly.spec.omissions == FIGURE_CATALOG[assembly.spec.figure_id].omissions
    assert assembly.sources
    assert dict(assembly.silver_units) == {} and dict(assembly.excluded_degenerate) == {}
