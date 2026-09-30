"""`McsResultsGoldBuilder` — satisfaz o port `GoldBuilder` (tabela `gold_mcs_results`).

Uma linha por modelo de cada `McsReport` (horizonte x esquema de bootstrap): posição na
ordem de eliminação (1 = primeiro eliminado; o sobrevivente é o último), p do passo, p
do MCS, pertença, alfa, estatística, parâmetros do bootstrap (reps, seed, bloco, gerador)
e T. As b̂_sb que definiram o bloco vêm dos `GoldInputs.block_estimates`: a maior em
`max_block_estimate` e todas em `block_estimates` (`"a|b=<valor>;…"`, na ordem de
`model_pairs()`).
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_MCS_RESULTS
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
)


def _estimates_text(estimates: Sequence[BlockEstimate]) -> str:
    return ";".join(f"{e.pair[0]}|{e.pair[1]}={e.value!r}" for e in estimates)


def _max_estimate(estimates: Sequence[BlockEstimate]) -> float | None:
    values = [e.value for e in estimates if e.value is not None]
    return max(values) if values else None


class McsResultsGoldBuilder:
    """Model Confidence Set por horizonte e esquema, uma linha por modelo."""

    name = "mcs_results"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por modelo de cada relatório MCS."""
        base = partition_columns(inputs, confirmatory=True)
        rows = []
        for report in inputs.mcs_reports:
            estimates = inputs.block_estimates.get(report.horizon, ())
            for rank, elimination in enumerate(report.eliminations, start=1):
                rows.append(
                    {
                        **base,
                        "horizon": report.horizon,
                        "scheme": report.scheme.value,
                        "model": elimination.model,
                        "elimination_rank": rank,
                        "step_p_value": elimination.step_p_value,
                        "mcs_p_value": elimination.mcs_p_value,
                        "included": elimination.model in report.included,
                        "alpha": report.alpha,
                        "statistic": report.statistic,
                        "reps": report.reps,
                        "seed": report.seed,
                        "block_size": report.block_size,
                        "generator": report.generator,
                        "n_points": report.n_points,
                        "max_block_estimate": _max_estimate(estimates),
                        "block_estimates": _estimates_text(estimates),
                    }
                )
        return GoldTable.sorted_by_key(GOLD_MCS_RESULTS.name, GOLD_MCS_RESULTS.key, rows)
