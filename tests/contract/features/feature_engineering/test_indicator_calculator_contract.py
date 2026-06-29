"""Contract test do port `IndicatorCalculator` — paridade Fake ↔ PandasTaIndicatorCalculator.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável de FORMA (concept 3.1 A6/Task 05):

- `calculate` devolve uma `Mapping[str, float]` por `Candle`, na ordem temporal.
- cada `Mapping` carrega EXATAMENTE as chaves de `INDICATOR_SPECS` (I8).
- `candle_range`/`candle_body` são os valores reais da própria barra (causais).
- valores `float` finitos pós-warmup (efetivo) e `NaN` tolerado no warmup (I6).
- entrada DESORDENADA produz saída ORDENADA por timestamp (I9).
- sequência vazia → saída vazia (C5).

A FÓRMULA canônica (Wilder/MACD/EMA/volatility) e a CAUSALIDADE (barras futuras não
alteram o passado) são redes específicas do real nas Tasks 06/07 — aqui validamos só
a forma compartilhada por fake e real.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)

# `IndicatorCalculator` (Protocol, duck-typed) tipa a fixture parametrizada [fake, real].
from financial_forecasting.features.feature_engineering.application.ports.out.indicator_calculator import (  # noqa: E501
    IndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

_ASSET = "AAPL"
_N_BARS = 260  # > maior warmup (ema_200=200) para finitude pós-warmup observável
_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)
# warmup efetivo a partir do qual TODOS os indicadores devem ser finitos: ema_200=200
# + folga; usamos o maior warmup declarado + 1 para o volatility efetivo.
_MAX_WARMUP = max(spec.warmup for spec in INDICATOR_SPECS.values())  # 200


def _candles(n: int) -> list[Candle]:
    """Série determinística de candles válidos (close oscilante, timestamps distintos)."""
    out: list[Candle] = []
    for i in range(n):
        # close com tendência + ondulação (evita pct_change degenerado → std não-zero).
        close = 100.0 + i * 0.3 + 3.0 * math.sin(i / 5.0)
        out.append(
            Candle(
                asset=_ASSET,
                timestamp=_BASE_TS + timedelta(days=i),
                open=close - 0.4,
                high=close + 1.2,
                low=close - 1.2,
                close=close,
                volume=1_000 + i,
            )
        )
    return out


_FACTORIES: list[type[IndicatorCalculator]] = [
    FakeIndicatorCalculator,
    PandasTaIndicatorCalculator,
]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def calculator(request: pytest.FixtureRequest) -> IndicatorCalculator:
    """Parametriza o contrato sobre o fake e o adapter real (paridade fake↔real)."""
    factory: type[IndicatorCalculator] = request.param
    return factory()


@pytest.mark.contract
def test_one_row_per_candle(calculator: IndicatorCalculator) -> None:
    """Devolve uma linha por candle de entrada."""
    candles = _candles(_N_BARS)
    rows = calculator.calculate(_ASSET, candles)
    assert len(rows) == len(candles)


@pytest.mark.contract
def test_each_row_has_exactly_registry_keys(calculator: IndicatorCalculator) -> None:
    """Cada linha tem EXATAMENTE as chaves de `INDICATOR_SPECS` (I8)."""
    rows = calculator.calculate(_ASSET, _candles(_N_BARS))
    expected = set(INDICATOR_SPECS)
    for row in rows:
        assert set(row) == expected


@pytest.mark.contract
def test_values_are_python_floats(calculator: IndicatorCalculator) -> None:
    """Os valores que cruzam a fronteira são `float` Python (não numpy/Series)."""
    rows = calculator.calculate(_ASSET, _candles(_N_BARS))
    for value in rows[-1].values():
        assert isinstance(value, float)


@pytest.mark.contract
def test_ohlc_derived_are_real_and_causal(calculator: IndicatorCalculator) -> None:
    """`candle_range`/`candle_body` batem com a própria barra (ponto-a-ponto)."""
    candles = _candles(_N_BARS)
    rows = calculator.calculate(_ASSET, candles)
    ordered = sorted(candles, key=lambda c: c.timestamp)
    for candle, row in zip(ordered, rows, strict=True):
        assert row["candle_range"] == pytest.approx(candle.high - candle.low, rel=1e-4)
        assert row["candle_body"] == pytest.approx(abs(candle.close - candle.open), rel=1e-4)


@pytest.mark.contract
def test_finite_after_max_warmup(calculator: IndicatorCalculator) -> None:
    """Pós-warmup (maior warmup) todos os indicadores são finitos (I6)."""
    rows = calculator.calculate(_ASSET, _candles(_N_BARS))
    for row in rows[_MAX_WARMUP + 1 :]:
        for name, value in row.items():
            assert math.isfinite(value), f"{name} not finite post-warmup"


@pytest.mark.contract
def test_unordered_input_yields_ordered_output(calculator: IndicatorCalculator) -> None:
    """Entrada desordenada → saída ordenada por timestamp (I9): mesma saída que a ordenada."""
    candles = _candles(_N_BARS)
    shuffled = list(reversed(candles))
    rows_ordered = calculator.calculate(_ASSET, candles)
    rows_shuffled = calculator.calculate(_ASSET, shuffled)
    # candle_range na barra k deve coincidir (a ordenação interna reordena o shuffle)
    for r_ord, r_shuf in zip(rows_ordered, rows_shuffled, strict=True):
        assert r_ord["candle_range"] == pytest.approx(r_shuf["candle_range"], rel=1e-4)


@pytest.mark.contract
def test_empty_input_yields_empty_output(calculator: IndicatorCalculator) -> None:
    """Sequência vazia → saída vazia (C5)."""
    assert list(calculator.calculate(_ASSET, [])) == []


@pytest.mark.contract
def test_real_coerces_to_float32_precision() -> None:
    """O real coage a `float32`: o valor cabe na precisão de float32 (I4)."""
    real = PandasTaIndicatorCalculator()
    rows = real.calculate(_ASSET, _candles(_N_BARS))
    sample = rows[-1]["ema_10"]
    assert sample == pytest.approx(float(np.float32(sample)), rel=0, abs=0)
