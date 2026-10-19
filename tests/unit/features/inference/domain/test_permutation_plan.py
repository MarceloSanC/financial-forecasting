"""`FamilyPermutationPlan` (Stage 7.3, Task 13; CA8, I6; ADR 7.3.0005 H3-PI)."""

from __future__ import annotations

import math
import random

import pytest

from financial_forecasting.features.inference.domain.value_objects.permutation_plan import (
    K_P,
    PERMUTATION_ALGORITHM,
    PERMUTATION_SEED,
    FamilyPermutationPlan,
)

pytestmark = pytest.mark.unit

# Fixado ao escrever o plano (seed 130, fold 2, n = 5, K_p = 3).
_GOLDEN = ((2, 3, 0, 4, 1), (4, 3, 2, 1, 0), (1, 3, 4, 2, 0))


def _plan(**overrides: int) -> FamilyPermutationPlan:
    fields = {"permutation_seed": 130, "k_p": 3, "fold_index": 2, "n_decisions": 5}
    fields.update(overrides)
    return FamilyPermutationPlan.generate(**fields)


def _independent_fisher_yates(
    seed: int, fold: int, n: int, k_p: int
) -> tuple[tuple[int, ...], ...]:
    """Re-derivação no próprio teste, do texto do algoritmo (concept 7.3 I6)."""
    rng = random.Random(seed * 1000 + fold)
    out = []
    for _ in range(k_p):
        positions = list(range(n))
        i = n - 1
        while i >= 1:
            r = math.floor(rng.random() * (i + 1))
            positions[i], positions[r] = positions[r], positions[i]
            i -= 1
        out.append(tuple(positions))
    return tuple(out)


def test_generates_k_p_permutations_of_range_n() -> None:
    plan = _plan(k_p=4, n_decisions=9)
    assert len(plan.permutations) == plan.k_p
    assert all(sorted(p) == list(range(9)) for p in plan.permutations)


def test_same_input_same_permutations() -> None:
    assert _plan() == _plan()
    assert (
        _plan(n_decisions=252, k_p=10).permutations == _plan(n_decisions=252, k_p=10).permutations
    )


def test_golden_n5_kp3_seed130_fold2() -> None:
    plan = _plan()
    assert plan.permutations == _GOLDEN
    assert plan.permutations == _independent_fisher_yates(130, 2, 5, 3)
    long = _plan(n_decisions=252, k_p=10, fold_index=4)
    assert long.permutations == _independent_fisher_yates(130, 4, 252, 10)


def test_seed_formula_is_seed_times_1000_plus_fold() -> None:
    assert _plan(fold_index=2).permutations != _plan(fold_index=3).permutations
    # com `seed + fold`, (130, 2) e (131, 1) dariam o mesmo gerador
    assert (
        _plan(permutation_seed=130, fold_index=2).permutations
        != _plan(permutation_seed=131, fold_index=1).permutations
    )


def test_is_not_random_shuffle() -> None:
    rng = random.Random(130 * 1000 + 2)
    shuffled = list(range(5))
    rng.shuffle(shuffled)
    assert tuple(shuffled) != _GOLDEN[0]


def test_indices_are_one_based() -> None:
    plan = _plan()
    assert plan.permutation_indices == (1, 2, 3)
    assert plan.permutation(1) == _GOLDEN[0]
    assert plan.permutation(3) == _GOLDEN[2]
    for index in (0, 4, True):
        with pytest.raises(ValueError, match="permutation index"):
            plan.permutation(index)


def test_constants_are_130_10_and_the_algorithm_id() -> None:
    assert PERMUTATION_SEED == 130  # noqa: PLR2004
    assert K_P == 10  # noqa: PLR2004
    assert PERMUTATION_ALGORITHM == "fisher_yates_random_random_v1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"k_p": 0},
        {"n_decisions": 0},
        {"fold_index": -1},
        {"permutation_seed": -1},
        {"k_p": True},
        {"n_decisions": True},
    ],
    ids=str,
)
def test_invalid_inputs_refused(overrides: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="FamilyPermutationPlan"):
        _plan(**overrides)


@pytest.mark.parametrize(
    "permutations",
    [
        pytest.param(((0, 0, 1, 2, 3),), id="not-a-permutation"),
        pytest.param(((0, 1, 2, 3),), id="wrong-length"),
        pytest.param(((0, 1, 2, 3, 4), (4, 3, 2, 1, 0)), id="k_p-mismatch"),
    ],
)
def test_raw_construction_with_non_permutation_refused(
    permutations: tuple[tuple[int, ...], ...],
) -> None:
    with pytest.raises(ValueError, match="permutation"):
        FamilyPermutationPlan(
            permutation_seed=130, k_p=1, fold_index=0, n_decisions=5, permutations=permutations
        )
