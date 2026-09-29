"""Testes do `gold_build_order` (Stage 6.4 Task 06; A1, I14, C1; ADR 6.4.0001)."""

from __future__ import annotations

import itertools
import random

import pytest

from financial_forecasting.features.evaluation.domain.services.gold_build_order import (
    gold_build_order,
)

_QUALITY = "quality_checks"
# Os cinco builders do concept 6.4 §4: as quatro tabelas confirmatórias dependem da de
# quality checks (a única que roda com o refresh bloqueado).
_CONCEPT_BUILDERS: tuple[tuple[str, frozenset[str]], ...] = (
    (_QUALITY, frozenset()),
    ("metrics_by_run", frozenset({_QUALITY})),
    ("calibration_table", frozenset({_QUALITY})),
    ("dm_results", frozenset({_QUALITY})),
    ("mcs_results", frozenset({_QUALITY})),
)
_N_PERMUTATIONS = 20


@pytest.mark.unit
def test_order_invariant_to_registration() -> None:
    """Mesma ordem para 20 permutações do registro dos cinco builders."""
    rng = random.Random(20260929)
    permutations = list(itertools.permutations(_CONCEPT_BUILDERS))
    chosen = rng.sample(permutations, _N_PERMUTATIONS)
    orders = {gold_build_order(list(permutation)) for permutation in chosen}
    assert len(orders) == 1
    [order] = orders
    assert sorted(order) == sorted(name for name, _ in _CONCEPT_BUILDERS)


@pytest.mark.unit
def test_dependencies_first() -> None:
    order = gold_build_order(_CONCEPT_BUILDERS)
    assert order[0] == _QUALITY
    for name, depends_on in _CONCEPT_BUILDERS:
        for dependency in depends_on:
            assert order.index(dependency) < order.index(name)


@pytest.mark.unit
def test_dependencies_first_chain() -> None:
    chain = (("c", frozenset({"b"})), ("a", frozenset()), ("b", frozenset({"a"})))
    assert gold_build_order(chain) == ("a", "b", "c")
    assert gold_build_order(()) == ()


@pytest.mark.unit
def test_duplicate_name_raises() -> None:
    with pytest.raises(ValueError, match=r"repeated: \['dm_results'\]"):
        gold_build_order((*_CONCEPT_BUILDERS, ("dm_results", frozenset())))


@pytest.mark.unit
def test_cycle_raises() -> None:
    cyclic = (
        ("a", frozenset({"c"})),
        ("b", frozenset({"a"})),
        ("c", frozenset({"b"})),
    )
    with pytest.raises(ValueError, match="builder dependency cycle") as raised:
        gold_build_order(cyclic)
    for name in ("a", "b", "c"):
        assert repr(name) in str(raised.value)


@pytest.mark.unit
def test_unknown_dependency_raises() -> None:
    with pytest.raises(
        ValueError, match="'dm_results' depends on 'ghost', which is not registered"
    ):
        gold_build_order(((_QUALITY, frozenset()), ("dm_results", frozenset({"ghost", _QUALITY}))))


@pytest.mark.unit
def test_self_dependency_raises() -> None:
    with pytest.raises(ValueError, match="'mcs_results' depends on itself"):
        gold_build_order(((_QUALITY, frozenset()), ("mcs_results", frozenset({"mcs_results"}))))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("builders", "message"),
    [
        pytest.param((("", frozenset()),), "non-empty str", id="empty-name"),
        pytest.param(((3, frozenset()),), "non-empty str", id="name-int"),
        pytest.param((("a", {"b"}),), "must be a frozenset", id="deps-set"),
    ],
)
def test_builder_shape_errors_raise(builders: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        gold_build_order(builders)  # type: ignore[arg-type]
