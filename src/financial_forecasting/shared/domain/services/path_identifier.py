"""Regra única de identificador de caminho (valor interpolado em path, glob ou SQL).

Serviço de domínio stdlib-only com **dono único** do padrão conservador `[A-Za-z0-9._-]`
(sem separador de path, espaço, controle nem não-ASCII) para todo identificador que vira
pedaço de caminho do medalhão (Stage 6.4 C3; ADR 6.4.0005 item 1, "the identifier rule
of the MedallionStore read-only pair"). Consumidores:

- `ParquetMedallionStore._validate_read_only_filters` (filtro `asset` do par read-only);
- `FakeMedallionStore` (o fake do mesmo port, com a mesma mensagem);
- `GoldPartition` (DTO do refresh do gold, 6.4): `asset` e `parent_sweep_id`.

A checagem usa `fullmatch`, nunca `match`/`search`: com `match`, o `$` do padrão casa
antes de um `\\n` final e `"AAPL\\n"` passaria.
"""

from __future__ import annotations

import re
from typing import Final

PATH_IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_path_identifier(value: object, *, field: str) -> None:
    """Exige `str` que case inteira com `PATH_IDENTIFIER_PATTERN`.

    Args:
        value: o identificador candidato.
        field: nome do campo na mensagem (ex. `"asset"` ou o prefixo do par read-only).

    Raises:
        ValueError: `value` não-`str` ou fora do padrão (inclusive vazio e com newline
            final), com a mensagem `"<field> must match '<padrão>'; got <value>"`.
    """
    if not isinstance(value, str) or not PATH_IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must match {PATH_IDENTIFIER_PATTERN.pattern!r}; got {value!r}")
