"""Unit do `ConformalCalibrator` sem pesos (Stage 7.2, Task 03) — concept §5 I2, I3, I5, C2, D7."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    BetaReference,
    ConformalCalibrator,
    ConformalVariant,
    PairCorrection,
    TailCorrection,
    beta_reference,
    exact_level,
    split_conformal_rank,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)

_TAIL_LEVELS = (0.02, 0.1, 0.25)
_N_252 = 252


def _calib(
    triples: list[tuple[float, float, float]], *, pair: tuple[float, float] = (0.1, 0.9)
) -> CalibrationSet:
    """Calib com um ponto por dia (alvos crescentes, todos antes do teste)."""
    points = tuple(
        CalibrationPoint(
            decision_timestamp=f"{2000 + i:04d}-01-01T21:00:00+00:00",
            target_timestamp=f"{2000 + i:04d}-01-02T21:00:00+00:00",
            lower=lower,
            upper=upper,
            realized=realized,
        )
        for i, (lower, upper, realized) in enumerate(triples)
    )
    return CalibrationSet(
        fold_index=0,
        seed=1,
        horizon=1,
        lower_level=pair[0],
        upper_level=pair[1],
        points=points,
        test_start="2999-01-01T21:00:00+00:00",
    )


def _split(calib: CalibrationSet) -> PairCorrection:
    return ConformalCalibrator.calibrate(calib, variant=ConformalVariant.SPLIT_CQR)


def test_rank_at_n_252_for_the_three_tail_alphas() -> None:
    ranks = [split_conformal_rank(_N_252, exact_level(level)) for level in _TAIL_LEVELS]
    assert ranks == [248, 228, 190]


def test_rank_small_n_table() -> None:
    for percent in (2, 10, 25):
        alpha = Fraction(percent, 100)
        for n in range(1, 31):
            # ⌈(n+1)(100 - p)/100⌉ em inteiros, independente da implementação
            expected = -(-((n + 1) * (100 - percent)) // 100)
            assert split_conformal_rank(n, alpha) == expected, (n, percent)


def test_rank_exact_off_the_grid() -> None:
    # fora da grade do plano o float erra: (8 + 1)(1 - 1/3) = 6 exato, mas
    # ceil(9 * (1 - float(1/3))) = 7 (mata o mutante `float(alpha)` no posto)
    assert split_conformal_rank(8, Fraction(1, 3)) == 6  # noqa: PLR2004


def test_upper_alpha_of_0_9_is_exactly_one_tenth() -> None:
    alpha_hi = 1 - exact_level(0.9)
    assert alpha_hi == Fraction(1, 10)
    for n in range(1, 401):
        assert split_conformal_rank(n, alpha_hi) == split_conformal_rank(n, exact_level(0.1))
    # pelo calibrador: n = 9 => (n+1)(1-alpha) = 9 exato; com alpha = Fraction(1 - 0.9),
    # o binário de 0.09999999999999998, o posto seria 10
    upper = _split(_calib([(-1.0, 1.0, 0.0)] * 9)).upper
    assert upper.alpha == Fraction(1, 10)
    assert upper.rank == 9  # noqa: PLR2004
    assert upper.level == 0.9  # noqa: PLR2004
    # alpha_lo também pelo decimal mais curto, nunca o binário de 0.1
    lower = _split(_calib([(-1.0, 1.0, 0.0)] * 9)).lower
    assert lower.alpha == Fraction(1, 10)
    assert lower.alpha != Fraction(0.1)


def test_rank_above_n_is_infinite_and_not_clipped() -> None:
    triples = [(-1.0 - i / 8, 1.0 + i / 8, 0.0) for i in range(10)]
    pair = _split(_calib(triples, pair=(0.02, 0.98)))
    for tail in (pair.lower, pair.upper):
        assert tail.n == 10  # noqa: PLR2004
        assert tail.rank == 11  # noqa: PLR2004
        assert tail.correction == math.inf
        assert tail.infinite is True
    assert pair.limits(lower=-1.0, upper=1.0) == (-math.inf, math.inf)


def test_finite_correction_is_flagged_finite() -> None:
    triples = [(-1.0, 1.0, 0.0)] * 49
    pair = _split(_calib(triples, pair=(0.02, 0.98)))
    assert pair.lower.rank == 49  # ⌈50 · 0,98⌉ = 49 ≤ n  # noqa: PLR2004
    assert pair.lower.infinite is False
    assert pair.lower.correction == -1.0


def test_ties_counted_with_multiplicity() -> None:
    # escores E^lo = q̂_lo - y = (0,5; 0,5; 0,5; 0,75); alpha = 0,25, n = 4 ⇒ k = 4
    triples = [(0.5, 2.0, 0.0), (0.5, 2.0, 0.0), (0.5, 2.0, 0.0), (0.75, 2.0, 0.0)]
    lower = _split(_calib(triples, pair=(0.25, 0.75))).lower
    assert lower.rank == 4  # noqa: PLR2004
    assert lower.correction == 0.75  # noqa: PLR2004
    # n = 3 (sem o 0,75): k = 3 cai no terceiro 0,5 — sem multiplicidade seria +∞
    tied = _split(_calib(triples[:3], pair=(0.25, 0.75))).lower
    assert tied.rank == 3  # noqa: PLR2004
    assert tied.correction == 0.5  # noqa: PLR2004
    assert tied.infinite is False
    # k no meio de escores com empate: n = 7, k = ceil(8 * 0,75) = 6 => o 6º com repetição
    middle = [(s, 2.0, 0.0) for s in (0.5, 0.5, 0.5, 0.75, 1.0, 1.25, 1.5)]
    six = _split(_calib(middle, pair=(0.25, 0.75))).lower
    assert six.rank == 6  # noqa: PLR2004
    assert six.correction == 1.25  # noqa: PLR2004 — sem multiplicidade seria 1,5


def test_score_sides() -> None:
    # y sempre 1 abaixo de q̂_lo ⇒ E^lo = 1 em todo ponto; E^hi = y - q̂_hi = -(q̂_lo + 11)
    below = [(i / 4, i / 4 + 10.0, i / 4 - 1.0) for i in range(20)]
    pair = _split(_calib(below))
    assert pair.lower.tail == "lower"
    assert pair.lower.correction == 1.0
    assert pair.upper.correction < 0
    assert pair.limits(lower=0.25, upper=10.25)[0] == 0.25 - 1.0
    # y sempre 2 acima de q̂_hi ⇒ E^hi = 2
    above = [(i / 4 - 10.0, i / 4, i / 4 + 2.0) for i in range(20)]
    pair = _split(_calib(above))
    assert pair.upper.tail == "upper"
    assert pair.upper.correction == 2.0  # noqa: PLR2004
    assert pair.lower.correction < 0
    assert pair.limits(lower=-10.0, upper=0.0)[1] == 2.0  # noqa: PLR2004


def test_k_th_smallest_not_largest() -> None:
    # E^lo = 0, 1, ..., 19; alpha = 0,25 e n = 20 ⇒ k = ⌈21 · 0,75⌉ = 16 ⇒ Q̂ = 15
    triples = [(float(i), 100.0, 0.0) for i in range(20)]
    lower = _split(_calib(list(reversed(triples)), pair=(0.25, 0.75))).lower
    assert lower.rank == 16  # noqa: PLR2004
    assert lower.correction == 15.0  # noqa: PLR2004


def test_negative_scores_shrink_positive_widen() -> None:
    inside = [(-1.0, 1.0, 0.0)] * 20  # E^lo = E^hi = -1: o intervalo encolhe
    shrink = _split(_calib(inside))
    low, high = shrink.limits(lower=-1.0, upper=1.0)
    assert (low, high) == (0.0, 0.0)
    outside = [(-1.0, 1.0, 3.0)] * 10 + [(-1.0, 1.0, -3.0)] * 10  # E = 2 nas duas caudas
    widen = _split(_calib(outside))
    assert widen.limits(lower=-1.0, upper=1.0) == (-3.0, 3.0)


def test_limits_are_not_rearranged() -> None:
    def tail(name: str, correction: float) -> TailCorrection:
        return TailCorrection(
            tail=name,  # type: ignore[arg-type]
            level=0.1,
            alpha=Fraction(1, 10),
            n=5,
            rank=5,
            correction=correction,
            infinite=math.isinf(correction),
        )

    crossed = PairCorrection(
        variant=ConformalVariant.SPLIT_CQR,
        rho=None,
        lower=tail("lower", -5.0),
        upper=tail("upper", -5.0),
    )
    assert crossed.limits(lower=0.0, upper=1.0) == (5.0, -4.0)  # L > U, sem trocar
    infinite = PairCorrection(
        variant=ConformalVariant.SPLIT_CQR,
        rho=None,
        lower=tail("lower", math.inf),
        upper=tail("upper", 0.5),
    )
    assert infinite.limits(lower=0.0, upper=1.0) == (-math.inf, 1.5)


def test_beta_reference_at_n_252() -> None:
    ref = beta_reference(_N_252, exact_level(0.02))
    a, b = 248, 5
    assert ref == BetaReference(
        a=a,
        b=b,
        mean=a / (a + b),
        sd=math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1))),
    )


def test_beta_reference_none_when_l_is_zero() -> None:
    assert beta_reference(10, exact_level(0.02)) is None


def test_beta_reference_uses_exact_alpha() -> None:
    ref = beta_reference(9, 1 - exact_level(0.9))
    assert ref is not None
    assert (ref.a, ref.b) == (9, 1)
    assert ref.mean == pytest.approx(0.9, abs=1e-15)


def test_beta_reference_exact_off_the_grid() -> None:
    # l = floor(100 * 29/100) = 29 exato; floor(100 * float(0.29)) = 28 (mata o
    # mutante `float(alpha)` na Beta)
    ref = beta_reference(99, Fraction(29, 100))
    assert ref is not None
    assert (ref.a, ref.b) == (71, 29)


def test_split_variant_refuses_rho() -> None:
    calib = _calib([(-1.0, 1.0, 0.0)] * 5)
    with pytest.raises(ValueError, match="rho"):
        ConformalCalibrator.calibrate(calib, variant=ConformalVariant.SPLIT_CQR, rho=0.99)


def test_unknown_variant_refused() -> None:
    calib = _calib([(-1.0, 1.0, 0.0)] * 5)
    with pytest.raises(ValueError, match="variant"):
        ConformalCalibrator.calibrate(calib, variant="aci")  # type: ignore[arg-type]


@pytest.mark.parametrize("alpha", [Fraction(0), Fraction(1), 0.1])
def test_rank_and_beta_refuse_invalid_alpha(alpha: object) -> None:
    with pytest.raises(ValueError, match="alpha"):
        split_conformal_rank(10, alpha)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="alpha"):
        beta_reference(10, alpha)  # type: ignore[arg-type]
