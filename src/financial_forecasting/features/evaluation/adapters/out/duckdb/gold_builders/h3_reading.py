"""`H3ReadingGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_h3_reading`).

Mapeamento puro da leitura de H3 (ADR 7.3.0001 item 4; technical 7.3 §1). Uma linha,
chave `(reading_rule,)` = o id da regra de leitura do `[h3]`:

- `heterogeneous_*`, `sustained`, `agreeing_families` (texto `"a,b"` ordenado, `""` sem
  família), `label` (o rótulo exato da leitura), `status`/`reason`;
- o bootstrap conjunto: `block_length`, `max_block_estimate`, `n_points` (T), e do plano
  `reps` e `bootstrap_seed`;
- a contagem de réplicas com Σ* <= 0 por método e horizonte;
- `ablation_cohort_id`, o cohort de ablação do `[h3]`.

Sem bloco `[h3]` → zero linhas.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_READING,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)
from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContributionReport,
)

Row = dict[str, object]


def _nonpositive(report: FamilyContributionReport | None, horizon: int) -> int | None:
    return None if report is None else report.nonpositive_replicas.get(horizon)


class H3ReadingGoldBuilder:
    """A leitura de H3 numa linha, com o bootstrap e as contagens."""

    name = "h3_reading"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha com a leitura (zero sem `[h3]`)."""
        reports = inputs.h3_reports
        parameters = inputs.parameters.h3_parameters
        reading = reports.reading
        rows: list[Row] = []
        if reading is not None and parameters is not None:
            rows.append(
                {
                    **partition_columns(inputs, confirmatory=True),
                    "reading_rule": parameters.reading_rule,
                    "heterogeneous_permutation": reading.heterogeneous_permutation,
                    "heterogeneous_ablation": reading.heterogeneous_ablation,
                    "sustained": reading.sustained,
                    "agreeing_families": ",".join(sorted(reading.agreeing_families)),
                    "block_length": reports.block_length,
                    "max_block_estimate": reports.max_block_estimate,
                    "reps": parameters.reps,
                    "bootstrap_seed": parameters.bootstrap_seed,
                    "n_points": reports.n_points,
                    "nonpositive_permutation_h1": _nonpositive(reports.permutation, 1),
                    "nonpositive_permutation_h7": _nonpositive(reports.permutation, 7),
                    "nonpositive_ablation_h1": _nonpositive(reports.ablation, 1),
                    "nonpositive_ablation_h7": _nonpositive(reports.ablation, 7),
                    "ablation_cohort_id": parameters.ablation_cohort_id,
                    "label": reading.label,
                    "status": reading.status,
                    "reason": reading.reason,
                }
            )
        return GoldTable.sorted_by_key(GOLD_H3_READING.name, GOLD_H3_READING.key, rows)
