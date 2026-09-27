"""Testes unitários do value object `DatasetContentFingerprint` (Stage 5.5, A4).

Contra o `CanonicalJsonHasher` real: estável para o mesmo conteúdo; muda com
ativo, timestamp, valor e ordem das colunas; recusa NaN e colunas desalinhadas.
"""

import math

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

_TIMESTAMPS = ("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00")
_COLUMNS = {"f_a": (1.0, 2.0), "target_return": (0.01, 0.02)}


def _fp(**overrides: object) -> DatasetContentFingerprint:
    kwargs: dict[str, object] = {
        "asset_id": "AAPL",
        "timestamps": _TIMESTAMPS,
        "columns": _COLUMNS,
        **overrides,
    }
    return DatasetContentFingerprint.compute(hasher=CanonicalJsonHasher(), **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_same_content_same_fingerprint() -> None:
    assert _fp() == _fp(columns={"f_a": [1.0, 2.0], "target_return": [0.01, 0.02]})


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"asset_id": "MSFT"},
        {"timestamps": ("2024-01-02T00:00:00+00:00", "2024-01-04T00:00:00+00:00")},
        {"columns": {"f_a": (1.0, 2.5), "target_return": (0.01, 0.02)}},
        {"columns": {"target_return": (0.01, 0.02), "f_a": (1.0, 2.0)}},
    ],
    ids=["asset", "timestamp", "value", "column-order"],
)
def test_any_content_change_changes_the_fingerprint(overrides: dict[str, object]) -> None:
    assert _fp(**overrides) != _fp()


@pytest.mark.unit
def test_nan_is_rejected() -> None:
    with pytest.raises(ValueError):
        _fp(columns={"f_a": (1.0, math.nan), "target_return": (0.01, 0.02)})


@pytest.mark.unit
def test_misaligned_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="2 timestamps"):
        _fp(columns={"f_a": (1.0,), "target_return": (0.01, 0.02)})
