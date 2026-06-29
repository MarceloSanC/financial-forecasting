"""`DatasetQualityGate` — gate de qualidade warmup-aware (domain service puro).

Serviço de domínio **puro stdlib-only** que valida o dataset montado ANTES de
persistir (concept 3.5 I5, D4). Opera sobre `Sequence`/`Mapping` — **nunca**
`DataFrame` (pandas vive só em `adapters/out`, I6) — e lê o warmup por feature do
`FeatureRegistry` (3.4), sem lista `FEATURE_WARMUP_BARS` paralela (D4 corrige o old,
que mantinha a lista à parte e podia divergir).

Quatro checagens (concept 3.5 I5 / old `dataset_quality_gate.py:87-99`):

- **(a) warmup + missing** — para cada feature, desconta o seu `warmup_count`
  (do registry) das primeiras linhas e mede o NaN-ratio só **após** o warmup; se
  o ratio exceder `max_nan_ratio_per_feature`, a feature entra em `failing_features`
  (ordenado desc. por ratio) → `DatasetQualityError` (C5).
- **(b) monotonicidade** — timestamps únicos (`require_unique_timestamps`) e
  ordenados crescente (`require_monotonic_timestamps`); violação → erro (C4).
- **(c) cobertura temporal** — span de dias `>= min_temporal_coverage_days` (C6).

A 1ª linha do dataset já foi dropada na montagem (alvo backward, ADR 3.5.0001), de
modo que o warmup do gate é medido sobre o frame final (paridade com o old, que
chamava `DatasetQualityGate.validate(..., warmup_counts=FEATURE_WARMUP_BARS)` após
o `dropna` do alvo).

Pureza (I6): importa SÓ stdlib + o `FeatureRegistry`/`DomainError` do domínio.
`import pandas`/`numpy` aqui REPROVA `domain-purity` no import-linter.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    get_feature_spec,
)
from financial_forecasting.shared.domain.exceptions.base import DomainError


class DatasetQualityError(DomainError):
    """Falha de gate de qualidade do dataset (warmup/missing/monotonia/cobertura).

    Erro de domínio **nomeável** (subclasse de `DomainError`) — substitui o
    `ValueError` cru do old (`dataset_quality_gate.py`) por um erro que o handler
    de aplicação distingue dos demais (C4/C5/C6).
    """


@dataclass(frozen=True)
class DatasetQualityGateConfig:
    """Configuração imutável do gate (porta verbatim do old `:9-13`, D4).

    - `max_nan_ratio_per_feature`: NaN-ratio máximo tolerado por feature **após**
      descontar o warmup (default `1.0` = sem limite, como o old).
    - `require_unique_timestamps`: exige timestamps sem duplicados (default `True`).
    - `require_monotonic_timestamps`: exige timestamps crescentes (default `True`).
    - `min_temporal_coverage_days`: span mínimo de dias do dataset (default `1`).
    """

    max_nan_ratio_per_feature: float = 1.0
    require_unique_timestamps: bool = True
    require_monotonic_timestamps: bool = True
    min_temporal_coverage_days: int = 1


def _is_missing(value: object) -> bool:
    """`True` se `value` é `None` ou `NaN` (faltante — paridade `pd.isna` escalar)."""
    return value is None or (isinstance(value, float) and math.isnan(value))


class DatasetQualityGate:
    """Gate de qualidade do dataset montado (concept 3.5 §4 / I5).

    Sem estado: pode ser instanciado uma vez e reusado. `validate` levanta
    `DatasetQualityError` na primeira violação que encontra (ordem: monotonia →
    cobertura → missing), sem silenciar.
    """

    def validate(
        self,
        *,
        timestamps: Sequence[object],
        rows: Sequence[Mapping[str, object]],
        feature_cols: Sequence[str],
        config: DatasetQualityGateConfig,
    ) -> None:
        """Valida o dataset; levanta `DatasetQualityError` na 1ª violação.

        - `timestamps`: 1 valor por linha (ordenável/comparável; tipicamente
          `datetime`), alinhado com `rows`.
        - `rows`: o dataset montado, 1 `Mapping` por linha.
        - `feature_cols`: as colunas de feature a checar (set/ordem do registry);
          o warmup de cada uma vem de `FeatureRegistry.get_feature_spec(col)`.
        """
        if len(timestamps) != len(rows):
            raise DatasetQualityError(
                f"timestamps ({len(timestamps)}) and rows ({len(rows)}) length mismatch"
            )
        self._check_timestamps(timestamps, config)
        self._check_temporal_coverage(timestamps, config)
        self._check_missing(rows, feature_cols, config)

    # -- (b) monotonicidade --------------------------------------------------

    @staticmethod
    def _check_timestamps(timestamps: Sequence[object], config: DatasetQualityGateConfig) -> None:
        """C4 — timestamps únicos e/ou monótonos crescentes, conforme a config."""
        if config.require_unique_timestamps and len(set(timestamps)) != len(timestamps):
            raise DatasetQualityError("Duplicate timestamps found while building TFT dataset")
        if config.require_monotonic_timestamps:
            monotonic = all(
                timestamps[i - 1] < timestamps[i]  # type: ignore[operator]
                for i in range(1, len(timestamps))
            )
            if not monotonic:
                raise DatasetQualityError("Timestamps are not monotonic in TFT dataset")

    # -- (c) cobertura temporal ----------------------------------------------

    @staticmethod
    def _check_temporal_coverage(
        timestamps: Sequence[object], config: DatasetQualityGateConfig
    ) -> None:
        """C6 — span de dias do dataset `>= min_temporal_coverage_days`."""
        if not timestamps:
            coverage_days = 0
        else:
            span = max(timestamps) - min(timestamps)  # type: ignore[operator, type-var]
            coverage_days = int(getattr(span, "days", 0)) + 1
        if coverage_days < int(config.min_temporal_coverage_days):
            raise DatasetQualityError(
                f"Temporal coverage insufficient: {coverage_days} day(s) < required "
                f"{int(config.min_temporal_coverage_days)}"
            )

    # -- (a) warmup + missing ------------------------------------------------

    @staticmethod
    def _check_missing(
        rows: Sequence[Mapping[str, object]],
        feature_cols: Sequence[str],
        config: DatasetQualityGateConfig,
    ) -> None:
        """C5 — NaN-ratio por feature `<= max`, medido APÓS descontar o warmup.

        Para cada feature, dropa as primeiras `warmup_count` linhas (do registry) e
        mede o NaN-ratio sobre o restante; features acima do limite entram em
        `failing_features` (ordenado desc. por ratio). Feature cuja série fica vazia
        após o warmup não é avaliada (paridade `features_not_evaluated` do old).
        """
        max_allowed = float(config.max_nan_ratio_per_feature)
        failing: dict[str, float] = {}
        for col in feature_cols:
            warmup = max(0, get_feature_spec(col).warmup_count)
            effective = [row.get(col) for row in rows][warmup:]
            if not effective:
                continue  # série vazia pós-warmup → não avaliada (old)
            ratio = sum(1 for value in effective if _is_missing(value)) / len(effective)
            if ratio > max_allowed:
                failing[col] = ratio
        if failing:
            ordered = sorted(failing.items(), key=lambda kv: kv[1], reverse=True)
            detail = ", ".join(f"{name}={ratio:.4f}" for name, ratio in ordered)
            raise DatasetQualityError(
                f"NaN-ratio above {max_allowed} for features (desc): {detail}"
            )
