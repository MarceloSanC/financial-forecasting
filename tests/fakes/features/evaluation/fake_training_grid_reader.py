"""Fake do port `TrainingGridReader` — linhas por ativo; grade e fingerprint pelo dono.

ADR 6.4.0009; o fingerprint pelo dono desde a issue #128.

Guarda as linhas do dataset por ativo e delega a montagem ao serviço de domínio
`build_training_grid` da `modeling` e o fingerprint a `grid_fingerprint` (a regra do
corte e a escolha das entradas do fingerprint têm um dono cada; o fake não as
reimplementa — issue #128). Ativo sem linhas → `build_training_grid(())` →
`NoUsableRowsError`, como o real. `calls` registra os ativos pedidos (testes de "lido
uma vez").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    TrainingGrid,
    build_training_grid,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

Row = Mapping[str, object]


class FakeTrainingGridReader:
    """Satisfaz `TrainingGridReader` sobre linhas em memória."""

    def __init__(
        self,
        rows_by_asset: Mapping[str, Sequence[Row]],
        *,
        columns: Sequence[str],
        hasher: Hasher,
    ) -> None:
        self._rows = {asset: [dict(row) for row in rows] for asset, rows in rows_by_asset.items()}
        self._columns = tuple(columns)
        self._hasher = hasher
        self.calls: list[str] = []

    def __call__(self, *, asset_id: str) -> tuple[TrainingGrid, DatasetContentFingerprint]:
        self.calls.append(asset_id)
        grid = build_training_grid(self._rows.get(asset_id, []), columns=self._columns)
        value = grid_fingerprint(grid, hasher=self._hasher, asset_id=asset_id)
        return grid, DatasetContentFingerprint(value)
