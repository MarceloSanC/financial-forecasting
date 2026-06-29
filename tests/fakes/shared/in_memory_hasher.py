"""Fake in-memory do port `Hasher` — determinístico, NÃO um mock.

`FakeHasher` aplica a MESMA semântica canônica do adapter real
(`CanonicalJsonHasher`): `json.dumps(sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` + sha256 hex, floats arredondados a 10 casas, NaN/±inf
rejeitados com `ValueError`, `None` -> `null`. Produz hashes reais e estáveis,
idênticos em comportamento ao adapter real (invariante I11, ADR 1.4.0001).

Como o adapter ainda não existe quando o fake é escrito (ordem inside-out), o
fake encapsula sua própria cópia mínima da regra de canonicalização. A
duplicação é resolvida no contract test (`tests/contract/shared/
test_hasher_contract.py`), que prova `fake.hash_mapping(p) ==
real.hash_mapping(p)` para uma bateria de payloads fixos — se divergirem, o
teste de igualdade cruzada falha.
"""

import json
import math
from collections.abc import Mapping
from hashlib import sha256

_FLOAT_PRECISION = 10


def _canonicalize(value: object) -> object:
    """Canonicaliza recursivamente um valor antes da serialização JSON.

    Arredonda floats a `_FLOAT_PRECISION` casas, rejeita NaN/±inf com
    `ValueError` e preserva os demais tipos. `bool` é tratado ANTES de `float`
    porque `bool` é subtipo de `int` em Python (não deve ser arredondado).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"valor float não-finito não é hasheável: {value!r}")
        return round(value, _FLOAT_PRECISION)
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_canonicalize(item) for item in value]
    return value


class FakeHasher:
    """Implementação in-memory determinística do contrato `Hasher`."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        """sha256 hex sobre o JSON canônico do mapping (ver módulo)."""
        canonical = _canonicalize(payload)
        text = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return sha256(text.encode("utf-8")).hexdigest()

    def hash_text(self, text: str) -> str:
        """sha256 hex sobre os bytes UTF-8 do texto (sensível à ordem)."""
        return sha256(text.encode("utf-8")).hexdigest()
