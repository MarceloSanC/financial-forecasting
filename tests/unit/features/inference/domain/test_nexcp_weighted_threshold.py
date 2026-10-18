"""Unit do NexCP com pesos geométricos (Stage 7.2, Task 04) — concept §5 I4, I17 e §6 C2."""

from __future__ import annotations

import math
import random
from dataclasses import fields, replace
from fractions import Fraction

import pytest

from financial_forecasting.features.inference.domain.services import (
    conformal_calibrator as calibrator_module,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    TailCorrection,
    exact_level,
    split_conformal_rank,
    weighted_conformal_threshold,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)

_SEED = 20261017
_ALPHAS = (Fraction(1, 50), Fraction(1, 10), Fraction(1, 4))


def _calib(lower_scores: list[float], *, pair: tuple[float, float] = (0.1, 0.9)) -> CalibrationSet:
    """Calib cujos escores E^lo = E^hi = `lower_scores`, na ordem do tempo (i = 1 o mais antigo).

    Com y = 0, q̂_lo = s e q̂_hi = -s, os dois escores são exatamente s.
    """
    points = tuple(
        CalibrationPoint(
            decision_timestamp=f"{2000 + i:04d}-01-01T21:00:00+00:00",
            target_timestamp=f"{2000 + i:04d}-01-02T21:00:00+00:00",
            lower=score,
            upper=-score,
            realized=0.0,
        )
        for i, score in enumerate(lower_scores)
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


def _reference(scores: list[float], weights: list[Fraction], alpha: Fraction) -> float:
    """Oráculo direto da definição: menor R com Σ_{s_j ≤ R} w_j / (Σ w + 1) ≥ 1 - alpha."""
    total = sum(weights, Fraction(0)) + 1
    for candidate in sorted(set(scores)):
        mass = sum((w for s, w in zip(scores, weights, strict=True) if s <= candidate), Fraction(0))
        if mass / total >= 1 - alpha:
            return candidate
    return math.inf


def _geometric(rho: float, n: int) -> list[Fraction]:
    r = exact_level(rho)
    return [r ** (n + 1 - i) for i in range(1, n + 1)]


def test_rho_one_equals_the_unweighted_rank() -> None:
    rng = random.Random(_SEED)
    for _ in range(200):
        n = rng.randint(1, 300)
        # metade dos casos com empates (escores de um conjunto pequeno)
        pool = [rng.uniform(-1, 1) for _ in range(3)]
        tied = rng.random() < 0.5  # noqa: PLR2004 — metade dos casos
        scores = [rng.choice(pool) if tied else rng.uniform(-1, 1) for _ in range(n)]
        for alpha in _ALPHAS:
            rank = split_conformal_rank(n, alpha)
            expected = math.inf if rank > n else sorted(scores)[rank - 1]
            got = weighted_conformal_threshold(scores, [Fraction(1)] * n, alpha)
            assert got == expected, (n, alpha)


def test_rho_one_calibrate_matches_split() -> None:
    rng = random.Random(_SEED + 1)
    scores = [rng.uniform(-1, 1) for _ in range(60)]
    for pair in ((0.02, 0.98), (0.1, 0.9), (0.25, 0.75)):
        calib = _calib(scores, pair=pair)
        split = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.SPLIT_CQR)
        nexcp = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.NEXCP, rho=1.0)
        assert nexcp.lower.correction == split.lower.correction
        assert nexcp.upper.correction == split.upper.correction


def test_most_recent_point_weighs_rho() -> None:
    # pesos de i = 1..3 com rho = 0,5: 1/8, 1/4, 1/2 (o mais recente pesa rho); Σw + 1 = 15/8
    weights = _geometric(0.5, 3)
    assert weights == [Fraction(1, 8), Fraction(1, 4), Fraction(1, 2)]
    alpha = Fraction(3, 5)  # 1 - alpha = 0,4
    increasing = weighted_conformal_threshold([1.0, 2.0, 3.0], weights, alpha)
    decreasing = weighted_conformal_threshold([3.0, 2.0, 1.0], weights, alpha)
    assert (increasing, decreasing) == (3.0, 2.0)
    # pelo calibrador: escores crescentes no tempo puxam o limiar para cima
    up = [i / 8 for i in range(40)]
    rising = ConformalCalibrator.calibrate(
        _calib(up, pair=(0.25, 0.75)), variant=ConformalVariant.NEXCP, rho=0.9
    )
    falling = ConformalCalibrator.calibrate(
        _calib(list(reversed(up)), pair=(0.25, 0.75)), variant=ConformalVariant.NEXCP, rho=0.9
    )
    assert rising.lower.correction == _reference(up, _geometric(0.9, 40), Fraction(1, 4))
    assert falling.lower.correction == _reference(
        list(reversed(up)), _geometric(0.9, 40), Fraction(1, 4)
    )
    assert rising.lower.correction > falling.lower.correction


def test_normalization_counts_the_test_point_weight() -> None:
    # pesos 1: sem o +1 a massa total seria 1 ≥ 0,9 (limiar 4); com o +1 é 4/5 < 0,9 ⇒ +∞
    assert weighted_conformal_threshold(
        [1.0, 2.0, 3.0, 4.0], [Fraction(1)] * 4, Fraction(1, 10)
    ) == (math.inf)
    # com 1 - alpha = 4/5 a massa total alcança exatamente (empate exato aceito)
    assert (
        weighted_conformal_threshold([1.0, 2.0, 3.0, 4.0], [Fraction(1)] * 4, Fraction(1, 5)) == 4.0  # noqa: PLR2004
    )


