"""Serviço de domínio `HolmCorrection` — Holm (1979) sobre a família de DMs de um horizonte.

Implementação **de registro**, stdlib-only (concept 6.2 §4, I1/I6/I7, C2/C4/C8; ADR
`6_2_0003` item 2; doc §6.4):

- `holm_adjust`: p-valores ajustados de Holm (Scheme 1) — com os p ordenados de forma
  estável, p̃_(j) = max_{i ≤ j} min(1, (m - i + 1)·p_(i)); devolvidos **na ordem de
  entrada**. Empates dão o mesmo resultado em qualquer ordem (o fator maior do primeiro
  do empate é absorvido pelo máximo acumulado);
- `holm_reject`: a rejeição **de registro** é p̃ ≤ alpha (equivale ao step-down com "≤" em
  aritmética exata; na fronteira p̃ = alpha rejeita);
- `HolmCorrection.family`: a família **fechada por construção** (B-FAMILIA; antigo "gate
  C") — um DM do candidato contra **cada** outro modelo da mesma `PairedLossSeries`
  (m = k - 1, mesma amostra pareada, sem filtro por H1 dos comparadores) e Holm sobre os
  m p-valores. **Sem seleção entre candidatos** (antigo "gate B"): a API recebe um único
  `candidate: str`.

Entrada validada pelo validador único `inference_input_validation` (C4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DieboldMarianoResult,
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
    validate_p_values,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)


def holm_adjust(p_values: Sequence[float]) -> tuple[float, ...]:
    """p-valores ajustados de Holm, na ordem de entrada; entrada inválida ergue (C4)."""
    validate_p_values(p_values)
    size = len(p_values)
    order = sorted(range(size), key=lambda index: p_values[index])
    adjusted = [0.0] * size
    running_max = 0.0
    for rank, index in enumerate(order):
        running_max = max(running_max, min(1.0, (size - rank) * p_values[index]))
        adjusted[index] = running_max
    return tuple(adjusted)


def holm_reject(p_values: Sequence[float], *, alpha: float) -> tuple[bool, ...]:
    """Rejeição de registro: p̃ ≤ alpha, na ordem de entrada; entrada inválida ergue (C4)."""
    validate_alpha(alpha)
    return tuple(adjusted <= alpha for adjusted in holm_adjust(p_values))


@dataclass(frozen=True)
class HolmComparison:
    """Um DM da família com o seu p-valor ajustado por Holm e a decisão ao nível alpha."""

    comparator: str
    dm: DieboldMarianoResult
    adjusted_p_value: float
    rejected: bool


@dataclass(frozen=True)
class DmHolmFamilyReport:
    """Família DM + Holm de um candidato num horizonte.

    Campos:
        horizon: horizonte da série.
        n_points: T da série.
        candidate: o único candidato da família.
        alpha: nível em (0, 1).
        variance_estimator: estimador de todos os DMs da família.
        comparisons: um `HolmComparison` por comparador, na ordem de `series.models`.

    Raises:
        ValueError: relatório incoerente (I7; C8), na construção.
    """

    horizon: int
    n_points: int
    candidate: str
    alpha: float
    variance_estimator: DmVarianceEstimator
    comparisons: tuple[HolmComparison, ...]

    def __post_init__(self) -> None:
        """I7/C8: família fechada, amostra única, Holm e decisão coerentes."""
        validate_alpha(self.alpha)
        if not isinstance(self.comparisons, tuple):
            raise ValueError(f"comparisons must be a tuple, got {type(self.comparisons).__name__}")
        if not self.comparisons:
            raise ValueError("a DmHolmFamilyReport needs m >= 1 comparisons")
        comparators = [comparison.comparator for comparison in self.comparisons]
        if len(set(comparators)) != len(comparators):
            raise ValueError(f"comparators must be unique, got {comparators}")
        if self.candidate in comparators:
            raise ValueError(f"candidate {self.candidate!r} cannot be one of its comparators")
        for comparison in self.comparisons:
            self._check_same_sample(comparison)
        p_values = [comparison.dm.p_value for comparison in self.comparisons]
        adjusted = holm_adjust(p_values)
        rejected = holm_reject(p_values, alpha=self.alpha)
        for comparison, expected, decision in zip(
            self.comparisons, adjusted, rejected, strict=True
        ):
            if comparison.adjusted_p_value != expected:
                raise ValueError(
                    f"comparator {comparison.comparator!r}: adjusted_p_value "
                    f"{comparison.adjusted_p_value} differs from holm_adjust ({expected})"
                )
            if not isinstance(comparison.rejected, bool):
                raise ValueError(
                    f"comparator {comparison.comparator!r}: rejected must be a bool, got "
                    f"{comparison.rejected!r}"
                )
            if comparison.rejected != decision:
                raise ValueError(
                    f"comparator {comparison.comparator!r}: rejected={comparison.rejected} is "
                    f"incoherent with adjusted {expected} and alpha {self.alpha}"
                )

    def _check_same_sample(self, comparison: HolmComparison) -> None:
        dm = comparison.dm
        if dm.horizon != self.horizon or dm.n_points != self.n_points:
            raise ValueError(
                f"comparator {comparison.comparator!r}: DM on horizon {dm.horizon} with "
                f"n_points {dm.n_points}, report has horizon {self.horizon} and n_points "
                f"{self.n_points}"
            )
        if dm.variance_estimator != self.variance_estimator:
            raise ValueError(
                f"comparator {comparison.comparator!r}: variance estimator "
                f"{dm.variance_estimator} differs from the report's {self.variance_estimator}"
            )


class HolmCorrection:
    """Família DM + Holm do candidato contra todos os outros modelos de um horizonte."""

    @staticmethod
    def family(
        series: PairedLossSeries,
        *,
        candidate: str,
        alpha: float,
        variance_estimator: DmVarianceEstimator = DmVarianceEstimator.RECTANGULAR,
    ) -> DmHolmFamilyReport:
        """Um DM por comparador (m = k - 1, ordem de `series.models`) e Holm sobre os m.

        Raises:
            ValueError: candidato fora de `series.models` (C2); alpha fora de (0, 1) (C4); e os
                erros do DM (C3).
        """
        if candidate not in series.models:
            raise ValueError(f"unknown candidate {candidate!r}; known models: {series.models}")
        validate_alpha(alpha)
        comparators = [model for model in series.models if model != candidate]
        results = [
            DieboldMariano.compare(
                series,
                candidate=candidate,
                comparator=comparator,
                variance_estimator=variance_estimator,
            )
            for comparator in comparators
        ]
        p_values = [result.p_value for result in results]
        adjusted = holm_adjust(p_values)
        # a decisão sai da regra única `holm_reject` (p̃ <= alpha), sem segunda escrita
        rejected = holm_reject(p_values, alpha=alpha)
        return DmHolmFamilyReport(
            horizon=series.horizon,
            n_points=series.n_points,
            candidate=candidate,
            alpha=alpha,
            variance_estimator=variance_estimator,
            comparisons=tuple(
                HolmComparison(
                    comparator=comparator,
                    dm=result,
                    adjusted_p_value=value,
                    rejected=decision,
                )
                for comparator, result, value, decision in zip(
                    comparators, results, adjusted, rejected, strict=True
                )
            ),
        )
