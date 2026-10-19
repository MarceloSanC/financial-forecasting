"""Testes unitários do value object `FamilyPartitionHash` (Stage 7.3, I17).

Contra o `CanonicalJsonHasher` real (puro, sem I/O; precedente `test_cohort_hash.py`).
"""

from __future__ import annotations

from hashlib import sha256

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.family_partition_hash import (
    FamilyPartitionHash,
)

pytestmark = pytest.mark.unit

_SHA256_HEX_LEN = 64
_FSH = sha256(b"feature-set").hexdigest()
_PARTITION: dict[str, tuple[str, ...]] = {
    "price": ("ret_1", "close_z"),
    "technical": ("rsi_14", "atr_14", "vol_21"),
    "sentiment": ("sent_mean",),
    "fundamental": ("pe_ratio", "eps_yoy"),
}


def _compute(
    partition: dict[str, tuple[str, ...]] | object = _PARTITION, feature_set_hash: object = _FSH
) -> FamilyPartitionHash:
    return FamilyPartitionHash.compute(
        hasher=CanonicalJsonHasher(),
        feature_set_hash=feature_set_hash,  # type: ignore[arg-type]
        partition=partition,  # type: ignore[arg-type]
    )


def test_value_is_the_canonical_hash_of_the_documented_payload() -> None:
    expected = CanonicalJsonHasher().hash_mapping(
        {
            "feature_set_hash": _FSH,
            "partition": {
                "price": ["close_z", "ret_1"],
                "technical": ["atr_14", "rsi_14", "vol_21"],
                "sentiment": ["sent_mean"],
                "fundamental": ["eps_yoy", "pe_ratio"],
            },
        }
    )
    assert _compute().value == expected


def test_order_within_a_family_does_not_change_the_hash() -> None:
    shuffled = {family: tuple(reversed(features)) for family, features in _PARTITION.items()}
    reordered_families = dict(reversed(list(_PARTITION.items())))
    assert _compute(shuffled) == _compute()
    assert _compute(reordered_families) == _compute()


def test_moving_a_feature_between_families_changes_the_hash() -> None:
    moved = dict(_PARTITION)
    moved["price"] = ("ret_1", "close_z", "vol_21")
    moved["technical"] = ("rsi_14", "atr_14")
    # mesmos nomes de família e mesmo conjunto de features: só a partição muda
    assert set(moved) == set(_PARTITION)
    assert _compute(moved) != _compute()


def test_feature_set_hash_changes_the_hash() -> None:
    other = sha256(b"other-feature-set").hexdigest()
    assert _compute(feature_set_hash=other) != _compute()


@pytest.mark.parametrize(
    "partition",
    [
        pytest.param({**_PARTITION, "price": ("ret_1", "ret_1")}, id="within-family"),
        pytest.param({**_PARTITION, "sentiment": ("sent_mean", "rsi_14")}, id="across-families"),
    ],
)
def test_repeated_feature_within_or_across_families_refused(
    partition: dict[str, tuple[str, ...]],
) -> None:
    with pytest.raises(ValueError, match="repeated"):
        _compute(partition)


@pytest.mark.parametrize(
    ("partition", "match"),
    [
        pytest.param({}, "partition must be a non-empty mapping", id="empty-partition"),
        pytest.param({**_PARTITION, "sentiment": ()}, "partition.sentiment", id="empty-family"),
        pytest.param({**_PARTITION, "sentiment": "sent_mean"}, "partition.sentiment", id="str"),
        pytest.param({**_PARTITION, "": ("x",)}, "partition family", id="empty-family-name"),
        pytest.param({**_PARTITION, "sentiment": ("",)}, "partition.sentiment", id="empty-name"),
        pytest.param([("price", ("a",))], "partition must be", id="not-a-mapping"),
    ],
)
def test_empty_partition_or_family_refused(partition: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _compute(partition)


@pytest.mark.parametrize("value", ["", "abc", _FSH.upper(), _FSH[:-1], None, 7], ids=repr)
def test_feature_set_hash_must_be_64_hex(value: object) -> None:
    with pytest.raises(ValueError, match="feature_set_hash"):
        _compute(feature_set_hash=value)


def test_value_is_64_hex() -> None:
    value = _compute().value
    assert len(value) == _SHA256_HEX_LEN
    assert set(value) <= set("0123456789abcdef")


def test_raw_construction_with_invalid_value_refused() -> None:
    with pytest.raises(ValueError, match=r"^FamilyPartitionHash\.value must be"):
        FamilyPartitionHash(value="xyz")
    assert FamilyPartitionHash(value=_FSH).value == _FSH
