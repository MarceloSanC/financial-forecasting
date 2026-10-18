"""Testes da `ConformalAssembly` (Stage 7.2, Task 14) — concept §4, C9, CA13, I14.

Um teste por regra do CA13, sobre o cohort sintético da 6.4 com folds inteiros e
registros de calib acrescentados pelos mesmos runs (`with_calib`). O candidato é
`tft` (seeds 1 e 2); as decisões de teste do fold `0` vão de 5 a 21 e as do `1` de
22 ao fim.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.domain.services.conformal_assembly import (
    NO_FOLD,
    OK,
    UNDEFINED,
    ConformalAssembly,
    ConformalAssemblyResult,
    ConformalUnitAssembly,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from tests.unit.features.evaluation.gold._cohort_factory import (
    GOLD_LEVELS,
    Cohort,
    add_records,
    make_cohort,
    replace_records,
    run_id,
    session,
    with_calib,
)

pytestmark = pytest.mark.unit

_CALIB = {"0": (0, 1, 2, 3), "1": (14, 15, 16, 17)}
_HORIZONS = (1, 2)


def _cohort(
    *,
    folds: tuple[str | None, ...] = ("0", "1"),
    calib: dict[str, tuple[int, ...]] | None = None,
    seeds: dict[str, tuple[int | None, ...]] | None = None,
) -> Cohort:
    cohort = make_cohort(folds=folds, **({"seeds": seeds} if seeds else {}))  # type: ignore[arg-type]
    return with_calib(cohort, model="tft", calib_decisions=_CALIB if calib is None else calib)


def _native(cohort: Cohort) -> dict[tuple[int, int], CoverageSeries]:
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=_HORIZONS,
        window_deficits={},
        required_models=frozenset({"tft"}),
    )
    assert assembled.alignment.findings == ()
    native: dict[tuple[int, int], CoverageSeries] = {}
    for samples in assembled.horizons:
        for seed, series in zip(samples.seeds["tft"], samples.full["tft"], strict=True):
            if seed is not None:
                native[(seed, samples.horizon)] = series
    return native


def _assemble(
    cohort: Cohort, native: dict[tuple[int, int], CoverageSeries] | None = None
) -> ConformalAssemblyResult:
    return ConformalAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        _native(cohort) if native is None else native,
        candidate="tft",
        horizons=_HORIZONS,
        levels=GOLD_LEVELS,
    )


def _unit(
    result: ConformalAssemblyResult, fold: str, seed: int, horizon: int
) -> ConformalUnitAssembly:
    return next(u for u in result.units if (u.fold_raw, u.seed, u.horizon) == (fold, seed, horizon))


def _calib_of(fold: str, seed: int, horizon: int) -> list[ForecastRecord]:
    return [
        r
        for r in _cohort().records
        if r.split == "calib" and r.run_id == run_id("tft", seed, fold) and r.horizon == horizon
    ]


def test_all_units_ok_in_order() -> None:
    result = _assemble(_cohort())
    keys = [(u.fold_raw, u.seed, u.horizon) for u in result.units]
    assert keys == [(f, s, h) for f in ("0", "1") for s in (1, 2) for h in _HORIZONS]
    assert {u.status for u in result.units} == {OK}
    assert all(u.reason is None for u in result.units)
    assert {u.fold_index for u in result.units} == {0, 1}


def test_calib_only_from_calib_records_of_the_unit_run() -> None:
    cohort = _cohort()
    # um registro de calib do run do fold 1 na decisão 0 (que é do calib do fold 0)
    stray = dataclasses.replace(_calib_of("0", 1, 1)[0], run_id=run_id("tft", 1, "1"), fold="1")
    result = _assemble(add_records(cohort, stray))
    unit = _unit(result, "0", 1, 1)
    assert [point[0] for point in unit.calib] == [session(d) for d in _CALIB["0"]]
    assert unit.status == OK


def test_test_only_from_test_records() -> None:
    cohort = _cohort()
    unit = _unit(_assemble(cohort), "1", 2, 2)
    expected = sorted(
        {
            r.target_timestamp
            for r in cohort.records
            if (r.split, r.run_id, r.horizon) == ("test", run_id("tft", 2, "1"), 2)
        }
    )
    assert [point[1] for point in unit.test] == expected
    assert not {point[1] for point in unit.calib} & set(expected)


def test_early_stop_records_never_enter() -> None:
    cohort = _cohort()
    # registros early_stop do mesmo run, em decisões que quebrariam o calib se entrassem
    early = tuple(
        dataclasses.replace(
            r,
            split="early_stop",
            decision_idx=r.decision_idx + 30,
            decision_timestamp=session(r.decision_idx + 30),
            target_timestamp=session(r.decision_idx + 31),
        )
        for r in _calib_of("0", 1, 1)
    )
    before = _unit(_assemble(cohort), "0", 1, 1)
    after = _unit(_assemble(add_records(cohort, *early)), "0", 1, 1)
    assert after == before


def test_realized_taken_at_the_calib_target() -> None:
    cohort = _cohort()
    unit = _unit(_assemble(cohort), "0", 1, 2)
    for decision, target, _, y in unit.calib:
        assert y == cohort.realized.realized_at(target)
        assert cohort.realized.index_of(target) == cohort.realized.index_of(decision) + 2


def test_full_series_folds_aligned_by_target() -> None:
    cohort = _cohort()
    native = _native(cohort)
    result = _assemble(cohort, native)
    for key, series in native.items():
        folds = result.full_series_folds[key]
        assert len(folds) == series.n_points
        for target, fold in zip(series.target_timestamps, folds, strict=True):
            decision = cohort.realized.index_of(target) - key[1]  # type: ignore[operator]
            assert fold == (0 if decision < 22 else 1)  # noqa: PLR2004


def test_unit_without_calib_undefined() -> None:
    result = _assemble(_cohort(calib={"0": _CALIB["0"]}))
    unit = _unit(result, "1", 1, 1)
    assert (unit.status, unit.reason) == (UNDEFINED, "unit has no calib point")
    assert _unit(result, "0", 1, 1).status == OK


def test_partial_calib_undefined() -> None:
    unit = _unit(_assemble(_cohort(calib={**_CALIB, "1": (14, 15, 17)})), "1", 1, 1)
    assert unit.status == UNDEFINED
    assert "calib is partial" in (unit.reason or "")


def test_calib_target_without_realized_undefined() -> None:
    unit = _unit(_assemble(_cohort(calib={**_CALIB, "1": (36, 37, 38, 39)})), "1", 1, 1)
    assert unit.status == UNDEFINED
    assert "realized_missing" in (unit.reason or "")


def test_horizon_mismatch_undefined() -> None:
    cohort = _cohort()
    target = run_id("tft", 1, "0")
    shifted = replace_records(
        cohort,
        lambda r: (r.split, r.run_id, r.horizon, r.decision_idx) == ("calib", target, 1, 2),
        lambda r: dataclasses.replace(r, target_timestamp=session(r.decision_idx + 3)),
    )
    unit = _unit(_assemble(shifted), "0", 1, 1)
    assert unit.status == UNDEFINED
    assert "horizon_label_mismatch" in (unit.reason or "")


def test_duplicate_undefined() -> None:
    cohort = _cohort()
    unit = _unit(_assemble(add_records(cohort, _calib_of("0", 1, 1)[0])), "0", 1, 1)
    assert unit.status == UNDEFINED
    assert "duplicate_point" in (unit.reason or "")


def test_incomplete_levels_undefined() -> None:
    cohort = _cohort()
    victim = _calib_of("0", 2, 1)[3]
    dropped = dataclasses.replace(cohort, records=tuple(r for r in cohort.records if r != victim))
    unit = _unit(_assemble(dropped), "0", 2, 1)
    assert unit.status == UNDEFINED
    assert "grid_incomplete" in (unit.reason or "")


@pytest.mark.parametrize(("fold", "raw"), [("x", "x"), (None, NO_FOLD)])
def test_non_integer_fold_undefined(fold: str | None, raw: str) -> None:
    cohort = _cohort(folds=(fold, "1"), calib={"1": _CALIB["1"]})
    native = _native(cohort)
    result = _assemble(cohort, native)
    bad = [u for u in result.units if u.fold_raw == raw]
    assert len(bad) == 4  # noqa: PLR2004 — duas seeds x dois horizontes
    assert all(u.fold_index is None and u.status == UNDEFINED for u in bad)
    assert all("is not an integer" in (u.reason or "") for u in bad)
    folds = result.full_series_folds[(1, 1)]
    assert folds[0] is None  # o primeiro alvo foi previsto pelo run do fold não inteiro
    assert folds[-1] == 1


def test_two_non_integer_folds_stay_distinct() -> None:
    cohort = _cohort(folds=("x", "y"), calib={})
    result = _assemble(cohort)
    assert {u.fold_raw for u in result.units} == {"x", "y"}
    assert len(result.units) == 8  # noqa: PLR2004


def test_seed_none_is_undefined_with_reason() -> None:
    cohort = _cohort(seeds={"gbm": (None,), "tft": (None,)})
    result = _assemble(cohort, native={})
    assert {u.status for u in result.units} == {UNDEFINED}
    assert {u.reason for u in result.units} == {"seed is None"}
    assert all(u.seed is None for u in result.units)


def test_grids_use_value_guardrail_not_value_raw() -> None:
    cohort = replace_records(
        _cohort(),
        lambda r: r.model == "tft" and r.split == "calib",
        lambda r: dataclasses.replace(r, value_guardrail=r.value_raw + 1.0),
    )
    unit = _unit(_assemble(cohort), "0", 1, 1)
    run = run_id("tft", 1, "0")

    def grid_at(split: str, target: str) -> dict[float, float]:
        return {
            r.quantile_level: r.value_guardrail
            for r in cohort.records
            if (r.split, r.run_id, r.horizon, r.target_timestamp) == (split, run, 1, target)
        }

    assert dict(unit.calib[0][2]) == grid_at("calib", unit.calib[0][1])
    assert dict(unit.test[0][2]) == grid_at("test", unit.test[0][1])
    # o 1º ponto de teste do fold 0 é o ponto especial do cohort: bruto ≠ guardrail
    special = cohort.special
    assert special is not None
    assert special.target_timestamp == unit.test[0][1]
    assert tuple(unit.test[0][2][level] for level in GOLD_LEVELS) == special.guardrail
    assert special.guardrail != special.raw
    assert unit.calib[0][2] != {
        r.quantile_level: r.value_raw
        for r in cohort.records
        if (r.split, r.run_id, r.horizon, r.target_timestamp) == ("calib", run, 1, unit.calib[0][1])
    }


def _with_targets(series: CoverageSeries, targets: list[str]) -> CoverageSeries:
    return CoverageSeries(
        horizon=series.horizon,
        levels=series.levels,
        target_timestamps=tuple(targets),
        forecasts=series.forecasts[: len(targets)],
        realized=series.realized[: len(targets)],
    )


@pytest.mark.parametrize("change", ["extra", "missing", "swapped"])
def test_test_targets_must_equal_native_fold_targets(change: str) -> None:
    cohort = _cohort()
    native = _native(cohort)
    series = native[(1, 1)]
    targets = list(series.target_timestamps)
    # um instante dentro do intervalo do fold 0, que não é alvo de nenhum registro
    odd = session(10).replace("T00:00:00", "T12:00:00")
    if change == "extra":
        targets.insert(5, odd)
        targets.pop()  # mesmo tamanho dos forecasts disponíveis
    elif change == "missing":
        targets.pop(5)
    else:
        targets[5] = odd
    targets = sorted(targets)
    native[(1, 1)] = _with_targets(series, targets)
    unit = _unit(_assemble(cohort, native), "0", 1, 1)
    assert unit.status == UNDEFINED
    assert "test targets differ from the native full series" in (unit.reason or "")


def test_violation_is_never_an_alignment_finding() -> None:
    cohort = add_records(_cohort(calib={**_CALIB, "1": (14, 15, 17)}), _calib_of("0", 1, 1)[0])
    result = _assemble(cohort)
    assert UNDEFINED in {u.status for u in result.units}
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=_HORIZONS,
        window_deficits={},
        required_models=frozenset({"tft"}),
    )
    assert assembled.alignment.findings == ()
