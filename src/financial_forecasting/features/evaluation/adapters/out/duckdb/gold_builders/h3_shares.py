"""`H3SharesGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_h3_shares`).

Mapeamento puro das participações e dos intervalos de Δ_f (ADR 7.3.0001 item 4; technical
7.3 §1). Chave `(method, family)`, uma linha por família em cada método:

- limite infinito (réplicas com Σ* <= 0, I14) vai como `null` com `lower_infinite` /
  `upper_infinite = true` (o padrão da 7.2; o `GoldTable` recusa não finito);
- `status`/`reason` da família; `method_status`/`method_reason` do método; método
  `undefined` ⇒ as quatro linhas com medidas nulas, `status = "undefined"` e o motivo;
- `nonpositive_replicas_h1/h7` = a contagem de réplicas com Σ* <= 0 por horizonte.

Sem bloco `[h3]` → zero linhas.
"""

from __future__ import annotations

import math

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_SHARES,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)

Row = dict[str, object]


def _bound(value: float | None) -> tuple[float | None, bool | None]:
    """(valor finito ou nulo, flag de infinito) — nulo e flag nula sem limite."""
    if value is None:
        return None, None
    if math.isinf(value):
        return None, True
    return value, False


class H3SharesGoldBuilder:
    """Participações, Δ_f, intervalo básico e leitura por família em cada método."""

    name = "h3_shares"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por (método, família) (zero sem `[h3]`)."""
        reports = inputs.h3_reports
        base = partition_columns(inputs, confirmatory=True)
        rows: list[Row] = []
        for report in (reports.permutation, reports.ablation):
            if report is None:
                continue
            for share in report.shares:
                lower, lower_infinite = _bound(share.lower)
                upper, upper_infinite = _bound(share.upper)
                rows.append(
                    {
                        **base,
                        "method": report.method,
                        "family": share.family,
                        "share_h1": share.share_h1,
                        "share_h7": share.share_h7,
                        "delta": share.delta,
                        "lower": lower,
                        "upper": upper,
                        "lower_infinite": lower_infinite,
                        "upper_infinite": upper_infinite,
                        "level": report.level,
                        "side": share.side,
                        "excludes_zero": share.excludes_zero,
                        "status": share.status,
                        "reason": share.reason,
                        "nonpositive_replicas_h1": report.nonpositive_replicas.get(1),
                        "nonpositive_replicas_h7": report.nonpositive_replicas.get(7),
                        "method_status": report.status,
                        "method_reason": report.reason,
                    }
                )
        return GoldTable.sorted_by_key(GOLD_H3_SHARES.name, GOLD_H3_SHARES.key, rows)
