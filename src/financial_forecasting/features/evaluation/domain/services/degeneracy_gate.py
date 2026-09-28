"""Serviço de domínio `DegeneracyGate` — gate de degeneração por linha (doc §5.3).

Pré-registrado no ADR `0_0_0011` (item sobre degeneração); a forma da tolerância é o
ADR `6_1_0003`. stdlib-only. Regras (concept 6.1 I8/I9, C3/C6):

- linha **degenerada** ⇔ `max - min` do vetor pós-guardrail ≤ `tolerance` (colapso
  total — equivale a `q_{τ_1} == q_{τ_K}` sob tolerância, o "q_low == q_high" do
  roadmap no par extremo);
- `tolerance` é absoluta (unidade de y), finita, ≥ 0 e **obrigatória, sem default**:
  o valor numérico é escolha pré-registrada do chamador (6.4/6.5), não do domínio;
- a taxa é **sempre** reportada; o colapso parcial por par é diagnóstico e não
  invalida a linha — `pair_collapse_rates` conta só entre as linhas NÃO-degeneradas
  (`None` quando não há nenhuma, C6); o limiar que reprova H1 é da 6.5;
- o gate nunca reordena, altera nem exclui linha: a máscara só escolhe o denominador
  das métricas de calibração (`CoverageMetrics`, ADR `6_1_0004`). A amplitude
  `max - min` é invariante à ordem, então o veredito por linha é o mesmo no bruto e
  no rearranjado (I9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

_MIN_LEVELS = 2


@dataclass(frozen=True)
class DegeneracyReport:
    """Veredito do gate sobre uma série x horizonte, com rastro de auditoria.

    Campos:
        horizon: horizonte da série de origem.
        n_points: T.
        target_timestamps: os da série de origem (auditoria da máscara).
        tolerance: a tolerância absoluta usada.
        levels: a grade de níveis da série de origem (auditoria; K >= 2, coerente com
            os pares de `pair_collapse_rates`).
        degenerate: máscara por linha, alinhada à série.
        n_degenerate: soma da máscara.
        rate: `n_degenerate / n_points` — sempre reportada.
        pair_collapse_rates: `(τ_l, τ_u, taxa)` por par simétrico; taxa de colapso
            parcial (`q_u - q_l ≤ tolerance`) entre as linhas NÃO-degeneradas, ou
            `None` se não houver nenhuma.
    """

    horizon: int
    n_points: int
    target_timestamps: tuple[str, ...]
    tolerance: float
    levels: tuple[float, ...]
    degenerate: tuple[bool, ...]
    n_degenerate: int
    rate: float
    pair_collapse_rates: tuple[tuple[float, float, float | None], ...]

    def __post_init__(self) -> None:
        """C4: relatório mal-formado (máscara de outra série, contagens incoerentes)."""
        # Pré-condição de `rate`: sem ela, a checagem abaixo dividiria por zero.
        if self.n_points < 1:
            raise ValueError(f"a DegeneracyReport needs n_points >= 1, got {self.n_points}")
        if len(self.degenerate) != self.n_points:
            raise ValueError(
                f"degenerate mask has {len(self.degenerate)} rows for n_points={self.n_points}"
            )
        if len(self.target_timestamps) != self.n_points:
            raise ValueError(
                f"target_timestamps has {len(self.target_timestamps)} rows for "
                f"n_points={self.n_points}"
            )
        if self.n_degenerate != sum(self.degenerate):
            raise ValueError(
                f"n_degenerate={self.n_degenerate} differs from the mask sum {sum(self.degenerate)}"
            )
        if self.rate != self.n_degenerate / self.n_points:
            raise ValueError(
                f"rate={self.rate} differs from n_degenerate / n_points = "
                f"{self.n_degenerate / self.n_points}"
            )
        self._check_levels_match_pairs()

    def _check_levels_match_pairs(self) -> None:
        # A grade e os pares vêm da mesma série: com p pares, K ∈ {2p, 2p+1} (o nível
        # central só existe com K ímpar) e os níveis, fora o central, são os τ dos pares
        # em ordem — do extremo para dentro à esquerda, de dentro para fora à direita.
        n_pairs = len(self.pair_collapse_rates)
        size = len(self.levels)
        if size < _MIN_LEVELS or size not in (2 * n_pairs, 2 * n_pairs + 1):
            raise ValueError(
                f"levels must hold K >= {_MIN_LEVELS} levels, K in "
                f"{{{2 * n_pairs}, {2 * n_pairs + 1}}} for {n_pairs} pairs, got {self.levels}"
            )
        outer = self.levels[:n_pairs] + self.levels[size - n_pairs :]
        expected = tuple(low for low, _, _ in self.pair_collapse_rates) + tuple(
            high for _, high, _ in reversed(self.pair_collapse_rates)
        )
        if outer != expected:
            raise ValueError(f"levels {self.levels} do not match the pairs of pair_collapse_rates")


class DegeneracyGate:
    """Gate de degeneração por linha sobre uma `CoverageSeries` (lê o pós-guardrail)."""

    @staticmethod
    def evaluate(series: CoverageSeries, *, tolerance: float) -> DegeneracyReport:
        """Marca as linhas colapsadas e mede o colapso parcial por par.

        Raises:
            ValueError: `tolerance` negativa ou não-finita (C3).
        """
        _validate_tolerance(tolerance)
        degenerate = tuple(
            max(values) - min(values) <= tolerance
            for values in (series.scored_values(i) for i in range(series.n_points))
        )
        n_degenerate = sum(degenerate)
        return DegeneracyReport(
            horizon=series.horizon,
            n_points=series.n_points,
            target_timestamps=series.target_timestamps,
            tolerance=tolerance,
            levels=series.levels,
            degenerate=degenerate,
            n_degenerate=n_degenerate,
            rate=n_degenerate / series.n_points,
            pair_collapse_rates=_pair_collapse_rates(series, degenerate, tolerance),
        )


def _validate_tolerance(tolerance: float) -> None:
    # Cópia privada intencional do predicado de número finito do `QuantileForecast` (4.3):
    # o helper de lá é privado e importá-lo abriria aresta nova no bc-independence.
    if isinstance(tolerance, bool) or not isinstance(tolerance, int | float):
        raise ValueError(f"tolerance must be a finite number >= 0, got {tolerance!r}")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError(f"tolerance must be a finite number >= 0, got {tolerance}")


def _pair_collapse_rates(
    series: CoverageSeries, degenerate: tuple[bool, ...], tolerance: float
) -> tuple[tuple[float, float, float | None], ...]:
    kept = [i for i, is_degenerate in enumerate(degenerate) if not is_degenerate]
    rates: list[tuple[float, float, float | None]] = []
    pairs = zip(series.symmetric_pairs, series.symmetric_pair_indices, strict=True)
    for (lower_level, upper_level), (k_low, k_high) in pairs:
        if not kept:
            rates.append((lower_level, upper_level, None))
            continue
        collapsed = sum(
            1
            for i in kept
            if series.scored_values(i)[k_high] - series.scored_values(i)[k_low] <= tolerance
        )
        rates.append((lower_level, upper_level, collapsed / len(kept)))
    return tuple(rates)
