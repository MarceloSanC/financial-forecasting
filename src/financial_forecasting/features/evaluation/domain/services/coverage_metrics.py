"""Serviço de domínio `CoverageMetrics` — cobertura marginal, PICP e MPIW (doc §4.1-§4.3).

stdlib-only. Métricas de **calibração e sharpness**, computadas **só nas linhas
não-degeneradas** (ADR `0_0_0011`; concept 6.1 I8):

- ĉ(τ_k) = média de 1{y ≤ q̂_{τ_k}} — empate conta como coberto (I6);
- PICP do par (τ_l, τ_u) = média de 1{l ≤ y ≤ u} — bordas inclusas (I6);
- MPIW = média de u - l, na unidade de y;
- nominal = 1 - 2·τ_l, derivado da grade da série (I7), nunca constante do código.

A máscara é sempre a da **própria** série: `evaluate` roda o `DegeneracyGate`
internamente e embute o `DegeneracyReport` no resultado (ADR `6_1_0004`) — não existe
caminho para aplicar a máscara de outra série. Com 100 % de degeneração o relatório é
"não aplicável" (`applicable = False`, listas vazias), não erro (C5). Nenhuma linha é
excluída da série; a máscara só escolhe o denominador.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
    DegeneracyReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

_MEDIAN_LEVEL = 0.5
_MIN_LEVELS = 2


@dataclass(frozen=True)
class PairCoverage:
    """PICP e MPIW de um par simétrico, sobre as linhas não-degeneradas.

    Campos:
        lower_level / upper_level: o par (τ_l, τ_u) da grade.
        nominal: 1 - 2·τ_l (dinâmico, da grade).
        picp: fração de linhas com l ≤ y ≤ u.
        mpiw: média de u - l, na unidade de y.
    """

    lower_level: float
    upper_level: float
    nominal: float
    picp: float
    mpiw: float

    def __post_init__(self) -> None:
        """I7: o nominal sai da fórmula única 1 - 2·τ_l."""
        if self.nominal != 1.0 - 2.0 * self.lower_level:
            raise ValueError(
                f"nominal must be 1 - 2 * lower_level = {1.0 - 2.0 * self.lower_level}, "
                f"got {self.nominal}"
            )


@dataclass(frozen=True)
class CoverageReport:
    """Cobertura de uma série x horizonte, com o gate que escolheu as linhas.

    Campos:
        horizon / n_points: os da série (T = todas as linhas).
        n_evaluated: linhas não-degeneradas (o denominador).
        applicable: `False` ⇔ `n_evaluated == 0` ("não aplicável").
        degeneracy: o `DegeneracyReport` da mesma série e tolerância.
        per_level: `(τ_k, ĉ(τ_k))` na ordem da grade; vazio se não aplicável.
        per_pair: um `PairCoverage` por par simétrico; vazio se não aplicável.
    """

    horizon: int
    n_points: int
    n_evaluated: int
    applicable: bool
    degeneracy: DegeneracyReport
    per_level: tuple[tuple[float, float], ...]
    per_pair: tuple[PairCoverage, ...]

    def __post_init__(self) -> None:
        """C4: relatório incoerente com o próprio gate ergue `ValueError`."""
        self._check_degeneracy_link()
        self._check_applicability()
        if self.applicable:
            self._check_grid_shape()

    def _check_degeneracy_link(self) -> None:
        if self.degeneracy.n_points != self.n_points:
            raise ValueError(
                f"degeneracy.n_points={self.degeneracy.n_points} differs from "
                f"n_points={self.n_points}"
            )
        if self.degeneracy.horizon != self.horizon:
            raise ValueError(
                f"degeneracy.horizon={self.degeneracy.horizon} differs from horizon={self.horizon}"
            )
        expected = self.n_points - self.degeneracy.n_degenerate
        if self.n_evaluated != expected:
            raise ValueError(
                f"n_evaluated={self.n_evaluated} differs from n_points - n_degenerate = {expected}"
            )

    def _check_applicability(self) -> None:
        if self.applicable and self.n_evaluated == 0:
            raise ValueError("applicable=True requires n_evaluated > 0")
        if not self.applicable and self.n_evaluated > 0:
            raise ValueError(f"applicable=False requires n_evaluated == 0, got {self.n_evaluated}")
        if not self.applicable and self.per_level:
            raise ValueError("a non-applicable CoverageReport must have per_level == ()")
        if not self.applicable and self.per_pair:
            raise ValueError("a non-applicable CoverageReport must have per_pair == ()")

    def _check_grid_shape(self) -> None:
        # O relatório não carrega a grade: K é lido de `per_level`, e os pares esperados
        # (τ_k, τ_{K-1-k}) com τ_k < 0.5 são derivados dele — tamanho e identidade.
        levels = tuple(level for level, _ in self.per_level)
        if len(levels) < _MIN_LEVELS:
            raise ValueError(
                f"per_level must hold the K >= {_MIN_LEVELS} grid levels, got {len(levels)}"
            )
        size = len(levels)
        expected_pairs = tuple(
            (levels[k], levels[size - 1 - k]) for k in range(size) if levels[k] < _MEDIAN_LEVEL
        )
        pairs = tuple((pair.lower_level, pair.upper_level) for pair in self.per_pair)
        if pairs != expected_pairs:
            raise ValueError(
                f"per_pair must hold one entry per symmetric pair {expected_pairs}, got {pairs}"
            )


class CoverageMetrics:
    """Cobertura marginal, PICP e MPIW sobre uma `CoverageSeries` (lê o pós-guardrail)."""

    @staticmethod
    def evaluate(series: CoverageSeries, *, tolerance: float) -> CoverageReport:
        """ĉ por nível e PICP/MPIW por par, só nas linhas não-degeneradas da série.

        Roda `DegeneracyGate.evaluate(series, tolerance=tolerance)` internamente (ADR
        6.1.0004); tolerância inválida ergue `ValueError` (C3).
        """
        degeneracy = DegeneracyGate.evaluate(series, tolerance=tolerance)
        kept = _kept_rows(degeneracy)
        n_evaluated = len(kept)
        if n_evaluated == 0:
            return CoverageReport(
                horizon=series.horizon,
                n_points=series.n_points,
                n_evaluated=0,
                applicable=False,
                degeneracy=degeneracy,
                per_level=(),
                per_pair=(),
            )
        per_level = tuple(
            (
                level,
                sum(1 for i in kept if series.realized[i] <= series.scored_values(i)[k])
                / n_evaluated,
            )
            for k, level in enumerate(series.levels)
        )
        per_pair = tuple(
            _pair_coverage(series, kept, pair, indices)
            for pair, indices in zip(
                series.symmetric_pairs, series.symmetric_pair_indices, strict=True
            )
        )
        return CoverageReport(
            horizon=series.horizon,
            n_points=series.n_points,
            n_evaluated=n_evaluated,
            applicable=True,
            degeneracy=degeneracy,
            per_level=per_level,
            per_pair=per_pair,
        )

    @staticmethod
    def interval_widths(
        series: CoverageSeries, *, tolerance: float, pair: tuple[float, float]
    ) -> tuple[float, ...]:
        """Larguras u - l do `pair` em cada linha não-degenerada, na ordem da série.

        Insumo do sharpness diagram. `pair` casa com um elemento de
        `series.symmetric_pairs` por igualdade exata de float.

        Raises:
            ValueError: `pair` fora de `series.symmetric_pairs` (C8) ou tolerância
                inválida (C3).
        """
        if pair not in series.symmetric_pairs:
            raise ValueError(
                f"pair {pair} is not one of the series symmetric pairs {series.symmetric_pairs}"
            )
        k_low, k_high = series.symmetric_pair_indices[series.symmetric_pairs.index(pair)]
        kept = _kept_rows(DegeneracyGate.evaluate(series, tolerance=tolerance))
        return tuple(series.scored_values(i)[k_high] - series.scored_values(i)[k_low] for i in kept)


def _kept_rows(degeneracy: DegeneracyReport) -> list[int]:
    return [i for i, is_degenerate in enumerate(degeneracy.degenerate) if not is_degenerate]


def _pair_coverage(
    series: CoverageSeries,
    kept: list[int],
    pair: tuple[float, float],
    indices: tuple[int, int],
) -> PairCoverage:
    lower_level, upper_level = pair
    k_low, k_high = indices
    covered = 0
    widths: list[float] = []
    for i in kept:
        values = series.scored_values(i)
        low, high = values[k_low], values[k_high]
        if low <= series.realized[i] <= high:
            covered += 1
        widths.append(high - low)
    return PairCoverage(
        lower_level=lower_level,
        upper_level=upper_level,
        nominal=1.0 - 2.0 * lower_level,
        picp=covered / len(kept),
        mpiw=math.fsum(widths) / len(kept),
    )
