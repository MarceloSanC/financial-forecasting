"""Fake do port `TrainingGridReader` — linhas por ativo, grade pelo dono (ADR 6.4.0009).

Guarda as linhas do dataset por ativo e delega a montagem ao serviço de domínio
`build_training_grid` da `modeling` (a regra do corte tem um dono; o fake não a
reimplementa). Ativo sem linhas → `build_training_grid(())` → `NoUsableRowsError`,
como o real. `calls` registra os ativos pedidos (testes de "lido uma vez").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from financial_forecasting.features.modeling.domain.services.training_grid import (
    TrainingGrid,
    build_training_grid,
)

Row = Mapping[str, object]


class FakeTrainingGridReader:
    """Satisfaz `TrainingGridReader` sobre linhas em memória."""

    def __init__(
        self, rows_by_asset: Mapping[str, Sequence[Row]], *, columns: Sequence[str]
    ) -> None:
        self._rows = {asset: [dict(row) for row in rows] for asset, rows in rows_by_asset.items()}
        self._columns = tuple(columns)
        self.calls: list[str] = []

    def __call__(self, *, asset_id: str) -> TrainingGrid:
        self.calls.append(asset_id)
        return build_training_grid(self._rows.get(asset_id, []), columns=self._columns)
