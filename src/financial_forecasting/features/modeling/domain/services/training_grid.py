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

from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
    NoUsableRowsError,
)


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
