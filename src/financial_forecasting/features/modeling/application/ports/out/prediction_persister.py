"""Port-out `PredictionPersister` — persistência da grade LONG de quantis (issue #68).

Protocol estrutural definido **no consumidor** (`modeling`), não no slice que o
satisfaz: Dependency Inversion (Martin, *Clean Architecture*) — os use cases de
`modeling` dependem desta abstração, e o `analytics_store` a satisfaz por
duck-typing com o use case `PersistPredictions`, **sem importar nada de
`modeling`**. Antes da #68 os três use cases (`RunBaselines`, `TrainGbmQuantile`,
`TrainTft`) recebiam a classe concreta `PersistPredictions` no construtor — o único
colaborador não-Protocol deles, insubstituível sem construir o objeto real.

O que cruza o port são os **DTOs do slice fornecedor**: `PersistPredictionsCommand`
(uma decisão x horizontes, com `QuantileForecast` por horizonte) entra e
`PersistPredictionsResult` (`rows_written`/`rows_skipped`, que o `modeling` agrega
nos summaries) sai — ambos type-only aqui. O `modeling` monta o comando e não
remonta a linha LONG (dono único do `target_timestamp`: ADR 4.3.0001).

Contrato semântico (o do `PersistPredictions`, concept 4.3):

- janela incompleta na resolução temporal → o horizonte inteiro é PULADO
  (`rows_skipped += n_níveis`), sem fabricar `y_true` (C1/I4/D7);
- colisão de PK lógica em `fact_oos_predictions` **propaga** (`DuplicateKeyError`,
  C5) — reprocessar é decisão consciente do chamador.

Fake: `tests/fakes/features/modeling/in_memory_prediction_persister.py`; suite
`[fake, real]`: `tests/contract/features/modeling/test_persistence_ports_contract.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
        PersistPredictionsCommand,
        PersistPredictionsResult,
    )


class PredictionPersister(Protocol):
    """Persiste a grade densa de uma decisão (todos os horizontes) no formato LONG."""

    def __call__(self, command: PersistPredictionsCommand) -> PersistPredictionsResult:
        """Grava as linhas LONG resolvíveis e devolve as contagens (ver módulo)."""
        ...
