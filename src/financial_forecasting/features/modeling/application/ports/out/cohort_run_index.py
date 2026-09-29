"""Port-out `CohortRunIndex` — o que o silver já tem de um cohort (Stage 5.5).

A retomada classifica cada unidade pelo que está gravado (ADR 5.5.0003, I7) e o
`verify` confere contagens e alinhamento (A8). Ambos precisam, por cohort, de:
quais runs existem em `dim_run`, de que fold, quantas linhas de predição cada um
tem em `fact_oos_predictions` e quais `target_timestamp` por horizonte.

Port consumer-owned do slice modeling (ADR 0.0.0053): o use case do cohort NÃO
recebe o `AnalyticsRepository` alheio. A assinatura usa só tipos builtin porque o
adapter vive no slice `analytics_store` e não pode importar tipos do modeling.

Formato devolvido:
    (model_version, seed) -> {run_id: (fold, linhas, {horizonte: frozenset[target ISO]})}
`seed` é `None` nas baselines. Run sem predição (órfão de `dim_run`) aparece com
0 linhas e conjuntos vazios.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

RunSummary = tuple[str, int, Mapping[int, frozenset[str]]]
"""(fold, linhas de predição, {horizonte: conjunto de target_timestamp ISO})."""


class CohortRunIndex(Protocol):
    """Leitura, por cohort, dos runs gravados e das suas predições."""

    def recorded_runs(
        self, *, asset_id: str, feature_set_name: str, cohort_id: str
    ) -> Mapping[tuple[str, int | None], Mapping[str, RunSummary]]:
        """`(model_version, seed) -> {run_id: (fold, linhas, targets por horizonte)}`."""
        ...
