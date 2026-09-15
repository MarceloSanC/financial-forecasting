"""Fake in-memory do port `PredictionPersister` (modeling, issue #68).

Satisfaz o Protocol por duck-typing, como o real (`PersistPredictions` do
`analytics_store`). Não é mock: guarda os comandos recebidos e devolve as MESMAS
contagens que o real devolveria — a regra de janela (`decision_idx + horizon` tem
de caber em `dataset_timestamps`) vive no domain service
`MultiHorizonPredictionPersister` do `analytics_store`, chamado aqui e no real
(casa única; o fake não a reimplementa — o que o gate `check_fake_parity.py`
exige). O que o fake NÃO faz: montar/gravar a linha LONG. Colisão de PK, portanto,
não existe aqui (o real propaga `DuplicateKeyError` do repositório); a suíte
`[fake, real]` cobre o que os dois compartilham — contagens por janela completa e
incompleta (`tests/contract/features/modeling/test_persistence_ports_contract.py`).
"""

from __future__ import annotations

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictionsCommand,
    PersistPredictionsResult,
)
from financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister import (  # noqa: E501
    IncompletePredictionWindowError,
    MultiHorizonPredictionPersister,
)


class InMemoryPredictionPersister:
    """Conta linhas resolvíveis por decisão e guarda o comando; nada é gravado."""

    def __init__(self) -> None:
        self.commands: list[PersistPredictionsCommand] = []

    def __call__(self, command: PersistPredictionsCommand) -> PersistPredictionsResult:
        self.commands.append(command)
        written = 0
        skipped = 0
        for horizon, forecast in command.forecasts.items():
            try:
                MultiHorizonPredictionPersister.build(
                    decision_idx=command.decision_idx,
                    horizon=horizon,
                    dataset_timestamps=command.dataset_timestamps,
                )
            except IncompletePredictionWindowError:
                skipped += len(forecast.levels)
            else:
                written += len(forecast.levels)
        return PersistPredictionsResult(rows_written=written, rows_skipped=skipped)
