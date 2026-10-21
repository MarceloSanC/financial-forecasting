"""Fake in-memory do port `PermutedPredictionPersister` do `inference` (Stage 7.3).

Não guarda linhas: registra cada comando em `commands` e as chaves que seriam gravadas
em `keys` — `(run_id, família, k, decisão, horizonte, nível)`. As regras são as do
real, reusadas e não reescritas (TA-12):

- `check_permuted_entry` do use case: `none ⇔ 0` e índice inteiro >= 0;
- `MultiHorizonPredictionPersister.build`: janela incompleta pula o horizonte e conta
  em `rows_skipped`;
- o vocabulário `PERMUTED_FAMILIES` do schema silver: família fora dele ergue
  `ValueError` (no real, o pandera recusa a escrita);
- chave já gravada ergue `DuplicateKeyError` (o real é append-only).

Toda recusa vem antes de registrar qualquer coisa do comando.
"""

from __future__ import annotations

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_permuted_predictions_schema import (  # noqa: E501
    PERMUTED_FAMILIES,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PersistPermutedPredictionsCommand,
    PersistPermutedPredictionsResult,
    check_permuted_entry,
)
from financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister import (  # noqa: E501
    IncompletePredictionWindowError,
    MultiHorizonPredictionPersister,
)
from financial_forecasting.shared.application.exceptions import DuplicateKeyError

Key = tuple[str, str, int, int, int, float]


class InMemoryPermutedPredictionPersister:
    """Conta e registra as chaves das linhas de atribuição de cada run."""

    def __init__(self) -> None:
        self.commands: list[PersistPermutedPredictionsCommand] = []
        self.keys: list[Key] = []

    def __call__(
        self, command: PersistPermutedPredictionsCommand
    ) -> PersistPermutedPredictionsResult:
        for entry in command.entries:
            check_permuted_entry(entry)
            if entry.permuted_family not in PERMUTED_FAMILIES:
                raise ValueError(
                    f"permuted_family {entry.permuted_family!r} is outside the vocabulary "
                    f"{list(PERMUTED_FAMILIES)}"
                )
        incoming: list[Key] = []
        skipped = 0
        for entry in command.entries:
            for horizon in sorted(entry.forecasts):
                levels = tuple(entry.forecasts[horizon].levels)
                try:
                    MultiHorizonPredictionPersister.build(
                        decision_idx=entry.decision_idx,
                        horizon=horizon,
                        dataset_timestamps=command.dataset_timestamps,
                    )
                except IncompletePredictionWindowError:
                    skipped += len(levels)
                    continue
                incoming.extend(
                    (
                        command.run_id,
                        entry.permuted_family,
                        entry.permutation_index,
                        entry.decision_idx,
                        horizon,
                        level,
                    )
                    for level in levels
                )
        collisions = sorted(set(incoming) & set(self.keys), key=str)
        if collisions:
            raise DuplicateKeyError(
                f"Duplicate logical PK collision in fact_permuted_predictions: {collisions[:3]}"
            )
        self.commands.append(command)
        self.keys.extend(incoming)
        return PersistPermutedPredictionsResult(rows_written=len(incoming), rows_skipped=skipped)
