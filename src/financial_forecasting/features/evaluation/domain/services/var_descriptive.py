"""Serviço de domínio `VarDescriptive` - VaR descritivo por cauda como re-rotulação.

stdlib-only (concept 6.3 §4, I2, I9, C7, C9; doc de domínio §7.5, conv. 24; ADR
`6_3_0001` item 5). Nenhum cálculo novo: para cada τ ≠ 0.5 da grade, na ordem da
grade, o backtest é `ChristoffersenTest.evaluate` da `HitSequence` unilateral do τ
(variante mascarada), e o serviço só re-rotula o nível da grade como nível de VaR:

- τ < 0.5 → cauda inferior (posição comprada), `var_level = 1 - τ`
  (VaR_a(r) = -q_{1-a}(r) no nível a; ex.: VaR_0.98 = -q_0.02);
- τ > 0.5 → cauda superior (posição vendida), `var_level = τ`.

Todo relatório carrega `VAR_DESCRIPTIVE_LABEL`: é descrição da grade nas caudas, sem
claim de gestão de risco (I9). Numa série 100 % degenerada (baselines pontuais) toda
cauda sai "não aplicável" (C7). O "sem lacunas" do perfil sai de `HitSequences` +
`ChristoffersenTest` diretamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenReport,
    ChristoffersenTest,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    belongs_to_dgt_partition,
)

VAR_DESCRIPTIVE_LABEL: Final = "VaR descritivo — sem claim de gestão de risco"
_MEDIAN_LEVEL = 0.5


def var_tail_for(level: float) -> tuple[HitKind, float]:
    """(`kind`, `var_level`) do τ da grade - regra única da re-rotulação (conv. 24).

    Raises:
        ValueError: τ fora de (0, 1) ou τ = 0.5 (a mediana não é cauda).
    """
    validate_rate(level, field="level")
    if level == _MEDIAN_LEVEL:
        raise ValueError("level 0.5 (the median) is not a VaR tail")
    if level < _MEDIAN_LEVEL:
        return HitKind.LOWER_TAIL, 1.0 - level
    return HitKind.UPPER_TAIL, level


@dataclass(frozen=True)
class VarTailBacktest:
    """Backtest de uma cauda da grade, re-rotulado como VaR descritivo.

    Campos:
        kind: `LOWER_TAIL` (τ < 0.5, posição comprada) ou `UPPER_TAIL` (τ > 0.5).
        level: o τ da grade.
        var_level: nível do VaR - `1 - τ` (inferior) ou `τ` (superior).
        backtest: `ChristoffersenReport` dos hits unilaterais do τ (inclui o Kupiec POF).

    Raises:
        ValueError: cauda incoerente (C9), um ramo por invariante.
    """

    kind: HitKind
    level: float
    var_level: float
    backtest: ChristoffersenReport

    def __post_init__(self) -> None:
        """C9: `kind`/`var_level` pela regra do τ; backtest do mesmo τ e da mesma cauda."""
        expected_kind, expected_var_level = var_tail_for(self.level)
        if self.kind is not expected_kind:
            raise ValueError(
                f"kind must be {expected_kind.value} for level={self.level}, got {self.kind!r}"
            )
        if self.var_level != expected_var_level:
            raise ValueError(
                f"var_level must be {expected_var_level!r} for level={self.level}, "
                f"got {self.var_level!r}"
            )
        if self.backtest.includes_degenerate or belongs_to_dgt_partition(self.backtest.dgt_step):
            raise ValueError(
                "a VaR tail backtests the masked variant of the whole series: "
                f"includes_degenerate={self.backtest.includes_degenerate!r}, "
                f"dgt_step={self.backtest.dgt_step!r}"
            )
        if self.backtest.kind is not self.kind or self.backtest.levels != (self.level,):
            raise ValueError(
                f"backtest must be of the same tail ({self.kind.value}, ({self.level},)), got "
                f"({self.backtest.kind.value}, {self.backtest.levels})"
            )


@dataclass(frozen=True)
class VarDescriptiveReport:
    """VaR descritivo de uma série x horizonte: um backtest por τ ≠ 0.5 da grade.

    Campos:
        horizon: o da série (e de todo backtest).
        tails: um `VarTailBacktest` por τ ≠ 0.5, na ordem da grade (nunca vazio).
        label: `VAR_DESCRIPTIVE_LABEL` - sem claim de gestão de risco (I9).

    Raises:
        ValueError: relatório incoerente (C9) ou rótulo divergente (I9).
    """

    horizon: int
    tails: tuple[VarTailBacktest, ...]
    label: str = VAR_DESCRIPTIVE_LABEL

    def __post_init__(self) -> None:
        """I9/C9: rótulo exato, caudas não-vazias, em ordem, do mesmo horizonte."""
        validate_horizon(self.horizon, field="horizon")
        if self.label != VAR_DESCRIPTIVE_LABEL:
            raise ValueError(
                f"a VarDescriptiveReport must carry VAR_DESCRIPTIVE_LABEL, got {self.label!r}"
            )
        if not self.tails:
            raise ValueError("a VarDescriptiveReport needs at least one tail")
        levels = tuple(tail.level for tail in self.tails)
        if any(b <= a for a, b in pairwise(levels)):
            raise ValueError(
                f"tails must follow the grid order (strictly increasing), got {levels}"
            )
        settings = {(tail.backtest.tolerance, tail.backtest.min_violations) for tail in self.tails}
        if len(settings) != 1:
            raise ValueError(
                "every tail must share the same tolerance and min_violations, got "
                f"{sorted(settings)}"
            )
        for tail in self.tails:
            if tail.backtest.horizon != self.horizon:
                raise ValueError(
                    f"every tail backtest must have horizon={self.horizon}, got "
                    f"{tail.backtest.horizon} at level={tail.level}"
                )


class VarDescriptive:
    """Laço por cauda da grade + re-rotulação; nenhum cálculo novo (ADR 6.3.0001 item 5)."""

    @staticmethod
    def backtest(
        series: CoverageSeries, *, tolerance: float, min_violations: int
    ) -> VarDescriptiveReport:
        """Um `VarTailBacktest` por τ ≠ 0.5, na ordem da grade (variante mascarada).

        Raises:
            ValueError: tolerância inválida (C3 do gate) ou `min_violations` inválido (C4).
        """
        tails: list[VarTailBacktest] = []
        for level in series.levels:
            if level == _MEDIAN_LEVEL:
                continue
            kind, var_level = var_tail_for(level)
            build = (
                HitSequences.lower_tail if kind is HitKind.LOWER_TAIL else HitSequences.upper_tail
            )
            sequence = build(series, level=level, tolerance=tolerance)
            tails.append(
                VarTailBacktest(
                    kind=kind,
                    level=level,
                    var_level=var_level,
                    backtest=ChristoffersenTest.evaluate(sequence, min_violations=min_violations),
                )
            )
        return VarDescriptiveReport(horizon=series.horizon, tails=tuple(tails))
