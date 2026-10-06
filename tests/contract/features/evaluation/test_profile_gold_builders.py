"""Mapeamento dos builders de perfil da Stage 6.6 (contract; fora da parametrização).

Cada builder copia célula a célula o relatório de domínio dos `GoldInputs` (forma da r1:
`completed_inputs()`); a forma do r0 (`completed_inputs_r0()`, sem regras de perfil) não
produz linha nas tabelas que dependem das regras (concept I9); os casos de fold
indefinido passam pelo `GoldTable` sem chave repetida (CA3).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.christoffersen_monte_carlo import (  # noqa: E501
    ChristoffersenMonteCarloGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.differential_acf import (  # noqa: E501
    DifferentialAcfGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.differential_breaks import (  # noqa: E501
    DifferentialBreaksGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_profiles import (  # noqa: E501
    DmProfilesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_seed_fraction import (  # noqa: E501
    DmSeedFractionGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.loss_differentials import (  # noqa: E501
    LossDifferentialsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.mcs_block_sensitivity import (  # noqa: E501
    McsBlockSensitivityGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.partial_degeneracy import (  # noqa: E501
    PartialDegeneracyGoldBuilder,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import GoldInputs
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    DmProfiles,
    SubsetStatus,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import UnitStatus
from tests.contract.features.evaluation._gold_inputs import (
    completed_inputs,
    completed_inputs_r0,
    samples_of,
)


def _dm_rows(inputs: GoldInputs) -> list[object]:
    return [
        row
        for profile in inputs.profile_reports
        if profile.dm_profiles is not None
        for row in profile.dm_profiles.rows
    ]


@pytest.mark.contract
def test_dm_profiles_cell_by_cell() -> None:
    inputs = completed_inputs()
    table = DmProfilesGoldBuilder().build(inputs)
    assert len(table.rows) == len(_dm_rows(inputs))
    by_key = {
        (r["horizon"], r["dimension"], r["fold"], r["seed"], r["level"], r["comparator"]): r
        for r in table.rows
    }
    for profile in inputs.profile_reports:
        report = profile.dm_profiles
        assert report is not None
        for unit in report.rows:
            row = by_key[
                (
                    report.horizon,
                    unit.dimension.value,
                    unit.fold,
                    unit.seed,
                    unit.level,
                    unit.comparator,
                )
            ]
            assert row["status"] == unit.status.value
            assert row["undefined_reason"] == unit.undefined_reason
            assert row["n_points"] == unit.n_points
            assert row["rejected"] == unit.rejected
            assert row["alpha"] == report.alpha
            assert row["variance_estimator"] == report.variance_estimator.value
            if unit.status is SubsetStatus.COMPUTED:
                assert unit.result is not None
                assert (row["statistic"], row["p_value"], row["mean_differential"]) == (
                    unit.result.statistic,
                    unit.result.p_value,
                    unit.result.mean_differential,
                )
            else:
                assert row["statistic"] is None


@pytest.mark.contract
def test_dm_seed_fraction_cell_by_cell() -> None:
    inputs = completed_inputs()
    table = DmSeedFractionGoldBuilder().build(inputs)
    expected = [
        (
            profile.horizon,
            f.comparator,
            f.n_seeds,
            f.n_rejecting,
            f.n_undefined,
            f.fraction_rejecting,
        )
        for profile in inputs.profile_reports
        if profile.dm_profiles is not None
        for f in profile.dm_profiles.seed_fractions
    ]
    got = [
        (
            r["horizon"],
            r["comparator"],
            r["n_seeds"],
            r["n_rejecting"],
            r["n_undefined"],
            r["fraction_rejecting"],
        )
        for r in table.rows
    ]
    assert sorted(got, key=repr) == sorted(expected, key=repr)
    assert table.rows


@pytest.mark.contract
@pytest.mark.parametrize("builder", [DmProfilesGoldBuilder(), DmSeedFractionGoldBuilder()])
def test_r0_inputs_build_no_rows(builder: object) -> None:
    assert builder.build(completed_inputs_r0()).rows == ()  # type: ignore[attr-defined]


@pytest.mark.contract
@pytest.mark.parametrize("case", ["mismatch", "not_contiguous"])
def test_undefined_fold_rows_have_unique_keys(case: str) -> None:
    """CA3: `fold_label_mismatch` (fold nulo) e `fold_not_contiguous` passam pelo
    `GoldTable` sem chave repetida."""
    inputs = completed_inputs()
    profiles = []
    for profile, samples in zip(inputs.profile_reports, samples_of(), strict=True):
        if case == "mismatch":
            changed = dataclasses.replace(samples, common_folds=None, fold_mismatch_detail="x")
        else:
            n = samples.n_common
            pattern = ("a",) * (n // 3) + ("b",) * (n // 3) + ("a",) * (n - 2 * (n // 3))
            changed = dataclasses.replace(samples, common_folds=pattern)
        dm = DmProfiles.evaluate(
            changed,
            candidate=inputs.parameters.candidate,
            alpha=inputs.parameters.dm_alpha,
            variance_estimator=inputs.parameters.dm_variance_estimators[0],
        )
        profiles.append(dataclasses.replace(profile, dm_profiles=dm))
    table = DmProfilesGoldBuilder().build(
        dataclasses.replace(inputs, profile_reports=tuple(profiles))
    )
    keys = [
        (r["horizon"], r["dimension"], r["fold"], r["seed"], r["level"], r["comparator"])
        for r in table.rows
    ]
    assert len(keys) == len(set(keys))


@pytest.mark.contract
def test_mcs_block_sensitivity_cell_by_cell() -> None:
    inputs = completed_inputs()
    table = McsBlockSensitivityGoldBuilder().build(inputs)
    assert table.rows
    by_key = {(r["horizon"], r["block_rule"], r["model"]): r for r in table.rows}
    for run in inputs.mcs_block_reports:
        assert run.report is not None
        for rank, elimination in enumerate(run.report.eliminations, start=1):
            row = by_key[(run.horizon, run.block_rule, elimination.model)]
            assert row["block_size"] == run.block_size == run.report.block_size
            assert row["scheme"] == run.scheme.value
            assert row["elimination_rank"] == rank
            assert row["mcs_p_value"] == elimination.mcs_p_value
            assert row["included"] == (elimination.model in run.report.included)
            assert (row["status"], row["undefined_reason"]) == ("computed", None)


@pytest.mark.contract
def test_mcs_block_error_run_maps_to_one_row() -> None:
    inputs = completed_inputs()
    first = inputs.mcs_block_reports[0]
    failed = dataclasses.replace(
        first, status=UnitStatus.ERROR, detail="ValueError: x", report=None
    )
    table = McsBlockSensitivityGoldBuilder().build(
        dataclasses.replace(inputs, mcs_block_reports=(failed,))
    )
    (row,) = table.rows
    assert (row["model"], row["status"], row["undefined_reason"], row["detail"]) == (
        None,
        "error",
        "error",
        "ValueError: x",
    )
    assert row["mcs_p_value"] is None
    assert row["block_size"] == first.block_size


@pytest.mark.contract
def test_christoffersen_monte_carlo_cell_by_cell() -> None:
    inputs = completed_inputs()
    table = ChristoffersenMonteCarloGoldBuilder().build(inputs)
    expected = [row for profile in inputs.profile_reports for row in profile.monte_carlo]
    assert table.rows
    assert len(table.rows) == len(expected)
    assert {r["horizon"] for r in table.rows} == {1}
    by_key = {
        (
            r["model"],
            r["seed"],
            r["sample"],
            r["kind"],
            r["level_low"],
            r["level_high"],
            r["includes_degenerate"],
        ): r
        for r in table.rows
    }
    for unit in expected:
        assert unit.values is not None
        high = unit.levels[1] if len(unit.levels) == 2 else None  # noqa: PLR2004
        row = by_key[
            (
                unit.model,
                unit.seed,
                unit.sample.value,
                unit.kind.value,
                unit.levels[0],
                high,
                unit.includes_degenerate,
            )
        ]
        assert (row["mc_p_uc"], row["mc_p_ind"], row["mc_p_cc"]) == (
            unit.values.p_uc,
            unit.values.p_ind,
            unit.values.p_cc,
        )
        assert (row["uc_status"], row["ind_status"]) == (
            unit.values.uc_status.value,
            unit.values.ind_status.value,
        )
        assert (row["draws"], row["mc_seed"], row["attempts"]) == (
            inputs.parameters.monte_carlo_draws,
            inputs.parameters.monte_carlo_seed,
            unit.values.attempts,
        )
    assert any(r["uc_status"] == "not_applicable" for r in table.rows)  # baseline pontual


@pytest.mark.contract
def test_r0_builds_mc_but_no_block_rows() -> None:
    inputs = completed_inputs_r0()
    assert McsBlockSensitivityGoldBuilder().build(inputs).rows == ()
    assert ChristoffersenMonteCarloGoldBuilder().build(inputs).rows


@pytest.mark.contract
def test_partial_degeneracy_symmetric_rows_are_the_gate_rates() -> None:
    """CA6: linhas `symmetric` = `pair_collapse_rates` do gate, célula a célula."""
    inputs = completed_inputs()
    table = PartialDegeneracyGoldBuilder().build(inputs)
    assert table.rows
    for horizon_report in inputs.horizon_reports:
        for series in horizon_report.series:
            got = [
                (r["level_low"], r["level_high"], r["collapse_rate"])
                for r in table.rows
                if (r["model"], r["seed"], r["horizon"], r["sample"], r["pair_kind"])
                == (
                    series.model,
                    series.seed,
                    horizon_report.horizon,
                    series.sample.value,
                    "symmetric",
                )
            ]
            assert got == list(series.coverage.degeneracy.pair_collapse_rates)
    assert all(r["tolerance"] == inputs.parameters.degeneracy_tolerance for r in table.rows)
    assert any(r["pair_kind"] == "adjacent" for r in table.rows)


@pytest.mark.contract
def test_differential_acf_and_breaks_cell_by_cell() -> None:
    inputs = completed_inputs()
    acf = DifferentialAcfGoldBuilder().build(inputs)
    breaks = DifferentialBreaksGoldBuilder().build(inputs)
    reports = [
        row.report
        for profile in inputs.profile_reports
        for row in profile.stationarity or ()
        if row.report is not None
    ]
    assert reports
    assert len(breaks.rows) == len(reports)
    computed = [r for r in reports if r.statistic is not None]
    assert len(acf.rows) == sum(len(r.acf) for r in computed)
    by_pair = {(r["horizon"], r["model_a"], r["model_b"]): r for r in breaks.rows}
    for report in reports:
        row = by_pair[(report.horizon, *report.pair)]
        assert (row["statistic"], row["p_value"], row["rejected"], row["status"]) == (
            report.statistic,
            report.p_value,
            report.rejected,
            report.status.value,
        )
        assert row["break_target_timestamp"] == report.break_target_timestamp
    first = computed[0]
    got = [
        r["acf"]
        for r in acf.rows
        if (r["horizon"], r["model_a"], r["model_b"]) == (first.horizon, *first.pair)
    ]
    assert got == list(first.acf)


@pytest.mark.contract
def test_loss_differentials_cell_by_cell() -> None:
    inputs = completed_inputs()
    table = LossDifferentialsGoldBuilder().build(inputs)
    expected = sum(
        len(series.values) for profile in inputs.profile_reports for series in profile.differentials
    )
    assert len(table.rows) == expected
    profile = inputs.profile_reports[0]
    series = profile.differentials[0]
    got = [
        (r["target_timestamp"], r["differential"], r["fold"])
        for r in table.rows
        if (r["horizon"], r["model_a"], r["model_b"]) == (profile.horizon, *series.pair)
    ]
    folds = series.folds or (None,) * len(series.values)
    assert got == list(zip(series.target_timestamps, series.values, folds, strict=True))


@pytest.mark.contract
def test_r0_writes_only_the_differentials() -> None:
    """I9: sem regras, degeneração parcial, ACF e quebras vazias; d_t gravada sempre."""
    inputs = completed_inputs_r0()
    assert PartialDegeneracyGoldBuilder().build(inputs).rows == ()
    assert DifferentialAcfGoldBuilder().build(inputs).rows == ()
    assert DifferentialBreaksGoldBuilder().build(inputs).rows == ()
    assert LossDifferentialsGoldBuilder().build(inputs).rows


@pytest.mark.contract
def test_stationarity_error_maps_to_an_error_row() -> None:
    inputs = completed_inputs()
    profile = inputs.profile_reports[0]
    assert profile.stationarity is not None
    failed = tuple(
        dataclasses.replace(row, status=UnitStatus.ERROR, detail="ValueError: x", report=None)
        for row in profile.stationarity
    )
    changed = dataclasses.replace(
        inputs, profile_reports=(dataclasses.replace(profile, stationarity=failed),)
    )
    rows = DifferentialBreaksGoldBuilder().build(changed).rows
    assert rows and all(
        (r["status"], r["undefined_reason"], r["detail"], r["statistic"])
        == ("error", "error", "ValueError: x", None)
        for r in rows
    )
    assert DifferentialAcfGoldBuilder().build(changed).rows == ()
