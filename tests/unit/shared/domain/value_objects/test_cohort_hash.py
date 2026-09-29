"""Testes unitários do value object `CohortHash` (Stage 5.5, A4 / I2).

Contra o `CanonicalJsonHasher` real (puro, sem I/O): estável para o mesmo
payload e para ordem de chaves diferente; muda com qualquer campo; sha256 hex.
"""

import dataclasses

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

_SHA256_HEX_LEN = 64
_PAYLOAD: dict[str, object] = {
    "name": "aapl_confirmatory",
    "revision": 0,
    "horizons": [1, 7],
    "quantile_levels": [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98],
    "seeds": [11, 22],
    "geometry": {"n_folds": 6, "test_size": 252},
}


@pytest.mark.unit
def test_same_payload_same_hash_regardless_of_key_order() -> None:
    hasher = CanonicalJsonHasher()
    reordered = dict(reversed(list(_PAYLOAD.items())))

    first = CohortHash.compute(hasher=hasher, payload=_PAYLOAD)
    second = CohortHash.compute(hasher=hasher, payload=reordered)

    assert first == second
    assert len(first.value) == _SHA256_HEX_LEN


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("revision", 1),
        ("horizons", [1]),
        ("quantile_levels", [0.05, 0.5, 0.95]),
        ("seeds", [22, 11]),
        ("geometry", {"n_folds": 5, "test_size": 252}),
    ],
)
def test_any_field_change_changes_the_hash(key: str, value: object) -> None:
    hasher = CanonicalJsonHasher()
    changed = {**_PAYLOAD, key: value}

    assert CohortHash.compute(hasher=hasher, payload=changed) != CohortHash.compute(
        hasher=hasher, payload=_PAYLOAD
    )


@pytest.mark.unit
def test_is_frozen() -> None:
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=_PAYLOAD)

    with pytest.raises(dataclasses.FrozenInstanceError):
        cohort_hash.value = "x"  # type: ignore[misc]
