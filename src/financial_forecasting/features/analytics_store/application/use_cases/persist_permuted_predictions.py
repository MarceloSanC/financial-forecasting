"""Use case `PersistPermutedPredictions` — grava as predições de atribuição de UM run (Stage 7.3).

Escritor da tabela silver `fact_permuted_predictions` (ADR 7.3.0002 item 4). Recebe um
run por chamada (~41 x as linhas de teste do run) e faz uma escrita append-only só, para
que o volume do cohort real (~8,7 M linhas) nunca esteja em memória de uma vez. Satisfaz
o port do consumidor `PermutedPredictionPersister` do `inference` por duck typing (padrão
do `PersistPredictions`, ADR 0.0.0053).

Regras (iguais às do `PersistPredictions`, de quem reusa o dono único do alinhamento):

- `target_timestamp_utc` pelo `MultiHorizonPredictionPersister` (ADR 4.3.0001): a mesma
  entrada dá o mesmo alvo que o `fact_oos_predictions`; janela incompleta pula o
  horizonte inteiro e conta em `rows_skipped`;
- `year = int(timestamp_utc[:4])`, o ano da decisão;
- `permuted_family == "none"` se e só se `permutation_index == 0` (a identidade), e o
  índice nunca é negativo (`ValueError`, antes de qualquer escrita); o vocabulário das
  famílias é do schema;
- `DuplicateKeyError` do repositório propaga (append-only).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
    Row,
)
from financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister import (  # noqa: E501
    IncompletePredictionWindowError,
    MultiHorizonPredictionPersister,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)

_LAYER = "silver"
_TABLE = "fact_permuted_predictions"
IDENTITY_FAMILY = "none"


@dataclass(frozen=True)
class PermutedDecisionEntry:
    """Uma decisão de uma passagem: família permutada (ou `none`), índice k e a grade."""

    permuted_family: str
    permutation_index: int
    decision_idx: int
    forecasts: Mapping[int, QuantileForecast]


@dataclass(frozen=True)
class PersistPermutedPredictionsCommand:
    """DTO de entrada — um run inteiro (identidade e todas as passagens permutadas)."""

    run_id: str
    model_version: str
    asset: str
    feature_set_name: str
    schema_version: int
    permutation_seed: int
    permutation_algorithm: str
    partition_hash: str
    dataset_timestamps: Sequence[str]
    entries: Sequence[PermutedDecisionEntry]


@dataclass(frozen=True)
class PersistPermutedPredictionsResult:
    """DTO de saída — linhas gravadas e puladas (janela incompleta)."""

    rows_written: int
    rows_skipped: int


def check_permuted_entry(entry: PermutedDecisionEntry) -> None:
    """`none ⇔ 0` e índice inteiro >= 0, antes de qualquer escrita (o fake reusa, TA-12)."""
    index = entry.permutation_index
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ValueError(f"permutation_index must be an int >= 0, got {index!r}")
    if (entry.permuted_family == IDENTITY_FAMILY) != (index == 0):
        raise ValueError(
            f"permuted_family {entry.permuted_family!r} with permutation_index {index}: "
            "'none' is the identity pass, and only it has index 0"
        )


class PersistPermutedPredictions:
    """Persiste as predições de atribuição de um run numa escrita só."""

    def __init__(self, *, repository: AnalyticsRepository) -> None:
        self._repository = repository

    def __call__(
        self, command: PersistPermutedPredictionsCommand
    ) -> PersistPermutedPredictionsResult:
        """Valida as entradas, monta as linhas LONG e grava o run (ver docstring do módulo)."""
        for entry in command.entries:
            check_permuted_entry(entry)
        rows: list[Row] = []
        rows_skipped = 0
        for entry in command.entries:
            for horizon in sorted(entry.forecasts):
                forecast = entry.forecasts[horizon]
                try:
                    window = MultiHorizonPredictionPersister.build(
                        decision_idx=entry.decision_idx,
                        horizon=horizon,
                        dataset_timestamps=command.dataset_timestamps,
                    )
                except IncompletePredictionWindowError:
                    rows_skipped += len(forecast.levels)
                    continue
                for level, value_raw, value_guardrail in zip(
                    forecast.levels, forecast.raw_values, forecast.guardrail_values, strict=True
                ):
                    rows.append(
                        {
                            "schema_version": command.schema_version,
                            "run_id": command.run_id,
                            "model_version": command.model_version,
                            "asset": command.asset,
                            "feature_set_name": command.feature_set_name,
                            "permuted_family": entry.permuted_family,
                            "permutation_index": entry.permutation_index,
                            "permutation_seed": command.permutation_seed,
                            "permutation_algorithm": command.permutation_algorithm,
                            "partition_hash": command.partition_hash,
                            "horizon": horizon,
                            "decision_idx": window.decision_idx,
                            "timestamp_utc": window.timestamp_utc,
                            "target_timestamp_utc": window.target_timestamp_utc,
                            "quantile_level": level,
                            "value_raw": value_raw,
                            "value_guardrail": value_guardrail,
                            "guardrail_applied": 1 if forecast.guardrail_applied else 0,
                            "year": int(window.timestamp_utc[:4]),
                        }
                    )
        if rows:
            self._repository.write(layer=_LAYER, table=_TABLE, rows=rows, allow_upsert=False)
        return PersistPermutedPredictionsResult(rows_written=len(rows), rows_skipped=rows_skipped)
