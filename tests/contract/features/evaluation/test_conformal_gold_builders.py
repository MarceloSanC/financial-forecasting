"""Contrato dos builders das tabelas gold conformais (Stage 7.2, Task 18; ADR 7.2.0003 item 7).

Mapeamento puro, conferido célula a célula sobre os relatórios conformais de
`completed_inputs()` (unidades `ok`, `undefined` da montagem e `error` do port, um limite
infinito, uma cobertura `undefined` e a média com uma seed excluída) e sobre insumos
mínimos montados aqui para os casos de borda (não aplicável, zero seeds, uma seed,
folds não inteiros).
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.conformal_corrections import (  # noqa: E501
    ConformalCorrectionsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.conformal_coverage import (  # noqa: E501
    ConformalCoverageGoldBuilder,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_CONFORMAL_COVERAGE,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    ConformalReports,
    ConformalTailRecord,
    ConformalUndefinedCoverage,
    ConformalUnitRecord,
    GoldInputs,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
    ConformalCoverage,
    ConformalCoverageReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from tests.contract.features.evaluation._gold_inputs import (
    CONFORMAL_NEXCP,
    CONFORMAL_SPLIT,
    completed_inputs,
    completed_inputs_without_conformal,
    samples_of,
)

pytestmark = pytest.mark.contract

Row = Mapping[str, object]
_PAIRS = ((0.1, 0.9), (0.25, 0.75))
_BANDS = completed_inputs().parameters.band_levels


def _corrections(inputs: GoldInputs | None = None) -> tuple[Row, ...]:
    return ConformalCorrectionsGoldBuilder().build(inputs or completed_inputs()).rows


def _coverage(inputs: GoldInputs | None = None) -> tuple[Row, ...]:
    return ConformalCoverageGoldBuilder().build(inputs or completed_inputs()).rows


def _with(reports: ConformalReports) -> GoldInputs:
    return dataclasses.replace(completed_inputs(), conformal_reports=reports)


def _only(rows: tuple[Row, ...], **where: object) -> list[Row]:
    return [row for row in rows if all(row[k] == v for k, v in where.items())]


def test_corrections_rows_cell_by_cell() -> None:
    rows = _corrections()
    units = completed_inputs().conformal_reports.units
    assert len(rows) == 2 * len(units)
    unit = next(
        u
        for u in units
        if (u.fold_raw, u.seed, u.horizon, u.lower_level, u.variant)
        == ("0", 2, 1, 0.25, CONFORMAL_SPLIT)
    )
    [lower] = _only(
        rows,
        fold_raw="0",
        seed=2,
        horizon=1,
        lower_level=0.25,
        variant=CONFORMAL_SPLIT,
        tail="lower",
    )
    tail = unit.tails[0]
    assert {k: lower[k] for k in GOLD_CONFORMAL_CORRECTIONS.read_columns} == {
        "fold": 0,
        "tail_level": 0.25,
        "rho": None,
        "status": "ok",
        "reason": None,
        "n": tail.n,
        "rank": tail.rank,
        "correction": tail.correction,
        "infinite": False,
        "beta_a": tail.beta_a,
        "beta_b": tail.beta_b,
        "beta_mean": tail.beta_mean,
        "beta_sd": tail.beta_sd,
    }
    assert lower["preregistration_ref"] == completed_inputs().preregistration_ref
    # NexCP: sem posto e sem Beta; rho da unidade
    [nexcp] = _only(
        rows,
        fold_raw="0",
        seed=2,
        horizon=1,
        lower_level=0.25,
        variant=CONFORMAL_NEXCP,
        tail="upper",
    )
    assert (nexcp["rank"], nexcp["beta_a"], nexcp["beta_mean"]) == (None, None, None)
    assert nexcp["rho"] == completed_inputs().parameters.conformal_parameters.nexcp_rho  # type: ignore[union-attr]


def test_beta_null_when_l_is_zero() -> None:
    def tail(name: str, level: float) -> ConformalTailRecord:
        return ConformalTailRecord(
            tail=name,
            level=level,
            n=10,
            rank=11,
            correction=math.inf,
            infinite=True,
            beta_a=None,
            beta_b=None,
            beta_mean=None,
            beta_sd=None,
        )

    unit = ConformalUnitRecord(
        fold_index=0,
        fold_raw="0",
        seed=1,
        horizon=1,
        lower_level=0.1,
        upper_level=0.9,
        variant=CONFORMAL_SPLIT,
        rho=None,
        status="ok",
        reason=None,
        tails=(tail("lower", 0.1), tail("upper", 0.9)),
    )
    rows = _corrections(
        _with(ConformalReports(units=(unit,), coverage=(), undefined_coverage=(), seed_means=()))
    )
    assert [(r["rank"], r["beta_a"], r["beta_sd"]) for r in rows] == [(11, None, None)] * 2


def test_infinite_correction_maps_to_null_with_flag() -> None:
    [row] = _only(
        _corrections(),
        fold_raw="0",
        seed=1,
        horizon=1,
        lower_level=0.1,
        variant=CONFORMAL_NEXCP,
        tail="lower",
    )
    assert (row["correction"], row["infinite"], row["status"]) == (None, True, "ok")


def test_non_ok_unit_maps_to_two_tail_rows_with_reason() -> None:
    rows = _only(
        _corrections(), fold_raw="1", seed=2, horizon=2, lower_level=0.1, variant=CONFORMAL_SPLIT
    )
    assert [r["tail"] for r in rows] == ["lower", "upper"]
    for row in rows:
        assert row["status"] == "error"
        assert row["reason"]
        measures = (
            "n",
            "rank",
            "correction",
            "infinite",
            "beta_a",
            "beta_b",
            "beta_mean",
            "beta_sd",
        )
        assert all(row[c] is None for c in measures)


def test_undefined_assembly_unit_expands_to_every_pair_and_variant() -> None:
    rows = _only(_corrections(), fold_raw="x", seed=2, horizon=2)
    keys = {(r["lower_level"], r["variant"], r["tail"]) for r in rows}
    assert keys == {
        (low, variant, tail)
        for low, _ in _PAIRS
        for variant in (CONFORMAL_SPLIT, CONFORMAL_NEXCP)
        for tail in ("lower", "upper")
    }
    assert {(r["status"], r["fold"]) for r in rows} == {("undefined", None)}


def test_coverage_rows_cell_by_cell() -> None:
    rows = _coverage()
    report = next(
        r
        for r in completed_inputs().conformal_reports.coverage
        if (r.seed, r.horizon, r.variant) == (1, 2, CONFORMAL_SPLIT)
    )
    pair = report.per_pair[1]
    tail_rows = _only(
        rows, seed=1, horizon=2, variant=CONFORMAL_SPLIT, kind="lower_tail", lower_level=0.25
    )
    assert [r["band_level"] for r in tail_rows] == list(_BANDS)
    first = tail_rows[0]
    band = pair.lower_tail.bands[0]
    assert (first["nominal"], first["count"], first["coverage"]) == (
        0.25,
        pair.lower_tail.count_at_or_below,
        pair.lower_tail.coverage,
    )
    assert (first["wilson_lower"], first["wilson_upper"], first["wilson_contains_nominal"]) == (
        band.lower,
        band.upper,
        band.contains_nominal,
    )
    assert (first["n_points"], first["n_evaluated"], first["status"]) == (
        report.n_points,
        report.n_evaluated,
        "ok",
    )
    [pair_row] = _only(
        rows, seed=1, horizon=2, variant=CONFORMAL_SPLIT, kind="pair", lower_level=0.25
    )
    assert (
        pair_row["coverage"],
        pair_row["count"],
        pair_row["mpiw"],
        pair_row["crossed_rate"],
    ) == (
        pair.picp,
        pair.covered_count,
        pair.mpiw,
        pair.crossed_rate,
    )
    assert pair_row["nominal"] == pair.nominal
    assert pair_row["band_level"] is None
    [nesting] = _only(rows, seed=1, horizon=2, variant=CONFORMAL_SPLIT, kind="nesting")
    assert (nesting["lower_level"], nesting["band_level"]) == (None, None)
    assert nesting["nesting_violation_rate"] == report.nesting_violation_rate
    # a média entre seeds: seed nula, c̄/n̄ e a média das coberturas lado a lado
    mean = next(
        m
        for m in completed_inputs().conformal_reports.seed_means
        if (m.horizon, m.variant) == (1, CONFORMAL_SPLIT)
    )
    [mean_tail] = _only(
        rows,
        seed=None,
        horizon=1,
        variant=CONFORMAL_SPLIT,
        kind="upper_tail",
        lower_level=0.1,
        band_level=_BANDS[0],
    )
    tail = mean.per_pair[0].upper_tail
    assert (
        mean_tail["coverage"],
        mean_tail["mean_of_seed_coverages"],
        mean_tail["sd_of_seed_coverages"],
    ) == (
        tail.coverage,
        tail.mean_of_seed_coverages,
        tail.sd_of_seed_coverages,
    )
    assert (mean_tail["n_seeds_used"], mean_tail["seeds_excluded"], mean_tail["n_evaluated"]) == (
        2,
        "",
        mean.n_mean,
    )
    [mean_pair] = _only(
        rows, seed=None, horizon=1, variant=CONFORMAL_SPLIT, kind="pair", lower_level=0.1
    )
    mean_values = mean.per_pair[0]
    assert (mean_pair["mean_of_seed_mpiws"], mean_pair["mean_of_seed_crossed_rates"]) == (
        mean_values.mean_of_seed_mpiws,
        mean_values.mean_of_seed_crossed_rates,
    )
    [mean_nesting] = _only(rows, seed=None, horizon=1, variant=CONFORMAL_SPLIT, kind="nesting")
    assert mean_nesting["mean_of_seed_nesting_rates"] == mean.mean_of_seed_nesting_rates


def test_infinite_mpiw_maps_to_null_with_flag() -> None:
    [row] = _only(
        _coverage(), seed=1, horizon=1, variant=CONFORMAL_NEXCP, kind="pair", lower_level=0.1
    )
    assert (row["mpiw"], row["mpiw_infinite"]) == (None, True)
    [mean] = _only(
        _coverage(), seed=None, horizon=1, variant=CONFORMAL_NEXCP, kind="pair", lower_level=0.1
    )
    assert (mean["mpiw"], mean["mpiw_infinite"], mean["mean_of_seed_mpiws"]) == (None, True, None)


def _scaffold_keys(rows: list[Row]) -> set[tuple[object, ...]]:
    return {(r["kind"], r["lower_level"], r["band_level"]) for r in rows}


_SCAFFOLD = {
    *(
        (kind, low, band)
        for low, _ in _PAIRS
        for kind in ("lower_tail", "upper_tail")
        for band in _BANDS
    ),
    *(("pair", low, None) for low, _ in _PAIRS),
    ("nesting", None, None),
}


def test_undefined_coverage_rows_carry_the_reason() -> None:
    rows = _only(_coverage(), seed=2, horizon=2, variant=CONFORMAL_SPLIT)
    assert _scaffold_keys(rows) == _SCAFFOLD
    assert len(rows) == len(_SCAFFOLD)  # sem colisão de chave
    undefined = next(
        u
        for u in completed_inputs().conformal_reports.undefined_coverage
        if u.variant == CONFORMAL_SPLIT
    )
    for row in rows:
        assert (row["status"], row["reason"], row["n_points"]) == (
            "undefined",
            undefined.reason,
            undefined.n_points,
        )
        assert (
            row["coverage"],
            row["count"],
            row["wilson_lower"],
            row["label"],
            row["n_evaluated"],
        ) == (None,) * 5


def _not_applicable_report() -> ConformalCoverageReport:
    samples = samples_of()[0]
    native = samples.full["naive"][0]  # 100 % degenerado
    limits = tuple(
        ConformalPairLimits(low, high, (0.0,) * native.n_points, (0.0,) * native.n_points)
        for low, high in _PAIRS
    )
    report = ConformalCoverage.evaluate(
        ConformalCoverageSeries(seed=1, native=native, variant=CONFORMAL_SPLIT, pairs=limits),
        tolerance=completed_inputs().parameters.degeneracy_tolerance,
        band_levels=_BANDS,
    )
    assert report.applicable is False
    return report


def test_not_applicable_coverage_rows_carry_status_and_null_measures() -> None:
    report = _not_applicable_report()
    rows = list(
        _coverage(
            _with(
                ConformalReports(units=(), coverage=(report,), undefined_coverage=(), seed_means=())
            )
        )
    )
    assert _scaffold_keys(rows) == _SCAFFOLD
    for row in rows:
        assert (row["status"], row["reason"], row["n_evaluated"], row["n_points"]) == (
            "not_applicable",
            None,
            0,
            report.n_points,
        )
        assert (row["coverage"], row["label"], row["wilson_upper"]) == (None, None, None)


def test_seed_mean_with_zero_complete_seeds_rows() -> None:
    mean = ConformalCoverage.seed_mean(
        [], horizon=1, variant=CONFORMAL_SPLIT, expected_seeds=(1, 2), band_levels=_BANDS
    )
    rows = list(
        _coverage(
            _with(
                ConformalReports(units=(), coverage=(), undefined_coverage=(), seed_means=(mean,))
            )
        )
    )
    assert _scaffold_keys(rows) == _SCAFFOLD
    for row in rows:
        assert (row["seed"], row["status"], row["n_seeds_used"], row["seeds_excluded"]) == (
            None,
            "undefined",
            0,
            "1,2",
        )
        assert row["reason"]
        assert (row["coverage"], row["label"]) == (None, None)


def test_seed_mean_with_one_seed_has_null_sd() -> None:
    rows = _only(_coverage(), seed=None, horizon=2, variant=CONFORMAL_NEXCP)
    assert {r["seeds_excluded"] for r in rows} == {"2"}
    assert {r["n_seeds_used"] for r in rows} == {1}
    for row in rows:
        for column in (
            "sd_of_seed_coverages",
            "sd_of_seed_mpiws",
            "sd_of_seed_crossed_rates",
            "sd_of_seed_nesting_rates",
        ):
            assert row[column] is None


def test_non_integer_folds_do_not_collide() -> None:
    def unit(fold: str) -> ConformalUnitRecord:
        nulls = tuple(
            ConformalTailRecord(
                tail=name,
                level=level,
                n=None,
                rank=None,
                correction=None,
                infinite=None,
                beta_a=None,
                beta_b=None,
                beta_mean=None,
                beta_sd=None,
            )
            for name, level in (("lower", 0.1), ("upper", 0.9))
        )
        return ConformalUnitRecord(
            fold_index=None,
            fold_raw=fold,
            seed=1,
            horizon=1,
            lower_level=0.1,
            upper_level=0.9,
            variant=CONFORMAL_SPLIT,
            rho=None,
            status="undefined",
            reason=f"fold {fold!r} is not an integer",
            tails=nulls,
        )

    table = ConformalCorrectionsGoldBuilder().build(
        _with(
            ConformalReports(
                units=(unit("x"), unit("y")), coverage=(), undefined_coverage=(), seed_means=()
            )
        )
    )
    assert [(r["fold_raw"], r["fold"]) for r in table.rows] == [("x", None)] * 2 + [("y", None)] * 2


def test_label_on_every_ok_coverage_row() -> None:
    rows = _coverage()
    assert {r["label"] for r in rows if r["status"] == "ok"} == {EMPIRICAL_COVERAGE_LABEL}
    assert {r["label"] for r in rows if r["status"] != "ok"} == {None}


def test_without_conformal_inputs_both_tables_are_empty() -> None:
    inputs = completed_inputs_without_conformal()
    assert ConformalCorrectionsGoldBuilder().build(inputs).rows == ()
    assert ConformalCoverageGoldBuilder().build(inputs).rows == ()
    assert ConformalCoverageGoldBuilder().build(inputs).name == GOLD_CONFORMAL_COVERAGE.name


def test_undefined_coverage_type_is_distinct_from_reports() -> None:
    assert all(
        isinstance(u, ConformalUndefinedCoverage)
        for u in completed_inputs().conformal_reports.undefined_coverage
    )
