"""Adapter CanonicalJsonHasher — implementação concreta do port `Hasher`.

Replica o esquema canônico do repo antigo
(analytics_store_schema.py:17-22): `json.dumps(sort_keys=True,
separators=(",", ":"), ensure_ascii=False)` + sha256 hex; e o ENDURECE
conforme o ADR 1.4.0001:

- Floats são arredondados a uma precisão fixa DECLARADA (`_FLOAT_PRECISION = 10`
  casas) antes de serializar — blinda contra divergência de último-ULP em
  somatórios da nova stack numérica (pandas/numpy/ROCm) entre versões e
  plataformas. `int` permanece `int`; `bool` é tratado ANTES de `float`
  (Python `bool` é subtipo de `int`, não deve ser arredondado).
- NaN/±inf são REJEITADOS com `ValueError` (fail-fast) — indicam dado
  corrompido a montante, não estado legítimo. `json.dumps(..., allow_nan=False)`
  é a defesa-em-profundidade ("belt-and-suspenders") que pega qualquer
  não-finito que escape do guard explícito.

Não faz I/O (sem `_sha256_file`/leitura de disco — isso é Step 4.x). A
canonicalização vive AQUI, no adapter, centralizada e contract-testada contra
o `FakeHasher` (paridade I11), mantendo o domínio puro (os VOs só montam o
payload e delegam).
"""

import json
import math
from collections.abc import Mapping
from hashlib import sha256

_FLOAT_PRECISION = 10
"""Casas decimais para arredondar floats antes do hash (ADR 1.4.0001).

Constante de módulo documentada e trivialmente trocável. 10 casas ficam muito
abaixo do ruído de um somatório (diferença de último-ULP) e muito acima da
precisão necessária para discriminar datasets distintos.
"""


def _canonicalize(value: object) -> object:
    """Canonicaliza recursivamente um valor antes da serialização JSON.

    Arredonda floats a `_FLOAT_PRECISION` casas, rejeita NaN/±inf com
    `ValueError` e percorre mappings/sequências. `bool` é tratado ANTES de
    `float` (subtipo de `int`).
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


class CanonicalJsonHasher:
    """Hasher canônico determinístico via JSON ordenado + sha256."""

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
