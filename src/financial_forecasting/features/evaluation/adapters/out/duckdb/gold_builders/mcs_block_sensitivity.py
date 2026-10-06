"""`McsBlockSensitivityGoldBuilder` — `GoldBuilder` da tabela `gold_mcs_block_sensitivity`.

Uma linha por modelo de cada rodada do MCS com bloco de sensibilidade (`McsBlockRun`,
Stage 6.6; ADR 6.6.0002): regra (`h`/`sqrt_T`), bloco efetivo, esquema e as colunas da
eliminação (as mesmas do `gold_mcs_results`). Rodada `error` → uma linha com `model`
nulo, o motivo e a mensagem, e as colunas do MCS nulas. Sem regras de perfil → nenhuma
rodada, nenhuma linha.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_MCS_BLOCK_SENSITIVITY,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
    McsBlockRun,
)

_ERROR = "error"


def _rows(run: McsBlockRun) -> list[dict[str, object]]:
    common: dict[str, object] = {
        "horizon": run.horizon,
        "block_rule": run.block_rule,
        "status": run.status.value,
        "detail": run.detail,
        "scheme": run.scheme.value,
        "block_size": run.block_size,
    }
    report = run.report
    if report is None:
        return [
            {
                **common,
                "model": None,
                "undefined_reason": _ERROR,
                "elimination_rank": None,
                "step_p_value": None,
                "mcs_p_value": None,
                "included": None,
                "alpha": None,
                "reps": None,
                "seed": None,
                "n_points": None,
            }
        ]
    return [
        {
            **common,
            "model": elimination.model,
            "undefined_reason": None,
            "elimination_rank": rank,
            "step_p_value": elimination.step_p_value,
            "mcs_p_value": elimination.mcs_p_value,
            "included": elimination.model in report.included,
            "alpha": report.alpha,
            "reps": report.reps,
            "seed": report.seed,
            "n_points": report.n_points,
        }
        for rank, elimination in enumerate(report.eliminations, start=1)
    ]


class McsBlockSensitivityGoldBuilder:
    """MCS com bloco l = h e l = ceil(sqrt(T)), uma linha por modelo de cada rodada."""

    name = "mcs_block_sensitivity"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por modelo (ou uma linha de erro) de cada rodada por bloco."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [{**base, **row} for run in inputs.mcs_block_reports for row in _rows(run)]
        return GoldTable.sorted_by_key(
            GOLD_MCS_BLOCK_SENSITIVITY.name, GOLD_MCS_BLOCK_SENSITIVITY.key, rows
        )
