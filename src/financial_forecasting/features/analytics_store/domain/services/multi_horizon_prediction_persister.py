"""Domain service `MultiHorizonPredictionPersister` — dono único do `target_timestamp`.

Serviço de domínio **puro** (stdlib-only) que materializa, sem off-by-one, a
convenção temporal das predições out-of-sample do BC `analytics_store`. Replica a
correção do old ADR-0003 (Stage R-20, opção d) — ver
`docs/adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md` —
fechando na origem o Gap 6 / bug E4 do projeto antigo, onde o TFT usava
`decoder_end_day` e o baseline `decision_day`, e **ambos** somavam
`pd.Timedelta(days=h)` de **calendário** numa grade de **pregão**.

Convenção canônica (concept 4.3 §5, I1-I4):

- ``timestamp_utc = dataset_timestamps[decision_idx]`` (o decision day — NUNCA o
  decoder end day);
- ``target_timestamp_utc = dataset_timestamps[decision_idx + horizon]`` indexado
  pelo **índice do array de sessões** (dia de pregão), JAMAIS por `timedelta` de
  calendário. Como `dataset_timestamps` já chega resolvido em grade de pregão (sem
  feriados/fins de semana, garantia da camada 2.4 / `TradingCalendar`), indexar o
  array é correto e O(1). Para uma sexta com h=1, o diff de **calendário** entre os
  dois timestamps é 3 dias (pula o fim de semana) — prova de que a indexação é por
  **sessão**, não por calendário.

O ``y_true`` / ``target_return`` NÃO é calculado aqui: é fornecido pelo caller, que
indexa ``target_return[decision_idx + horizon]`` (`target_return` é backward,
``target_return[t] = log(close[t]/close[t-1])``), garantindo
``y_true(h) = target_return[decision_idx + h]`` separado do decision day por
**exatamente h sessões**. Este serviço apenas garante o alinhamento dos timestamps.

PUREZA (concept 4.3 I8 / D3): importa só ``dataclasses`` + ``collections.abc``; os
timestamps trafegam como ``str`` ISO UTC, sem `pandas`/`datetime`/parsing — corrige
a violação do old, que importava `pd.Timestamp` apenas para `.isoformat()`. Os gates
domain-purity (import-linter) + `scripts/check_layout.py` reprovam vazamento.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class IncompletePredictionWindowError(ValueError):
    """`decision_idx` (+ horizon) fora dos limites de `dataset_timestamps`.

    O caller (use case `PersistPredictions`) captura este erro e **pula a linha**
    (skip), contabilizando `rows_skipped`, sem fabricar `y_true` (concept 4.3 C1/I4).
    """


@dataclass(frozen=True)
class PredictionWindow:
    """Janela de predição resolvida — âncora temporal de uma linha (decision, h).

    Campos:
        decision_idx: índice da barra de decisão na grade do dataset.
        timestamp_utc: ``dataset_timestamps[decision_idx]`` (decision day, ISO UTC).
        target_timestamp_utc: ``dataset_timestamps[decision_idx + horizon]``
            (alvo previsto, indexado por dia de pregão, ISO UTC).
    """

    decision_idx: int
    timestamp_utc: str
    target_timestamp_utc: str


class MultiHorizonPredictionPersister:
    """Convenção canônica de `target_timestamp` para `fact_oos_predictions`.

    Dono **único** da regra de alinhamento temporal (concept 4.3 §5). Ver a docstring
    do módulo para a convenção completa e o ADR `4_3_0001`.
    """

    @staticmethod
    def build(
        *,
        decision_idx: int,
        horizon: int,
        dataset_timestamps: Sequence[str],
    ) -> PredictionWindow:
        """Resolve a janela ``(timestamp_utc, target_timestamp_utc)`` por sessão.

        Args:
            decision_idx: índice (>= 0) da barra de decisão na grade do dataset.
            horizon: horizonte de previsão em dias de pregão (>= 1).
            dataset_timestamps: sequência de timestamps ISO UTC **já resolvida em
                grade de pregão** (sem feriados/fins de semana; garantia da 2.4).

        Returns:
            `PredictionWindow` com `timestamp_utc = dataset_timestamps[decision_idx]`
            e `target_timestamp_utc = dataset_timestamps[decision_idx + horizon]`.

        Raises:
            ValueError: `horizon < 1` ou `decision_idx < 0` (bug do caller — C2).
            IncompletePredictionWindowError: `decision_idx + horizon >= len` ou
                `decision_idx >= len` (janela incompleta — C1/I4).
        """
        # I4/C1/C2: argumentos inválidos (bug do caller) ANTES da borda (skip).
        if horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {horizon}")
        if decision_idx < 0:
            raise ValueError(f"decision_idx must be >= 0, got {decision_idx}")

        target_pos = decision_idx + horizon
        length = len(dataset_timestamps)
        if decision_idx >= length:
            raise IncompletePredictionWindowError(
                f"decision_idx={decision_idx} >= len(dataset_timestamps)={length}"
            )
        if target_pos >= length:
            raise IncompletePredictionWindowError(
                f"decision_idx={decision_idx} + horizon={horizon} = {target_pos} "
                f">= len(dataset_timestamps)={length}"
            )

        # I1/I2: âncora no decision day; alvo indexado por sessão (índice do array).
        return PredictionWindow(
            decision_idx=decision_idx,
            timestamp_utc=dataset_timestamps[decision_idx],
            target_timestamp_utc=dataset_timestamps[target_pos],
        )
