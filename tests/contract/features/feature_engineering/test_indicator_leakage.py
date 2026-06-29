"""Teste de leakage / causalidade dos indicadores (concept 3.1 I2/A8/Task 07).

Teste OBRIGATÓRIO (ADR 0.0.0021): o indicador calculado em `t` permanece INALTERADO
ao anexar barras FUTURAS. Procedimento: calcular sobre N barras, anexar M barras
posteriores, recalcular sobre N+M, e provar que os valores das N barras originais
(pós-warmup) são IDÊNTICOS — a chegada de futuro não muda o passado. Garantido pela
ordenação por `timestamp` (`.sort_values`, I9) + janelas trailing.

Cobre tanto os indicadores trailing (`rsi`/`macd`/`ema`/`volatility` — causalidade
não-trivial) quanto os `same_timestamp_ohlc_derived` (`candle_range`/`candle_body` —
trivialmente causais, por completude). Inclui ainda o caso de ENTRADA DESORDENADA
(timestamps fora de ordem) para provar que `.sort_values` (I9) torna o resultado
independente da ordem de entrada — reforça a causalidade.

Roda sobre o adapter REAL (`PandasTaIndicatorCalculator`). A comparação pós-warmup usa
igualdade `float32` exata (o adapter coage a `float32`; recomputar a mesma série
trailing produz o MESMO `float32`).
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

_ASSET = "AAPL"
_N_ORIGINAL = 240  # > maior warmup (ema_200=200), região pós-warmup ampla
_M_FUTURE = 30  # barras futuras anexadas
_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)
# Compara a partir do maior warmup efetivo (ema_200=200) + folga: região onde TODOS
# os indicadores trailing já estão estabilizados.
_COMPARE_FROM = 200


def _candle(i: int) -> Candle:
    """Candle determinístico no índice `i` (close oscilante, OHLC consistente)."""
    close = 100.0 + i * 0.3 + 3.0 * math.sin(i / 5.0)
    return Candle(
        asset=_ASSET,
        timestamp=_BASE_TS + timedelta(days=i),
        open=close - 0.4,
        high=close + 1.2,
        low=close - 1.2,
        close=close,
        volume=1_000 + i,
    )


def _candles(n: int) -> list[Candle]:
    return [_candle(i) for i in range(n)]


@pytest.fixture(scope="module")
def calculator() -> PandasTaIndicatorCalculator:
    return PandasTaIndicatorCalculator()


@pytest.mark.contract
def test_appending_future_bars_does_not_change_past(
    calculator: PandasTaIndicatorCalculator,
) -> None:
    """Anexar M barras futuras NÃO altera os valores pós-warmup das N originais (I2)."""
    original = _candles(_N_ORIGINAL)
    extended = _candles(_N_ORIGINAL + _M_FUTURE)

    rows_original = calculator.calculate(_ASSET, original)
    rows_extended = calculator.calculate(_ASSET, extended)

    # as primeiras N linhas do estendido correspondem às N originais (mesma ordem)
    for i in range(_COMPARE_FROM, _N_ORIGINAL):
        for name in INDICATOR_SPECS:
            before = rows_original[i][name]
            after = rows_extended[i][name]
            assert (
                before == after
            ), f"leakage at bar {i} for {name!r}: {before} != {after} after appending future bars"


@pytest.mark.contract
def test_unordered_input_yields_same_result_as_ordered(
    calculator: PandasTaIndicatorCalculator,
) -> None:
    """Entrada desordenada → mesma saída que a ordenada (I9 garante causalidade)."""
    ordered = _candles(_N_ORIGINAL)
    shuffled = list(ordered)
    random.Random(20260629).shuffle(shuffled)

    rows_ordered = calculator.calculate(_ASSET, ordered)
    rows_shuffled = calculator.calculate(_ASSET, shuffled)

    assert len(rows_ordered) == len(rows_shuffled)
    for i in range(_COMPARE_FROM, _N_ORIGINAL):
        for name in INDICATOR_SPECS:
            assert (
                rows_ordered[i][name] == rows_shuffled[i][name]
            ), f"order-dependence at bar {i} for {name!r}: sort_values (I9) not applied"


@pytest.mark.contract
def test_ohlc_derived_are_bar_local_and_causal(
    calculator: PandasTaIndicatorCalculator,
) -> None:
    """`candle_range`/`candle_body` dependem SÓ da própria barra (trivialmente causais)."""
    original = _candles(_N_ORIGINAL)
    extended = _candles(_N_ORIGINAL + _M_FUTURE)
    rows_original = calculator.calculate(_ASSET, original)
    rows_extended = calculator.calculate(_ASSET, extended)
    for i in range(_N_ORIGINAL):  # válido desde a barra 0 (warmup 0)
        for name in ("candle_range", "candle_body"):
            assert rows_original[i][name] == rows_extended[i][name]
