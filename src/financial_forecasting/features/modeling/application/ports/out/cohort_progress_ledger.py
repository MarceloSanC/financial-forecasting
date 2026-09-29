"""Port-out `CohortProgressLedger` — progresso durável do cohort confirmatório (Stage 5.5).

Registra, fora do silver, o que a orquestração do cohort precisa para ser
RETOMÁVEL e EXCLUSIVA (ADR 5.5.0003):

- **lock de escritor único** do `data_root` (`acquire_writer`/`release_writer`):
  os arquivos anuais de `fact_oos_predictions` são compartilhados entre cohorts e
  revisões, e a gravação atômica não isola escritores concorrentes (I12). Lock
  órfão de uma queda só sai com `break_stale=True` (decisão explícita do humano).
- **unidades concluídas** (`completed_units`/`mark_completed`): `unit_key ->
  {run_id: linhas de predição}`, marcadas só DEPOIS de o use case da unidade
  retornar; a retomada reconfere essas contagens no silver (I6).
- **ambiente da primeira execução** (`record_environment`/`environment`/
  `run_started_at`): versões, device e identidade do código; a retomada com
  qualquer diferença aborta (I5). O instante de início é passado pelo chamador
  (port `Clock`) e gravado uma única vez — é a âncora local comparada ao
  comentário da issue (D3).
- **resultados dos sweeps** (`record_sweep_result`/`sweep_results`): o `sweep` e o
  `freeze` rodam em processos separados; o `freeze` copia a proveniência daqui,
  nunca de uma releitura do dado.

Port consumer-owned do slice modeling (ADR 0.0.0053). Adapter real:
`JsonCohortProgressLedger` (JSON gravado por arquivo temporário + `os.replace`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from financial_forecasting.shared.domain.exceptions.base import ApplicationError


class CohortRunLockedError(ApplicationError):
    """O lock de escritor do `data_root` já tem dono (outro processo ou queda anterior).

    A mensagem nomeia o dono (pid, host, início) para o humano decidir entre
    esperar e quebrar o lock órfão (`--break-stale-lock`).
    """


class CohortProgressLedger(Protocol):
    """Contrato de progresso, ambiente, lock e resultados de sweep do cohort."""

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        """Adquire o lock de escritor único; já detido → `CohortRunLockedError`.

        `break_stale=True` remove o lock existente e o adquire (uso explícito).
        """
        ...

    def release_writer(self) -> None:
        """Libera o lock (idempotente: sem lock, não faz nada).

        Invariante: libera só o lock que ESTA instância adquiriu — depois de um
        `break_stale=True` de outro processo, o dono antigo não apaga o lock do
        novo (o adapter guarda um token; o fake, de processo único, não tem
        outro dono possível).
        """
        ...

    def completed_units(self, cohort_id: str) -> Mapping[str, Mapping[str, int]]:
        """`unit_key -> {run_id: linhas}` das unidades marcadas; vazio se nenhuma."""
        ...

    def mark_completed(
        self, cohort_id: str, unit_key: str, rows_by_run: Mapping[str, int]
    ) -> None:
        """Marca a unidade como concluída com as contagens por `run_id`."""
        ...

    def environment(self, cohort_id: str) -> Mapping[str, str] | None:
        """Último ambiente gravado; `None` se ainda não houve execução.

        O use case só grava na primeira execução e compara nas seguintes (I5).
        """
        ...

    def record_environment(
        self, cohort_id: str, env: Mapping[str, str], *, started_at: str
    ) -> None:
        """Grava o ambiente; o instante de início é gravado só na primeira vez."""
        ...

    def run_started_at(self, cohort_id: str) -> str | None:
        """Instante (ISO-8601) da primeira execução; `None` se ainda não houve."""
        ...

    def record_sweep_result(
        self, scope_id: str, model: str, result: Mapping[str, object]
    ) -> None:
        """Grava o resultado do sweep de `model` (`"tft"`/`"gbm"`) sob o scope id.

        `result` passa por JSON: tuplas voltam como listas e chaves como texto —
        o leitor normaliza (o fake faz a mesma ida e volta, para paridade).
        """
        ...

    def sweep_results(self, scope_id: str) -> Mapping[str, Mapping[str, object]]:
        """`model -> resultado` gravados sob o scope id; vazio se nenhum."""
        ...
