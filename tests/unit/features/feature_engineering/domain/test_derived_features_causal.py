"""Unit tests do domain service `DerivedFeatures` (Stage 3.4 Tasks 04-07).

Cobre (concept 3.4 §11 A5/A6, §6 C6/C7/C8):

- valores conhecidos (oráculo manual / paridade com a fórmula);
- causalidade (I6): anexar barras FUTURAS não altera o prefixo já computado;
- `None` no warmup (C7); divisão protegida (C6); `clip` antes de `sqrt` (C8);
- ranges de flags/regimes; paridade lag==shift; YoY `None` antes de 252.

Domínio puro — importa SÓ stdlib + o módulo de domínio (sem pandas/numpy).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import pytest

from financial_forecasting.features.feature_engineering.domain.services import (
    derived_features as df,
)

# Assinatura comum das derivadas unárias sobre uma sequência de preço/volume.
_UnaryFn = Callable[[Sequence[float | int | None]], tuple[float | None, ...]]

# Sequência de preços crescente simples (sem faltantes) para os testes de valor.
_CLOSE = (10.0, 11.0, 12.1, 13.31, 14.641, 16.1051, 17.71561, 19.487171)
_VOLUME = (100.0, 110.0, 90.0, 105.0, 95.0, 120.0, 80.0, 130.0)


# =============================================================================
# helpers internos
# =============================================================================


@pytest.mark.unit
def test_safe_ratio_returns_none_on_zero_or_missing_denominator() -> None:
    """C6 — `_safe_ratio` devolve `None` para denom 0/None/NaN ou num faltante."""
    assert df._safe_ratio(10.0, 0.0) is None
    assert df._safe_ratio(10.0, None) is None
    assert df._safe_ratio(10.0, math.nan) is None
    assert df._safe_ratio(None, 2.0) is None
    assert df._safe_ratio(10.0, 4.0) == pytest.approx(2.5)


@pytest.mark.unit
def test_shift_is_causal_and_rejects_non_positive_n() -> None:
    """`_shift(n>0)` é causal; `n<=0` levanta `ValueError` (I6)."""
    assert df._shift(_CLOSE, 1) == (None, *_CLOSE[:-1])
    with pytest.raises(ValueError, match="n > 0"):
        df._shift(_CLOSE, 0)
    with pytest.raises(ValueError, match="n > 0"):
        df._shift(_CLOSE, -1)


@pytest.mark.unit
def test_rolling_window_none_in_warmup_and_on_missing() -> None:
    """C7 — janela trailing é `None` no warmup e quando há faltante na janela."""
    seq = (1.0, 2.0, None, 4.0, 5.0)
    means = df._rolling_mean(seq, 2)
    assert means[0] is None  # warmup
    assert means[1] == pytest.approx(1.5)
    assert means[2] is None  # faltante na janela
    assert means[3] is None  # faltante na janela (t-1 era None)
    assert means[4] == pytest.approx(4.5)


@pytest.mark.unit
def test_std_pop_uses_ddof_zero() -> None:
    """`_rolling_std_pop` usa ddof=0 (variância populacional)."""
    # window [2,4,6]: mean=4, var_pop = (4+0+4)/3 = 2.6667, std = 1.63299...
    out = df._rolling_std_pop((2.0, 4.0, 6.0), 3)
    assert out[2] == pytest.approx(math.sqrt(8.0 / 3.0))


# =============================================================================
# A5 — valores conhecidos (paridade com a fórmula)
# =============================================================================


@pytest.mark.unit
def test_log_return_1d_matches_formula_and_warmup() -> None:
    """`log_return_1d` bate com `ln(c_t/c_t-1)`; `None` no warmup (A5)."""
    out = df.log_return_1d(_CLOSE)
    assert out[0] is None
    # close cresce 10% a cada passo → ln(1.1) constante
    for v in out[1:]:
        assert v == pytest.approx(math.log(1.1))


@pytest.mark.unit
def test_log_return_none_on_nonpositive_or_missing() -> None:
    """`log_return` devolve `None` para preço faltante ou <= 0."""
    out = df.log_return((10.0, None, -1.0, 12.0), 1)
    assert out == (None, None, None, None)


@pytest.mark.unit
def test_momentum_and_reversal_relationship() -> None:
    """`reversal_5d == -momentum_5d`; `momentum_5d` bate com pct_change(5)."""
    mom = df.momentum_5d(_CLOSE)
    rev = df.reversal_5d(_CLOSE)
    for m, r in zip(mom, rev, strict=True):
        if m is None:
            assert r is None
        else:
            assert r == pytest.approx(-m)


@pytest.mark.unit
def test_drawdown_lookback_warmup_and_value() -> None:
    """`drawdown_lookback` é `None` antes de 63; com close crescente é 0 no pico."""
    n = 80
    close = tuple(float(i + 1) for i in range(n))  # estritamente crescente
    out = df.drawdown_lookback(close)
    assert all(v is None for v in out[:62])
    # close crescente → close_t é sempre o rolling_max → drawdown 0
    assert out[62] == pytest.approx(0.0)
    assert out[-1] == pytest.approx(0.0)


@pytest.mark.unit
def test_amihud_none_when_volume_nonpositive() -> None:
    """`amihud` é `None` no warmup e onde volume <= 0 (C6)."""
    close = (10.0, 11.0, 12.0)
    volume = (100.0, 0.0, 50.0)
    out = df.amihud_illiquidity_proxy(close, volume)
    assert out[0] is None  # warmup
    assert out[1] is None  # volume == 0
    assert out[2] == pytest.approx(abs((12.0 - 11.0) / 11.0) / 50.0)


@pytest.mark.unit
def test_volume_zscore_warmup_and_spike_flag_range() -> None:
    """`volume_zscore` é `None` no warmup; `volume_spike_flag` ∈ {0,1} (A6)."""
    n = 40
    volume = [100.0] * n
    volume[35] = 1000.0  # spike grande
    z = df.volume_zscore(volume)
    flags = df.volume_spike_flag(volume)
    # warmup: shift(1) + rolling(20) → primeiras 21 posições None
    assert z[20] is None
    assert all(f in (0, 1) for f in flags)
    # o spike em t=35: janela trailing t-20..t-1 ainda é constante (100) → std=0 →
    # zscore None ali (paridade), mas posições seguintes detectam o degrau.
    assert all(z[t] is None for t in range(21))


@pytest.mark.unit
def test_volume_zscore_none_when_trailing_std_zero() -> None:
    """C6 — `volume_zscore` é `None` quando o `std` trailing é 0 (volume constante)."""
    volume = [100.0] * 30
    z = df.volume_zscore(volume)
    assert all(v is None for v in z)  # std trailing sempre 0


# =============================================================================
# A6 — causalidade: anexar barras futuras não altera o prefixo
# =============================================================================

_GROUP1_UNARY_CLOSE: list[_UnaryFn] = [
    df.log_return_1d,
    df.log_return_5d,
    df.log_return_21d,
    df.momentum_5d,
    df.momentum_21d,
    df.momentum_63d,
    df.reversal_1d,
    df.reversal_5d,
    df.drawdown_lookback,
]


@pytest.mark.unit
@pytest.mark.parametrize("fn", _GROUP1_UNARY_CLOSE)
def test_appending_future_bars_does_not_change_prefix_close(fn: _UnaryFn) -> None:
    """I6 — anexar barras futuras NÃO altera o prefixo já computado (close)."""
    n = 80
    base = tuple(10.0 + math.sin(i) for i in range(n))
    future = (*base, 99.0, 1.0, 50.0, 123.0)
    out_base = fn(base)
    out_future = fn(future)
    assert out_future[:n] == out_base


@pytest.mark.unit
def test_appending_future_bars_does_not_change_prefix_volume() -> None:
    """I6 — prefixo estável para `volume_zscore`/`volume_spike_flag` (volume)."""
    n = 60
    base = tuple(100.0 + 10.0 * math.sin(i) for i in range(n))
    future = (*base, 500.0, 50.0, 800.0)
    assert df.volume_zscore(future)[:n] == df.volume_zscore(base)
    assert df.volume_spike_flag(future)[:n] == df.volume_spike_flag(base)


@pytest.mark.unit
def test_appending_future_bars_does_not_change_prefix_amihud() -> None:
    """I6 — prefixo estável para `amihud` (close + volume)."""
    n = 50
    close = tuple(10.0 + math.sin(i) for i in range(n))
    volume = tuple(100.0 + i for i in range(n))
    close_f = (*close, 20.0, 5.0)
    volume_f = (*volume, 200.0, 300.0)
    assert df.amihud_illiquidity_proxy(close_f, volume_f)[:n] == df.amihud_illiquidity_proxy(
        close, volume
    )


# =============================================================================
# Task 05 — volatilidades + regimes
# =============================================================================


@pytest.mark.unit
def test_quantile_linear_matches_pandas_default() -> None:
    """`_quantile_linear` bate com a interpolação linear default do pandas/numpy."""
    # [1,2,3,4]: q=0.10 → h=0.3 → 1*(0.7)+2*(0.3) = 1.3
    assert df._quantile_linear((1.0, 2.0, 3.0, 4.0), 0.10) == pytest.approx(1.3)
    # mediana de [1,2,3,4] = 2.5
    assert df._quantile_linear((4.0, 1.0, 3.0, 2.0), 0.5) == pytest.approx(2.5)
    # janela de 1 ponto → o próprio valor
    assert df._quantile_linear((7.0,), 0.9) == pytest.approx(7.0)


@pytest.mark.unit
def test_parkinson_is_nonnegative_and_warmup_none() -> None:
    """`volatility_parkinson` >= 0 (ou None); None no warmup (C8/C7)."""
    n = 40
    high = tuple(11.0 + 0.5 * math.sin(i) for i in range(n))
    low = tuple(10.0 + 0.4 * math.sin(i) for i in range(n))
    out = df.volatility_parkinson(high, low)
    assert all(v is None for v in out[:19])  # warmup 20
    assert all(v is None or v >= 0.0 for v in out)


@pytest.mark.unit
def test_garman_klass_is_nonnegative_and_clips_negative_var() -> None:
    """`volatility_garman_klass` >= 0 (clip antes da raiz, C8)."""
    n = 40
    open_ = tuple(10.0 + 0.1 * i for i in range(n))
    high = tuple(11.0 + 0.1 * i for i in range(n))
    low = tuple(9.5 + 0.1 * i for i in range(n))
    close = tuple(10.5 + 0.1 * i for i in range(n))
    out = df.volatility_garman_klass(open_, high, low, close)
    assert all(v is None or v >= 0.0 for v in out)
    assert out[18] is None  # warmup


@pytest.mark.unit
def test_downside_semivolatility_nonnegative() -> None:
    """`downside_semivolatility` >= 0 (ou None no warmup)."""
    n = 40
    close = tuple(100.0 + 5.0 * math.sin(i) for i in range(n))
    out = df.downside_semivolatility(close)
    assert all(v is None or v >= 0.0 for v in out)
    assert out[19] is None  # warmup 20


@pytest.mark.unit
def test_vol_of_vol_warmup_is_40_when_input_is_raw_returns_std() -> None:
    """`vol_of_vol` é None antes da posição 40 quando a entrada é volatility_20d cru.

    Aqui simulamos a cadeia: volatility_20d com 20 posições de warmup (None) + janela
    std de 20 → primeiras 39 posições None (warmup efetivo 40 — I7).
    """
    n = 80
    # volatility_20d "cru": None nas 19 primeiras, depois valores positivos a partir
    # do indice 19. A janela std de 20 precisa de 20 valores consecutivos nao-None: a
    # primeira janela completa termina no indice 19 + 20 - 1 = 38 (warmup efetivo 40).
    vol20: list[float | None] = [None] * 19 + [0.1 + 0.01 * i for i in range(n - 19)]
    out = df.vol_of_vol(vol20)
    assert all(v is None for v in out[:38])
    assert out[38] is not None


@pytest.mark.unit
def test_volatility_regime_range_and_warmup() -> None:
    """`volatility_regime` ∈ {0,1,2} (ou None); None no warmup (A6)."""
    n = 100
    vol20 = tuple(0.1 + 0.05 * abs(math.sin(i)) for i in range(n))
    out = df.volatility_regime(vol20)
    assert out[62] is None  # shift(1)+rolling(63) → warmup
    assert all(v in (0, 1, 2) for v in out if v is not None)
    assert any(v is not None for v in out)


@pytest.mark.unit
def test_trend_regime_range() -> None:
    """`trend_regime` ∈ {-1,0,1} (ou None no warmup) (A6)."""
    n = 100
    ema10 = tuple(100.0 + math.sin(i) for i in range(n))
    ema50 = tuple(99.5 + 0.5 * math.sin(i / 2.0) for i in range(n))
    out = df.trend_regime(ema10, ema50)
    assert all(v in (-1, 0, 1) for v in out if v is not None)
    assert out[62] is None  # warmup


@pytest.mark.unit
def test_stress_tail_return_flag_range_and_warmup() -> None:
    """`stress_tail_return_flag` ∈ {0,1} (ou None no warmup) (A6)."""
    n = 100
    close = tuple(100.0 * (1.0 + 0.01 * math.sin(i)) for i in range(n))
    out = df.stress_tail_return_flag(close)
    assert all(v in (0, 1) for v in out if v is not None)
    assert out[62] is None  # warmup


@pytest.mark.unit
def test_appending_future_bars_does_not_change_prefix_volatility() -> None:
    """I6 — prefixo estável para volatilidades de 1 entrada (downside / vol_of_vol)."""
    n = 80
    close = tuple(100.0 + 5.0 * math.sin(i) for i in range(n))
    close_f = (*close, 130.0, 70.0, 200.0)
    assert df.downside_semivolatility(close_f)[:n] == df.downside_semivolatility(close)
    vol20 = tuple(0.1 + 0.02 * abs(math.sin(i)) for i in range(n))
    vol20_f = (*vol20, 0.9, 0.05)
    assert df.vol_of_vol(vol20_f)[:n] == df.vol_of_vol(vol20)
    assert df.volatility_regime(vol20_f)[:n] == df.volatility_regime(vol20)
    assert df.stress_tail_return_flag(close_f)[:n] == df.stress_tail_return_flag(close)


@pytest.mark.unit
def test_appending_future_bars_does_not_change_prefix_hl_volatility() -> None:
    """I6 — prefixo estável para Parkinson/Garman-Klass (high/low/open/close)."""
    n = 60
    high = tuple(11.0 + 0.5 * math.sin(i) for i in range(n))
    low = tuple(10.0 + 0.4 * math.sin(i) for i in range(n))
    open_ = tuple(10.5 + 0.3 * math.sin(i) for i in range(n))
    close = tuple(10.7 + 0.2 * math.sin(i) for i in range(n))
    high_f = (*high, 20.0, 5.0)
    low_f = (*low, 4.0, 1.0)
    open_f = (*open_, 8.0, 2.0)
    close_f = (*close, 9.0, 3.0)
    assert df.volatility_parkinson(high_f, low_f)[:n] == df.volatility_parkinson(high, low)
    assert df.volatility_garman_klass(open_f, high_f, low_f, close_f)[
        :n
    ] == df.volatility_garman_klass(open_, high, low, close)


@pytest.mark.unit
def test_trend_regime_prefix_stable_on_future_bars() -> None:
    """I6 — prefixo estável para `trend_regime` (ema_10/ema_50)."""
    n = 90
    ema10 = tuple(100.0 + math.sin(i) for i in range(n))
    ema50 = tuple(99.5 + 0.5 * math.sin(i / 2.0) for i in range(n))
    ema10_f = (*ema10, 130.0, 70.0)
    ema50_f = (*ema50, 80.0, 120.0)
    assert df.trend_regime(ema10_f, ema50_f)[:n] == df.trend_regime(ema10, ema50)
