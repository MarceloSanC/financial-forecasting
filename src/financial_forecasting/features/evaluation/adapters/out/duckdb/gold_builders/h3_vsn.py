"""`H3VsnGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_h3_vsn`).

Mapeamento puro do resumo da VSN (ADR 7.3.0001 item 4; technical 7.3 §1). Chave
`(kind, name)` com `kind ∈ {variable, family}`: p10/p50/p90 nas decisões, `n_decisions`,
`family` (a da partição, ou `"none"` para calendário, alvo passado e índice relativo) e o
rótulo exato. Resumo `undefined` ⇒ uma linha por família com medidas nulas, o status e o
motivo, sem rótulo.

Sem bloco `[h3]` → zero linhas.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)
from financial_forecasting.features.evaluation.domain.services.family_contribution import OK
from financial_forecasting.features.evaluation.domain.services.vsn_summary import FAMILY

Row = dict[str, object]


class H3VsnGoldBuilder:
    """Resumo da VSN por variável e por família."""

    name = "h3_vsn"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por variável e por família (zero sem `[h3]`)."""
        summary = inputs.h3_reports.vsn
        parameters = inputs.parameters.h3_parameters
        base = partition_columns(inputs, confirmatory=True)
        rows: list[Row] = []
        if summary is not None and summary.status == OK:
            rows = [
                {
                    **base,
                    "kind": entry.kind,
                    "name": entry.name,
                    "family": entry.family,
                    "p10": entry.p10,
                    "p50": entry.p50,
                    "p90": entry.p90,
                    "n_decisions": entry.n_decisions,
                    "label": summary.label,
                    "status": summary.status,
                    "reason": None,
                }
                for entry in summary.entries
            ]
        elif summary is not None and parameters is not None:
            rows = [
                {
                    **base,
                    "kind": FAMILY,
                    "name": family,
                    "family": family,
                    "p10": None,
                    "p50": None,
                    "p90": None,
                    "n_decisions": None,
                    "label": None,
                    "status": summary.status,
                    "reason": summary.reason,
                }
                for family in parameters.families
            ]
        return GoldTable.sorted_by_key(GOLD_H3_VSN.name, GOLD_H3_VSN.key, rows)
