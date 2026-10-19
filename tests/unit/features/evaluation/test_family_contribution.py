"""Unit do `FamilyContribution` e do `linear_quantile` (Stage 7.3, Task 25; I13-I15).

Casos analíticos sobre `FamilyLossDifferentials` pequenos e `BootstrapIndices`
construídos à mão. A conta independente das réplicas (`_replica_deltas`) usa a MESMA
linha de índices para as 8 séries, como o pré-registro exige (H3-B).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContribution,
    FamilyContributionReport,
    linear_quantile,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)

pytestmark = pytest.mark.unit

_LEVEL = 0.9875
Series = dict[tuple[str, int], tuple[float, ...]]


def _ones(n: int) -> Series:
    return {(f, h): (1.0,) * n for f in H3_FAMILIES for h in (1, 7)}


def _differentials(series: Series, method: str = "permutation") -> FamilyLossDifferentials:
    n = len(next(iter(series.values())))
    return FamilyLossDifferentials(
        method=method,
        families=H3_FAMILIES,
        horizons=(1, 7),
        decision_timestamps=tuple(f"2024-01-{i + 1:02d}T00:00:00+00:00" for i in range(n)),
        differentials=series,
        seed_importances={},
        permutation_importances={},
    )


def _indices(rows: Sequence[Sequence[int]]) -> BootstrapIndices:
    return BootstrapIndices(
        scheme=BootstrapScheme.STATIONARY,
        block_size=1,
        seed=0,
        n_obs=len(rows[0]),
        generator="hand-made",
        indices=tuple(tuple(row) for row in rows),
    )


def _identity_rows(n: int, reps: int = 3) -> BootstrapIndices:
    return _indices([list(range(n))] * reps)


def _evaluate(
    series: Series, rows: BootstrapIndices, level: float = _LEVEL
) -> FamilyContributionReport:
    return FamilyContribution.evaluate(_differentials(series), bootstrap=rows, level=level)


def _share(report: FamilyContributionReport, family: str) -> object:
    return next(s for s in report.shares if s.family == family)


def _replica_deltas(
    series: Series, rows: Sequence[Sequence[int]], family: str
) -> list[float | None]:
    """Δ* da família em cada réplica, com a mesma linha para as 8 séries (None se Σ* <= 0)."""
    out: list[float | None] = []
    for row in rows:
        mean = {key: sum(values[i] for i in row) / len(row) for key, values in series.items()}
        totals = {h: sum(mean[(f, h)] for f in H3_FAMILIES) for h in (1, 7)}
        if min(totals.values()) <= 0:
            out.append(None)
        else:
            out.append(mean[(family, 7)] / totals[7] - mean[(family, 1)] / totals[1])
    return out


# --- linear_quantile ---------------------------------------------------------------------


def test_linear_quantile_is_type_7() -> None:
    values = [4.0, 1.0, 3.0, 2.0]
    assert linear_quantile(values, 0.5) == 2.5  # noqa: PLR2004
    assert linear_quantile(values, 0.25) == 1.75  # noqa: PLR2004
    assert linear_quantile(values, 0.0) == 1.0
    assert linear_quantile(values, 1.0) == 4.0  # noqa: PLR2004
    assert linear_quantile([5.0], 0.3) == 5.0  # noqa: PLR2004


def test_linear_quantile_propagates_infinity_never_nan() -> None:
    assert linear_quantile([1.0, math.inf], 0.5) == math.inf
    assert linear_quantile([-math.inf, 1.0], 0.5) == -math.inf
    assert linear_quantile([-math.inf, math.inf], 0.5) == -math.inf
    assert linear_quantile([1.0, 2.0, math.inf], 0.5) == 2.0  # noqa: PLR2004
    assert not math.isnan(linear_quantile([-math.inf, -math.inf, math.inf], 0.75))
    with pytest.raises(ValueError, match="NaN"):
        linear_quantile([1.0, math.nan], 0.5)


# --- importância, participação e Δ --------------------------------------------------------


def test_importance_share_and_delta() -> None:
    series = _ones(2)
    series[("technical", 1)] = (2.0, 2.0)
    series[("fundamental", 1)] = (0.0, 0.0)
    series[("price", 7)] = (2.0, 2.0)
    series[("fundamental", 7)] = (2.0, 2.0)

    report = _evaluate(series, _identity_rows(2))

    # TA-4: Σ_g I_g(1) = 1 + 2 + 1 + 0 = 4 e Σ_g I_g(7) = 2 + 1 + 1 + 2 = 6 — cada
    # participação divide pelo total do seu horizonte
    assert report.importance[("technical", 1)] == 2.0  # noqa: PLR2004
    price = _share(report, "price")
    # share_h1 = 1/4, share_h7 = 2/6 e Δ = 1/3 - 1/4 = 1/12
    assert price.share_h1 == 0.25  # type: ignore[attr-defined]  # noqa: PLR2004
    assert price.share_h7 == pytest.approx(1 / 3)  # type: ignore[attr-defined]
    assert price.delta == pytest.approx(1 / 12)  # type: ignore[attr-defined]
    assert price.lower == pytest.approx(1 / 12)  # type: ignore[attr-defined]
    assert price.upper == pytest.approx(1 / 12)  # type: ignore[attr-defined]
    assert report.status == "ok"
    assert report.level == _LEVEL


def test_basic_interval_formula() -> None:
    """[2Δ̂ - q_{1-a/2}, 2Δ̂ - q_{a/2}] — mata o intervalo percentil [q_{a/2}, q_{1-a/2}]."""
    series = _ones(3)
    series[("price", 7)] = (0.0, 2.0, 7.0)
    rows = [[0, 1, 2], [1, 1, 2], [2, 2, 2], [0, 0, 1]]
    level = 0.5

    report = _evaluate(series, _indices(rows), level=level)

    price = _share(report, "price")
    replicas = [d for d in _replica_deltas(series, rows, "price") if d is not None]
    delta = price.delta  # type: ignore[attr-defined]
    q_low, q_high = linear_quantile(replicas, 0.25), linear_quantile(replicas, 0.75)
    assert price.lower == pytest.approx(2 * delta - q_high, abs=1e-15)  # type: ignore[attr-defined]
    assert price.upper == pytest.approx(2 * delta - q_low, abs=1e-15)  # type: ignore[attr-defined]
    assert price.lower != pytest.approx(q_low)  # type: ignore[attr-defined]


def test_level_uses_a_over_two_with_a_0_0125() -> None:
    rng = random.Random(7)
    n = 12
    series = _ones(n)
    series[("price", 7)] = tuple(rng.uniform(0.0, 4.0) for _ in range(n))
    series[("sentiment", 1)] = tuple(rng.uniform(0.0, 4.0) for _ in range(n))
    rows = [[rng.randrange(n) for _ in range(n)] for _ in range(1000)]

    report = _evaluate(series, _indices(rows))
    loose = _evaluate(series, _indices(rows), level=0.95)

    replicas = [d for d in _replica_deltas(series, rows, "price") if d is not None]
    a = 0.05 / 4
    delta = _share(report, "price").delta  # type: ignore[attr-defined]
    expected = 2 * delta - linear_quantile(replicas, 1 - a / 2)
    assert _share(report, "price").lower == pytest.approx(expected, abs=1e-12)  # type: ignore[attr-defined]
    assert _share(loose, "price").lower != pytest.approx(expected, abs=1e-12)  # type: ignore[attr-defined]


@pytest.mark.parametrize("horizon", [1, 7])
def test_point_total_nonpositive_is_undefined(horizon: int) -> None:
    series = _ones(2)
    for family in H3_FAMILIES:
        series[(family, horizon)] = (-1.0, 0.5)

    report = _evaluate(series, _identity_rows(2))

    assert report.status == "undefined"
    assert "H3-NEG" in str(report.reason)
    assert report.heterogeneous is None
    assert all(s.status == "undefined" and s.delta is None for s in report.shares)
    assert report.importance[("price", horizon)] == -0.25  # noqa: PLR2004


def _negative_at(horizon: int) -> Series:
    """t = 0 tem total negativo no horizonte; t = 1 e t = 2, positivo nos dois."""
    series = _ones(3)
    for family in H3_FAMILIES:
        series[(family, horizon)] = (-1.0, 1.0, 1.0)
    series[("price", 7)] = tuple(
        v * w for v, w in zip(series[("price", 7)], (1, 2, 3), strict=True)
    )
    return series


@pytest.mark.parametrize("horizon", [1, 7])
def test_nonpositive_replicas_enter_as_plus_inf_upper_minus_inf_lower(horizon: int) -> None:
    """Uma réplica com Σ* <= 0 SÓ num horizonte: +inf em q_{1-a/2}, -inf em q_{a/2}."""
    series = _negative_at(horizon)
    rows = [[0, 0, 0], [1, 2, 2], [1, 1, 1], [2, 2, 2], [1, 1, 2]]
    level = 0.5

    report = _evaluate(series, _indices(rows), level=level)

    replicas = _replica_deltas(series, rows, "price")
    assert replicas[0] is None  # a réplica de t = 0 só tem Σ* <= 0 nesse horizonte
    high = linear_quantile([math.inf if d is None else d for d in replicas], 0.75)
    low = linear_quantile([-math.inf if d is None else d for d in replicas], 0.25)
    price = _share(report, "price")
    delta = price.delta  # type: ignore[attr-defined]
    assert price.lower == pytest.approx(2 * delta - high, abs=1e-15)  # type: ignore[attr-defined]
    assert price.upper == pytest.approx(2 * delta - low, abs=1e-15)  # type: ignore[attr-defined]
    finite = [d for d in replicas if d is not None]  # o descarte daria outros limites
    assert price.lower != pytest.approx(2 * delta - linear_quantile(finite, 0.75))  # type: ignore[attr-defined]
    assert price.upper != pytest.approx(2 * delta - linear_quantile(finite, 0.25))  # type: ignore[attr-defined]
    assert report.nonpositive_replicas[horizon] == 1
    assert report.nonpositive_replicas[8 - horizon] == 0
    assert report.status == "ok"


def test_many_nonpositive_replicas_make_bounds_infinite_and_method_ok() -> None:
    series = _negative_at(1)
    rows = [[0, 0, 0]] * 3 + [[1, 2, 2], [2, 2, 1]]

    report = _evaluate(series, _indices(rows), level=0.5)

    price = _share(report, "price")
    assert price.lower == -math.inf  # type: ignore[attr-defined]
    assert price.upper == math.inf  # type: ignore[attr-defined]
    assert price.excludes_zero is False  # type: ignore[attr-defined]
    assert price.status == "ok"  # type: ignore[attr-defined]
    assert report.status == "ok"
    assert report.heterogeneous is False


def test_nonpositive_counts_by_horizon() -> None:
    series = _negative_at(1)
    for family in H3_FAMILIES:
        series[(family, 7)] = (1.0, -1.0, 1.0)
    rows = [[0, 0, 0], [1, 1, 1], [0, 1, 1], [0, 0, 1], [2, 2, 2]]

    report = _evaluate(series, _indices(rows), level=0.5)

    assert dict(report.nonpositive_replicas) == {1: 2, 7: 2}


# --- leitura ---------------------------------------------------------------------------


def test_side_is_the_sign_of_delta_hat() -> None:
    series = _ones(2)
    series[("price", 1)] = (2.0, 2.0)

    report = _evaluate(series, _identity_rows(2))

    price = _share(report, "price")
    assert price.delta < 0  # type: ignore[attr-defined]
    assert price.side == -1  # type: ignore[attr-defined]
    assert price.excludes_zero is True  # type: ignore[attr-defined]
    assert _share(report, "technical").side == 1  # type: ignore[attr-defined]


def test_interval_excluding_zero_on_the_opposite_side_is_undefined() -> None:
    series = _ones(2)
    series[("price", 7)] = (0.0, 2.2)  # Δ̂ pequeno e positivo; réplicas de t = 1 grandes
    rows = [[1, 1]] * 3

    report = _evaluate(series, _indices(rows), level=0.5)

    price = _share(report, "price")
    assert price.delta > 0  # type: ignore[attr-defined]
    assert price.upper < 0  # type: ignore[attr-defined]
    assert price.status == "undefined"  # type: ignore[attr-defined]
    assert "opposite" in str(price.reason)  # type: ignore[attr-defined]
    assert price.excludes_zero is None  # type: ignore[attr-defined]


def test_bound_exactly_zero_is_undefined() -> None:
    report = _evaluate(_ones(2), _identity_rows(2))

    for share in report.shares:
        assert (share.delta, share.lower, share.upper) == (0.0, 0.0, 0.0)
        assert share.status == "undefined"
        assert "exactly 0" in str(share.reason)
    assert report.heterogeneous is False


def test_heterogeneous_iff_some_ok_family_excludes_zero() -> None:
    series = _ones(2)
    series[("price", 7)] = (2.0, 2.0)
    assert _evaluate(series, _identity_rows(2)).heterogeneous is True
    wide = _negative_at(1)
    assert (
        _evaluate(wide, _indices([[0, 0, 0]] * 3 + [[1, 2, 2]]), level=0.5).heterogeneous is False
    )


def test_same_indices_for_both_horizons_and_all_families() -> None:
    """Uma linha de índices para as 8 séries: a conta independente bate exatamente."""
    rng = random.Random(11)
    n = 8
    series = {
        (f, h): tuple(rng.uniform(0.2, 3.0) for _ in range(n)) for f in H3_FAMILIES for h in (1, 7)
    }
    rows = [[rng.randrange(n) for _ in range(n)] for _ in range(50)]

    report = _evaluate(series, _indices(rows), level=0.8)

    for family in H3_FAMILIES:
        replicas = [d for d in _replica_deltas(series, rows, family) if d is not None]
        share = _share(report, family)
        delta = share.delta  # type: ignore[attr-defined]
        assert share.lower == pytest.approx(2 * delta - linear_quantile(replicas, 0.9), abs=1e-12)  # type: ignore[attr-defined]
        assert share.upper == pytest.approx(2 * delta - linear_quantile(replicas, 0.1), abs=1e-12)  # type: ignore[attr-defined]


def test_call_errors() -> None:
    with pytest.raises(ValueError, match="n_obs"):
        _evaluate(_ones(3), _identity_rows(2))
    with pytest.raises(ValueError, match="level"):
        _evaluate(_ones(2), _identity_rows(2), level=1.0)


# --- infinitos do mesmo sinal com fração ≠ 0 e a defesa contra NaN (C7-1) -----------------


def test_linear_quantile_between_two_infinities_of_the_same_sign() -> None:
    assert linear_quantile([1.0, math.inf, math.inf], 0.75) == math.inf
    assert linear_quantile([-math.inf, -math.inf, 1.0], 0.25) == -math.inf


def test_many_nonpositive_replicas_at_the_bonferroni_level_give_minus_inf_not_nan() -> None:
    rng = random.Random(5)
    series = _negative_at(1)
    rows = [[0, 0, 0]] * 10 + [[rng.choice((1, 2)) for _ in range(3)] for _ in range(990)]

    report = _evaluate(series, _indices(rows))

    price = _share(report, "price")
    assert report.nonpositive_replicas[1] >= 8  # noqa: PLR2004
    assert price.lower == -math.inf  # type: ignore[attr-defined]
    assert not math.isnan(price.lower)  # type: ignore[attr-defined]
    assert price.status == "ok"  # type: ignore[attr-defined]


def test_a_nan_bound_is_never_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from financial_forecasting.features.evaluation.domain.services import (  # noqa: PLC0415
        family_contribution,
    )

    monkeypatch.setattr(family_contribution, "linear_quantile", lambda values, p: math.nan)
    report = _evaluate(_ones(2), _identity_rows(2))
    for share in report.shares:
        assert share.status == "undefined"
        assert "NaN" in str(share.reason)
        assert (share.lower, share.upper) == (None, None)  # C8-12: nulo, nunca NaN
    assert report.heterogeneous is False


# --- fronteira Σ == 0.0 exato (C7-2) -------------------------------------------------------


def test_point_total_exactly_zero_is_undefined() -> None:
    series = _ones(2)
    series[("price", 1)] = (1.0, 1.0)
    series[("technical", 1)] = (-1.0, -1.0)
    series[("sentiment", 1)] = (0.0, 0.0)
    series[("fundamental", 1)] = (0.0, 0.0)

    report = _evaluate(series, _identity_rows(2))

    assert report.status == "undefined"
    assert "H3-NEG" in str(report.reason)


def test_replica_total_exactly_zero_counts_as_nonpositive() -> None:
    series = _ones(2)
    for family in H3_FAMILIES:
        series[(family, 1)] = (0.0, 1.0)  # t = 0 soma exatamente 0 em h = 1

    report = _evaluate(series, _indices([[0, 0], [1, 1], [0, 0], [0, 1]]), level=0.5)

    assert report.status == "ok"
    assert report.nonpositive_replicas[1] == 2  # noqa: PLR2004


def test_zero_delta_with_a_strictly_positive_interval_is_undefined() -> None:
    """C7-3: Δ̂ == 0 sem lado; intervalo que exclui 0 vira `undefined` "opposite"."""
    series = _ones(2)
    series[("price", 7)] = (0.0, 2.0)  # média 1: s_7 = s_1 = 1/4, Δ̂ = 0

    report = _evaluate(series, _indices([[0, 0]] * 3), level=0.5)

    price = _share(report, "price")
    assert price.delta == 0.0  # type: ignore[attr-defined]
    assert price.side == 0  # type: ignore[attr-defined]
    assert price.lower > 0  # type: ignore[attr-defined]
    assert price.status == "undefined"  # type: ignore[attr-defined]
    assert "opposite" in str(price.reason)  # type: ignore[attr-defined]
