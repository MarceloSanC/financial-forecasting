"""Serviço de domínio `HitSequences` — constrói a `HitSequence` de uma `CoverageSeries`.

stdlib-only (concept 6.3 §4, I2, I3, I4, C2, C7; ADR `6_3_0001` item 2; ADR
`6_3_0004` item 4; ADR `6_1_0004`). Três construtores, um por `HitKind`:

- `interval(series, pair=(τ_l, τ_u))`: violação = `not is_inside_closed(y, l, u)`;
- `lower_tail(series, level=τ)`: violação = `is_at_or_below(y, q̂_τ)`;
- `upper_tail(series, level=τ)`: violação = `not is_at_or_below(y, q̂_τ)`.

A regra de indicador (FA7, empates) tem dono único — os predicados de
`coverage_series.py`, os mesmos do `CoverageMetrics` (I3); lê-se o vetor
pós-guardrail (`series.scored_values`). A taxa nominal sai da grade pela regra do
`kind` (`violation_rate_for`, I2).

**Máscara da própria série (I4, padrão ADR 6.1.0004):** cada construtor roda
`DegeneracyGate.evaluate(series, tolerance=tolerance)` sobre a **mesma** série — não
existe caminho para passar a máscara de outra — e a linha degenerada vira `None`
(lacuna, nunca removida). A variante "sem lacunas" (`include_degenerate=True`) não
mascara, salvo série 100 % degenerada, que sai toda `None` (os baselines pontuais
não entram nos backtests — doc §5.3 item 2, §7.2). `tolerance` é keyword-only e sem
default (ADR 6.1.0003); a tolerância e a taxa do gate ficam gravadas na sequência.
"""

from __future__ import annotations

from collections.abc import Callable

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
    is_at_or_below,
    is_inside_closed,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
    violation_rate_for,
)

# Indicador de violação de uma linha: (realizado, vetor pós-guardrail) → violou?
_Indicator = Callable[[float, tuple[float, ...]], bool]


class HitSequences:
    """Construtores de `HitSequence` sobre uma `CoverageSeries` (lê o pós-guardrail)."""

    @staticmethod
    def interval(
        series: CoverageSeries,
        *,
        pair: tuple[float, float],
        tolerance: float,
        include_degenerate: bool = False,
    ) -> HitSequence:
        """Violações do intervalo fechado do `pair` (FA7: bordas contam como dentro).

        Raises:
            ValueError: `pair` fora de `series.symmetric_pairs` (igualdade exata, C2)
                ou tolerância inválida (C3 do gate).
        """
        if pair not in series.symmetric_pairs:
            raise ValueError(
                f"pair {pair} is not one of the series symmetric pairs {series.symmetric_pairs}"
            )
        k_low, k_high = series.symmetric_pair_indices[series.symmetric_pairs.index(pair)]

        def violated(realized: float, values: tuple[float, ...]) -> bool:
            return not is_inside_closed(realized, values[k_low], values[k_high])

        return _build(
            series,
            kind=HitKind.INTERVAL,
            levels=pair,
            indicator=violated,
            tolerance=tolerance,
            include_degenerate=include_degenerate,
        )

    @staticmethod
    def lower_tail(
        series: CoverageSeries,
        *,
        level: float,
        tolerance: float,
        include_degenerate: bool = False,
    ) -> HitSequence:
        """Violações da cauda inferior em τ: `y ≤ q̂_τ` (FA7: o empate é violação).

        Raises:
            ValueError: `level` fora de `series.levels` (igualdade exata, C2) ou
                tolerância inválida (C3 do gate).
        """
        k = _level_index(series, level)

        def violated(realized: float, values: tuple[float, ...]) -> bool:
            return is_at_or_below(realized, values[k])

        return _build(
            series,
            kind=HitKind.LOWER_TAIL,
            levels=(level,),
            indicator=violated,
            tolerance=tolerance,
            include_degenerate=include_degenerate,
        )

    @staticmethod
    def upper_tail(
        series: CoverageSeries,
        *,
        level: float,
        tolerance: float,
        include_degenerate: bool = False,
    ) -> HitSequence:
        """Violações da cauda superior em τ: `y > q̂_τ` (FA7: o empate não é violação).

        Raises:
            ValueError: `level` fora de `series.levels` (igualdade exata, C2) ou
                tolerância inválida (C3 do gate).
        """
        k = _level_index(series, level)

        def violated(realized: float, values: tuple[float, ...]) -> bool:
            return not is_at_or_below(realized, values[k])

        return _build(
            series,
            kind=HitKind.UPPER_TAIL,
            levels=(level,),
            indicator=violated,
            tolerance=tolerance,
            include_degenerate=include_degenerate,
        )


def _level_index(series: CoverageSeries, level: float) -> int:
    if level not in series.levels:
        raise ValueError(f"level {level} is not one of the series levels {series.levels}")
    return series.levels.index(level)


def _build(  # noqa: PLR0913 — série + os cinco eixos da sequência (keyword-only)
    series: CoverageSeries,
    *,
    kind: HitKind,
    levels: tuple[float, ...],
    indicator: _Indicator,
    tolerance: float,
    include_degenerate: bool,
) -> HitSequence:
    """Aplica a máscara do gate da própria série e o indicador linha a linha."""
    report = DegeneracyGate.evaluate(series, tolerance=tolerance)
    fully_degenerate = report.n_degenerate == series.n_points
    # Variante "sem lacunas": nenhuma máscara, salvo série 100 % degenerada (toda None).
    mask = report.degenerate if not include_degenerate or fully_degenerate else None
    violations = tuple(
        None
        if mask is not None and mask[i]
        else indicator(series.realized[i], series.scored_values(i))
        for i in range(series.n_points)
    )
    return HitSequence(
        horizon=series.horizon,
        kind=kind,
        levels=levels,
        violation_rate=violation_rate_for(kind, levels),
        target_timestamps=series.target_timestamps,
        violations=violations,
        tolerance=tolerance,
        degeneracy_rate=report.rate,
        includes_degenerate=include_degenerate,
    )
