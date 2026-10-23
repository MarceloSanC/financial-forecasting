"""`SilverContentAccumulator` — digests por unidade do silver consumido pelo refresh (Stage 8.1).

Colaborador por chamada do `RefreshGold` (technical 8.1 §1 "Decisões de forma"; ADR
`8_1_0002` itens 2 e 3; concept 8.1 I6): cada leitura do refresh entrega aqui, já
pós-filtradas, as linhas que consome, com os tipos declarados das colunas
(`SilverTableReader.columns`). As linhas são agrupadas por **unidade de conteúdo** e
cada unidade é hasheada pelo `SilverContentHash` na chamada que a recebe e descartada —
a memória fica limitada a uma leitura; só os digests ficam. Nada de I/O.

Unidades (chaves de `unit_key`):

- `dim_run|<parent_sweep_id>` — `add_dim_run`;
- `<tabela>|<run_id>|<year>` — `add_facts`, com `run_id` e `year` lidos **da linha**:
  um run lido de uma vez ou ano a ano dá as mesmas unidades;
- `realized|<asset>` — `add_realized`, a série realizada que o refresh usa, com os
  tipos `timestamp` (`str`, não-nulo) e `target_return` (`float`, não-nulo).

A mesma unidade em duas leituras é erro de programação (`ValueError`): o digest de uma
unidade descreve todas as suas linhas, e duas leituras parciais não se somam.
"""

from __future__ import annotations

import numbers
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    REALIZED_TABLE,
    SilverContent,
    unit_key,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    KIND_FLOAT,
    KIND_STR,
    SilverContentHash,
)

if TYPE_CHECKING:
    from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
        RealizedReturns,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

DIM_RUN_TABLE: Final = "dim_run"
REALIZED_COLUMNS: Final[Mapping[str, tuple[str, bool]]] = {
    "timestamp": (KIND_STR, False),
    "target_return": (KIND_FLOAT, False),
}

Row = Mapping[str, object]
Columns = Mapping[str, tuple[str, bool]]


def _fact_unit_parts(table: str, row: Row) -> tuple[str, int]:
    """`(run_id, year)` da linha de fato; ausente ou de tipo errado → `ValueError`."""
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(f"{table} row must carry a non-empty str run_id, got {run_id!r}")
    year = row.get("year")
    if isinstance(year, bool) or not isinstance(year, numbers.Integral):
        raise ValueError(f"{table} row must carry an int year, got {year!r}")
    return run_id, int(year)


class SilverContentAccumulator:
    """Acumula os digests das unidades consumidas por uma chamada do refresh."""

    def __init__(self, *, hasher: Hasher) -> None:
        self._hasher = hasher
        self._units: dict[str, tuple[str, SilverContentHash]] = {}

    def add_dim_run(self, *, columns: Columns, parent_sweep_id: str, rows: Iterable[Row]) -> None:
        """Unidade `dim_run|<parent_sweep_id>` com as linhas do cohort consumidas."""
        self._add(DIM_RUN_TABLE, unit_key(DIM_RUN_TABLE, parent_sweep_id), columns, rows)

    def add_facts(self, *, table: str, columns: Columns, rows: Iterable[Row]) -> None:
        """Uma unidade `<table>|<run_id>|<year>` por par `(run_id, year)` das linhas."""
        groups: dict[tuple[str, int], list[Row]] = {}
        for row in rows:
            groups.setdefault(_fact_unit_parts(table, row), []).append(row)
        for (run_id, year), group in groups.items():
            self._add(table, unit_key(table, run_id, year), columns, group)

    def add_realized(self, *, asset: str, realized: RealizedReturns) -> None:
        """Unidade `realized|<asset>`: `timestamp` e `target_return` de cada sessão."""
        rows = [
            {"timestamp": timestamp, "target_return": value}
            for timestamp, value in zip(realized.timestamps, realized.returns, strict=True)
        ]
        self._add(REALIZED_TABLE, unit_key(REALIZED_TABLE, asset), REALIZED_COLUMNS, rows)

    def result(self) -> SilverContent:
        """Digests por unidade, combinados por tabela e no total."""
        by_table: dict[str, dict[str, SilverContentHash]] = {}
        for key, (table, digest) in self._units.items():
            by_table.setdefault(table, {})[key] = digest
        everything = {key: digest for key, (_, digest) in self._units.items()}
        return SilverContent(
            digest=SilverContentHash.combine(hasher=self._hasher, digests=everything).value,
            tables={
                table: SilverContentHash.combine(hasher=self._hasher, digests=digests).value
                for table, digests in by_table.items()
            },
            units={key: digest.value for key, digest in everything.items()},
        )

    def _add(self, table: str, key: str, columns: Columns, rows: Iterable[Row]) -> None:
        if key in self._units:
            raise ValueError(f"silver content unit {key!r} was already read")
        digest = SilverContentHash.of_unit(
            hasher=self._hasher, table=table, columns=columns, rows=rows
        )
        self._units[key] = (table, digest)
