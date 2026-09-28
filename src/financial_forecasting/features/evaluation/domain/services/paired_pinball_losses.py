"""Fábrica `paired_pinball_losses` — L_t pareadas de k modelos, com média entre seeds.

Serviço de domínio stdlib-only (concept 6.2 §4, I1/I3, C1; ADR `6_2_0001` item 5). É o
**único** caminho que garante que as colunas de uma `PairedLossSeries` são L_t (doc
§2.4, §6.4, §6.7, §6.9 — antigo "gate A"):

- L_t de cada série = `PinballScore.per_point_losses` (média dos K rho_τ do ponto,
  sobre o vetor pós-guardrail — 6.1);
- por modelo, a coluna é a **média ponto a ponto** das S ≥ 1 séries (seeds) —
  `math.fsum` das S perdas do ponto / S; S = 1 é a identidade (regra B-SEEDS: média de
  perdas, não de previsões);
- todas as séries, entre seeds **e** entre modelos, têm o mesmo `horizon`, os mesmos
  `target_timestamps`, a mesma grade `levels` e os mesmos realizados `realized` da
  primeira — senão `ValueError` nomeando o modelo e o **índice** da seed na sequência (a
  `CoverageSeries` não carrega id de seed; a fábrica valida, nunca alinha). O pareamento
  exige o mesmo y_t em todas as colunas: com alvos diferentes o diferencial d_t mediria o
  alvo, não o modelo (regra aditiva de C1, technical 6.2 §7);
- a ordem dos modelos é a do mapping.

Não importa nada de `modeling` e não altera a `CoverageSeries` (6.1).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_MIN_MODELS = 2


def paired_pinball_losses(
    series_by_model: Mapping[str, Sequence[CoverageSeries]],
) -> PairedLossSeries:
    """Monta a `PairedLossSeries` de L_t a partir das séries de cada modelo.

    Args:
        series_by_model: modelo → S ≥ 1 `CoverageSeries` (uma por seed), todas do mesmo
            horizonte, timestamps, grade e realizados. A ordem das chaves é a ordem dos
            modelos.

    Returns:
        A série pareada do horizonte, uma coluna L_t (média entre seeds) por modelo.

    Raises:
        ValueError: < 2 modelos; modelo sem séries; séries com horizonte, timestamps ou
            grade ou realizados diferentes (entre seeds ou entre modelos); e as violações do
            VO (C1).
    """
    if len(series_by_model) < _MIN_MODELS:
        raise ValueError(
            f"paired losses need k >= {_MIN_MODELS} models, got {list(series_by_model)}"
        )
    for model, seeds in series_by_model.items():
        if not seeds:
            raise ValueError(f"model {model!r} has no series (needs S >= 1 seeds)")
    reference = next(iter(series_by_model.values()))[0]
    for model, seeds in series_by_model.items():
        for seed_index, series in enumerate(seeds):
            _check_same_axes(reference, series, model=model, seed_index=seed_index)
    return PairedLossSeries(
        horizon=reference.horizon,
        models=tuple(series_by_model),
        target_timestamps=reference.target_timestamps,
        losses=tuple(_seed_mean(seeds) for seeds in series_by_model.values()),
    )


def _check_same_axes(
    reference: CoverageSeries, series: CoverageSeries, *, model: str, seed_index: int
) -> None:
    """Horizonte, timestamps, grade e realizados iguais aos da referência (a primeira)."""
    where = f"model {model!r}, seed index {seed_index}"
    if series.horizon != reference.horizon:
        raise ValueError(f"{where}: horizon {series.horizon} differs from {reference.horizon}")
    if series.target_timestamps != reference.target_timestamps:
        raise ValueError(f"{where}: target_timestamps differ from the first series")
    if series.levels != reference.levels:
        raise ValueError(f"{where}: levels {series.levels} differ from {reference.levels}")
    if series.realized != reference.realized:
        raise ValueError(f"{where}: realized values differ from the first series")


def _seed_mean(seeds: Sequence[CoverageSeries]) -> tuple[float, ...]:
    """Média ponto a ponto das L_t das S seeds (`math.fsum` / S)."""
    per_seed = [PinballScore.per_point_losses(series) for series in seeds]
    count = len(per_seed)
    return tuple(math.fsum(point) / count for point in zip(*per_seed, strict=True))
