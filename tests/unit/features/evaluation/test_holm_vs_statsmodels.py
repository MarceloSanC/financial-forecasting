"""Unit test de `HolmCorrection` contra casos analíticos (A6 unit, A7, C2, C4, C8, I1, I7).

Desvio de caminho declarado (concept 6.2 D7; ADR 6.2.0003 item 4): o nome do arquivo é o
do roadmap (`test_holm_vs_statsmodels.py`), mas o conteúdo é **só analítico** — casos
trabalhados de Holm (1979) com p-valores diádicos (a aritmética de `(m - i + 1)·p` e do
máximo acumulado é exata, logo igualdade `==`), teto em 1, ordem de entrada, empates e a
fronteira p̃ = alpha. O cruzamento com `statsmodels.stats.multitest.multipletests(method=
'holm')` fica na suíte de contrato do `InferenceBackend` (Task 10) — unit não importa
biblioteca.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
from collections.abc import Callable
from itertools import permutations

import pytest

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    DmHolmFamilyReport,
    HolmComparison,
    HolmCorrection,
    holm_adjust,
    holm_reject,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_DYADIC = (0.125, 0.25, 0.0625, 0.5)
_DYADIC_ADJUSTED = (0.375, 0.5, 0.25, 0.5)
_ALPHA = 0.05
_K7_MODELS = ("m1", "m2", "m3", "cand", "m4", "m5", "m6")
_K7_POINTS = 12
_K7_HORIZON = 2
_K7_SEED = 20260928  # random.Random: perdas sintéticas contínuas (sem empate, var̂ > 0)


@pytest.mark.unit
def test_holm_dyadic_worked_case() -> None:
    """Ordenados: 0,0625·4 = 0,25; 0,125·3 = 0,375; 0,25·2 = 0,5; 0,5·1 = 0,5."""
    assert holm_adjust(_DYADIC) == _DYADIC_ADJUSTED


@pytest.mark.unit
@pytest.mark.parametrize("p_value", [0.0, 0.03, 0.5, 1.0])
def test_holm_single_p_is_raw(p_value: float) -> None:
    assert holm_adjust([p_value]) == (p_value,)


@pytest.mark.unit
def test_holm_cap_one() -> None:
    """0,5·2 = 1,0 e o máximo acumulado leva 0,75·1 a 1,0; nada passa de 1."""
    assert holm_adjust((0.5, 0.75)) == (1.0, 1.0)
    assert holm_adjust((0.9, 0.8, 0.7)) == (1.0, 1.0, 1.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "p_values", [(0.125, 0.125), (0.125, 0.125, 0.0625), (0.0625, 0.125, 0.125)]
)
def test_holm_tie_order_free(p_values: tuple[float, ...]) -> None:
    """Empate: o mesmo p̃ para os empatados, em qualquer ordem de entrada."""
    for permuted in permutations(p_values):
        adjusted = dict(zip(permuted, holm_adjust(permuted), strict=True))
        assert holm_adjust(permuted) == tuple(adjusted[p] for p in permuted)
    assert holm_adjust((0.125, 0.125)) == (0.25, 0.25)


@pytest.mark.unit
def test_holm_input_order_preserved() -> None:
    expected = dict(zip(_DYADIC, _DYADIC_ADJUSTED, strict=True))
    for permuted in permutations(_DYADIC):
        assert holm_adjust(permuted) == tuple(expected[p] for p in permuted)


@pytest.mark.unit
def test_holm_boundary_rejects_at_alpha() -> None:
    """p̃ = alpha rejeita (registro p̃ ≤ alpha); logo acima de p̃, não."""
    assert holm_reject((0.125, 0.125), alpha=0.25) == (True, True)
    assert holm_reject(_DYADIC, alpha=0.375) == (True, False, True, False)
    assert holm_reject(_DYADIC, alpha=0.3) == (False, False, True, False)


@pytest.mark.unit
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: holm_adjust([]), id="adjust-empty"),
        pytest.param(lambda: holm_adjust([0.1, -0.1]), id="adjust-negative"),
        pytest.param(lambda: holm_adjust([1.1]), id="adjust-above-one"),
        pytest.param(lambda: holm_adjust([math.nan]), id="adjust-nan"),
        pytest.param(lambda: holm_adjust([None]), id="adjust-none"),
        pytest.param(lambda: holm_adjust([True]), id="adjust-bool"),
        pytest.param(lambda: holm_reject([], alpha=_ALPHA), id="reject-empty"),
        pytest.param(lambda: holm_reject([1.1], alpha=_ALPHA), id="reject-above-one"),
        pytest.param(lambda: holm_reject([0.1], alpha=0.0), id="alpha-zero"),
        pytest.param(lambda: holm_reject([0.1], alpha=1.0), id="alpha-one"),
        pytest.param(lambda: holm_reject([0.1], alpha=-0.1), id="alpha-negative"),
        pytest.param(lambda: holm_reject([0.1], alpha=math.nan), id="alpha-nan"),
        pytest.param(lambda: holm_reject([0.1], alpha=True), id="alpha-bool"),
    ],
)
def test_holm_c4_invalid_raises(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"p_values|alpha"):
        call()


def _k7_series() -> PairedLossSeries:
    rng = random.Random(_K7_SEED)
    return PairedLossSeries(
        horizon=_K7_HORIZON,
        models=_K7_MODELS,
        target_timestamps=tuple(f"2024-02-{day:02d}" for day in range(1, _K7_POINTS + 1)),
        losses=tuple(tuple(rng.uniform(0.0, 2.0) for _ in range(_K7_POINTS)) for _ in _K7_MODELS),
    )


@pytest.mark.unit
@pytest.mark.parametrize("estimator", list(DmVarianceEstimator))
def test_family_k7_all_comparators(estimator: DmVarianceEstimator) -> None:
    series = _k7_series()
    report = HolmCorrection.family(
        series, candidate="cand", alpha=_ALPHA, variance_estimator=estimator
    )
    comparators = tuple(comparison.comparator for comparison in report.comparisons)
    assert comparators == ("m1", "m2", "m3", "m4", "m5", "m6")
    for comparison in report.comparisons:
        assert comparison.dm == DieboldMariano.compare(
            series, candidate="cand", comparator=comparison.comparator, variance_estimator=estimator
        )
    p_values = [comparison.dm.p_value for comparison in report.comparisons]
    adjusted = holm_adjust(p_values)
    assert tuple(comparison.adjusted_p_value for comparison in report.comparisons) == adjusted
    assert tuple(comparison.rejected for comparison in report.comparisons) == holm_reject(
        p_values, alpha=_ALPHA
    )
    assert (report.candidate, report.alpha, report.variance_estimator) == (
        "cand",
        _ALPHA,
        estimator,
    )


@pytest.mark.unit
def test_family_horizon_propagated() -> None:
    """I1: o relatório carrega o horizonte e o T da série (um horizonte por família)."""
    series = _k7_series()
    report = HolmCorrection.family(series, candidate="m1", alpha=_ALPHA)
    assert (report.horizon, report.n_points) == (_K7_HORIZON, _K7_POINTS)
    assert all(comparison.dm.horizon == _K7_HORIZON for comparison in report.comparisons)


@pytest.mark.unit
def test_family_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="unknown candidate 'zzz'"):
        HolmCorrection.family(_k7_series(), candidate="zzz", alpha=_ALPHA)


@pytest.mark.unit
@pytest.mark.parametrize("alpha", [0.0, 1.0, math.nan])
def test_family_invalid_alpha_raises(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha must be"):
        HolmCorrection.family(_k7_series(), candidate="cand", alpha=alpha)


@pytest.mark.unit
def test_family_single_candidate_signature() -> None:
    """Antigo "gate B": um único `candidate: str`; `alpha` keyword-only sem default."""
    signature = inspect.signature(HolmCorrection.family)
    assert list(signature.parameters) == ["series", "candidate", "alpha", "variance_estimator"]
    candidate = signature.parameters["candidate"]
    alpha = signature.parameters["alpha"]
    assert candidate.annotation in ("str", str)
    assert candidate.kind is inspect.Parameter.KEYWORD_ONLY
    assert alpha.kind is inspect.Parameter.KEYWORD_ONLY
    assert alpha.default is inspect.Parameter.empty


def _valid_report() -> DmHolmFamilyReport:
    return HolmCorrection.family(_k7_series(), candidate="cand", alpha=_ALPHA)


def _replace_first(report: DmHolmFamilyReport, **changes: object) -> DmHolmFamilyReport:
    first = dataclasses.replace(report.comparisons[0], **changes)  # type: ignore[arg-type]
    return dataclasses.replace(report, comparisons=(first, *report.comparisons[1:]))


def _other_sample_dm(report: DmHolmFamilyReport, **changes: object) -> HolmComparison:
    dm = dataclasses.replace(report.comparisons[0].dm, **changes)  # type: ignore[arg-type]
    return dataclasses.replace(report.comparisons[0], dm=dm)


_INCOHERENT: list[tuple[str, Callable[[DmHolmFamilyReport], object], str]] = [
    ("empty", lambda r: dataclasses.replace(r, comparisons=()), "m >= 1"),
    (
        "repeated-comparator",
        lambda r: _replace_first(r, comparator=r.comparisons[1].comparator),
        "unique",
    ),
    ("candidate-among-comparators", lambda r: _replace_first(r, comparator="cand"), "cannot be"),
    (
        "n-points-mixed",
        lambda r: dataclasses.replace(
            r,
            comparisons=(
                _other_sample_dm(r, n_points=_K7_POINTS - 1, degrees_of_freedom=_K7_POINTS - 2),
                *r.comparisons[1:],
            ),
        ),
        "n_points",
    ),
    (
        "horizon-mixed",
        lambda r: dataclasses.replace(
            r, comparisons=(_other_sample_dm(r, horizon=3, horizon_used=3), *r.comparisons[1:])
        ),
        "horizon",
    ),
    (
        "estimator-mixed",
        lambda r: dataclasses.replace(r, variance_estimator=DmVarianceEstimator.BARTLETT),
        "variance estimator",
    ),
    (
        "adjusted-not-holm",
        lambda r: _replace_first(r, adjusted_p_value=r.comparisons[0].dm.p_value / 2),
        "holm_adjust",
    ),
    (
        "rejected-not-bool",
        lambda r: _replace_first(r, rejected=int(r.comparisons[0].rejected)),
        "rejected must be a bool",
    ),
    (
        "comparisons-list",
        lambda r: dataclasses.replace(r, comparisons=list(r.comparisons)),
        "must be a tuple",
    ),
    (
        "rejected-incoherent",
        lambda r: _replace_first(r, rejected=not r.comparisons[0].rejected),
        "incoherent",
    ),
    ("alpha-out-of-range", lambda r: dataclasses.replace(r, alpha=1.0), "alpha must be"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build", "message"), [pytest.param(b, m, id=i) for i, b, m in _INCOHERENT]
)
def test_family_report_incoherent_raises(
    build: Callable[[DmHolmFamilyReport], object], message: str
) -> None:
    valid = _valid_report()
    with pytest.raises(ValueError, match=message):
        build(valid)
