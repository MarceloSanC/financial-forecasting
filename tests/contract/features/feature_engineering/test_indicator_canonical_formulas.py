"""Fixture-oráculo de fórmula canônica dos indicadores (concept 3.1 I3/A7/Task 06).

Rede ANALÍTICA independente (oráculo, ADR 0.0.0021): recalcula cada indicador em
`numpy`/stdlib PURO — independente do `pandas-ta-classic` — e compara com a saída do
`PandasTaIndicatorCalculator` dentro de `atol`/`rtol` calibrados para `float32` (I4).
É a rede que protege contra troca silenciosa de semântica da lib (supply-chain,
overview §10) e prova a paridade de fórmula com o old (Q1).

Fórmulas canônicas verificadas (I3/C6):
- **RSI = Wilder** (smoothing recursivo/RMA, NÃO SMA): `avg = (avg_prev*(n-1)+x)/n`,
  seed = média simples dos primeiros `n` ganhos/perdas (primeiro RSI no índice `n`).
- **MACD = EMA12 - EMA26**; **signal = EMA9(MACD)**.
- **EMA recursiva** com `alpha = 2/(N+1)`, seed = SMA dos primeiros `N` valores
  (primeiro EMA no índice `N-1`).
- **`volatility_20d` = std rolling(20) de `close.pct_change()`** (ddof=1, pandas
  default); warmup EFETIVO 21 (1 do `pct_change` + 20 da janela `std`) — I7/D6.
- `candle_range = high - low`; `candle_body = |close - open|`.

A finitude pós-warmup (I6) usa o warmup EFETIVO de cada indicador (21 para o
volatility). O oráculo computa em `float64` e a comparação tolera a precisão de
`float32` (a saída do adapter é `float32`).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

_ASSET = "AAPL"
_N_BARS = 260  # > maior warmup (ema_200=200), com folga para o regime estacionário
_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)

# Tolerâncias calibradas para `float32` (saída do adapter): valores ~50-150, epsilon
# relativo do float32 ~1.2e-7 → abs ~2e-5; usamos margem confortável.
_ATOL = 1e-3
_RTOL = 1e-4
# Tolerância da volatilidade (valores ~1e-2, magnitude pequena → rtol maior).
_VOL_ATOL = 1e-6
_VOL_RTOL = 1e-3

_VOLATILITY_WINDOW = 20
_VOLATILITY_EFFECTIVE_WARMUP = 21  # 1 do pct_change + 20 da janela std (I7/D6)


def _closes() -> list[float]:
    """Série de closes determinística, oscilante (pct_change não-degenerado)."""
    return [100.0 + i * 0.3 + 3.0 * math.sin(i / 5.0) for i in range(_N_BARS)]


def _candles(closes: list[float]) -> list[Candle]:
    """Candles válidos a partir dos closes (OHLC consistente, timestamps distintos)."""
    out: list[Candle] = []
    for i, close in enumerate(closes):
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


# =============================================================================
# Oráculos analíticos (numpy puro) — independentes do pandas-ta-classic
# =============================================================================


def _ema_oracle(x: np.ndarray, n: int) -> np.ndarray:
    """EMA recursiva: seed = SMA dos primeiros `n`, depois `alpha=2/(n+1)`."""
    alpha = 2.0 / (n + 1)
    out = np.full_like(x, np.nan)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _ema_from(x: np.ndarray, n: int, start: int) -> np.ndarray:
    """EMA9 sobre uma série que começa a valer em `start` (usado pelo signal do MACD)."""
    alpha = 2.0 / (n + 1)
    out = np.full(len(x), np.nan)
    out[start + n - 1] = x[start : start + n].mean()
    for i in range(start + n, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi_wilder_oracle(x: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI de Wilder: RMA recursiva dos ganhos/perdas, seed = média simples (primeiro em `n`)."""
    diffs = np.diff(x)
    gain = np.where(diffs > 0, diffs, 0.0)
    loss = np.where(diffs < 0, -diffs, 0.0)
    out = np.full(len(x), np.nan)
    avg_gain = gain[:n].mean()
    avg_loss = loss[:n].mean()
    out[n] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(n + 1, len(x)):
        avg_gain = (avg_gain * (n - 1) + gain[i - 1]) / n
        avg_loss = (avg_loss * (n - 1) + loss[i - 1]) / n
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def _volatility_oracle(x: np.ndarray, window: int = _VOLATILITY_WINDOW) -> np.ndarray:
    """std rolling(window) de pct_change (ddof=1, pandas default)."""
    rets = np.full(len(x), np.nan)
    rets[1:] = x[1:] / x[:-1] - 1.0
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        seg = rets[i - window + 1 : i + 1]
        if i >= window and not np.isnan(seg).any():
            out[i] = seg.std(ddof=1)
    return out


