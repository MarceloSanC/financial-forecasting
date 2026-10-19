"""VO `PermutedForecastRecord` — uma linha de `fact_permuted_predictions` com o run (7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; ADR 7.3.0002 item 4). Uma
linha longa da tabela de atribuição (um nível de quantil de uma decisão, um horizonte, uma
família permutada e uma permutação) com a identidade do run: `seed` e `fold_index` vêm do
`dim_run` do mesmo `run_id` (junção na leitura, como no `ForecastRecord`).

A identidade do modelo é a linha `(permuted_family = "none", permutation_index = 0)`; toda
outra linha é uma família das quatro do ADR 0.0.0016 com `k >= 1` (I7). A forma de cada
campo é validada aqui; as regras entre linhas (grade completa, uma observação por ponto,
`(família, k)` presente para todo k) são da redução por run e da montagem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

IDENTITY_FAMILY: Final = "none"
"""A família da linha de identidade (sem permutação, `permutation_index = 0`)."""

PERMUTED_FAMILY_VOCABULARY: Final = frozenset({IDENTITY_FAMILY, *H3_FAMILIES})


def check_family(value: object, *, field: str) -> None:
    """A família de uma linha de atribuição: `"none"` ou uma das quatro do ADR 0.0.0016."""
    if value not in PERMUTED_FAMILY_VOCABULARY:
        raise ValueError(
            f"{field} must be one of {sorted(PERMUTED_FAMILY_VOCABULARY)}, got {value!r}"
        )


@dataclass(frozen=True, kw_only=True)
class PermutedForecastRecord:
    """Um nível de quantil de uma predição de atribuição, com a identidade do run.

    Raises:
        ValueError: campo fora da forma, família fora do vocabulário, ou `none` sem
            `permutation_index = 0` (e vice-versa).
    """

    run_id: str
    model: str
    seed: int
    fold_index: int
    permuted_family: str
    permutation_index: int
    permutation_seed: int
    permutation_algorithm: str
    partition_hash: str
    horizon: int
    decision_idx: int
    decision_timestamp: str
    target_timestamp: str
    quantile_level: float
    value_raw: float
    value_guardrail: float
    guardrail_applied: bool

    def __post_init__(self) -> None:
        """Forma de cada campo e a regra `none ⇔ 0` (mensagem nomeia o campo)."""
        for field in (
            "run_id",
            "model",
            "permutation_algorithm",
            "decision_timestamp",
            "target_timestamp",
        ):
            check_non_empty_str(getattr(self, field), field=field)
        for field in ("seed", "fold_index", "permutation_index", "permutation_seed"):
            validate_int_at_least(getattr(self, field), minimum=0, field=field)
        validate_int_at_least(self.decision_idx, minimum=0, field="decision_idx")
        validate_horizon(self.horizon, field="horizon")
        validate_sha256_hex(self.partition_hash, field="partition_hash")
        check_family(self.permuted_family, field="permuted_family")
        if (self.permuted_family == IDENTITY_FAMILY) != (self.permutation_index == 0):
            raise ValueError(
                "permuted_family 'none' iff permutation_index 0 (the identity row), got "
                f"{self.permuted_family!r} with index {self.permutation_index!r}"
            )
        level = self.quantile_level
        if not isinstance(level, float) or not is_finite_number(level):
            raise ValueError(f"quantile_level must be a finite float, got {level!r}")
        for field in ("value_raw", "value_guardrail"):
            if not isinstance(getattr(self, field), float):
                raise ValueError(f"{field} must be a float, got {getattr(self, field)!r}")
        if type(self.guardrail_applied) is not bool:
            raise ValueError(f"guardrail_applied must be a bool, got {self.guardrail_applied!r}")
