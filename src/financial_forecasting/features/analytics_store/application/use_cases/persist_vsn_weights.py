"""Use case `PersistVsnWeights` — grava os pesos da VSN do encoder de UM run (Stage 7.3).

Escritor da tabela silver `fact_vsn_weights` (ADR 7.3.0002 item 4): uma linha por
(decisão de teste, variável do encoder). Um run por chamada, uma escrita append-only só.
Satisfaz o port do consumidor `VsnWeightPersister` do `inference` por duck typing.

A família de cada variável vem do COMANDO (`variable_families`: a família da registry,
ou `"none"` para o calendário, o alvo passado e o índice relativo); variável sem família
declarada é `ValueError`. `timestamp_utc` é o da sessão da decisão na grade do dataset, e
`year = int(timestamp_utc[:4])`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
    Row,
)

_LAYER = "silver"
_TABLE = "fact_vsn_weights"


@dataclass(frozen=True)
class VsnDecisionEntry:
    """Os pesos do encoder de uma decisão: variável → peso."""

    decision_idx: int
    weights: Mapping[str, float]


@dataclass(frozen=True)
class PersistVsnWeightsCommand:
    """DTO de entrada — um run inteiro e a família de cada variável."""

    run_id: str
    model_version: str
    asset: str
    feature_set_name: str
    schema_version: int
    dataset_timestamps: Sequence[str]
    variable_families: Mapping[str, str]
    decisions: Sequence[VsnDecisionEntry]


@dataclass(frozen=True)
class PersistVsnWeightsResult:
    """DTO de saída — linhas gravadas."""

    rows_written: int


class PersistVsnWeights:
    """Persiste os pesos da VSN de um run numa escrita só."""

    def __init__(self, *, repository: AnalyticsRepository) -> None:
        self._repository = repository

    def __call__(self, command: PersistVsnWeightsCommand) -> PersistVsnWeightsResult:
        """Monta uma linha por (decisão, variável) e grava o run."""
        rows: list[Row] = []
        n_sessions = len(command.dataset_timestamps)
        for entry in command.decisions:
            if not 0 <= entry.decision_idx < n_sessions:
                raise ValueError(
                    f"decision_idx {entry.decision_idx} is outside the dataset grid "
                    f"(0..{n_sessions - 1})"
                )
            timestamp = command.dataset_timestamps[entry.decision_idx]
            for variable, weight in entry.weights.items():
                if variable not in command.variable_families:
                    raise ValueError(f"variable {variable!r} has no declared family")
                rows.append(
                    {
                        "schema_version": command.schema_version,
                        "run_id": command.run_id,
                        "model_version": command.model_version,
                        "asset": command.asset,
                        "feature_set_name": command.feature_set_name,
                        "decision_idx": entry.decision_idx,
                        "timestamp_utc": timestamp,
                        "variable": variable,
                        "family": command.variable_families[variable],
                        "weight": float(weight),
                        "year": int(timestamp[:4]),
                    }
                )
        if rows:
            self._repository.write(layer=_LAYER, table=_TABLE, rows=rows, allow_upsert=False)
        return PersistVsnWeightsResult(rows_written=len(rows))