# =============================================================================
# Helpers de comparação
# =============================================================================


def _column(rows: list[dict[str, float]], name: str) -> np.ndarray:
    return np.array([row[name] for row in rows], dtype=float)


@pytest.fixture(scope="module")
def adapter_rows() -> list[dict[str, float]]:
    """Saída do adapter real sobre a série canônica (computada uma vez)."""
    real = PandasTaIndicatorCalculator()
    return [dict(row) for row in real.calculate(_ASSET, _candles(_closes()))]


# =============================================================================
# Testes de fórmula canônica
# =============================================================================


@pytest.mark.contract
@pytest.mark.parametrize("length", [10, 50, 100, 200])
def test_ema_matches_recursive_alpha_oracle(
    adapter_rows: list[dict[str, float]], length: int
) -> None:
    """EMA bate com o oráculo recursivo `alpha=2/(N+1)` pós-warmup (I3)."""
    closes = np.array(_closes(), dtype=float)
    oracle = _ema_oracle(closes, length)
    produced = _column(adapter_rows, f"ema_{length}")
    start = length  # pós o primeiro valor (índice N-1)
    np.testing.assert_allclose(produced[start:], oracle[start:], atol=_ATOL, rtol=_RTOL)


@pytest.mark.contract
def test_rsi_uses_wilder_not_sma(adapter_rows: list[dict[str, float]]) -> None:
    """RSI bate com Wilder (RMA) e NÃO com a variante SMA (I3/C6)."""
    closes = np.array(_closes(), dtype=float)
    wilder = _rsi_wilder_oracle(closes, 14)
    produced = _column(adapter_rows, "rsi_14")
    # bate com Wilder pós-warmup declarado (14)
    np.testing.assert_allclose(produced[14:], wilder[14:], atol=_ATOL, rtol=_RTOL)


@pytest.mark.contract
def test_macd_is_ema12_minus_ema26(adapter_rows: list[dict[str, float]]) -> None:
    """MACD = EMA12 - EMA26 (I3)."""
    closes = np.array(_closes(), dtype=float)
    macd_oracle = _ema_oracle(closes, 12) - _ema_oracle(closes, 26)
    produced = _column(adapter_rows, "macd")
    np.testing.assert_allclose(produced[26:], macd_oracle[26:], atol=_ATOL, rtol=_RTOL)


@pytest.mark.contract
def test_macd_signal_is_ema9_of_macd(adapter_rows: list[dict[str, float]]) -> None:
    """signal = EMA9(MACD), seedado onde a linha MACD começa a valer (I3)."""
    closes = np.array(_closes(), dtype=float)
    macd_line = _ema_oracle(closes, 12) - _ema_oracle(closes, 26)
    macd_line_start = 26 - 1  # primeiro valor da linha MACD (índice 25)
    signal_oracle = _ema_from(macd_line, 9, macd_line_start)
    produced = _column(adapter_rows, "macd_signal")
    # warmup declarado do signal = 35; comparar a partir daí (efetivo 33)
    np.testing.assert_allclose(produced[35:], signal_oracle[35:], atol=_ATOL, rtol=_RTOL)


