"""`DmProfilesGoldBuilder` — satisfaz o port `GoldBuilder` (tabela `gold_dm_profiles`).

Uma linha por unidade (recorte, comparador) do `DmProfilesReport` de cada horizonte
(Stage 6.6; ADR 6.6.0003): dimensão `fold`/`seed`/`tau` com as colunas tipadas da
dimensão, o status e o motivo de uma unidade indefinida, a janela e, quando calculada,
o `DieboldMarianoResult` com a rejeição à alpha bruta. Revisão sem regras de perfil
(`dm_profiles` ausente) → nenhuma linha.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_DM_PROFILES,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class DmProfilesGoldBuilder:
    """DM por fold, por seed e por nível, uma linha por (recorte, comparador)."""

    name = "dm_profiles"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por unidade de cada horizonte com regras de perfil."""
        base = partition_columns(inputs, confirmatory=True)
        rows = []
        for profile in inputs.profile_reports:
            report = profile.dm_profiles
            if report is None:
                continue
            for row in report.rows:
                result = row.result
                rows.append(
                    {
                        **base,
                        "horizon": report.horizon,
                        "dimension": row.dimension.value,
                        "fold": row.fold,
                        "seed": row.seed,
                        "level": row.level,
                        "comparator": row.comparator,
                        "candidate": report.candidate,
                        "status": row.status.value,
                        "undefined_reason": row.undefined_reason,
                        "detail": row.detail,
                        "n_points": row.n_points,
                        "first_target_timestamp": row.first_target_timestamp,
                        "last_target_timestamp": row.last_target_timestamp,
                        "variance_estimator": report.variance_estimator.value,
                        "mean_differential": None if result is None else result.mean_differential,
                        "statistic": None if result is None else result.statistic,
                        "p_value": None if result is None else result.p_value,
                        "rejected": row.rejected,
                        "fallback_applied": None if result is None else result.fallback_applied,
                        "horizon_used": None if result is None else result.horizon_used,
                        "alpha": report.alpha,
                    }
                )
        return GoldTable.sorted_by_key(GOLD_DM_PROFILES.name, GOLD_DM_PROFILES.key, rows)
