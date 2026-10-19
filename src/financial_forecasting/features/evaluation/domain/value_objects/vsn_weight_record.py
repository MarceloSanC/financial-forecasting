"""VO `VsnWeightRecord` — uma linha de `fact_vsn_weights` com o run (Stage 7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; ADR 7.3.0002 item 4). O peso
de seleção do encoder de uma variável numa decisão de teste, com a identidade do run
(`seed` e `fold_index` do `dim_run`). A família é a da partição gravada (`"none"` para
calendário, alvo passado e índice relativo de tempo). As regras entre linhas são da
redução `reduce_vsn_run`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_forecast_record import (  # noqa: E501
    check_family,
)


@dataclass(frozen=True, kw_only=True)
class VsnWeightRecord:
    """O peso da VSN de uma variável numa decisão, com a identidade do run.

    Raises:
        ValueError: campo fora da forma, família fora do vocabulário ou peso fora de
            [0, 1] (a VSN devolve pesos de softmax).
    """

    run_id: str
    model: str
    seed: int
    fold_index: int
    decision_idx: int
    decision_timestamp: str
    variable: str
    family: str
    weight: float

    def __post_init__(self) -> None:
        """Forma de cada campo (mensagem nomeia o campo)."""
        for field in ("run_id", "model", "decision_timestamp", "variable"):
            check_non_empty_str(getattr(self, field), field=field)
        for field in ("seed", "fold_index", "decision_idx"):
            validate_int_at_least(getattr(self, field), minimum=0, field=field)
        check_family(self.family, field="family")
        weight = self.weight
        if not isinstance(weight, float) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError(f"weight must be a finite float in [0, 1], got {weight!r}")
