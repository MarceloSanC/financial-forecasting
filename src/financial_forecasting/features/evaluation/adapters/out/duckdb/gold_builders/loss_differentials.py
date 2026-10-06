"""`LossDifferentialsGoldBuilder` — `GoldBuilder` da tabela `gold_loss_differentials`.

Uma linha por ponto da série d_t = L_a - L_b de cada par da série pareada primária, com o
fold do ponto quando a montagem o tem (Stage 6.6; insumo do plot de d_t da 8.3). Não
depende de regra de perfil: gravada também sob o r0 (concept I9).
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_LOSS_DIFFERENTIALS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class LossDifferentialsGoldBuilder:
    """A série d_t de cada par, ponto a ponto."""

    name = "loss_differentials"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por (par, alvo) de cada horizonte."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [
            {
                **base,
                "horizon": profile.horizon,
                "model_a": series.pair[0],
                "model_b": series.pair[1],
                "target_timestamp": target,
                "fold": None if series.folds is None else series.folds[index],
                "differential": value,
            }
            for profile in inputs.profile_reports
            for series in profile.differentials
            for index, (target, value) in enumerate(
                zip(series.target_timestamps, series.values, strict=True)
            )
        ]
        return GoldTable.sorted_by_key(
            GOLD_LOSS_DIFFERENTIALS.name, GOLD_LOSS_DIFFERENTIALS.key, rows
        )
