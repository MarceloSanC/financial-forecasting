"""Value object PreregistrationHash — identidade do pré-registro confirmatório (Stage 6.5).

Frozen, domínio puro (stdlib-only). O valor é o sha256 hex do JSON canônico do
payload inteiro do pré-registro (`Preregistration.as_payload()`): mudar qualquer
folha muda o hash (ADR 6.5.0001 item 3, I2). Vive aqui porque o `check_layout`
só permite `hash_mapping` dentro de `shared/domain/value_objects/` — identidade
só pelos VOs de shared (precedente: `CohortHash`, ADR 5.5.0001).

**Por que codificar os floats.** O `CanonicalJsonHasher` arredonda todo float a
10 casas antes de serializar (ADR 1.4.0001): uma tolerância de 1e-12, 1e-11 ou
0.0 daria o mesmo hash, e o plano poderia mudar sem mudar a identidade. Antes de
delegar, este VO troca cada `float` `x` pela string `f"float:{x!r}"` (o `repr`
mais curto que volta exatamente ao mesmo float), de modo que o arredondamento do
hasher nunca se aplica a um valor do pré-registro. `bool` fica intacto (é
subtipo de `int`, não de `float`) e `int` fica `int`.

**Por que a coerção int/float não é daqui.** `0` e `0.0` são o mesmo plano num
campo float, mas só o VO do plano sabe o tipo declarado de cada campo; ele
coage antes de montar o payload (ADR 6.5.0001 item 2). Este VO hasheia o que
recebe: `{"x": 0}` e `{"x": 0.0}` dão hashes diferentes aqui.

O hash é delegado ao port `Hasher`; o type hint usa `TYPE_CHECKING` para
preservar a pureza do domínio (o Protocol é satisfeito por duck-typing).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

_FLOAT_PREFIX = "float:"


def _encode_floats(value: object) -> object:
    """Cópia do valor com todo `float` trocado por `"float:<repr>"`.

    Percorre mapeamentos, listas e tuplas; não muta a entrada. Float não finito
    ergue `ValueError` (mesmo contrato fail-fast do hasher canônico, que deixaria
    de vê-lo depois da codificação).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"valor float não-finito não é hasheável: {value!r}")
        return f"{_FLOAT_PREFIX}{value!r}"
    if isinstance(value, Mapping):
        return _encode_mapping(value)
    if isinstance(value, list | tuple):
        return [_encode_floats(item) for item in value]
    return value


def _encode_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    """Cópia do mapeamento com os floats codificados (ver `_encode_floats`)."""
    return {key: _encode_floats(item) for key, item in mapping.items()}


@dataclass(frozen=True)
class PreregistrationHash:
    """Hash sha256 do payload canônico de um pré-registro, com floats exatos.

    Attributes:
        value: string hex sha256 do JSON canônico do payload codificado.
    """

    value: str

    @classmethod
    def compute(cls, *, hasher: Hasher, payload: Mapping[str, object]) -> PreregistrationHash:
        """Calcula o hash do payload inteiro depois de codificar cada float."""
        return cls(value=hasher.hash_mapping(_encode_mapping(payload)))
