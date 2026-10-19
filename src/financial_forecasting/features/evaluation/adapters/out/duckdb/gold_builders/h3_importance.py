"""`H3ImportanceGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_h3_importance`).

Mapeamento puro das importâncias de H3 (ADR 7.3.0001 item 4; technical 7.3 §1, "Colunas
das tabelas gold"). Chave `(method, family, horizon, seed, permutation_index)`:

- a linha agregada `(seed nulo, k nulo)` = I_f(h), com o status e o motivo do método
  (no método `undefined` por total não positivo a importância continua a do ponto; sem
  importância calculada, nula);
- o perfil por seed `(s, nulo)` e, só na permutação, o perfil por permutação `(nulo, k)`,
  das séries d_t do método (ausentes quando a montagem foi `undefined`);
- `n_points` = T, o número de decisões das séries d_t DO MÉTODO (nulo sem elas).

Sem bloco `[h3]` → zero linhas.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_IMPORTANCE,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)
from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContributionReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)

Row = dict[str, object]
_FAMILIES = ("price", "technical", "sentiment", "fundamental")
_HORIZONS = (1, 7)


def _method_rows(
    base: Row,
    report: FamilyContributionReport,
    differentials: FamilyLossDifferentials | None,
    n_points: int | None,
) -> list[Row]:
    status = {"status": report.status, "reason": report.reason, "n_points": n_points}
    rows: list[Row] = [
        {
            **base,
            **status,
            "method": report.method,
            "family": family,
            "horizon": horizon,
            "seed": None,
            "permutation_index": None,
            "importance": report.importance.get((family, horizon)),
        }
        for family in _FAMILIES
        for horizon in _HORIZONS
    ]
    if differentials is None:
        return rows
    rows += [
        {
            **base,
            **status,
            "method": report.method,
            "family": family,
            "horizon": horizon,
            "seed": seed,
            "permutation_index": None,
            "importance": value,
        }
        for (family, horizon, seed), value in differentials.seed_importances.items()
    ]
    rows += [
        {
            **base,
            **status,
            "method": report.method,
            "family": family,
            "horizon": horizon,
            "seed": None,
            "permutation_index": k,
            "importance": value,
        }
        for (family, horizon, k), value in differentials.permutation_importances.items()
    ]
    return rows


class H3ImportanceGoldBuilder:
    """Importâncias de H3: a agregada e os perfis por seed e por permutação."""

    name = "h3_importance"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """As linhas dos dois métodos (zero sem `[h3]`)."""
        reports = inputs.h3_reports
        base = partition_columns(inputs, confirmatory=True)
        rows: list[Row] = []
        for report, differentials in (
            (reports.permutation, reports.permutation_differentials),
            (reports.ablation, reports.ablation_differentials),
        ):
            if report is not None:
                # n_points do PRÓPRIO método (C8-11): o T das suas séries d_t, nulo sem elas
                n_points = None if differentials is None else len(differentials.decision_timestamps)
                rows += _method_rows(base, report, differentials, n_points)
        return GoldTable.sorted_by_key(GOLD_H3_IMPORTANCE.name, GOLD_H3_IMPORTANCE.key, rows)
