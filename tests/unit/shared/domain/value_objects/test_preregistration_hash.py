"""Testes unitários do value object `PreregistrationHash` (Stage 6.5, A1 / I2 / I3).

Contra o `CanonicalJsonHasher` real (puro, sem I/O; precedente
`test_cohort_hash.py`): o hasher sozinho arredonda floats a 10 casas, o VO
codifica cada float exatamente antes de delegar. A coerção int/float é do
chamador (o VO do plano), não daqui.
"""

import copy
import dataclasses

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)

_SHA256_HEX_LEN = 64
_PAYLOAD: dict[str, object] = {
    "name": "test_plan",
    "revision": 0,
    "horizons": [1, 7],
    "h1_gate": {"degeneracy_tolerance": 1e-12, "gate_band_level": 0.975},
    "power_scenarios": [{"label": "w", "lower_rate": 0.125, "upper_rate": 0.125}],
    "flag": True,
}


def _compute(payload: dict[str, object]) -> PreregistrationHash:
    return PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=payload)


@pytest.mark.unit
def test_prereg_hash_float_encoded_exactly() -> None:
    hasher = CanonicalJsonHasher()
    tight = {"tol": 1e-12}
    loose = {"tol": 1e-11}

    # O hasher sozinho arredonda a 10 casas: prova de que o teste discrimina.
    assert hasher.hash_mapping(tight) == hasher.hash_mapping(loose)
    assert _compute(tight) != _compute(loose)
    assert len(_compute(tight).value) == _SHA256_HEX_LEN
    assert _compute(tight).value == hasher.hash_mapping({"tol": "float:1e-12"})


@pytest.mark.unit
def test_prereg_hash_nested_floats_encoded() -> None:
    hasher = CanonicalJsonHasher()
    nested_a = {"outer": {"inner": [1e-12, {"deep": 2e-13}]}, "pair": (3e-12,)}
    nested_b = {"outer": {"inner": [1e-11, {"deep": 2e-13}]}, "pair": (3e-12,)}
    nested_c = {"outer": {"inner": [1e-12, {"deep": 2e-12}]}, "pair": (3e-12,)}
    nested_d = {"outer": {"inner": [1e-12, {"deep": 2e-13}]}, "pair": (3e-11,)}

    assert hasher.hash_mapping(nested_a) == hasher.hash_mapping(nested_b)
    hashes = {_compute(p) for p in (nested_a, nested_b, nested_c, nested_d)}
    assert len(hashes) == 4  # noqa: PLR2004 — quatro payloads distintos
    expected = {
        "outer": {"inner": ["float:1e-12", {"deep": "float:2e-13"}]},
        "pair": ["float:3e-12"],
    }
    assert _compute(nested_a).value == hasher.hash_mapping(expected)


@pytest.mark.unit
def test_prereg_hash_int_not_coerced() -> None:
    assert _compute({"x": 0}) != _compute({"x": 0.0})
    assert _compute({"x": 0}).value == CanonicalJsonHasher().hash_mapping({"x": 0})


@pytest.mark.unit
def test_prereg_hash_bool_untouched() -> None:
    hasher = CanonicalJsonHasher()

    assert _compute({"flag": True}).value == hasher.hash_mapping({"flag": True})
    assert _compute({"flag": True}).value != hasher.hash_mapping({"flag": "float:1.0"})
    assert _compute({"flag": True}) != _compute({"flag": 1.0})


@pytest.mark.unit
def test_prereg_hash_key_order_irrelevant() -> None:
    reordered = dict(reversed(list(_PAYLOAD.items())))

    assert _compute(reordered) == _compute(_PAYLOAD)


@pytest.mark.unit
def test_prereg_hash_payload_not_mutated() -> None:
    payload = copy.deepcopy(_PAYLOAD)

    _compute(payload)

    assert payload == _PAYLOAD
    h1_gate = payload["h1_gate"]
    assert isinstance(h1_gate, dict)
    assert isinstance(h1_gate["degeneracy_tolerance"], float)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_float_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="não-finito"):
        _compute({"x": [bad]})


@pytest.mark.unit
def test_is_frozen() -> None:
    digest = _compute(_PAYLOAD)

    with pytest.raises(dataclasses.FrozenInstanceError):
        digest.value = "x"  # type: ignore[misc]
