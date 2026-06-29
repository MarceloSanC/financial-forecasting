"""Testes unitários do value object `ConfigSignature` (domínio puro).

Cobre os critérios A2 (ignora chaves voláteis + hash estável) e A5
(determinismo, ordem de chaves irrelevante) do concept, mais I9 (frozen).
Testa contra o `FakeHasher` in-memory (port injetado), nunca um mock — o fake
produz hashes reais e estáveis.
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.config_signature import (
    ConfigSignature,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_SHA256_HEX_LEN = 64


@pytest.mark.unit
def test_is_deterministic() -> None:
    """I1: mesma config -> mesma assinatura em chamadas repetidas."""
    hasher = FakeHasher()
    config = {"lr": 0.001, "epochs": 50, "model": "tft"}

    first = ConfigSignature.compute(hasher=hasher, config=config)
    second = ConfigSignature.compute(hasher=hasher, config=config)

    assert first == second
    assert first.value == second.value


@pytest.mark.unit
def test_key_order_is_irrelevant() -> None:
    """I2: ordem de inserção das chaves não muda a assinatura."""
    hasher = FakeHasher()
    config_a = {"a": 1, "b": 2, "c": 3}
    config_b = {"c": 3, "b": 2, "a": 1}

    sig_a = ConfigSignature.compute(hasher=hasher, config=config_a)
    sig_b = ConfigSignature.compute(hasher=hasher, config=config_b)

    assert sig_a == sig_b


@pytest.mark.unit
@pytest.mark.parametrize(
    "volatile_key",
    ["created_at", "started_at", "ended_at", "timestamp"],
)
def test_ignores_volatile_key(volatile_key: str) -> None:
    """I5: variar uma chave volátil não muda a assinatura."""
    hasher = FakeHasher()
    base = {"lr": 0.01, "model": "tft"}
    with_volatile = {**base, volatile_key: "2026-06-29T00:00:00"}

    sig_base = ConfigSignature.compute(hasher=hasher, config=base)
    sig_volatile = ConfigSignature.compute(hasher=hasher, config=with_volatile)

    assert sig_base == sig_volatile


@pytest.mark.unit
def test_ignores_all_volatile_keys_together() -> None:
    """I5: todas as voláteis juntas com valores diferentes não mudam a assinatura."""
    hasher = FakeHasher()
    base = {"lr": 0.01}
    noisy = {
        **base,
        "created_at": "2026-01-01",
        "started_at": "2026-01-02",
        "ended_at": "2026-01-03",
        "timestamp": 999,
    }

    assert ConfigSignature.compute(hasher=hasher, config=base) == (
        ConfigSignature.compute(hasher=hasher, config=noisy)
    )


@pytest.mark.unit
def test_non_volatile_change_changes_signature() -> None:
    """Sensibilidade: mudar um campo real muda a assinatura."""
    hasher = FakeHasher()
    sig_a = ConfigSignature.compute(hasher=hasher, config={"lr": 0.01})
    sig_b = ConfigSignature.compute(hasher=hasher, config={"lr": 0.02})

    assert sig_a != sig_b


@pytest.mark.unit
def test_value_is_hex_sha256() -> None:
    """A assinatura é um hex digest sha256 de 64 caracteres."""
    hasher = FakeHasher()
    sig = ConfigSignature.compute(hasher=hasher, config={"lr": 0.01})

    assert len(sig.value) == _SHA256_HEX_LEN
    assert all(char in "0123456789abcdef" for char in sig.value)


@pytest.mark.unit
def test_is_frozen() -> None:
    """I9: VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    sig = ConfigSignature.compute(hasher=FakeHasher(), config={"lr": 0.01})

    with pytest.raises(dataclasses.FrozenInstanceError):
        sig.value = "tampered"  # type: ignore[misc]
