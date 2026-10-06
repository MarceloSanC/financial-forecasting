"""Unit test do `DmProfiles` (Stage 6.6 Task 10; CA3; ADR 6.6.0003).

Sobre amostras montadas pelo `SeriesAssembly` a partir do cohort sintético da 6.4
(`make_cohort`): o DM de perfil é o `DieboldMariano.compare` da 6.2 sobre recortes da
série primária (fold único = amostra inteira reproduz a família primária); rejeição à alpha
bruta, sem Holm (três modelos, p = 0,04 nos dois comparadores e alpha = 0,05: Holm não
rejeitaria); os quatro motivos `undefined` e o `error` isolado por unidade; a fração de
seeds com uma seed e com todas indefinidas.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest

from financial_forecasting.features.evaluation.domain.services import dm_profiles as module
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DieboldMarianoResult,
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    CONSTANT_DIFFERENTIAL,
    ERROR,
    FOLD_LABEL_MISMATCH,
    FOLD_NOT_CONTIGUOUS,
    TOO_SHORT,
    DmProfileDimension,
    DmProfiles,
    DmProfilesReport,
    SubsetStatus,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    HolmCorrection,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from tests.unit.features.evaluation.gold._cohort_factory import make_cohort

_CAND = "tft"
_ALPHA = 0.05
_RECT = DmVarianceEstimator.RECTANGULAR
_THREE_MODELS: Mapping[str, tuple[int | None, ...]] = {
    "gbm": (None,),
    "tft": (1, 2),
    "zr": (None,),
}


def _samples(
    *,
    folds: tuple[str, ...] = ("f0", "f1"),
    seeds: Mapping[str, tuple[int | None, ...]] | None = None,
    horizon_index: int = 0,
) -> HorizonSamples:
    cohort = make_cohort(folds=folds) if seeds is None else make_cohort(folds=folds, seeds=seeds)
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 2),
        window_deficits={},
        required_models=frozenset({_CAND}),
    )
    assert assembled.alignment.findings == ()
    return assembled.horizons[horizon_index]


def _evaluate(samples: HorizonSamples, alpha: float = _ALPHA) -> DmProfilesReport:
    return DmProfiles.evaluate(samples, candidate=_CAND, alpha=alpha, variance_estimator=_RECT)


@pytest.mark.unit
def test_single_fold_reproduces_the_primary_family() -> None:
    samples = _samples(folds=("f0",))
    report = _evaluate(samples)
    primary = HolmCorrection.family(
        paired_pinball_losses({m: samples.common[m] for m in samples.models}),
        candidate=_CAND,
        alpha=_ALPHA,
    )
    fold_rows = [r for r in report.rows if r.dimension is DmProfileDimension.FOLD]
    assert [r.comparator for r in fold_rows] == [c.comparator for c in primary.comparisons]
    for row, comparison in zip(fold_rows, primary.comparisons, strict=True):
        assert row.status is SubsetStatus.COMPUTED
        assert row.fold == "f0"
        assert row.result is not None
        assert row.result.statistic == comparison.dm.statistic
        assert row.result.p_value == comparison.dm.p_value
        assert row.n_points == samples.n_common


@pytest.mark.unit
def test_two_folds_are_two_windows_in_temporal_order() -> None:
    samples = _samples()
    rows = [r for r in _evaluate(samples).rows if r.dimension is DmProfileDimension.FOLD]
    assert [r.fold for r in rows] == ["f0", "f1"]
    assert sum(r.n_points or 0 for r in rows) == samples.n_common
    assert rows[0].last_target_timestamp is not None
    assert rows[1].first_target_timestamp is not None
    assert rows[0].last_target_timestamp < rows[1].first_target_timestamp


@pytest.mark.unit
def test_seed_and_tau_subsets() -> None:
    samples = _samples()
    report = _evaluate(samples)
    seeds = [r for r in report.rows if r.dimension is DmProfileDimension.SEED]
    assert [r.seed for r in seeds] == [1, 2]
    taus = [r for r in report.rows if r.dimension is DmProfileDimension.TAU]
    assert [r.level for r in taus] == list(samples.levels)
    one_seed = paired_pinball_losses(
        {"gbm": samples.common["gbm"], _CAND: (samples.common[_CAND][1],)}
    )
    expected = DieboldMariano.compare(one_seed, candidate=_CAND, comparator="gbm")
    assert seeds[1].result is not None
    assert seeds[1].result.statistic == expected.statistic


@pytest.mark.unit
def test_rejection_is_at_the_raw_alpha_without_holm(monkeypatch: pytest.MonkeyPatch) -> None:
    """p = 0,04 nos dois comparadores, alpha = 0,05: bruto rejeita; Holm (m = 2) daria 0,08."""
    real = DieboldMariano.compare

    def fixed(series: object, **kwargs: object) -> DieboldMarianoResult:
        return dataclasses.replace(real(series, **kwargs), p_value=0.04)  # type: ignore[arg-type]

    monkeypatch.setattr(module.DieboldMariano, "compare", staticmethod(fixed))
    report = _evaluate(_samples(seeds=_THREE_MODELS))
    computed = [r for r in report.rows if r.status is SubsetStatus.COMPUTED]
    assert computed
    assert all(r.rejected is True for r in computed)


@pytest.mark.unit
def test_fold_label_mismatch() -> None:
    samples = dataclasses.replace(
        _samples(), common_folds=None, fold_mismatch_detail="target x: folds differ"
    )
    rows = [r for r in _evaluate(samples).rows if r.dimension is DmProfileDimension.FOLD]
    assert [(r.fold, r.undefined_reason, r.detail) for r in rows] == [
        (None, FOLD_LABEL_MISMATCH, "target x: folds differ")
    ]
    assert rows[0].result is None


@pytest.mark.unit
def test_fold_not_contiguous_is_one_row_per_label_and_comparator() -> None:
    samples = _samples()
    n = samples.n_common
    third = n // 3
    pattern = ("a",) * third + ("b",) * third + ("a",) * (n - 2 * third)
    rows = [
        r
        for r in _evaluate(dataclasses.replace(samples, common_folds=pattern)).rows
        if r.dimension is DmProfileDimension.FOLD
    ]
    assert [(r.fold, r.status, r.undefined_reason) for r in rows] == [
        ("a", SubsetStatus.UNDEFINED, FOLD_NOT_CONTIGUOUS),
        ("b", SubsetStatus.COMPUTED, None),
    ]


@pytest.mark.unit
def test_too_short_fold() -> None:
    samples = _samples(horizon_index=1)  # h = 2
    pattern = ("x", "x") + ("f1",) * (samples.n_common - 2)
    rows = [
        r
        for r in _evaluate(dataclasses.replace(samples, common_folds=pattern)).rows
        if r.dimension is DmProfileDimension.FOLD
    ]
    assert (rows[0].fold, rows[0].undefined_reason) == ("x", TOO_SHORT)
    assert rows[1].status is SubsetStatus.COMPUTED


def _with_comparator_equal_to_seed(samples: HorizonSamples, seed_index: int) -> HorizonSamples:
    twin = (samples.common[_CAND][seed_index],)
    return dataclasses.replace(
        samples,
        full={**samples.full, "gbm": (samples.full[_CAND][seed_index],)},
        common={**samples.common, "gbm": twin},
    )


@pytest.mark.unit
def test_constant_differential_and_seed_fraction() -> None:
    samples = _with_comparator_equal_to_seed(_samples(), 0)
    report = _evaluate(samples, alpha=0.999)
    seeds = [r for r in report.rows if r.dimension is DmProfileDimension.SEED]
    assert (seeds[0].status, seeds[0].undefined_reason) == (
        SubsetStatus.UNDEFINED,
        CONSTANT_DIFFERENTIAL,
    )
    assert seeds[1].status is SubsetStatus.COMPUTED
    (fraction,) = report.seed_fractions
    assert (fraction.n_seeds, fraction.n_undefined) == (2, 1)
    assert fraction.n_rejecting == int(seeds[1].rejected is True)
    assert fraction.fraction_rejecting == float(fraction.n_rejecting)


@pytest.mark.unit
def test_seed_fraction_is_none_when_every_seed_is_undefined() -> None:
    base = _samples()
    twin = base.common[_CAND][0]
    samples = dataclasses.replace(
        base,
        full={**base.full, _CAND: (base.full[_CAND][0], base.full[_CAND][0])},
        common={**base.common, _CAND: (twin, twin), "gbm": (twin,)},
    )
    (fraction,) = _evaluate(samples).seed_fractions
    assert (fraction.n_seeds, fraction.n_undefined, fraction.fraction_rejecting) == (2, 2, None)


@pytest.mark.unit
def test_error_of_one_unit_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    real = DieboldMariano.compare

    def failing(series: object, **kwargs: object) -> DieboldMarianoResult:
        if kwargs["comparator"] == "zr":
            raise ArithmeticError("boom")
        return real(series, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module.DieboldMariano, "compare", staticmethod(failing))
    report = _evaluate(_samples(seeds=_THREE_MODELS))
    errors = [r for r in report.rows if r.undefined_reason == ERROR]
    assert errors
    assert all(r.comparator == "zr" and "ArithmeticError: boom" in r.detail for r in errors)
    assert all(r.status is SubsetStatus.COMPUTED for r in report.rows if r.comparator == "gbm")


@pytest.mark.unit
def test_invalid_requests() -> None:
    samples = _samples()
    with pytest.raises(ValueError, match="candidate"):
        DmProfiles.evaluate(samples, candidate="nope", alpha=_ALPHA, variance_estimator=_RECT)
    with pytest.raises(ValueError, match="alpha"):
        DmProfiles.evaluate(samples, candidate=_CAND, alpha=1.5, variance_estimator=_RECT)
