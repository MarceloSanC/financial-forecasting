"""Grid único de treino — regra de corte do prefixo sem valor (Stage 5.5, D11).

O dataset TFT guarda as linhas de aquecimento dos indicadores como NaN (ADR
3.5.0002). O TFT recusa NaN e o LightGBM aceita: sem uma regra única, os modelos
treinariam sobre conjuntos diferentes. A regra é cortar o PREFIXO até a primeira
linha em que todas as colunas de modelagem são finitas — os blocos de teste são
ladrilhados a partir do fim da série, então o corte encurta treinos e nunca move
o OOS — e recusar qualquer valor ausente depois dele (ADR 5.5.0004).

Domínio puro: recebe colunas já extraídas, não lê store nem conhece o registry.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
    NoUsableRowsError,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher


def _is_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def usable_start(values: Mapping[str, Sequence[float | None]]) -> int:
    """Índice da primeira linha em que TODAS as colunas são finitas.

    Valor ausente (None, NaN, ±inf) depois desse índice ergue
    `InteriorMissingValuesError` com a contagem por coluna. Sem nenhuma linha
    utilizável (ou sem linhas) ergue `NoUsableRowsError`. Colunas de tamanhos
    diferentes são erro de programação (`ValueError`).
    """
    if not values:
        raise ValueError("usable_start needs at least one column")
    lengths = {len(column) for column in values.values()}
    if len(lengths) != 1:
        raise ValueError(f"columns must have the same length; got lengths {sorted(lengths)}")
    (n_rows,) = lengths

    first = next(
        (i for i in range(n_rows) if all(_is_finite(col[i]) for col in values.values())),
        None,
    )
    if first is None:
        raise NoUsableRowsError(
            f"no row has every column finite ({n_rows} rows, columns {sorted(values)})"
        )

    interior = {
        name: missing
        for name, column in values.items()
        if (missing := sum(1 for value in column[first:] if not _is_finite(value)))
    }
    if interior:
        raise InteriorMissingValuesError(interior, first_usable=first)
    return first


Row = Mapping[str, object]
_TIMESTAMP = "timestamp"


@dataclass(frozen=True)
class TrainingGrid:
    """Linhas do dataset de treino em ordem cronológica, já sem o prefixo sem valor.

    `columns` guarda cada coluna pedida (inclui `target_return`) alinhada a
    `timestamps`; `trimmed_prefix` é quantas linhas iniciais o corte removeu.
    """

    timestamps: tuple[datetime, ...]
    columns: Mapping[str, tuple[float, ...]]
    trimmed_prefix: int

    def timestamps_iso(self) -> tuple[str, ...]:
        return tuple(ts.isoformat() for ts in self.timestamps)

    def sessions(self) -> tuple[date, ...]:
        return tuple(ts.date() for ts in self.timestamps)

    def column(self, name: str) -> tuple[float, ...]:
        return self.columns[name]

    def content_fingerprint(self, *, hasher: Hasher, asset_id: str) -> str:
        """Impressão digital do conteúdo do grid (todas as colunas; ordem irrelevante).

        Caminho único para sweeps e cohort compararem o dado (I4): o mesmo grid dá
        a mesma impressão digital por qualquer use case.
        """
        return DatasetContentFingerprint.compute(
            hasher=hasher,
            asset_id=asset_id,
            timestamps=self.timestamps_iso(),
            columns=self.columns,
        ).value

    def matrix(self, names: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Matriz linha-a-linha das colunas `names`, na ordem pedida."""
        selected = [self.columns[name] for name in names]
        return tuple(zip(*selected, strict=True)) if selected else tuple(
            () for _ in self.timestamps
        )


def _timestamp_of(row: Row) -> datetime:
    value = row.get(_TIMESTAMP)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"dataset row 'timestamp' must be a tz-aware datetime; got {value!r}")
    return value


def _numeric_or_missing(row: Row, column: str) -> float | None:
    """Número vira float; `None` é ausente (decidido pelo corte); outro tipo ergue."""
    value = row.get(column)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row {column!r} must be numeric or None; got {value!r}")
    return float(value)


def build_training_grid(rows: Sequence[Row], *, columns: Sequence[str]) -> TrainingGrid:
    """Monta o grid único: ordena, valida, extrai `columns` e corta o prefixo.

    - Coluna pedida ausente das rows → `ValueError` (C6, drift registry x dataset;
      presença checada na primeira row — schema homogêneo do Parquet).
    - Timestamp repetido → `ValueError` (o grid de sessões exige unicidade).
    - Prefixo até a primeira linha com todas as `columns` finitas é removido;
      ausente depois dele → `InteriorMissingValuesError` (`usable_start`).
    - Sem linhas → `NoUsableRowsError`.

    O filtro por ativo é do chamador (a leitura do store já filtra por partição).
    """
    if not rows:
        raise NoUsableRowsError("dataset has no rows")
    missing = tuple(name for name in columns if name not in rows[0])
    if missing:
        raise ValueError(
            f"dataset is missing expected feature columns {missing!r} — "
            "registry x dataset drift (C6)"
        )
    ordered = sorted(rows, key=_timestamp_of)
    timestamps = tuple(_timestamp_of(row) for row in ordered)
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("dataset has repeated timestamps — the session grid must be unique")

    raw = {name: [_numeric_or_missing(row, name) for row in ordered] for name in columns}
    start = usable_start(raw)
    trimmed = {name: _finite_tail(name, values[start:]) for name, values in raw.items()}
    return TrainingGrid(
        timestamps=timestamps[start:],
        columns=MappingProxyType(trimmed),
        trimmed_prefix=start,
    )


def _finite_tail(name: str, values: Sequence[float | None]) -> tuple[float, ...]:
    """Valores depois do prefixo; `usable_start` já garantiu que são finitos.

    Ausente aqui é violação do invariante (desalinharia a coluna dos
    timestamps), não dado a pular: ergue em vez de filtrar.
    """
    if any(value is None for value in values):
        raise AssertionError(f"column {name!r} has a missing value after usable_start")
    return tuple(float(value) for value in values if value is not None)
