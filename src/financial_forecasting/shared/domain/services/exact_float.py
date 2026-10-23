"""Regra única de codificação exata de float para os VOs de identidade (Stage 8.1).

Serviço de domínio stdlib-only com **dono único** da troca de um `float` `x` pela
string `"float:<repr(x)>"` — o `repr` mais curto que volta exatamente ao mesmo float.
O `CanonicalJsonHasher` arredonda todo float a 10 casas (ADR 1.4.0001); um VO que
precisa distinguir valores exatos codifica antes de delegar, e o arredondamento nunca
se aplica (ADR 6.5.0001). Consumidores:

- `PreregistrationHash` (pré-registro confirmatório, 6.5);
- `SilverContentHash` (conteúdo do silver lido pelo refresh, ADR 8.1.0002 item 1:
  "shared, not copied").

O `repr` é tomado de `float(value)`: um escalar de numpy subclasse de `float` tem
`repr` próprio (`np.float64(0.1)` no numpy 2), e a identidade não pode depender do
tipo que o leitor entrega. Para `float` nativo o valor codificado é o mesmo de antes
da extração (golden do `PreregistrationHash` inalterado).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Final

FLOAT_PREFIX: Final = "float:"


def encode_exact_float(value: float) -> str:
    """Codifica um float finito como `"float:<repr>"`.

    Raises:
        ValueError: `value` não finito (mesmo contrato fail-fast do hasher canônico,
            que deixaria de vê-lo depois da codificação).
    """
    if not math.isfinite(value):
        raise ValueError(f"valor float não-finito não é hasheável: {value!r}")
    return f"{FLOAT_PREFIX}{float(value)!r}"


def encode_floats(value: object) -> object:
    """Cópia do valor com todo `float` trocado por `"float:<repr>"`.

    Percorre mapeamentos (devolve `dict`), listas e tuplas (devolve `list`); não muta a
    entrada. `bool` fica intacto (subtipo de `int`, não de `float`) e `int` fica `int`.
    Float não finito ergue `ValueError` (ver `encode_exact_float`).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return encode_exact_float(value)
    if isinstance(value, Mapping):
        return {key: encode_floats(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [encode_floats(item) for item in value]
    return value
