"""Contract test do port `Hasher` — paridade FakeHasher ↔ CanonicalJsonHasher.

Um ÚNICO contrato parametrizado sobre `[FakeHasher(), CanonicalJsonHasher()]`
prova que ambas as implementações honram a MESMA semântica canônica
(invariante I11, critério A8): determinismo, ordem de chaves irrelevante,
None->null, floats canonicalizados, NaN/±inf -> ValueError, e `hash_text`
determinístico e sensível à ordem.

O REFORÇO de paridade (`fake.hash_mapping(p) == real.hash_mapping(p)` sobre
payloads fixos) prova que fake e real produzem o MESMO hash — não só o mesmo
comportamento — resolvendo a duplicação da regra de canonicalização entre os
dois (a cópia mínima do FakeHasher da task-02).
"""

import math

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher
from tests.fakes.shared.in_memory_hasher import FakeHasher

# Bateria de payloads canônicos fixos para a igualdade cruzada fake==real.
_FIXED_MAPPINGS: list[dict[str, object]] = [
    {},
    {"a": 1, "b": "x", "c": None},
    {"asset": "AAPL", "row_count": 252, "close_sum": 1234.5, "volume_sum": 9.0},
    {"nested": {"k": [1, 2, 3], "f": 3.14159}, "flag": True},
    {"z": 1, "a": 2, "m": 3},
]
_FIXED_TEXTS: list[str] = ["", "a|b|c", "feature_one|feature_two", "AAPL"]


@pytest.fixture(params=[FakeHasher(), CanonicalJsonHasher()], ids=["fake", "real"])
def hasher(request: pytest.FixtureRequest) -> Hasher:
    """Parametriza o contrato sobre o fake e o adapter real."""
    impl: Hasher = request.param
    return impl


@pytest.mark.contract
def test_hash_mapping_is_deterministic(hasher: Hasher) -> None:
    """I1: mesmo mapping -> mesmo hash em duas chamadas."""
    payload = {"a": 1, "b": 2.0, "c": "x"}

    assert hasher.hash_mapping(payload) == hasher.hash_mapping(payload)


@pytest.mark.contract
def test_hash_mapping_key_order_irrelevant(hasher: Hasher) -> None:
    """I2: ordem de inserção das chaves não muda o hash."""
    first = hasher.hash_mapping({"a": 1, "b": 2, "c": 3})
    second = hasher.hash_mapping({"c": 3, "a": 1, "b": 2})

    assert first == second


@pytest.mark.contract
def test_none_participates_in_key(hasher: Hasher) -> None:
    """None -> null: chave com None difere de chave ausente."""
    with_none = hasher.hash_mapping({"a": 1, "b": None})
    without_key = hasher.hash_mapping({"a": 1})

    assert with_none != without_key


@pytest.mark.contract
def test_floats_canonicalized_below_precision_floor(hasher: Hasher) -> None:
    """I3: floats round(.,10)-equivalentes -> mesmo hash."""
    base = hasher.hash_mapping({"x": 100.0})
    noisy = hasher.hash_mapping({"x": 100.000000000001})

    assert base == noisy


@pytest.mark.contract
def test_real_float_difference_changes_hash(hasher: Hasher) -> None:
    """I3: diferença real de float -> hash diferente."""
    assert hasher.hash_mapping({"x": 1.0}) != hasher.hash_mapping({"x": 2.0})


@pytest.mark.contract
def test_nan_raises_value_error(hasher: Hasher) -> None:
    """I4: NaN no payload -> ValueError."""
    with pytest.raises(ValueError, match="não-finito"):
        hasher.hash_mapping({"x": math.nan})


@pytest.mark.contract
@pytest.mark.parametrize("non_finite", [math.inf, -math.inf])
def test_inf_raises_value_error(hasher: Hasher, non_finite: float) -> None:
    """I4: ±inf no payload -> ValueError."""
    with pytest.raises(ValueError, match="não-finito"):
        hasher.hash_mapping({"x": non_finite})


@pytest.mark.contract
def test_nested_nan_raises_value_error(hasher: Hasher) -> None:
    """I4: NaN aninhado (dentro de mapping/lista) também é rejeitado."""
    with pytest.raises(ValueError, match="não-finito"):
        hasher.hash_mapping({"outer": {"inner": [1.0, math.nan]}})


@pytest.mark.contract
def test_hash_text_is_deterministic(hasher: Hasher) -> None:
    """hash_text determinístico: mesmo texto -> mesmo hash."""
    assert hasher.hash_text("a|b|c") == hasher.hash_text("a|b|c")


@pytest.mark.contract
def test_hash_text_is_order_sensitive(hasher: Hasher) -> None:
    """hash_text sensível à ordem: 'a|b' != 'b|a'."""
    assert hasher.hash_text("a|b") != hasher.hash_text("b|a")


@pytest.mark.contract
@pytest.mark.parametrize("payload", _FIXED_MAPPINGS)
def test_fake_and_real_produce_same_mapping_hash(payload: dict[str, object]) -> None:
    """I11: fake e real produzem o MESMO hash de mapping (igualdade cruzada)."""
    fake = FakeHasher()
    real = CanonicalJsonHasher()

    assert fake.hash_mapping(payload) == real.hash_mapping(payload)


@pytest.mark.contract
@pytest.mark.parametrize("text", _FIXED_TEXTS)
def test_fake_and_real_produce_same_text_hash(text: str) -> None:
    """I11: fake e real produzem o MESMO hash de texto (igualdade cruzada)."""
    fake = FakeHasher()
    real = CanonicalJsonHasher()

    assert fake.hash_text(text) == real.hash_text(text)
