"""Contract test do port `Hasher` — a semântica canônica declarada no port.

Prova, contra o `CanonicalJsonHasher`, as propriedades que o docstring do port
promete (ADR 1.4.0001): determinismo (I1), ordem de chaves irrelevante (I2),
`None` -> `null`, floats canonicalizados por arredondamento declarado com a
precisão OBSERVÁVEL em exatamente 10 casas (I3), NaN/±inf -> `ValueError` (I4),
e `hash_text` determinístico e sensível à ordem.

Há uma única implementação, de propósito. O `FakeHasher` que parametrizava
este contrato sobre `[fake, real]` era cópia byte-a-byte do adapter — um
contract test entre duas cópias não tem proposição a verificar (issue #70).
Como o hasher é puro, determinístico e sem I/O, não existe shortcut legítimo
para um fake oferecer (Meszaros), e os testes de domínio/use case injetam o
próprio adapter. O VALOR do esquema (byte-compat com hashes persistidos) fica
pinado à parte em `test_hasher_golden.py`; aqui ficam as propriedades.
"""

import math
from collections.abc import Callable

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher


@pytest.fixture
def hasher() -> Hasher:
    """A única implementação do port (ver docstring do módulo)."""
    return CanonicalJsonHasher()


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
def test_floats_canonicalized_inside_nested_mapping(hasher: Hasher) -> None:
    """I3 recursivo: float sub-precisão DENTRO de um mapping aninhado é arredondado.

    Pina a recursão de `_canonicalize` em mappings: sem ela, o float aninhado
    iria cru para o JSON e o ruído de último-ULP mudaria o hash (mutante
    'não recursa' sobrevive). Top-level já é coberto; o aninhado não era.
    """
    base = hasher.hash_mapping({"outer": {"f": 100.0}})
    noisy = hasher.hash_mapping({"outer": {"f": 100.000000000001}})

    assert base == noisy


@pytest.mark.contract
def test_floats_canonicalized_inside_nested_list(hasher: Hasher) -> None:
    """I3 recursivo: float sub-precisão DENTRO de uma lista é arredondado.

    Pina a recursão de `_canonicalize` em list/tuple — análogo ao caso de
    mapping aninhado, fechando o branch de sequência.
    """
    base = hasher.hash_mapping({"series": [1.0, 100.0]})
    noisy = hasher.hash_mapping({"series": [1.0, 100.000000000001]})

    assert base == noisy


@pytest.mark.contract
def test_nested_real_float_difference_changes_hash(hasher: Hasher) -> None:
    """I3 recursivo: diferença real de float aninhado AINDA muda o hash.

    Garante que a recursão arredonda mas não achata sinal real (não é a
    identidade): um delta acima do piso de 1e-10 dentro de estrutura aninhada
    continua discriminando.
    """
    base = hasher.hash_mapping({"outer": {"f": 100.0}, "series": [1.0]})
    different = hasher.hash_mapping({"outer": {"f": 100.5}, "series": [1.0]})

    assert base != different


# -- I3 observável: float com 12 casas decimais pina a precisão em EXATAMENTE 10 --
#
# As fixtures `100.000000000001` acima só exigem que o ruído COLAPSE — passam
# para qualquer precisão <= 12 e por isso não distinguem `round(., 10)` de
# `round(., 5)` (issue #70: baixar a precisão era invisível à suíte inteira).
# Aqui a 10ª casa é significativa: as casas 11-12 têm de sumir E a 10ª tem de
# sobreviver, o que só `round(., 10)` satisfaz nas duas direções.

_TWELVE_DECIMALS = 1.234567891234
_TEN_DECIMALS = 1.2345678912  # o que resta após round(., 10)
_NINE_DECIMALS = 1.234567891  # difere na 10ª casa


def _at_top_level(value: float) -> dict[str, object]:
    return {"x": value}


def _inside_mapping(value: float) -> dict[str, object]:
    return {"outer": {"f": value}}


def _inside_list(value: float) -> dict[str, object]:
    return {"series": [value, 2.0]}


_SHAPES = [_at_top_level, _inside_mapping, _inside_list]
_SHAPE_IDS = ["top_level", "nested_mapping", "nested_list"]


@pytest.mark.contract
@pytest.mark.parametrize("shape", _SHAPES, ids=_SHAPE_IDS)
def test_digits_beyond_the_tenth_decimal_do_not_change_the_hash(
    hasher: Hasher, shape: Callable[[float], dict[str, object]]
) -> None:
    """I3: as casas 11-12 são descartadas — 12 casas hasheiam como 10.

    Falha se a precisão declarada SUBIR (>= 11): a 11ª casa passaria a
    discriminar e os dois payloads divergiriam.
    """
    twelve = hasher.hash_mapping(shape(_TWELVE_DECIMALS))
    ten = hasher.hash_mapping(shape(_TEN_DECIMALS))

    assert twelve == ten


@pytest.mark.contract
@pytest.mark.parametrize("shape", _SHAPES, ids=_SHAPE_IDS)
def test_the_tenth_decimal_still_discriminates(
    hasher: Hasher, shape: Callable[[float], dict[str, object]]
) -> None:
    """I3: a 10ª casa sobrevive — 12 casas NÃO hasheiam como 9.

    Falha se a precisão declarada DESCER (<= 9): a 10ª casa seria descartada e
    os dois payloads colapsariam no mesmo hash — a mutação que era invisível.
    """
    twelve = hasher.hash_mapping(shape(_TWELVE_DECIMALS))
    nine = hasher.hash_mapping(shape(_NINE_DECIMALS))

    assert twelve != nine


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
