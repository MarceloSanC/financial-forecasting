"""VO `BlockEstimate` e o enum `UndefinedReason` — a estimativa b̂_sb de um par (6.4).

Value object de domínio **frozen, stdlib-only** (concept 6.4 I11, C6; ADR `6_4_0002`
item 4). Para um par de modelos da `PairedLossSeries` de um horizonte, carrega
**exatamente um** de:

- `value`: a estimativa de Politis-White do bloco estacionário (finita, ≥ 0), vinda do
  `McsBackend.optimal_block_length`; ou
- `reason`: por que a estimativa é indefinida — diferencial constante ou série que
  falha `validate_block_length_request` (detectados **no domínio antes** do backend,
  pelo passo de pré-condições) ou `ArithmeticError` do backend (convertido pelo use
  case; qualquer outra exceção propaga).

Mora em `value_objects/` para que o `QualityCheckContext` (registry) e o check de
pré-condições o importem sem ciclo registry ↔ check (technical 6.4 §1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)

_PAIR_SIZE = 2


class UndefinedReason(StrEnum):
    """Motivo de uma estimativa b̂_sb indefinida (vira o `kind` do FAIL)."""

    CONSTANT_DIFFERENTIAL = "constant_differential"
    INVALID_SERIES = "invalid_series"
    BACKEND_ARITHMETIC = "backend_arithmetic"


@dataclass(frozen=True)
class BlockEstimate:
    """Estimativa b̂_sb de um par: valor definido **ou** motivo de indefinição.

    Campos:
        pair: `(modelo_i, modelo_j)`, dois nomes distintos não-vazios.
        value: estimativa finita ≥ 0, ou `None` quando indefinida.
        reason: motivo da indefinição, ou `None` quando definida.
        detail: texto do motivo (obrigatório com `reason`; pode ser vazio com `value`).

    Raises:
        ValueError: par mal-formado, ambos/nenhum de `value`/`reason`, valor inválido
            ou motivo sem detalhe, na construção.
    """

    pair: tuple[str, str]
    value: float | None
    reason: UndefinedReason | None
    detail: str

    def __post_init__(self) -> None:
        """Par, exclusividade valor x motivo e forma de cada lado."""
        pair = self.pair
        if not isinstance(pair, tuple) or len(pair) != _PAIR_SIZE:
            raise ValueError(f"pair must be a (model, model) tuple, got {pair!r}")
        for name in pair:
            check_non_empty_str(name, field="pair model")
        if pair[0] == pair[1]:
            raise ValueError(f"pair must name two distinct models, got {pair!r}")
        if (self.value is None) == (self.reason is None):
            raise ValueError(
                "exactly one of value and reason must be set, got "
                f"value={self.value!r} and reason={self.reason!r}"
            )
        if not isinstance(self.detail, str):
            raise ValueError(f"detail must be a str, got {self.detail!r}")
        if self.value is not None and (not is_finite_number(self.value) or self.value < 0.0):
            raise ValueError(f"value must be a finite number >= 0, got {self.value!r}")
        if self.reason is not None:
            if not isinstance(self.reason, UndefinedReason):
                raise ValueError(f"reason must be an UndefinedReason, got {self.reason!r}")
            check_non_empty_str(self.detail, field="detail")

    @property
    def is_defined(self) -> bool:
        """`True` quando há estimativa (`value`)."""
        return self.value is not None
