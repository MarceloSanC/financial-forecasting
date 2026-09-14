"""Teste do consumidor do port `IndicatorCalculator` via fake (concept 3.1 A5/Task 03).

Prova que:

- O `FakeIndicatorCalculator` satisfaz o `Protocol` `IndicatorCalculator` por
  duck-typing — atribuível a uma variável tipada `IndicatorCalculator` (mypy --strict
  confirma; aqui também em runtime via `isinstance` contra o `runtime_checkable`?
  o Protocol não é runtime_checkable, então a prova de tipo é o mypy + o uso).
- Um CONSUMIDOR genérico (função que tipa `IndicatorCalculator`) usa o fake SEM
  importar `pandas` — a `application` é testável sem infra externa
  (skill `pytest-with-fakes`).
- A saída tem uma linha por candle com EXATAMENTE as chaves de `INDICATOR_SPECS`,
  `candle_range`/`candle_body` reais, `NaN` só no warmup, finito pós-warmup.
- Desde a #32 os trailing são a fórmula canônica (oráculo `indicator_formulas`),
  mascarada ao warmup NOMINAL: `ema_10` na barra 10 é a EMA de fato (semente SMA em 9,
  um passo de recursão) — o fake responde como o real responderia, em `float64`.

Importa SÓ stdlib + o port/registry de domínio + a entity `Candle` + o fake. Nada de
`pandas`/`pandas_ta_classic`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest

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
_N_BARS = 60  # cobre o warmup nominal dos trailing curtos do fake (rsi/macd/volatility).
_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _candles(n: int) -> list[Candle]:
    """Série determinística de candles válidos (close crescente, timestamps distintos)."""
    out: list[Candle] = []
    for i in range(n):
        close = 100.0 + i
        out.append(
            Candle(
                asset=_ASSET,
                timestamp=_BASE_TS + timedelta(days=i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000 + i,
            )
        )
    return out


def _consume(
    calculator: IndicatorCalculator, candles: Sequence[Candle]
) -> Sequence[Mapping[str, float]]:
    """Consumidor genérico tipado pelo PORT (não pelo concreto) — sem pandas."""
    return calculator.calculate(_ASSET, candles)


@pytest.mark.unit
def test_fake_satisfies_protocol_and_is_consumable() -> None:
    """O fake é atribuível ao `Protocol` e um consumidor genérico o usa (A5)."""
    calculator: IndicatorCalculator = FakeIndicatorCalculator()
    rows = _consume(calculator, _candles(_N_BARS))
    assert len(rows) == _N_BARS


@pytest.mark.unit
def test_each_row_has_exactly_registry_keys() -> None:
    """Cada linha tem EXATAMENTE as chaves de `INDICATOR_SPECS` (forma do contrato)."""
    calculator: IndicatorCalculator = FakeIndicatorCalculator()
    rows = _consume(calculator, _candles(_N_BARS))
    expected = set(INDICATOR_SPECS)
    for row in rows:
        assert set(row) == expected


@pytest.mark.unit
def test_ohlc_derived_are_real_and_causal() -> None:
    """`candle_range`/`candle_body` são os valores reais da própria barra."""
    candles = _candles(_N_BARS)
    calculator: IndicatorCalculator = FakeIndicatorCalculator()
    rows = _consume(calculator, candles)
    ordered = sorted(candles, key=lambda c: c.timestamp)
    for candle, row in zip(ordered, rows, strict=True):
        assert row["candle_range"] == pytest.approx(candle.high - candle.low)
        assert row["candle_body"] == pytest.approx(abs(candle.close - candle.open))


@pytest.mark.unit
def test_nan_only_during_warmup_then_finite() -> None:
    """Trailing indicators: `NaN` durante o warmup, finito depois (I6)."""
    calculator: IndicatorCalculator = FakeIndicatorCalculator()
    rows = _consume(calculator, _candles(_N_BARS))
    rsi_warmup = INDICATOR_SPECS["rsi_14"].warmup
    # dentro do warmup → NaN
    assert math.isnan(rows[0]["rsi_14"])
    # logo após o warmup → finito
    assert math.isfinite(rows[rsi_warmup]["rsi_14"])


@pytest.mark.unit
def test_empty_input_yields_empty_output() -> None:
    """Sequência vazia → saída vazia (C5)."""
    calculator: IndicatorCalculator = FakeIndicatorCalculator()
    assert list(_consume(calculator, [])) == []


def test_trailing_values_are_the_canonical_formula_masked_to_nominal_warmup() -> None:
    """#32 — `ema_10` do fake é a EMA canônica (não placeholder), com `NaN` até a barra 9.

    Semente = SMA dos 10 primeiros closes em 9 (mascarada: warmup nominal 10), barra 10 =
    um passo `((1-a)*sma + a*close_10) / ((1-a)+a)`, `a = 2/11`. Um fake com placeholder
    reprovaria aqui — e reprovaria no validador anti-leakage do `DatasetAssembler`.
    """
    candles = _candles(_N_BARS)
    rows = FakeIndicatorCalculator().calculate(_ASSET, candles)
    closes = [float(c.close) for c in candles]
    alpha = 2.0 / 11.0
    sma = sum(closes[:10]) / 10.0
    expected_10 = ((1.0 - alpha) * sma + alpha * closes[10]) / ((1.0 - alpha) + alpha)

    assert math.isnan(rows[9]["ema_10"])  # semente existe no oráculo, mascarada ao nominal
    assert rows[10]["ema_10"] == expected_10
