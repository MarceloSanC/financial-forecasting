"""Value object `BaselineSpec` — as 5 famílias canônicas de baseline pré-registradas.

Frozen, domínio puro (stdlib-only). Uma `BaselineSpec` nomeia UMA das 5 famílias
canônicas de baseline do doc de domínio `quantile-model-training.md` §3 (ordem da
tabela §3.8), com os parâmetros pré-registrados de cada família (ADR 0.0.0052;
ADR 5.2.0003 fixa W = 252 para `historical_quantiles`):

- `zero_return` — ≡ random walk sem drift do log-preço (§3.2); sem parâmetros.
- `historical_mean` — μ̂ do train expansivo (§3.3); sem parâmetros.
- `ar1` — quantis paramétricos gaussianos h-step (§3.5); sem parâmetros na spec
  (μ̂, φ̂, sigma²_eps são estimados por fold — ADR 5.2.0002).
- `ewma_vol` — EWMA RiskMetrics sobre r² (§3.6); exige `decay_lambda ∈ (0, 1)`
  (canônico λ = 0.94, RMTD §5.3.2.2).
- `historical_quantiles` — quantil tipo 7 da janela rolante (§3.7); exige
  `window >= 20` (canônico W = 252 — ADR 5.2.0003).

A construção **valida** (C3 do concept §6): família fora do canônico, parâmetro
obrigatório ausente ou parâmetro proibido presente erguem `ValueError` —
invariante verificada, não assumida (I7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

BASELINE_FAMILIES: Final = (
    "zero_return",
    "historical_mean",
    "ar1",
    "ewma_vol",
    "historical_quantiles",
)
"""As 5 famílias canônicas, na ordem do doc de domínio §3.8."""

_CANONICAL_EWMA_DECAY_LAMBDA: Final = 0.94
_MIN_HISTORICAL_QUANTILES_WINDOW: Final = 20


@dataclass(frozen=True)
class BaselineSpec:
    """Especificação imutável de um baseline canônico (família + parâmetros).

    Attributes:
        family: uma das 5 famílias de `BASELINE_FAMILIES`.
        window: W da janela rolante — obrigatório (>= 20) só em
            `historical_quantiles`; proibido nas demais famílias.
        decay_lambda: λ do EWMA — obrigatório (em (0, 1)) só em `ewma_vol`;
            proibido nas demais famílias.
    """

    family: str
    window: int | None = None
    decay_lambda: float | None = None

    def __post_init__(self) -> None:
        """Valida família canônica e a disciplina de parâmetros por família (C3)."""
        if self.family not in BASELINE_FAMILIES:
            raise ValueError(
                f"BaselineSpec.family must be one of {BASELINE_FAMILIES}; got {self.family!r}"
            )
        if self.family == "ewma_vol":
            if self.decay_lambda is None:
                raise ValueError("BaselineSpec('ewma_vol') requires decay_lambda")
            if not 0.0 < self.decay_lambda < 1.0:
                raise ValueError(
                    f"BaselineSpec.decay_lambda must be in (0, 1); got {self.decay_lambda}"
                )
            if self.window is not None:
                raise ValueError("BaselineSpec('ewma_vol') forbids window")
        elif self.family == "historical_quantiles":
            if self.window is None:
                raise ValueError("BaselineSpec('historical_quantiles') requires window")
            if self.window < _MIN_HISTORICAL_QUANTILES_WINDOW:
                raise ValueError(
                    "BaselineSpec.window must be >= "
                    f"{_MIN_HISTORICAL_QUANTILES_WINDOW}; got {self.window}"
                )
            if self.decay_lambda is not None:
                raise ValueError("BaselineSpec('historical_quantiles') forbids decay_lambda")
        else:
            if self.window is not None:
                raise ValueError(f"BaselineSpec({self.family!r}) forbids window")
            if self.decay_lambda is not None:
                raise ValueError(f"BaselineSpec({self.family!r}) forbids decay_lambda")

    @property
    def model_version(self) -> str:
        """Identidade persistida da spec (`baseline_<family>` — casa `baseline_*`)."""
        return f"baseline_{self.family}"

    @staticmethod
    def canonical_five(*, historical_quantiles_window: int = 252) -> tuple[BaselineSpec, ...]:
        """As 5 specs pré-registradas (ADR 0.0.0052 + ADR 5.2.0003), ordem do doc §3.8.

        W = 252 sessões é a convenção pré-registrada (decisão humana 2026-07-15,
        ADR 5.2.0003); o parâmetro `historical_quantiles_window` existe **só**
        para testes/sensibilidade (override sancionado pelo próprio ADR).

        Args:
            historical_quantiles_window: W da janela do `historical_quantiles`
                (default canônico 252).

        Returns:
            Tupla com exatamente 5 specs, na ordem canônica de
            `BASELINE_FAMILIES`.
        """
        return (
            BaselineSpec(family="zero_return"),
            BaselineSpec(family="historical_mean"),
            BaselineSpec(family="ar1"),
            BaselineSpec(family="ewma_vol", decay_lambda=_CANONICAL_EWMA_DECAY_LAMBDA),
            BaselineSpec(family="historical_quantiles", window=historical_quantiles_window),
        )
