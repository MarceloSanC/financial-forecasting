"""`PartialDegeneracyGoldBuilder` — `GoldBuilder` da tabela `gold_partial_degeneracy`.

Uma linha por par (simétrico ou adjacente) de cada série (modelo, seed, amostra) do
`ProfileReports` (Stage 6.6; ADR 6.6.0002 T2): a taxa de colapso parcial entre as linhas
não-degeneradas (nula sem nenhuma) e a tolerância do plano. Falha da taxa adjacente de
uma série → uma linha `error` com níveis nulos. Sem regras de perfil → nenhuma linha.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_PARTIAL_DEGENERACY,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class PartialDegeneracyGoldBuilder:
    """Colapso parcial por par simétrico e adjacente, por série."""

    name = "partial_degeneracy"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por par (ou erro) de cada série dos horizontes com regras de perfil."""
        base = partition_columns(inputs, confirmatory=True)
        tolerance = inputs.parameters.degeneracy_tolerance
        rows = [
            {
                **base,
                "model": row.model,
                "seed": row.seed,
                "horizon": profile.horizon,
                "sample": row.sample.value,
                "pair_kind": row.pair_kind.value,
                "level_low": row.level_low,
                "level_high": row.level_high,
                "status": row.status.value,
                "detail": row.detail,
                "collapse_rate": row.collapse_rate,
                "tolerance": tolerance,
            }
            for profile in inputs.profile_reports
            for row in profile.partial_degeneracy or ()
        ]
        return GoldTable.sorted_by_key(
            GOLD_PARTIAL_DEGENERACY.name, GOLD_PARTIAL_DEGENERACY.key, rows
        )
