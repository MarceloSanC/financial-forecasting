"""Use case `PersistPredictions` — grava a grade densa LONG (raw + guardrail).

Combina o domain service `MultiHorizonPredictionPersister` (dono do alinhamento
temporal, 4.3 task-01) e o VO `QuantileForecast` (grade densa + guardrail, task-02),
mapeia cada `(decision_idx, horizon, nível)` para uma linha LONG e grava via o
port-out `AnalyticsRepository` (4.2) na tabela silver `fact_oos_predictions` (4.1).

Convenção (concept 4.3 §1/§5, I6/I7/I9):

- **Formato LONG (H-1):** uma linha por `(decision, h, quantile_level)`, com
  `value_raw` **e** `value_guardrail` na MESMA linha (D6 — herdado de
  `PredictionRow`/schema 4.1); PK lógica
  `(run_id, split, horizon, timestamp_utc, target_timestamp_utc, quantile_level)`.
- **Janela incompleta:** o persister levanta `IncompletePredictionWindowError`; o use
  case **captura e pula a linha** (`continue` + `rows_skipped += 1`), sem fabricar
  `y_true` (concept 4.3 C1/I4/D7).
- **Colunas de schema na fronteira (D5/I7):** `schema_version`, `model_version`,
  `asset`, `feature_set_name` vêm do `command`; `year = ano do decision_day`
  (`int(timestamp_utc[:4])`), consistente cruzando fronteira de ano. O VO
  `PredictionRow` (4.1) deliberadamente não carrega essas colunas (domínio puro), mas
  o schema `pandera` as exige `nullable=False`.
- **Colisão de PK (C5):** o use case **não** captura `DuplicateKeyError` — propaga
  (reprocessamento consciente é responsabilidade do caller).

Hexagonal (I9): recebe o `AnalyticsRepository` (Protocol) por injeção; DTOs frozen
in/out; testado contra `FakeAnalyticsRepository` (fake, não mock; ADR `0_0_0021`).
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
from financial_forecasting.features.analytics_store.domain.value_objects.prediction_row import (
    PredictionRow,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)

_LAYER = "silver"
_TABLE = "fact_oos_predictions"


@dataclass(frozen=True)
class PersistPredictionsCommand:
    """DTO de entrada — uma decisão e seus horizontes para um `run`/`split`/`asset`.

    Campos:
        run_id: identidade da execução produtora (hash hex da 1.4).
        split: rótulo do split (ex.: ``"test"``).
        model_version: versão/rótulo do modelo produtor (ex.: ``"tft_v1"``).
        asset: ativo (ex.: ``"AAPL"``) — coluna de partição.
        feature_set_name: nome do conjunto de features — coluna de partição.
        schema_version: versão do schema `fact_oos_predictions`.
        decision_idx: índice da barra de decisão na grade do dataset.
        dataset_timestamps: timestamps ISO UTC em grade de pregão (garantia 2.4).
        forecasts: por horizonte, a `QuantileForecast` (grade densa) correspondente.
    """

    run_id: str
    split: str
    model_version: str
    asset: str
    feature_set_name: str
    schema_version: int
    decision_idx: int
    dataset_timestamps: Sequence[str]
    forecasts: Mapping[int, QuantileForecast]


@dataclass(frozen=True)
class PersistPredictionsResult:
    """DTO de saída — contagem de linhas gravadas e puladas (janela incompleta)."""

    rows_written: int
    rows_skipped: int


class PersistPredictions:
    """Use case que persiste a grade densa de quantis no formato LONG (4.3)."""

    def __init__(self, *, repository: AnalyticsRepository) -> None:
        self._repository = repository

    def __call__(self, command: PersistPredictionsCommand) -> PersistPredictionsResult:
        """Resolve o alinhamento, monta as linhas LONG e grava o batch.

        Para cada `(horizon, QuantileForecast)`, resolve a janela temporal via o
        persister; em janela incompleta, pula o horizonte inteiro (todos os níveis)
        contabilizando `rows_skipped`. As linhas válidas são gravadas em um único
        `write` append-only; `DuplicateKeyError` propaga (C5).
        """
        rows: list[Row] = []
        rows_skipped = 0

        for horizon in sorted(command.forecasts):
            forecast = command.forecasts[horizon]
            try:
                window = MultiHorizonPredictionPersister.build(
                    decision_idx=command.decision_idx,
                    horizon=horizon,
                    dataset_timestamps=command.dataset_timestamps,
                )
            except IncompletePredictionWindowError:
                # C1/I4/D7: janela incompleta → pula TODOS os níveis deste horizonte,
                # sem fabricar y_true. Conta uma linha pulada por nível da grade.
                rows_skipped += len(forecast.levels)
                continue

            for level, value_raw, value_guardrail in zip(
                forecast.levels,
                forecast.raw_values,
                forecast.guardrail_values,
                strict=True,
            ):
                prediction_row = PredictionRow(
                    run_id=command.run_id,
                    split=command.split,
                    horizon=horizon,
                    decision_idx=window.decision_idx,
                    timestamp_utc=window.timestamp_utc,
                    target_timestamp_utc=window.target_timestamp_utc,
                    quantile_level=level,
                    value_raw=value_raw,
                    value_guardrail=value_guardrail,
                    guardrail_applied=1 if forecast.guardrail_applied else 0,
                )
                rows.append(self._to_row(prediction_row, command))

        if rows:
            self._repository.write(
                layer=_LAYER,
                table=_TABLE,
                rows=rows,
                allow_upsert=False,
            )

        return PersistPredictionsResult(rows_written=len(rows), rows_skipped=rows_skipped)

    @staticmethod
    def _to_row(prediction_row: PredictionRow, command: PersistPredictionsCommand) -> Row:
        """Mapeia `PredictionRow` → `Row` preenchendo as colunas de schema (D5/I7).

        `year = ano do decision_day` (`int(timestamp_utc[:4])`); as demais colunas
        ausentes no VO (`schema_version`/`model_version`/`asset`/`feature_set_name`)
        vêm do `command`. O dict resultante tem exatamente as 15 colunas do schema
        `fact_oos_predictions` (4.1).
        """
        return {
            "schema_version": command.schema_version,
            "run_id": prediction_row.run_id,
            "model_version": command.model_version,
            "asset": command.asset,
            "feature_set_name": command.feature_set_name,
            "split": prediction_row.split,
            "horizon": prediction_row.horizon,
            "decision_idx": prediction_row.decision_idx,
            "timestamp_utc": prediction_row.timestamp_utc,
            "target_timestamp_utc": prediction_row.target_timestamp_utc,
            "quantile_level": prediction_row.quantile_level,
            "value_raw": prediction_row.value_raw,
            "value_guardrail": prediction_row.value_guardrail,
            "guardrail_applied": prediction_row.guardrail_applied,
            "year": int(prediction_row.timestamp_utc[:4]),
        }
