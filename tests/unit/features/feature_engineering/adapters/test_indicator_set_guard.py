"""Teste do guard de set completo do `PandasTaIndicatorCalculator` (I8/C2).

Exercita diretamente `_require_complete_set` — a invariante que endurece o
`RuntimeError("Missing technical indicators")` do old para IGUALDADE de conjunto
(coluna faltando OU sobrando → erro explícito antes de devolver; concept 3.1 I8/C2/A6).
Cobre os dois lados da divergência (missing e extra), que o caminho feliz do contract
test não atinge.
"""

from __future__ import annotations

import pandas as pd
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)


@pytest.mark.unit
def test_missing_column_raises() -> None:
    """Coluna faltando (set incompleto) → RuntimeError com `missing` listado (C2)."""
    names = list(INDICATOR_SPECS)
    incomplete = pd.DataFrame({name: [0.0] for name in names[:-1]})  # falta a última
    with pytest.raises(RuntimeError, match="missing="):
        PandasTaIndicatorCalculator._require_complete_set(incomplete)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """Coluna extra (set sobrando) → RuntimeError com `extra` listado (C2)."""
    columns = {name: [0.0] for name in INDICATOR_SPECS}
    columns["unexpected_indicator"] = [0.0]
    with pytest.raises(RuntimeError, match="extra="):
        PandasTaIndicatorCalculator._require_complete_set(pd.DataFrame(columns))


@pytest.mark.unit
def test_complete_set_does_not_raise() -> None:
    """Set exato (igualdade) → não levanta (caminho feliz do guard)."""
    complete = pd.DataFrame({name: [0.0] for name in INDICATOR_SPECS})
    PandasTaIndicatorCalculator._require_complete_set(complete)
