"""Use case `ReadTrainingGrid` — a grade de treino de um ativo para quem só a lê.

Real do port `TrainingGridReader` do `evaluation` (ADR 6.4.0009), por duck typing; a
leitura e o corte são os da 5.5 (ADR 5.5.0004): delega a `load_training_grid`, com as
colunas de modelagem injetadas no wiring (`modeling_columns()`). Devolve também o
fingerprint da grade, calculado por `grid_fingerprint` — a mesma função dos sweeps e
do cohort, dona única das entradas do fingerprint (issue #128). **Nenhuma regra
nova** — o dono da grade e do fingerprint continua sendo a `modeling`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    load_training_grid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.services.training_grid import TrainingGrid
from financial_forecasting.shared.application.ports.out.medallion_store import MedallionStore
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher


class ReadTrainingGrid:
    """Lê a grade de treino aparada de um ativo (a mesma leitura do treino) e o fingerprint."""

    def __init__(self, *, store: MedallionStore, columns: Sequence[str], hasher: Hasher) -> None:
        self._store = store
        self._columns = tuple(columns)
        self._hasher = hasher

    def __call__(self, *, asset_id: str) -> tuple[TrainingGrid, DatasetContentFingerprint]:
        """A grade do ativo e o seu fingerprint; os erros de `load_training_grid` propagam."""
        grid = load_training_grid(store=self._store, asset_id=asset_id, columns=self._columns)
        value = grid_fingerprint(grid, hasher=self._hasher, asset_id=asset_id)
        return grid, DatasetContentFingerprint(value)
