"""Regra única de "hash sha256 hex" dos valores de identidade (issue #160).

Serviço de domínio stdlib-only com **dono único** da forma de um hash de identidade:
64 caracteres hex **minúsculos** — exatamente o `hexdigest()` que o `Hasher` canônico
devolve (ADR 1.4.0001). Consumidores:

- os VOs de identidade de `shared/domain/value_objects/` (`RunId`, `ConfigSignature`,
  `SplitFingerprint`, `DatasetFingerprint`, `DatasetContentFingerprint`, `CohortHash`,
  `PreregistrationHash`), no `__post_init__`;
- os VOs do `analytics_store` que guardam esses hashes como `str` (`RunRecord`,
  `PredictionRow`);
- os blocos do pré-registro do `evaluation` (`CohortReference.cohort_hash`,
  `RealizedSource.dataset_fingerprint`).

Validar na construção, e não só na factory `compute`, é o que fecha o caminho cru
`Cls(value=...)` (gate `scripts/check_vo_invariants.py`, issue #61). O formato não
muda: só se recusa o que nunca saiu do hasher.

A checagem usa `fullmatch`, nunca `match`/`search`: com `match`, o `$` do padrão casa
antes de um `\\n` final.
"""

from __future__ import annotations

import re
from typing import Final

SHA256_HEX_PATTERN: Final = re.compile(r"[0-9a-f]{64}")


def validate_sha256_hex(value: object, *, field: str) -> None:
    """Exige `str` de 64 caracteres hex minúsculos (o `hexdigest()` do sha256).

    Args:
        value: o hash candidato.
        field: nome do campo na mensagem (ex.: `"RunId.value"` ou `"run_id"`).

    Raises:
        ValueError: `value` não-`str`, com tamanho diferente de 64 ou com caractere fora
            de `[0-9a-f]` (inclusive maiúsculas), com a mensagem
            `"<field> must be a lowercase sha256 hex of 64 characters, got <value>"`.
    """
    if not isinstance(value, str) or not SHA256_HEX_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase sha256 hex of 64 characters, got {value!r}")