@pytest.mark.contract
def test_volatility_is_rolling_std_of_returns(adapter_rows: list[dict[str, float]]) -> None:
    """volatility_20d = std rolling(20) de pct_change; finito a partir da barra 21 (I7)."""
    closes = np.array(_closes(), dtype=float)
    vol_oracle = _volatility_oracle(closes, _VOLATILITY_WINDOW)
    produced = _column(adapter_rows, "volatility_20d")
    eff = _VOLATILITY_EFFECTIVE_WARMUP
    np.testing.assert_allclose(produced[eff:], vol_oracle[eff:], atol=_VOL_ATOL, rtol=_VOL_RTOL)
    # I6/I7: finitude a partir do warmup EFETIVO (21)
    assert np.all(np.isfinite(produced[eff:]))


@pytest.mark.contract
def test_candle_range_and_body_are_exact(adapter_rows: list[dict[str, float]]) -> None:
    """candle_range = high - low; candle_body = |close - open| (exatos por barra)."""
    candles = _candles(_closes())
    rng = _column(adapter_rows, "candle_range")
    body = _column(adapter_rows, "candle_body")
    for i, candle in enumerate(candles):
        assert rng[i] == pytest.approx(candle.high - candle.low, abs=_ATOL)
        assert body[i] == pytest.approx(abs(candle.close - candle.open), abs=_ATOL)


@pytest.mark.contract
def test_finite_after_effective_warmup(adapter_rows: list[dict[str, float]]) -> None:
    """Cada indicador é finito a partir do seu warmup EFETIVO (I6/I7); NaN só antes."""
    for name, spec in INDICATOR_SPECS.items():
        produced = _column(adapter_rows, name)
        effective = _VOLATILITY_EFFECTIVE_WARMUP if name == "volatility_20d" else spec.warmup
        assert np.all(np.isfinite(produced[effective:])), f"{name} not finite post-warmup"


@pytest.mark.contract
@pytest.mark.parametrize(
    ("name", "last_nan_index"),
    [
        ("ema_10", 8),  # EMA_N: NaN até N-2, primeiro finito em N-1
        ("ema_50", 48),
        ("ema_100", 98),
        ("ema_200", 198),
        ("macd", 24),  # MACD seedado pela EMA26: NaN até 24, finito em 25
        ("volatility_20d", 19),  # janela de 20 sobre pct_change: NaN dentro da janela
    ],
)
def test_warmup_region_is_nan_before_first_finite(
    adapter_rows: list[dict[str, float]], name: str, last_nan_index: int
) -> None:
    """O warmup PRODUZ `NaN` antes do primeiro valor finito (I6/I7/D6) — não só finito depois.

    As outras asserções de finitude provam só o lado pós-warmup; um cálculo que
    seedasse o indicador cedo demais (seed não-causal/look-ahead a partir da barra 0)
    passaria nelas. Este teste prende o LADO `NaN`: a barra imediatamente anterior ao
    primeiro finito ainda é `NaN`, e a primeira barra (índice 0) também — provando que
    a região de aquecimento existe de fato e na posição esperada (boundary estável,
    verificado contra o adapter real).
    """
    produced = _column(adapter_rows, name)
    assert math.isnan(produced[0]), f"{name} deveria ser NaN na barra 0 (warmup)"
    assert math.isnan(
        produced[last_nan_index]
    ), f"{name} deveria ser NaN na barra {last_nan_index} (última do warmup)"
    assert math.isfinite(
        produced[last_nan_index + 1]
    ), f"{name} deveria ser finito na barra {last_nan_index + 1} (primeira pós-warmup)"


@pytest.mark.contract
def test_rsi_diverges_from_sma_variant() -> None:
    """Sanidade: a variante SMA do RSI difere de Wilder (a fixture pegaria a troca)."""
    closes = np.array(_closes(), dtype=float)
    wilder = _rsi_wilder_oracle(closes, 14)
    # variante SMA ingênua (média simples da janela, não recursiva): difere de Wilder
    diffs = np.diff(closes)
    gain = np.where(diffs > 0, diffs, 0.0)
    loss = np.where(diffs < 0, -diffs, 0.0)
    sma_rsi = np.full(len(closes), np.nan)
    for i in range(14, len(closes)):
        ag = gain[i - 14 : i].mean()
        al = loss[i - 14 : i].mean()
        sma_rsi[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    # as duas séries NÃO devem ser iguais (senão o teste de Wilder não discrimina)
    assert not np.allclose(wilder[20:], sma_rsi[20:], atol=1e-2)
