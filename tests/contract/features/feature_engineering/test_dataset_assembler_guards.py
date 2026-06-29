"""Testes dos guards internos do `DatasetAssembler` (Stage 3.5) — branches de erro.

Exercita os branches DEFENSIVOS do adapter de montagem que o caminho feliz não
toca (concept 3.5 §6 / I2/I7), mas que uma mutação ("pular o raise", "retornar
default") silenciaria:

- `_order_columns`: coluna declarada ausente (C8) e coluna extra inesperada.
- `_validate_anti_leakage`: divergência de COMPRIMENTO montado↔oráculo.
- `_validate_asof_guard`: early-return quando não há `fundamentals_effective_date`.
- `_close`: NaN↔None equivalentes; built ausente com oráculo presente → `False`.
- `_to_date`: tipo não-coercível → `TypeError`.

Adicionados na AUDITORIA DE TESTES da Stage 3.5 (gap de cobertura dos guards
280/332/347/371/374/413/421 do `dataset_assembler.py`).
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas import (
    dataset_assembler as da,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
)


def test_order_columns_raises_on_missing_declared_column() -> None:
    """C8 — frame sem uma coluna declarada (registry/cauda) → `ValueError` (L371)."""
    frame = pd.DataFrame({"timestamp": [1], "asset_id": ["AAPL"]})  # faltam features/cauda
    with pytest.raises(ValueError, match="missing declared columns"):
        da.DatasetAssembler._order_columns(frame)


def test_order_columns_raises_on_unexpected_extra_column() -> None:
    """Coluna extra fora do contrato (≠ `day`) → `ValueError` (L374)."""
    # Monta um frame mínimo conforme e injeta uma coluna extra inesperada.
    cols = {
        "timestamp": pd.to_datetime(["2024-01-01"], utc=True),
        "asset_id": ["AAPL"],
        "fundamentals_effective_date": pd.to_datetime(["2024-01-01"], utc=True),
        "day_of_week": [0],
        "month": [1],
        "target_return": [0.0],
        "time_idx": [0],
        "surprise_extra": [1.0],  # extra inesperada
    }
    for spec in list_feature_specs():
        cols[spec.name] = [0.0]
    frame = pd.DataFrame(cols)
    with pytest.raises(ValueError, match="unexpected extra columns"):
        da.DatasetAssembler._order_columns(frame)


def test_validate_anti_leakage_raises_on_length_mismatch() -> None:
    """L347 — coluna montada com comprimento != oráculo → `AntiLeakageError`."""
    assembler = da.DatasetAssembler()
    # Frame com a coluna montada de comprimento 1; oráculo devolve comprimento 2.
    frame = pd.DataFrame({"log_return_1d": [0.0]})
    assembler._compute_derived = lambda _frame: {"log_return_1d": (0.0, 0.0)}  # type: ignore[assignment,method-assign]
    with pytest.raises(AntiLeakageError, match="length"):
        assembler._validate_anti_leakage(frame)


def test_validate_asof_guard_returns_when_column_absent() -> None:
    """L332 — sem `fundamentals_effective_date` o guard apenas retorna (no-op)."""
    frame = pd.DataFrame({"day": pd.to_datetime(["2024-01-01"], utc=True)})
    # Não levanta nem altera nada.
    da.DatasetAssembler._validate_asof_guard(frame)


def test_close_helper_branches() -> None:
    """`_close`: None↔NaN iguais; built ausente vs oráculo presente → `False` (L413)."""
    assert da._close(math.nan, None) is True  # ambos ausentes
    assert da._close(None, None) is True
    assert da._close(math.nan, 1.0) is False  # built ausente, oráculo presente (L413)
    assert da._close(1.0, 1.0) is True
    assert da._close(1.0, 1.0 + 1e-12) is True  # dentro de atol
    assert da._close(1.0, 2.0) is False


def test_to_date_rejects_non_datetime() -> None:
    """L421 — `_to_date` de um tipo não-datetime levanta `TypeError`."""
    with pytest.raises(TypeError, match="cannot coerce"):
        da._to_date("2024-01-01")
    # `date` puro não é `datetime` → também rejeitado pelo contrato (timestamp tz-aware).
    with pytest.raises(TypeError):
        da._to_date(date(2024, 1, 1))
