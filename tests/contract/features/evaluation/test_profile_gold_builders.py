"""Mapeamento dos builders de perfil da Stage 6.6 (contract; fora da parametrização).

Cada builder copia célula a célula o relatório de domínio dos `GoldInputs` (forma da r1:
`completed_inputs()`); a forma do r0 (`completed_inputs_r0()`, sem regras de perfil) não
produz linha nas tabelas que dependem das regras (concept I9); os casos de fold
indefinido passam pelo `GoldTable` sem chave repetida (CA3).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_profiles import (  # noqa: E501
    DmProfilesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_seed_fraction import (  # noqa: E501
    DmSeedFractionGoldBuilder,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import GoldInputs
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    DmProfiles,
    SubsetStatus,
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
