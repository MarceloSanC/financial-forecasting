"""Contract test fake↔real do `DatasetAssemblerPort` — forma de `feature_rows` (#72).

O `DatasetQualityGate` (domínio) consome `DatasetAssemblyResult.feature_rows` e mede
missing por `None`/NaN. Este contrato garante que o fake `InMemoryDatasetAssembler`
e o adapter real `DatasetAssembler` entregam a MESMA forma ao gate — senão o use case
passa nos unitários com uma forma que o real nunca produz (foi o caso antes da #72:
o fake emitia `0.0` em toda linha e o ramo de reprovação por missing era
inalcançável).

Contrato (I6 — só primitivos cruzam a fronteira):

- `len(feature_rows) == n_rows == len(timestamps)`;
- toda linha tem EXATAMENTE as `feature_columns`;
- todo valor é `None` (faltante) ou `float` finito — nunca `NaN` cru nem `int`;
- missing é REPRESENTÁVEL: com warmup nominal > 0 existe pelo menos um `None`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblerPort,
    DatasetAssemblyInputs,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.feature_engineering.in_memory_dataset_assembler import (
    InMemoryDatasetAssembler,
)
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

pytestmark = pytest.mark.contract

_N = 300


def _synthetic_inputs(n: int = _N) -> DatasetAssemblyInputs:
    """Insumos sintéticos determinísticos aceitos pelos dois assemblers."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for i in range(n):
        close = 100.0 + math.sin(i / 9.0) * 4.0 + i * 0.04
        candles.append(
            Candle(
                asset="AAPL",
                timestamp=base + timedelta(days=i),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + i * 100,
            )
        )
    days: list[date] = [c.timestamp.date() for c in candles]
    return DatasetAssemblyInputs(
        asset="AAPL",
        candles=[
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": float(c.volume),
            }
            for c in candles
        ],
        indicators=list(FakeIndicatorCalculator().calculate("AAPL", candles)),
        daily_sentiment=[],
        asof_rows=[
            {
                "day": day,
                "fundamentals_effective_date": day - timedelta(days=30),
                "revenue": 1000.0,
                "net_income": 100.0,
                "operating_cash_flow": 120.0,
                "total_shareholder_equity": 500.0,
                "total_liabilities": 250.0,
                "net_margin": 0.1,
                "leverage_ratio": 0.5,
                "cashflow_efficiency": 0.12,
            }
            for day in days
        ],
        grid_days=days,
    )


@pytest.mark.parametrize(
    "make_assembler",
    [
        pytest.param(InMemoryDatasetAssembler, id="fake"),
        pytest.param(DatasetAssembler, id="real"),
    ],
)
def test_feature_rows_shape_is_identical_for_fake_and_real(
    make_assembler: Callable[[], DatasetAssemblerPort],
) -> None:
    """Fake e real entregam ao gate a mesma forma: `None` ou float finito, alinhados."""
    result = make_assembler().assemble(_synthetic_inputs())

    assert len(result.feature_rows) == result.n_rows == len(result.timestamps)
    expected_cols = set(result.feature_columns)
    saw_missing = False
    for row in result.feature_rows:
        assert set(row) == expected_cols
        for value in row.values():
            if value is None:
                saw_missing = True
                continue
            assert isinstance(value, float) and not isinstance(value, bool)
            assert math.isfinite(value)  # NaN cru NÃO cruza a fronteira (I6)
    assert saw_missing  # missing é representável — o gate tem o que medir
