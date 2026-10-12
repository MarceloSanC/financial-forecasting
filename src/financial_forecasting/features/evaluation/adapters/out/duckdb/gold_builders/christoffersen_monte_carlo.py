"""`ChristoffersenMonteCarloGoldBuilder` — `GoldBuilder` de `gold_christoffersen_monte_carlo`.

Uma linha por sequência de hits de h = 1 (não-DGT) com o p-valor Monte Carlo de
LR_uc/LR_ind/LR_cc (`MonteCarloRow` do `ProfileReports`, Stage 6.6; ADR 6.3.0006): a
mesma identidade de sequência da `gold_calibration_table` (modelo, seed, amostra, tipo,
níveis, inclusão das degeneradas), os dois status do `MonteCarloPValues` pelo valor, o
`draws`/`seed` do plano e as tentativas. Unidade `error` → p-valores e status nulos com a
mensagem. Só existe em h = 1: nenhuma linha de outro horizonte.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)

_INTERVAL_LEVELS = 2


class ChristoffersenMonteCarloGoldBuilder:
    """P-valores Monte Carlo de Christoffersen em h = 1, uma linha por sequência."""

    name = "christoffersen_monte_carlo"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por `MonteCarloRow` de cada horizonte (só h = 1 as tem)."""
        base = partition_columns(inputs, confirmatory=True)
        rows = []
        for profile in inputs.profile_reports:
            for row in profile.monte_carlo:
                values = row.values
                rows.append(
                    {
                        **base,
                        "model": row.model,
                        "seed": row.seed,
                        "horizon": profile.horizon,
                        "sample": row.sample.value,
                        "kind": row.kind.value,
                        "level_low": row.levels[0],
                        "level_high": (
                            row.levels[1] if len(row.levels) == _INTERVAL_LEVELS else None
                        ),
                        "includes_degenerate": row.includes_degenerate,
                        "status": row.status.value,
                        "detail": row.detail,
                        "uc_status": None if values is None else values.uc_status.value,
                        "ind_status": None if values is None else values.ind_status.value,
                        "mc_p_uc": None if values is None else values.p_uc,
                        "mc_p_ind": None if values is None else values.p_ind,
                        "mc_p_cc": None if values is None else values.p_cc,
                        "draws": inputs.parameters.monte_carlo_draws,
                        "mc_seed": inputs.parameters.monte_carlo_seed,
                        "attempts": None if values is None else values.attempts,
                    }
                )
        return GoldTable.sorted_by_key(
            GOLD_CHRISTOFFERSEN_MONTE_CARLO.name, GOLD_CHRISTOFFERSEN_MONTE_CARLO.key, rows
        )
