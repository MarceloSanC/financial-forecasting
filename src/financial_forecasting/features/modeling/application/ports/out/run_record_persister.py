"""Port-out `RunRecordPersister` — registro de uma execução em `dim_run` (issue #68).

Protocol estrutural definido **no consumidor** (`modeling`); satisfeito por
duck-typing pelo use case `PersistRunRecord` do `analytics_store`, que não importa
nada daqui (Dependency Inversion — ver `prediction_persister.py`). Antes da #68 os
use cases de `modeling` recebiam o `AnalyticsRepository` do outro slice e escreviam
`dim_run` direto (`write(layer="silver", table="dim_run", ...)`) — furando a camada
de aplicação do slice dono e conhecendo o schema da tabela.

O que cruza o port é o VO `RunRecord` do `analytics_store` (a definição canônica da
linha, 4.1 I1/I9/I10). É deliberadamente o VO e não um DTO-espelho: um comando com
os mesmos 10 campos seria a "segunda definição da mesma linha de tabela" que a #68
lista como não-objetivo (o mesmo argumento que descartou o ACL). Uso compartilhado
de VO entre slices do mesmo contexto é declarado no `.importlinter`
(`bc-independence`) e no LAYOUT §7.

O resultado é o DTO do fornecedor, `PersistRunRecordResult` (type-only aqui).

Contrato semântico (o do `PersistRunRecord`, 4.1 D5 / 4.2 I5): 1 linha por chamada;
regravar o mesmo `run_id` substitui (política `upsert` de `dim_run`), sem erguer;
`created_at_utc` é do adapter, não do chamador.

Fake: `tests/fakes/features/modeling/in_memory_run_record_persister.py`; suite
`[fake, real]`: `tests/contract/features/modeling/test_persistence_ports_contract.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
        PersistRunRecordResult,
    )
    from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
        RunRecord,
    )


class RunRecordPersister(Protocol):
    """Registra uma execução (`RunRecord`) na dimensão `dim_run`."""

    def __call__(self, record: RunRecord) -> PersistRunRecordResult:
        """Grava `record`; rerun do mesmo `run_id` substitui a linha (ver módulo)."""
        ...
