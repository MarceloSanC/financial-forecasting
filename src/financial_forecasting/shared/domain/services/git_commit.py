"""Regra única de "sha de commit git" dos registros de execução (Stage 8.1, CC3-3).

Serviço de domínio stdlib-only com **dono único** da forma de um commit gravado como
identidade de código: 40 caracteres hex **minúsculos** — exatamente o que
`git rev-parse HEAD` imprime num repositório SHA-1. Consumidores:

- o registro de atestação commitado (`JudgedRecord.commit`, `evaluation`);
- as linhas do log de tentativas (`JudgedAttempt.commit`, `evaluation`);
- o snapshot do ambiente de execução (`EvaluationEnvironment`, chave `commit`).

A checagem usa `fullmatch`, nunca `match`/`search`: com `match`, o `$` do padrão casa
antes de um `\\n` final (molde de `sha256_hex.py`).
"""

from __future__ import annotations

import re
from typing import Final

GIT_COMMIT_PATTERN: Final = re.compile(r"[0-9a-f]{40}")


def validate_git_commit_sha(value: object, *, field: str) -> None:
    """Exige `str` de 40 caracteres hex minúsculos (o sha de `git rev-parse HEAD`).

    Raises:
        ValueError: `value` não-`str`, com tamanho diferente de 40 ou com caractere fora
            de `[0-9a-f]`, com a mensagem
            `"<field> must be 40 lowercase hex characters, got <value>"`.
    """
    if not isinstance(value, str) or not GIT_COMMIT_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be 40 lowercase hex characters, got {value!r}")
