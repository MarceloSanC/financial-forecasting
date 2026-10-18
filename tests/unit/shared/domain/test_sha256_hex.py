"""Testes da regra única de hash sha256 hex (issue #160).

`validate_sha256_hex` é o dono da forma dos hashes de identidade consumida pelos VOs
de `shared/domain/value_objects/` e pelos VOs do `analytics_store`.
"""

from __future__ import annotations

from hashlib import sha256

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("0" * 64, id="zeros"),
        pytest.param("0123456789abcdef" * 4, id="all-hex-digits"),
        pytest.param(sha256(b"x").hexdigest(), id="hexdigest"),
    ],
)
def test_sha256_hex_accepts(value: str) -> None:
    assert validate_sha256_hex(value, field="run_id") is None


@pytest.mark.unit
def test_sha256_hex_accepts_every_canonical_hasher_output() -> None:
    """O formato aceito é exatamente o que o hasher canônico produz."""
    hasher = CanonicalJsonHasher()

    validate_sha256_hex(hasher.hash_mapping({"a": 1}), field="value")
    validate_sha256_hex(hasher.hash_text("a|b"), field="value")


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("a" * 63, id="63-chars"),
        pytest.param("a" * 65, id="65-chars"),
        pytest.param("A" * 64, id="uppercase"),
        pytest.param("g" * 64, id="non-hex-letter"),
        pytest.param("a" * 63 + "\n", id="trailing-newline-in-64"),
        pytest.param("a" * 64 + "\n", id="trailing-newline"),
        pytest.param(" " + "a" * 63, id="leading-space"),
        pytest.param("run-1", id="label"),
        pytest.param(None, id="none"),
        pytest.param(64, id="int"),
        pytest.param(b"a" * 64, id="bytes"),
    ],
)
def test_sha256_hex_rejects(value: object) -> None:
    with pytest.raises(ValueError, match="lowercase sha256 hex of 64 characters"):
        validate_sha256_hex(value, field="run_id")


@pytest.mark.unit
def test_sha256_hex_message_names_the_field_and_the_value() -> None:
    with pytest.raises(ValueError, match=r"^RunId\.value must be .*, got 'run-1'$"):
        validate_sha256_hex("run-1", field="RunId.value")
