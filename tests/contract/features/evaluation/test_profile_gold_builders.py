"""Mapeamento dos builders de perfil da Stage 6.6 (contract; fora da parametrização).

Cada builder copia célula a célula o relatório de domínio dos `GoldInputs` (forma da r1:
`completed_inputs()`); a forma do r0 (`completed_inputs_r0()`, sem regras de perfil) não
produz linha nas tabelas que dependem das regras (concept I9); os casos de fold
indefinido passam pelo `GoldTable` sem chave repetida (CA3).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    partition_columns,
)
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
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    McsBlockRun,
)
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    adjacent_collapse_rates,
)
from financial_forecasting.features.evaluation.domain.services.differential_stationarity import (
    StationarityStatus,
)
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    DmProfiles,
    SubsetStatus,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    PairKind,
    UnitStatus,
)
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


# -- linha inteira: cada coluna do builder conferida contra o relatório de domínio ----------


def _strip(rows: object, inputs: GoldInputs) -> list[dict[str, object]]:
    """As linhas sem as colunas de partição (conferidas aqui) e em ordem canônica."""
    base = partition_columns(inputs, confirmatory=True)
    out = []
    for row in rows:  # type: ignore[attr-defined]
        assert {k: row[k] for k in base} == base
        out.append({k: v for k, v in row.items() if k not in base})
    return sorted(out, key=repr)


def _expected_dm(inputs: GoldInputs) -> list[dict[str, object]]:
    rows = []
    for profile in inputs.profile_reports:
        report = profile.dm_profiles
        if report is None:
            continue
        for unit in report.rows:
            result = unit.result
            rows.append(
                {
                    "horizon": report.horizon,
                    "dimension": unit.dimension.value,
                    "fold": unit.fold,
                    "seed": unit.seed,
                    "level": unit.level,
                    "comparator": unit.comparator,
                    "candidate": report.candidate,
                    "status": unit.status.value,
                    "undefined_reason": unit.undefined_reason,
                    "detail": unit.detail,
                    "n_points": unit.n_points,
                    "first_target_timestamp": unit.first_target_timestamp,
                    "last_target_timestamp": unit.last_target_timestamp,
                    "variance_estimator": report.variance_estimator.value,
                    "mean_differential": None if result is None else result.mean_differential,
                    "statistic": None if result is None else result.statistic,
                    "p_value": None if result is None else result.p_value,
                    "rejected": unit.rejected,
                    "fallback_applied": None if result is None else result.fallback_applied,
                    "horizon_used": None if result is None else result.horizon_used,
                    "alpha": report.alpha,
                }
            )
    return sorted(rows, key=repr)


def _expected_seed_fraction(inputs: GoldInputs) -> list[dict[str, object]]:
    return sorted(
        (
            {
                "horizon": p.dm_profiles.horizon,
                "comparator": f.comparator,
                "candidate": p.dm_profiles.candidate,
                "n_seeds": f.n_seeds,
                "n_rejecting": f.n_rejecting,
                "n_undefined": f.n_undefined,
                "fraction_rejecting": f.fraction_rejecting,
                "alpha": p.dm_profiles.alpha,
            }
            for p in inputs.profile_reports
            if p.dm_profiles is not None
            for f in p.dm_profiles.seed_fractions
        ),
        key=repr,
    )


def _expected_mcs_block(inputs: GoldInputs) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in inputs.mcs_block_reports:
        common = {
            "horizon": run.horizon,
            "block_rule": run.block_rule,
            "status": run.status.value,
            "detail": run.detail,
            "scheme": run.scheme.value,
            "block_size": run.block_size,
        }
        report = run.report
        if report is None:
            empty = ("elimination_rank", "step_p_value", "mcs_p_value", "included")
            rows.append(
                {**common, "model": None, "undefined_reason": "error"}
                | dict.fromkeys((*empty, "alpha", "reps", "seed", "n_points"))
            )
            continue
        rows += [
            {
                **common,
                "model": e.model,
                "undefined_reason": None,
                "elimination_rank": rank,
                "step_p_value": e.step_p_value,
                "mcs_p_value": e.mcs_p_value,
                "included": e.model in report.included,
                "alpha": report.alpha,
                "reps": report.reps,
                "seed": report.seed,
                "n_points": report.n_points,
            }
            for rank, e in enumerate(report.eliminations, start=1)
        ]
    return sorted(rows, key=repr)


def _expected_mc(inputs: GoldInputs) -> list[dict[str, object]]:
    rows = []
    for profile in inputs.profile_reports:
        for unit in profile.monte_carlo:
            v = unit.values
            rows.append(
                {
                    "model": unit.model,
                    "seed": unit.seed,
                    "horizon": profile.horizon,
                    "sample": unit.sample.value,
                    "kind": unit.kind.value,
                    "level_low": unit.levels[0],
                    "level_high": unit.levels[1] if len(unit.levels) == 2 else None,  # noqa: PLR2004
                    "includes_degenerate": unit.includes_degenerate,
                    "status": unit.status.value,
                    "detail": unit.detail,
                    "uc_status": None if v is None else v.uc_status.value,
                    "ind_status": None if v is None else v.ind_status.value,
                    "mc_p_uc": None if v is None else v.p_uc,
                    "mc_p_ind": None if v is None else v.p_ind,
                    "mc_p_cc": None if v is None else v.p_cc,
                    "draws": inputs.parameters.monte_carlo_draws,
                    "mc_seed": inputs.parameters.monte_carlo_seed,
                    "attempts": None if v is None else v.attempts,
                }
            )
    return sorted(rows, key=repr)


def _expected_partial(inputs: GoldInputs) -> list[dict[str, object]]:
    return sorted(
        (
            {
                "model": r.model,
                "seed": r.seed,
                "horizon": p.horizon,
                "sample": r.sample.value,
                "pair_kind": r.pair_kind.value,
                "level_low": r.level_low,
                "level_high": r.level_high,
                "status": r.status.value,
                "detail": r.detail,
                "collapse_rate": r.collapse_rate,
                "tolerance": inputs.parameters.degeneracy_tolerance,
            }
            for p in inputs.profile_reports
            for r in p.partial_degeneracy or ()
        ),
        key=repr,
    )


def _expected_breaks(inputs: GoldInputs) -> list[dict[str, object]]:
    rules = inputs.parameters.profile_parameters
    assert rules is not None
    rows = []
    for p in inputs.profile_reports:
        for r in p.stationarity or ():
            rep = r.report
            values = (
                dict.fromkeys(
                    ("statistic", "p_value", "rejected", "horizon_used", "n_points", "max_lag")
                )
                | {"break_target_timestamp": None}
                if rep is None
                else {
                    "statistic": rep.statistic,
                    "p_value": rep.p_value,
                    "rejected": rep.rejected,
                    "horizon_used": rep.horizon_used,
                    "break_target_timestamp": rep.break_target_timestamp,
                    "n_points": rep.n_points,
                    "max_lag": rep.max_lag,
                }
            )
            rows.append(
                {
                    "horizon": p.horizon,
                    "model_a": r.pair[0],
                    "model_b": r.pair[1],
                    "status": "error" if rep is None else rep.status.value,
                    "undefined_reason": "error" if rep is None else rep.undefined_reason,
                    "detail": r.detail,
                    "alpha": rules.stationarity.break_alpha if rep is None else rep.alpha,
                    **values,
                }
            )
    return sorted(rows, key=repr)


def _expected_acf(inputs: GoldInputs) -> list[dict[str, object]]:
    return sorted(
        (
            {
                "horizon": rep.horizon,
                "model_a": rep.pair[0],
                "model_b": rep.pair[1],
                "lag": lag,
                "acf": value,
                "n_points": rep.n_points,
                "max_lag": rep.max_lag,
            }
            for p in inputs.profile_reports
            for r in p.stationarity or ()
            if (rep := r.report) is not None
            for lag, value in enumerate(rep.acf, start=1)
        ),
        key=repr,
    )


def _with_failures(inputs: GoldInputs) -> GoldInputs:
    """Insumos da r1 com um caso de erro (ou indefinido) em cada tabela de perfil."""
    profiles = list(inputs.profile_reports)
    mc_at = next(i for i, p in enumerate(profiles) if p.monte_carlo)
    mc = profiles[mc_at]
    profiles[mc_at] = dataclasses.replace(
        mc,
        monte_carlo=(
            dataclasses.replace(
                mc.monte_carlo[0], status=UnitStatus.ERROR, detail="ValueError: mc", values=None
            ),
            *mc.monte_carlo[1:],
        ),
    )
    first = profiles[0]
    assert first.partial_degeneracy is not None and first.stationarity is not None
    assert first.dm_profiles is not None
    target = first.partial_degeneracy[0]
    partial = (
        *(
            r
            for r in first.partial_degeneracy
            if not (
                (r.model, r.seed, r.sample) == (target.model, target.seed, target.sample)
                and r.pair_kind is PairKind.ADJACENT
            )
        ),
        dataclasses.replace(
            target,
            pair_kind=PairKind.ADJACENT,
            level_low=None,
            level_high=None,
            collapse_rate=None,
            status=UnitStatus.ERROR,
            detail="ArithmeticError: adj",
        ),
    )
    failed, constant, *rest = first.stationarity
    assert constant.report is not None
    stationarity = (
        dataclasses.replace(failed, status=UnitStatus.ERROR, detail="ValueError: st", report=None),
        dataclasses.replace(
            constant,
            report=dataclasses.replace(
                constant.report,
                status=StationarityStatus.UNDEFINED,
                undefined_reason="constant_differential",
                acf=(),
                statistic=None,
                p_value=None,
                rejected=None,
                horizon_used=None,
                break_target_timestamp=None,
            ),
        ),
        *rest,
    )
    unit = first.dm_profiles.rows[0]
    dm = dataclasses.replace(
        first.dm_profiles,
        rows=(
            dataclasses.replace(
                unit,
                status=SubsetStatus.UNDEFINED,
                undefined_reason="error",
                detail="ValueError: dm",
                result=None,
                rejected=None,
            ),
            *first.dm_profiles.rows[1:],
        ),
    )
    profiles[0] = dataclasses.replace(
        profiles[0], partial_degeneracy=partial, stationarity=stationarity, dm_profiles=dm
    )
    blocks: list[McsBlockRun] = list(inputs.mcs_block_reports)
    blocks[0] = dataclasses.replace(
        blocks[0], status=UnitStatus.ERROR, detail="ValueError: mcs", report=None
    )
    return dataclasses.replace(
        inputs, profile_reports=tuple(profiles), mcs_block_reports=tuple(blocks)
    )


_FULL_ROW_CASES = [
    (DmProfilesGoldBuilder(), _expected_dm),
    (DmSeedFractionGoldBuilder(), _expected_seed_fraction),
    (McsBlockSensitivityGoldBuilder(), _expected_mcs_block),
    (ChristoffersenMonteCarloGoldBuilder(), _expected_mc),
    (PartialDegeneracyGoldBuilder(), _expected_partial),
    (DifferentialBreaksGoldBuilder(), _expected_breaks),
    (DifferentialAcfGoldBuilder(), _expected_acf),
]


@pytest.mark.contract
@pytest.mark.parametrize("case", ["computed", "with_failures"])
@pytest.mark.parametrize(
    ("builder", "expected"), _FULL_ROW_CASES, ids=lambda x: getattr(x, "name", "")
)
def test_profile_builders_write_every_column_of_the_domain_report(
    builder: object, expected: object, case: str
) -> None:
    """Linha inteira = relatório de domínio, inclusive as linhas `error`/`undefined`."""
    inputs = completed_inputs() if case == "computed" else _with_failures(completed_inputs())
    rows = builder.build(inputs).rows  # type: ignore[attr-defined]
    want = expected(inputs)  # type: ignore[operator]
    assert want
    assert _strip(rows, inputs) == want


@pytest.mark.contract
def test_failure_variants_reach_the_tables() -> None:
    """Os casos injetados por `_with_failures` aparecem nas tabelas (o teste acima os cobre)."""
    inputs = _with_failures(completed_inputs())
    statuses = {
        name: {(r["status"], r.get("undefined_reason")) for r in b.build(inputs).rows}
        for name, b in (
            ("mc", ChristoffersenMonteCarloGoldBuilder()),
            ("partial", PartialDegeneracyGoldBuilder()),
            ("breaks", DifferentialBreaksGoldBuilder()),
            ("dm", DmProfilesGoldBuilder()),
            ("mcs", McsBlockSensitivityGoldBuilder()),
        )
    }
    assert ("error", None) in statuses["mc"]
    assert ("error", None) in statuses["partial"]
    assert {("error", "error"), ("undefined", "constant_differential")} <= statuses["breaks"]
    assert ("undefined", "error") in statuses["dm"]
    assert ("error", "error") in statuses["mcs"]


@pytest.mark.contract
def test_adjacent_rows_are_the_adjacent_collapse_rates() -> None:
    """CA6: linhas `adjacent` = `adjacent_collapse_rates` da série, célula a célula."""
    inputs = completed_inputs()
    table = PartialDegeneracyGoldBuilder().build(inputs)
    checked = 0
    for samples in samples_of():
        for model in samples.models:
            for index, seed in enumerate(samples.seeds[model]):
                for sample, series in (
                    ("model_full", samples.full[model][index]),
                    ("common", samples.common[model][index]),
                ):
                    got = [
                        (r["level_low"], r["level_high"], r["collapse_rate"])
                        for r in table.rows
                        if (r["model"], r["seed"], r["horizon"], r["sample"], r["pair_kind"])
                        == (model, seed, samples.horizon, sample, "adjacent")
                    ]
                    want = adjacent_collapse_rates(
                        series, tolerance=inputs.parameters.degeneracy_tolerance
                    )
                    assert got == list(want)
                    checked += 1
    assert checked
