"""Value object SilverContentHash — identidade do conteúdo do silver lido pelo refresh (Stage 8.1).

Frozen, domínio puro (stdlib-only). Um digest identifica uma **unidade de conteúdo**
(as linhas de uma tabela do silver que o `RefreshGold` consome numa unidade — ADR
8.1.0002 item 3); `combine` junta digests por chave (por tabela e no total). Vive aqui
porque o `check_layout` (regra 6) só permite `hash_mapping` dentro de
`shared/domain/value_objects/` (LAYOUT §7).

**Canonização pelo tipo declarado (ADR 8.1.0002 item 2b).** O chamador entrega, junto
com as linhas, o tipo declarado de cada coluna no schema do silver —
`coluna -> (tipo, nulável)`, com tipo em `"int"`/`"float"`/`"str"`/`"bool"` — e o valor
é canonizado por ele, nunca pelo tipo em runtime:

- `int`: inteiro (inclusive de numpy) → `int`; float integral (`3.0`) → `3`; float
  fracionário ou não finito → `ValueError`;
- `float`: real (inclusive de numpy) → `"float:<repr>"` exato (regra compartilhada em
  `shared/domain/services/exact_float.py`); não finito vira ficha própria
  (`float:inf`, `float:-inf`, `float:nan`), nunca recusado (decisão 8.1-H7: a linha
  inválida de atribuição é dado da unidade `undefined` da 7.3 e não aborta o refresh);
- `str` e `bool`: exigidos como tais (`"1"` e `1` nunca se confundem);
- `None` só em coluna nulável; em coluna não-nula (o que um NaN vira no leitor real)
  → `ValueError`;
- coluna fora das declaradas → `ValueError`; coluna declarada ausente da linha não é
  erro e difere de `None` (a linha canônica simplesmente não tem a chave).

As colunas de proveniência de escrita (`WRITE_PROVENANCE_COLUMNS`) saem **antes** da
checagem de coluna declarada: o instante da escrita é proveniência, não identidade
(R-CAMADAS).

**Payload da unidade.** Cada linha canonizada vira um JSON canônico (`sort_keys`,
separadores fixos); a unidade hasheia `{"table": <tabela>, "rows": [<JSON das linhas,
ordenados>]}` pelo `Hasher`. Como nenhum float nativo sobra no payload, o
arredondamento do hasher (ADR 1.4.0001) nunca se aplica; como as linhas são ordenadas,
o digest depende só do multiconjunto de linhas, não da ordem de leitura.

O hash é delegado ao port `Hasher`; o type hint usa `TYPE_CHECKING` para preservar a
pureza do domínio (o Protocol é satisfeito por duck-typing).
"""

from __future__ import annotations

import json
import math
import numbers
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final

from financial_forecasting.shared.domain.services.exact_float import (
    FLOAT_PREFIX,
    encode_exact_float,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

KIND_INT: Final = "int"
KIND_FLOAT: Final = "float"
KIND_STR: Final = "str"
KIND_BOOL: Final = "bool"
_KINDS: Final = frozenset({KIND_INT, KIND_FLOAT, KIND_STR, KIND_BOOL})


def _float_token(value: float) -> str:
    """Codificação exata de um float; não finito vira ficha própria (8.1-H7)."""
    if math.isnan(value):
        return f"{FLOAT_PREFIX}nan"
    if math.isinf(value):
        return f"{FLOAT_PREFIX}inf" if value > 0 else f"{FLOAT_PREFIX}-inf"
    return encode_exact_float(value)


def _canonical_value(value: object, *, kind: str, nullable: bool, where: str) -> object:
    """Canoniza um valor pelo tipo declarado da coluna (ver docstring do módulo)."""
    if value is None:
        if nullable:
            return None
        raise ValueError(f"{where}: None in a non-nullable column")
    if kind == KIND_INT:
        if isinstance(value, bool):
            raise ValueError(f"{where}: bool in an int column: {value!r}")
        if isinstance(value, numbers.Integral):
            return int(value)
        if isinstance(value, numbers.Real):
            as_float = float(value)
            if math.isfinite(as_float) and as_float.is_integer():
                return int(as_float)
            raise ValueError(f"{where}: non-integral value in an int column: {value!r}")
    elif kind == KIND_FLOAT:
        if isinstance(value, numbers.Real) and not isinstance(value, bool):
            return _float_token(float(value))
    elif kind == KIND_STR:
        if isinstance(value, str):
            return str(value)
    elif isinstance(value, bool):  # KIND_BOOL
        return value
    raise ValueError(f"{where}: {type(value).__name__} in a {kind} column: {value!r}")


@dataclass(frozen=True)
class SilverContentHash:
    """Hash sha256 de uma unidade de conteúdo do silver (ou da combinação de unidades).

    Attributes:
        value: string hex sha256 do payload canônico.
    """

    WRITE_PROVENANCE_COLUMNS: ClassVar[frozenset[str]] = frozenset({"created_at_utc"})

    value: str

    def __post_init__(self) -> None:
        # o construtor cru também passa por aqui, não só as factories (#160)
        validate_sha256_hex(self.value, field="SilverContentHash.value")

    @classmethod
    def of_unit(
        cls,
        *,
        hasher: Hasher,
        table: str,
        columns: Mapping[str, tuple[str, bool]],
        rows: Iterable[Mapping[str, object]],
    ) -> SilverContentHash:
        """Digest do multiconjunto de linhas de uma unidade, canonizadas por `columns`.

        Raises:
            ValueError: tabela vazia, tipo declarado desconhecido, coluna não declarada,
                `None` em coluna não-nula ou valor incompatível com o tipo declarado.
        """
        if not isinstance(table, str) or not table:
            raise ValueError(f"table must be a non-empty string, got {table!r}")
        for name, (kind, _) in columns.items():
            if kind not in _KINDS:
                raise ValueError(f"{table}.{name}: unknown declared kind {kind!r}")
        canonical_rows = sorted(cls._canonical_row(table, columns, row) for row in rows)
        return cls(value=hasher.hash_mapping({"table": table, "rows": canonical_rows}))

    @classmethod
    def combine(
        cls, *, hasher: Hasher, digests: Mapping[str, SilverContentHash]
    ) -> SilverContentHash:
        """Digest do mapeamento chave → digest (depende das chaves e dos digests)."""
        return cls(value=hasher.hash_mapping({key: d.value for key, d in digests.items()}))

    @classmethod
    def _canonical_row(
        cls, table: str, columns: Mapping[str, tuple[str, bool]], row: Mapping[str, object]
    ) -> str:
        canonical: dict[str, object] = {}
        for name, value in row.items():
            if name in cls.WRITE_PROVENANCE_COLUMNS:
                continue
            if name not in columns:
                raise ValueError(f"{table}.{name}: column not declared")
            kind, nullable = columns[name]
            canonical[name] = _canonical_value(
                value, kind=kind, nullable=nullable, where=f"{table}.{name}"
            )
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
