"""Use case `ReadTrainingGrid` — a grade de treino de um ativo para quem só a lê.

Real do port `TrainingGridReader` do `evaluation` (ADR 6.4.0009), por duck typing; a
leitura e o corte são os da 5.5 (ADR 5.5.0004): delega a `load_training_grid`, com as
colunas de modelagem injetadas no wiring (`modeling_columns()`). **Nenhuma regra
nova** — o dono da grade continua sendo a `modeling`.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    load_training_grid,
)
from financial_forecasting.features.modeling.domain.services.training_grid import TrainingGrid
from financial_forecasting.shared.application.ports.out.medallion_store import MedallionStore


class ReadTrainingGrid:
    """Lê a grade de treino aparada de um ativo (a mesma leitura do treino)."""

    def __init__(self, *, store: MedallionStore, columns: Sequence[str]) -> None:
        self._store = store
        self._columns = tuple(columns)

    def __call__(self, *, asset_id: str) -> TrainingGrid:
        """A grade do ativo; os erros do dono (`load_training_grid`) propagam."""
        return load_training_grid(store=self._store, asset_id=asset_id, columns=self._columns)
