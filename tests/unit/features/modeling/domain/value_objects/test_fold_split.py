"""Testes unitários do value object `FoldSplit` (domínio puro).

Cobrem construção válida (I8), imutabilidade e cada violação das invariantes de
disjunção/ordenação (I1/I2): ordem de bloco quebrada, sobreposição, lista vazia,
não-crescente, `fold_index` negativo.
"""

import dataclasses

import pytest

from financial_forecasting.features.modeling.domain.value_objects.fold_split import (
    FoldSplit,
)
from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_TRAIN = ("2020-01-01", "2020-01-02", "2020-01-03")
_EARLY_STOP = ("2020-01-10", "2020-01-11")
_CALIB = ("2020-01-20", "2020-01-21")
_TEST = ("2020-01-30", "2020-01-31")


def _fingerprint() -> SplitFingerprint:
    return SplitFingerprint.compute(
        hasher=FakeHasher(),
        train=list(_TRAIN),
        val=list(_EARLY_STOP),
        test=list(_TEST),
        calib=list(_CALIB),
    )


def _fold(**overrides: object) -> FoldSplit:
    kwargs: dict[str, object] = {
        "fold_index": 0,
        "train": _TRAIN,
        "early_stop": _EARLY_STOP,
        "calib": _CALIB,
        "test": _TEST,
        "fingerprint": _fingerprint(),
    }
    kwargs.update(overrides)
    return FoldSplit(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_construct_valid_fold() -> None:
    """Fold com 4 blocos ordenados e disjuntos constrói e preserva os campos."""
    fold = _fold()

    assert fold.fold_index == 0
    assert fold.train == _TRAIN
    assert fold.early_stop == _EARLY_STOP
    assert fold.calib == _CALIB
    assert fold.test == _TEST
    assert fold.fingerprint == _fingerprint()


@pytest.mark.unit
def test_is_frozen() -> None:
    """VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    fold = _fold()

    with pytest.raises(dataclasses.FrozenInstanceError):
        fold.fold_index = 3  # type: ignore[misc]


@pytest.mark.unit
def test_negative_fold_index_raises() -> None:
    """fold_index < 0 é rejeitado."""
    with pytest.raises(ValueError, match="fold_index"):
        _fold(fold_index=-1)


@pytest.mark.unit
@pytest.mark.parametrize("block", ["train", "early_stop", "calib", "test"])
def test_empty_block_raises(block: str) -> None:
    """Qualquer bloco vazio é rejeitado."""
    with pytest.raises(ValueError, match=f"{block} must be non-empty"):
        _fold(**{block: ()})


@pytest.mark.unit
def test_non_increasing_block_raises() -> None:
    """Bloco com timestamps fora de ordem (ou duplicados) é rejeitado."""
    with pytest.raises(ValueError, match="strictly increasing"):
        _fold(train=("2020-01-03", "2020-01-01"))


@pytest.mark.unit
def test_block_out_of_order_raises() -> None:
    """early_stop antes do fim do train (fronteira invertida) é rejeitado."""
    with pytest.raises(ValueError, match="time-ordered and disjoint"):
        _fold(early_stop=("2020-01-02", "2020-01-12"))


@pytest.mark.unit
def test_overlap_between_calib_and_test_raises() -> None:
    """Sobreposição calib/test (calib[-1] == test[0]) é rejeitada."""
    with pytest.raises(ValueError, match="time-ordered and disjoint"):
        _fold(calib=("2020-01-20", "2020-01-30"))


@pytest.mark.unit
def test_calib_after_test_raises() -> None:
    """calib inteiramente após o test (ordem trocada) é rejeitado."""
    with pytest.raises(ValueError, match="time-ordered and disjoint"):
        _fold(calib=("2020-02-10", "2020-02-11"))
