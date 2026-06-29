"""Testes unitários do value object `SplitFingerprint` (domínio puro).

Cobre o critério A3 (invariante à ordem dentro de cada split, sensível ao
conteúdo) e A5 (determinismo) do concept, mais I9 (frozen). Testa contra o
`FakeHasher` in-memory (port injetado).
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_TRAIN = ["2020-01-01", "2020-01-02", "2020-01-03"]
_VAL = ["2020-02-01", "2020-02-02"]
_TEST = ["2020-03-01"]


@pytest.mark.unit
def test_is_deterministic() -> None:
    """I1: mesmos splits -> mesma impressão em chamadas repetidas."""
    hasher = FakeHasher()

    first = SplitFingerprint.compute(hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST)
    second = SplitFingerprint.compute(hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST)

    assert first == second


@pytest.mark.unit
def test_order_within_split_is_irrelevant() -> None:
    """I6: trocar a ordem DENTRO de um split não muda a impressão."""
    hasher = FakeHasher()
    shuffled_train = ["2020-01-03", "2020-01-01", "2020-01-02"]

    ordered = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST
    )
    shuffled = SplitFingerprint.compute(
        hasher=hasher, train=shuffled_train, val=_VAL, test=_TEST
    )

    assert ordered == shuffled


@pytest.mark.unit
def test_content_of_split_matters() -> None:
    """I6: mudar o CONTEÚDO de um split muda a impressão."""
    hasher = FakeHasher()
    different_train = ["2020-01-01", "2020-01-02", "2020-01-99"]

    base = SplitFingerprint.compute(hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST)
    changed = SplitFingerprint.compute(
        hasher=hasher, train=different_train, val=_VAL, test=_TEST
    )

    assert base != changed


@pytest.mark.unit
def test_split_assignment_matters() -> None:
    """Mover um timestamp de train para val muda a impressão (split é estrutura)."""
    hasher = FakeHasher()

    base = SplitFingerprint.compute(
        hasher=hasher,
        train=["2020-01-01", "2020-01-02"],
        val=["2020-02-01"],
        test=_TEST,
    )
    moved = SplitFingerprint.compute(
        hasher=hasher,
        train=["2020-01-01"],
        val=["2020-02-01", "2020-01-02"],
        test=_TEST,
    )

    assert base != moved


@pytest.mark.unit
def test_is_frozen() -> None:
    """I9: VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    fingerprint = SplitFingerprint.compute(
        hasher=FakeHasher(), train=_TRAIN, val=_VAL, test=_TEST
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        fingerprint.value = "tampered"  # type: ignore[misc]
