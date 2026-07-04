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
_CALIB = ["2020-02-20", "2020-02-21"]


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


# --- calib opcional (split 4-vias, Stage 5.1 / ADR 5.1.0003) ----------------


@pytest.mark.unit
def test_omitting_calib_is_backward_compatible() -> None:
    """Retrocompat: 3-vias e calib=None produzem a MESMA impressão de sempre."""
    hasher = FakeHasher()

    without = SplitFingerprint.compute(hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST)
    explicit_none = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=None
    )

    assert without == explicit_none


@pytest.mark.unit
def test_calib_changes_fingerprint() -> None:
    """Adicionar um calib dedicado muda a impressão (fronteira first-class)."""
    hasher = FakeHasher()

    three_way = SplitFingerprint.compute(hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST)
    four_way = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=_CALIB
    )

    assert three_way != four_way


@pytest.mark.unit
def test_calib_order_is_irrelevant() -> None:
    """A ordem DENTRO do calib não muda a impressão (sorted antes do hash)."""
    hasher = FakeHasher()
    shuffled_calib = ["2020-02-21", "2020-02-20"]

    ordered = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=_CALIB
    )
    shuffled = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=shuffled_calib
    )

    assert ordered == shuffled


@pytest.mark.unit
def test_calib_content_matters() -> None:
    """Dois folds iguais em train/val/test mas com calib distinto NÃO colidem."""
    hasher = FakeHasher()
    other_calib = ["2020-02-20", "2020-02-25"]

    base = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=_CALIB
    )
    changed = SplitFingerprint.compute(
        hasher=hasher, train=_TRAIN, val=_VAL, test=_TEST, calib=other_calib
    )

    assert base != changed