def test_insufficient_mass_is_infinite() -> None:
    # rho = 0,9, n = 20: Σw/(Σw + 1) ≈ 0,886 < 0,9 ⇒ +∞ nas duas caudas (C2: não é erro)
    pair = ConformalCalibrator.calibrate(
        _calib([i / 4 for i in range(20)]), variant=ConformalVariant.NEXCP, rho=0.9
    )
    for tail in (pair.lower, pair.upper):
        assert tail.correction == math.inf
        assert tail.infinite is True
        assert tail.n == 20  # noqa: PLR2004
    assert pair.limits(lower=0.0, upper=0.0) == (-math.inf, math.inf)


def test_n_252_tail_002_finite_at_099_infinite_at_098() -> None:
    scores = [i / 64 for i in range(252)]
    calib = _calib(scores, pair=(0.02, 0.98))
    finite = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.NEXCP, rho=0.99)
    infinite = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.NEXCP, rho=0.98)
    assert finite.lower.infinite is False
    assert finite.lower.correction == _reference(scores, _geometric(0.99, 252), Fraction(1, 50))
    assert infinite.lower.infinite is True
    assert infinite.upper.infinite is True


def test_tied_scores_enter_together() -> None:
    # escore 1,0 duas vezes com pesos 1 e 2: juntos 3/5 = 1 - alpha ⇒ limiar 1,0;
    # contar só um dos dois (1/5 ou 2/5) levaria a 2,0
    weights = [Fraction(1), Fraction(2), Fraction(1)]
    assert weighted_conformal_threshold([1.0, 1.0, 2.0], weights, Fraction(2, 5)) == 1.0
    assert (
        weighted_conformal_threshold(
            [1.0, 2.0, 1.0], [Fraction(1), Fraction(1), Fraction(2)], Fraction(2, 5)
        )
        == 1.0
    )


def test_calibrate_passes_exact_geometric_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = random.Random(_SEED + 2)
    n = 100
    # escores distintos por cauda: q_lo, q_hi e y independentes
    points = tuple(
        CalibrationPoint(
            decision_timestamp=f"{2000 + i:04d}-01-01T21:00:00+00:00",
            target_timestamp=f"{2000 + i:04d}-01-02T21:00:00+00:00",
            lower=rng.uniform(-2, 0),
            upper=rng.uniform(0, 2),
            realized=rng.uniform(-1, 1),
        )
        for i in range(n)
    )
    calib = replace(_calib([0.0]), points=points, lower_level=0.25, upper_level=0.75)
    lower_scores = [p.lower - p.realized for p in points]
    upper_scores = [p.realized - p.upper for p in points]
    seen: list[list[Fraction]] = []

    def spy(scores: list[float], weights: list[Fraction], alpha: Fraction) -> float:
        seen.append(list(weights))
        return weighted_conformal_threshold(scores, weights, alpha)

    monkeypatch.setattr(calibrator_module, "weighted_conformal_threshold", spy)
    for rho in (0.99, 0.95):
        seen.clear()
        pair = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.NEXCP, rho=rho)
        weights = [exact_level(rho) ** (n + 1 - i) for i in range(1, n + 1)]
        assert seen == [weights, weights]  # exatos, nunca o binário de rho
        assert weights[-1] == exact_level(rho)  # o mais recente pesa rho
        assert pair.lower.correction == weighted_conformal_threshold(
            lower_scores, weights, Fraction(1, 4)
        )
        assert pair.upper.correction == weighted_conformal_threshold(
            upper_scores, weights, Fraction(1, 4)
        )
        assert pair.lower.correction != pair.upper.correction
        assert pair.rho == rho
        assert pair.variant is ConformalVariant.NEXCP


def test_nexcp_has_no_rank_and_no_beta() -> None:
    pair = ConformalCalibrator.calibrate(
        _calib([i / 4 for i in range(60)]), variant=ConformalVariant.NEXCP, rho=0.99
    )
    assert pair.lower.rank is None
    assert pair.upper.rank is None
    assert pair.lower.alpha == Fraction(1, 10)
    assert pair.upper.alpha == Fraction(1, 10)
    assert "beta" not in {f.name for f in fields(TailCorrection)}


def test_variant_has_exactly_the_two_members() -> None:
    assert {v.value for v in ConformalVariant} == {
        "split_cqr_asymmetric_unweighted_v1",
        "nexcp_fixed_geometric_weights_v1",
    }


@pytest.mark.parametrize("rho", [0.0, 1.0000001, math.nan, -0.5, math.inf, True, None])
def test_rho_refused(rho: object) -> None:
    calib = _calib([i / 4 for i in range(10)])
    with pytest.raises(ValueError, match="rho"):
        ConformalCalibrator.calibrate(calib, variant=ConformalVariant.NEXCP, rho=rho)  # type: ignore[arg-type]


def test_weighted_threshold_refuses_bad_inputs() -> None:
    with pytest.raises(ValueError, match="weights"):
        weighted_conformal_threshold([1.0, 2.0], [Fraction(1)], Fraction(1, 10))
    with pytest.raises(ValueError, match="weights"):
        weighted_conformal_threshold([1.0], [Fraction(0)], Fraction(1, 10))
    with pytest.raises(ValueError, match="scores"):
        weighted_conformal_threshold([], [], Fraction(1, 10))
    with pytest.raises(ValueError, match="alpha"):
        weighted_conformal_threshold([1.0], [Fraction(1)], Fraction(0))


def test_huge_rho_refused_with_value_error() -> None:
    # exact_rho por exact_level: 10**400 vira ValueError com o campo (Checkpoint C, C3-3)
    with pytest.raises(ValueError, match="rho"):
        ConformalCalibrator.calibrate(
            _calib([i / 4 for i in range(10)]), variant=ConformalVariant.NEXCP, rho=10**400
        )
