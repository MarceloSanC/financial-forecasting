"""Testes unitários do value object `RunId` (domínio puro).

Cobre o critério A1 do concept: determinismo + sensibilidade a CADA um dos 9
campos (incluindo `None -> valor` nos opcionais), e I7 (`None` participa da
chave: `seed=None` difere de `seed=0`), mais I9 (frozen). Testa contra o
`FakeHasher` in-memory (port injetado).
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.run_id import RunId
from tests.fakes.shared.in_memory_hasher import FakeHasher

_BASE_KWARGS: dict[str, object | None] = {
    "asset": "AAPL",
    "feature_set_hash": "abc123",
    "trial_number": 7,
    "fold": "fold_0",
    "seed": 42,
    "model_version": "tft_v1",
    "config_signature": "cfgsig",
    "split_signature": "splitsig",
    "pipeline_version": "pipe_v1",
}

# Para cada campo, um valor distinto do base (e do tipo correto) usado para
# provar sensibilidade campo-a-campo (A1).
_FIELD_OVERRIDES: dict[str, object | None] = {
    "asset": "MSFT",
    "feature_set_hash": "def456",
    "trial_number": 8,
    "fold": "fold_1",
    "seed": 43,
    "model_version": "tft_v2",
    "config_signature": "cfgsig_other",
    "split_signature": "splitsig_other",
    "pipeline_version": "pipe_v2",
}


def _compute(hasher: FakeHasher, **overrides: object | None) -> RunId:
    kwargs = {**_BASE_KWARGS, **overrides}
    return RunId.compute(hasher=hasher, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_is_deterministic() -> None:
    """I1: mesmos 9 campos -> mesmo run_id em chamadas repetidas."""
    hasher = FakeHasher()

    assert _compute(hasher) == _compute(hasher)


@pytest.mark.unit
@pytest.mark.parametrize("field", list(_FIELD_OVERRIDES))
def test_each_field_changes_run_id(field: str) -> None:
    """A1: variar QUALQUER um dos 9 campos muda o run_id."""
    hasher = FakeHasher()

    base = _compute(hasher)
    changed = _compute(hasher, **{field: _FIELD_OVERRIDES[field]})

    assert base != changed


@pytest.mark.unit
@pytest.mark.parametrize("optional_field", ["trial_number", "fold", "seed"])
def test_none_to_value_changes_run_id(optional_field: str) -> None:
    """A1/I7: trocar None por um valor num opcional muda o run_id."""
    hasher = FakeHasher()

    as_none = _compute(hasher, **{optional_field: None})
    as_value = _compute(hasher, **{optional_field: _BASE_KWARGS[optional_field]})

    assert as_none != as_value


@pytest.mark.unit
def test_seed_none_differs_from_seed_zero() -> None:
    """I7: `seed=None` (null) NÃO colide com `seed=0` — None participa da chave."""
    hasher = FakeHasher()

    seed_none = _compute(hasher, seed=None)
    seed_zero = _compute(hasher, seed=0)

    assert seed_none != seed_zero


@pytest.mark.unit
def test_all_optionals_none_is_deterministic() -> None:
    """I7: com os 3 opcionais em None, o run_id ainda é estável e válido."""
    hasher = FakeHasher()

    first = _compute(hasher, trial_number=None, fold=None, seed=None)
    second = _compute(hasher, trial_number=None, fold=None, seed=None)

    assert first == second


@pytest.mark.unit
def test_is_frozen() -> None:
    """I9: VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    run_id = _compute(FakeHasher())

    with pytest.raises(dataclasses.FrozenInstanceError):
        run_id.value = "tampered"  # type: ignore[misc]
