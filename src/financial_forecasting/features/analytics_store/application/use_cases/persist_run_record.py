"""Use case `PersistRunRecord` — grava 1 linha de `dim_run` (issue #68, defeito (a)).

Até a #68, os três use cases de `modeling` (`RunBaselines`, `TrainGbmQuantile`,
`TrainTft`) escreviam `dim_run` **direto** no `AnalyticsRepository` deste slice —
enquanto as predições passavam pelo use case `PersistPredictions`. Consequência:
qualquer invariante que a camada de aplicação do `analytics_store` imponha para
predições não era imposta para `dim_run`, e duas partes do código conheciam a
tabela (`layer`/`table`/`asdict`). Este use case fecha o encapsulamento do módulo
dono: `modeling` entrega um `RunRecord` (VO deste slice — a definição canônica da
linha, ADR 4.1 I1/I9/I10) e **só este arquivo** sabe onde e como ele é gravado.

Convenção (concept 4.2 I5 / 4.1 D5):

- **Tabela:** `silver.dim_run`, `update_policy == "upsert"` no registry — regravar o
  mesmo `run_id` substitui a linha (idempotência do rerun), então o `write` vai sem
  `allow_upsert` e sem capturar nada: o repositório decide pelo registry.
- **`created_at_utc`:** injetado pelo adapter em write-time (4.2 I5) — o VO não o
  carrega e este use case não o fabrica.
- **Um record por chamada:** `dim_run` é 1 linha por `(spec x fold)`; o chamador
  grava cada execução na hora em que a identidade dela (`run_id`) fica conhecida.

Hexagonal (I9): recebe o `AnalyticsRepository` (Protocol) por injeção; VO frozen
in, DTO frozen out; testado contra `FakeAnalyticsRepository` (fake, não mock).
`modeling` consome este use case pelo port `RunRecordPersister`
(`modeling/application/ports/out/`), satisfeito estruturalmente — este módulo não
importa nada de `modeling`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
    Row,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)

_LAYER = "silver"
_TABLE = "dim_run"


@dataclass(frozen=True)
class PersistRunRecordResult:
    """DTO de saída — linhas gravadas (sempre 1: um record por chamada)."""

    rows_written: int


class PersistRunRecord:
    """Use case que persiste um `RunRecord` em `silver.dim_run` (4.1 D5 / 4.2 I5)."""

    def __init__(self, *, repository: AnalyticsRepository) -> None:
        self._repository = repository

    def __call__(self, record: RunRecord) -> PersistRunRecordResult:
        """Grava `record` como uma linha de `dim_run`; rerun do mesmo `run_id` substitui."""
        rows: list[Row] = [asdict(record)]
        self._repository.write(layer=_LAYER, table=_TABLE, rows=rows)
        return PersistRunRecordResult(rows_written=len(rows))
