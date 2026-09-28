"""Fixture-fábrica local do slice `evaluation` (unit): monta `CoverageSeries` sintéticas.

Local do slice, não compartilhada (precedente `tests/integration/features/modeling/
conftest.py`); usada pelos testes das Tasks 02-07 da Stage 6.1. Uma única fábrica
evita N cópias da montagem da série — em especial dos timestamps ISO crescentes e da
escolha entre `QuantileForecast.from_raw` (o caminho de produção, que aplica o
guardrail) e a construção direta do VO (que não valida nada: é como se produz uma
grade cruzada em `guardrail_values` para o caso C1, ou um par raw ≠ guardrail sob
medida para o A1b).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
    violation_rate_for,
)

# Grade simétrica sintética de 7 níveis (3 pares + a mediana), só para teste. NÃO é a do
# candidato: essa é {0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98} (doc de domínio de modeling).
SEVEN_LEVELS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)

SeriesFactory = Callable[..., CoverageSeries]


def iso_timestamps(n_points: int) -> tuple[str, ...]:
    """`n_points` timestamps ISO UTC estritamente crescentes (um por dia)."""
    return tuple((_EPOCH + timedelta(days=offset)).isoformat() for offset in range(n_points))


def build_series(  # noqa: PLR0913 — um parâmetro por eixo da série sintética (keyword-only)
    grids: Sequence[Sequence[float]],
    realized: Sequence[float],
    *,
    levels: Sequence[float] = SEVEN_LEVELS,
    horizon: int = 1,
    direct: bool = False,
    guardrail_grids: Sequence[Sequence[float]] | None = None,
    timestamps: Sequence[str] | None = None,
) -> CoverageSeries:
    """Monta uma `CoverageSeries` a partir de listas de grades (uma por ponto).

    Args:
        grids: valores brutos por ponto, alinhados a `levels`.
        realized: retorno realizado por ponto.
        levels: grade comum (padrão: 7 níveis simétricos).
        horizon: rótulo do horizonte.
        direct: `True` constrói o `QuantileForecast` direto, com
            `guardrail_values = raw_values` e `guardrail_applied = False` (sem validar
            nem ordenar); `False` usa `QuantileForecast.from_raw`.
        guardrail_grids: com `direct=True`, `guardrail_values` explícitos por ponto
            (raw ≠ guardrail sob medida); `guardrail_applied` vira `raw != guardrail`.
        timestamps: timestamps por ponto; padrão: `iso_timestamps(len(realized))`.
    """
    level_tuple = tuple(levels)
    forecasts: list[QuantileForecast] = []
    for index, grid in enumerate(grids):
        raw = tuple(grid)
        if not direct:
            forecasts.append(QuantileForecast.from_raw(levels=level_tuple, raw_values=raw))
            continue
        scored = raw if guardrail_grids is None else tuple(guardrail_grids[index])
        forecasts.append(
            QuantileForecast(
                levels=level_tuple,
                raw_values=raw,
                guardrail_values=scored,
                guardrail_applied=scored != raw,
            )
        )
    return CoverageSeries(
        horizon=horizon,
        levels=level_tuple,
        target_timestamps=(
            iso_timestamps(len(realized)) if timestamps is None else tuple(timestamps)
        ),
        forecasts=tuple(forecasts),
        realized=tuple(realized),
    )


@pytest.fixture
def make_series() -> SeriesFactory:
    """A fábrica `build_series` como fixture (injeção pelo pytest nos testes)."""
    return build_series


HitSequenceFactory = Callable[..., HitSequence]


def build_hit_sequence(  # noqa: PLR0913 — um parâmetro por campo usual do VO (keyword-only)
    violations: Sequence[bool | None],
    *,
    kind: HitKind = HitKind.LOWER_TAIL,
    levels: Sequence[float] = (0.05,),
    horizon: int = 1,
    tolerance: float = 0.0,
    includes_degenerate: bool = False,
    **overrides: object,
) -> HitSequence:
    """Monta uma `HitSequence` (Stage 6.3, Tasks 05/07/08) a partir das violações.

    Deriva `violation_rate` pela regra do `kind` (`violation_rate_for`, a mesma do VO),
    `degeneracy_rate = n_None / T` (a forma do `DegeneracyReport`) e os timestamps via
    `iso_timestamps`. `overrides` troca qualquer campo do VO (ex.: `violation_rate`,
    `degeneracy_rate`, `target_timestamps`, `dgt_offset`, `dgt_step`) para os casos de
    C1.
    """
    values = tuple(violations)
    level_tuple = tuple(levels)
    n_gaps = sum(1 for value in values if value is None)
    fields: dict[str, object] = {
        "horizon": horizon,
        "kind": kind,
        "levels": level_tuple,
        "violation_rate": violation_rate_for(kind, level_tuple) if level_tuple else 0.0,
        "target_timestamps": iso_timestamps(len(values)),
        "violations": values,
        "tolerance": tolerance,
        "degeneracy_rate": n_gaps / len(values) if values else 0.0,
        "includes_degenerate": includes_degenerate,
    }
    fields.update(overrides)
    return HitSequence(**fields)  # type: ignore[arg-type]


@pytest.fixture
def make_hit_sequence() -> HitSequenceFactory:
    """A fábrica `build_hit_sequence` como fixture (Tasks 05, 07 e 08 da 6.3)."""
    return build_hit_sequence
