"""Testes unitários do value object `DatasetFingerprint` (domínio puro).

Cobre o critério A4 do concept: canonicalização de floats (mesmo valor
matemático arredondado a 10 casas -> mesmo hash; diferença real -> hash
diferente) e rejeição de NaN/±inf (C1/C2 -> ValueError), mais I1/I9. Testa
contra o `FakeHasher` in-memory (port injetado), que aplica a mesma regra
canônica do adapter real.
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_BASE_KWARGS: dict[str, object] = {
    "asset": "AAPL",
    "timestamp_min": "2020-01-01",
    "timestamp_max": "2020-12-31",
    "row_count": 252,
    "close_sum": 12345.678,
    "volume_sum": 9_876_543.0,
    "parquet_file_hash": "deadbeef",
}


def _compute(hasher: FakeHasher, **overrides: object) -> DatasetFingerprint:
    kwargs = {**_BASE_KWARGS, **overrides}
    return DatasetFingerprint.compute(hasher=hasher, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_is_deterministic() -> None:
    """I1: mesmo dataset -> mesma impressão em chamadas repetidas."""
    hasher = FakeHasher()

    assert _compute(hasher) == _compute(hasher)


@pytest.mark.unit
def test_float_below_precision_floor_does_not_change_hash() -> None:
    """A4: diferença abaixo de 1e-10 (round a 10 casas) -> mesmo hash."""
    hasher = FakeHasher()

    base = _compute(hasher, close_sum=100.0)
    noisy = _compute(hasher, close_sum=100.000000000001)

    assert base == noisy


@pytest.mark.unit
def test_real_float_difference_changes_hash() -> None:
    """A4: diferença real (acima do piso de arredondamento) -> hash diferente."""
    hasher = FakeHasher()

    base = _compute(hasher, close_sum=100.0)
    different = _compute(hasher, close_sum=100.5)

    assert base != different


@pytest.mark.unit
@pytest.mark.parametrize("field", ["close_sum", "volume_sum"])
def test_nan_raises_value_error(field: str) -> None:
    """C1: NaN em close_sum/volume_sum -> ValueError (fail-fast)."""
    hasher = FakeHasher()

    with pytest.raises(ValueError, match="não-finito"):
        _compute(hasher, **{field: float("nan")})


@pytest.mark.unit
@pytest.mark.parametrize("field", ["close_sum", "volume_sum"])
@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf")])
def test_inf_raises_value_error(field: str, non_finite: float) -> None:
    """C2: +inf/-inf em close_sum/volume_sum -> ValueError."""
    hasher = FakeHasher()

    with pytest.raises(ValueError, match="não-finito"):
        _compute(hasher, **{field: non_finite})


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    ["asset", "timestamp_min", "timestamp_max", "parquet_file_hash"],
)
def test_each_string_field_changes_hash(field: str) -> None:
    """Sensibilidade: alterar qualquer campo string muda a impressão."""
    hasher = FakeHasher()

    base = _compute(hasher)
    changed = _compute(hasher, **{field: "DIFFERENT"})

    assert base != changed


@pytest.mark.unit
def test_row_count_change_changes_hash() -> None:
    """Sensibilidade: row_count distinto muda a impressão."""
    hasher = FakeHasher()

    assert _compute(hasher, row_count=252) != _compute(hasher, row_count=253)


@pytest.mark.unit
def test_is_frozen() -> None:
    """I9: VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    fingerprint = _compute(FakeHasher())

    with pytest.raises(dataclasses.FrozenInstanceError):
        fingerprint.value = "tampered"  # type: ignore[misc]
