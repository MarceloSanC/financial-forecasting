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


# =============================================================================
# Task 06 — sentimento dinâmico + fundamento derivado + YoY
# =============================================================================


@pytest.mark.unit
@pytest.mark.parametrize("n", [1, 3, 5])
def test_sentiment_lag_equals_shift(n: int) -> None:
    """Paridade lag==shift: `sentiment_lag_n[t] == sentiment[t-n]`; `None` em t<n."""
    sent = (0.1, 0.2, -0.3, 0.4, -0.5, 0.6, 0.7)
    lag = df.sentiment_lag(sent, n)
    assert all(v is None for v in lag[:n])
    for t in range(n, len(sent)):
        assert lag[t] == pytest.approx(sent[t - n])


@pytest.mark.unit
def test_sentiment_lag_helpers_match_generic() -> None:
    """Os helpers nomeados batem com `sentiment_lag(seq, n)`."""
    sent = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    assert df.sentiment_lag_1(sent) == df.sentiment_lag(sent, 1)
    assert df.sentiment_lag_3(sent) == df.sentiment_lag(sent, 3)
    assert df.sentiment_lag_5(sent) == df.sentiment_lag(sent, 5)


@pytest.mark.unit
def test_ewm_recursion_matches_hand_computed() -> None:
    """`_ewm(span=10, adjust=False)` bate com a recursão calculada à mão (alpha=2/11)."""
    out = df._ewm((1.0, 2.0, 3.0), 10)
    alpha = 2.0 / 11.0
    y0 = 1.0
    y1 = alpha * 2.0 + (1.0 - alpha) * y0
    y2 = alpha * 3.0 + (1.0 - alpha) * y1
    assert out[0] == pytest.approx(y0)
    assert out[1] == pytest.approx(y1)
    assert out[2] == pytest.approx(y2)


@pytest.mark.unit
def test_ewm_propagates_none_before_first_valid() -> None:
    """`_ewm` propaga `None` antes do 1º valor válido e faz seed nele."""
    out = df._ewm((None, None, 5.0, 7.0), 10)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == pytest.approx(5.0)  # seed y_0 = x_0
    alpha = 2.0 / 11.0
    assert out[3] == pytest.approx(alpha * 7.0 + (1.0 - alpha) * 5.0)


@pytest.mark.unit
def test_sentiment_surprise_warmup_and_value() -> None:
    """`sentiment_surprise = sentiment_t - mean(sentiment.shift(1), 5)`; None no warmup."""
    sent = (1.0, 1.0, 1.0, 1.0, 1.0, 2.0)
    out = df.sentiment_surprise(sent)
    assert all(v is None for v in out[:5])  # warmup 5
    # t=5: baseline = mean(sent[0..4]) = 1.0; surprise = 2 - 1 = 1.0
    assert out[5] == pytest.approx(1.0)


@pytest.mark.unit
def test_sentiment_interactions() -> None:
    """`sentiment_x_volatility`/`sentiment_x_volume` são produtos elemento a elemento."""
    sent = (0.5, -0.2, None, 0.4)
    vol20 = (0.1, 0.2, 0.3, None)
    volume = (100.0, 200.0, 300.0, 400.0)
    sxv = df.sentiment_x_volatility(sent, vol20)
    assert sxv[0] == pytest.approx(0.05)
    assert sxv[1] == pytest.approx(-0.04)
    assert sxv[2] is None  # sentiment faltante
    assert sxv[3] is None  # vol faltante
    sxvol = df.sentiment_x_volume(sent, volume)
    assert sxvol[0] == pytest.approx(50.0)
    assert sxvol[2] is None


@pytest.mark.unit
def test_fundamental_ratios_protected_division() -> None:
    """C6 — ratios fundamentais devolvem `None` quando o denominador é 0/None."""
    net_income = (10.0, 20.0, 30.0, None)
    revenue = (100.0, 0.0, None, 400.0)
    nm = df.net_margin(net_income, revenue)
    assert nm[0] == pytest.approx(0.1)
    assert nm[1] is None  # revenue == 0
    assert nm[2] is None  # revenue None
    assert nm[3] is None  # net_income None
    liabilities = (50.0, 80.0)
    equity = (100.0, 0.0)
    lev = df.leverage_ratio(liabilities, equity)
    assert lev[0] == pytest.approx(0.5)
    assert lev[1] is None
    cf = df.cashflow_efficiency((30.0,), (120.0,))
    assert cf[0] == pytest.approx(0.25)


@pytest.mark.unit
def test_yoy_growth_none_before_252_and_value_at_252() -> None:
    """A5 — YoY é `None` antes de 252; em 252 bate com `seq[252]/seq[0]-1`."""
    n = 300
    revenue = tuple(100.0 + i for i in range(n))
    rev_yoy = df.revenue_yoy_growth(revenue)
    assert all(v is None for v in rev_yoy[:252])
    assert rev_yoy[252] == pytest.approx(revenue[252] / revenue[0] - 1.0)
    net_income = tuple(10.0 + 0.5 * i for i in range(n))
    ni_yoy = df.net_income_yoy_growth(net_income)
    assert all(v is None for v in ni_yoy[:252])
    assert ni_yoy[252] == pytest.approx(net_income[252] / net_income[0] - 1.0)


@pytest.mark.unit
def test_appending_future_bars_does_not_change_prefix_sentiment_and_yoy() -> None:
    """I6 — prefixo estável para sentimento dinâmico e YoY ao anexar barras futuras."""
    n = 60
    sent = tuple(0.1 * math.sin(i) for i in range(n))
    sent_f = (*sent, 0.9, -0.9, 0.5)
    for fn in (
        df.sentiment_lag_1,
        df.sentiment_lag_3,
        df.sentiment_lag_5,
        df.sentiment_ema,
        df.sentiment_surprise,
    ):
        assert fn(sent_f)[:n] == fn(sent), fn.__name__
    rev = tuple(100.0 + i for i in range(300))
    rev_f = (*rev, 9999.0, 1.0)
    assert df.revenue_yoy_growth(rev_f)[:300] == df.revenue_yoy_growth(rev)


# =============================================================================
# Task 07 — bateria transversal de causalidade (TODAS as derivadas)
# =============================================================================
#
# A6/I6 — "anexar barras futuras não altera o passado" provado UMA vez para CADA
# derivada pública de `DerivedFeatures`. Cada entrada é uma fixture de sequências
# alinhadas + o invocador da função; o teste anexa barras futuras arbitrárias e
# afirma que o prefixo é idêntico. Fecha o invariante global de causalidade.

_PREFIX_N = 300  # cobre o maior warmup (YoY 252)


def _wavy(base: float, amp: float, n: int = _PREFIX_N) -> tuple[float, ...]:
    """Sequência ondulada determinística e estritamente positiva (para logs/ratios)."""
    return tuple(base + amp * math.sin(i / 3.0) for i in range(n))


# name -> (invocador sobre sequências-base, invocador sobre sequências+futuro).
# Cada par usa as MESMAS sequências-base; o segundo só anexa barras futuras.
_FUTURE = (999.0, -999.0, 1.0)


def _call_all_derived(extra: tuple[float, ...] | None) -> dict[str, tuple[object, ...]]:
    """Invoca TODA derivada pública sobre fixtures comuns (+ `extra` barras futuras).

    Devolve {name: saída}. Quando `extra` é dado, as sequências de entrada recebem
    barras futuras anexadas; o prefixo das saídas deve coincidir com `extra=None`.
    """
    tail = extra if extra is not None else ()
    close = (*_wavy(100.0, 5.0), *tail)
    high = (*_wavy(101.0, 5.0), *([t + 1.0 for t in tail]))
    low = (*_wavy(99.0, 4.0), *([abs(t) + 0.5 for t in tail]))
    open_ = (*_wavy(100.0, 3.0), *([abs(t) + 0.6 for t in tail]))
    volume = (*_wavy(1000.0, 100.0), *([abs(t) + 1.0 for t in tail]))
    vol20 = (*_wavy(0.2, 0.05), *([abs(t) / 1000.0 + 0.01 for t in tail]))
    ema10 = (*_wavy(100.0, 1.0), *([abs(t) + 0.1 for t in tail]))
    ema50 = (*_wavy(99.5, 0.5), *([abs(t) + 0.2 for t in tail]))
    sent = (*_wavy(0.1, 0.3), *([math.tanh(t) for t in tail]))
    revenue = (*tuple(100.0 + i for i in range(_PREFIX_N)), *([abs(t) + 1.0 for t in tail]))
    net_income = (*tuple(10.0 + 0.5 * i for i in range(_PREFIX_N)), *([abs(t) + 1.0 for t in tail]))
    liabilities = (*_wavy(50.0, 5.0), *([abs(t) + 1.0 for t in tail]))
    equity = (*_wavy(80.0, 5.0), *([abs(t) + 2.0 for t in tail]))
    ocf = (*_wavy(30.0, 3.0), *([abs(t) + 1.0 for t in tail]))

    return {
        "log_return_1d": df.log_return_1d(close),
        "log_return_5d": df.log_return_5d(close),
        "log_return_21d": df.log_return_21d(close),
        "momentum_5d": df.momentum_5d(close),
        "momentum_21d": df.momentum_21d(close),
        "momentum_63d": df.momentum_63d(close),
        "reversal_1d": df.reversal_1d(close),
        "reversal_5d": df.reversal_5d(close),
        "drawdown_lookback": df.drawdown_lookback(close),
        "amihud_illiquidity_proxy": df.amihud_illiquidity_proxy(close, volume),
        "volume_zscore": df.volume_zscore(volume),
        "volume_spike_flag": df.volume_spike_flag(volume),
        "volatility_parkinson": df.volatility_parkinson(high, low),
        "volatility_garman_klass": df.volatility_garman_klass(open_, high, low, close),
        "downside_semivolatility": df.downside_semivolatility(close),
        "vol_of_vol": df.vol_of_vol(vol20),
        "volatility_regime": df.volatility_regime(vol20),
        "trend_regime": df.trend_regime(ema10, ema50),
        "stress_tail_return_flag": df.stress_tail_return_flag(close),
        "sentiment_lag_1": df.sentiment_lag_1(sent),
        "sentiment_lag_3": df.sentiment_lag_3(sent),
        "sentiment_lag_5": df.sentiment_lag_5(sent),
        "sentiment_ema": df.sentiment_ema(sent),
        "sentiment_surprise": df.sentiment_surprise(sent),
        "sentiment_x_volatility": df.sentiment_x_volatility(sent, vol20),
        "sentiment_x_volume": df.sentiment_x_volume(sent, volume),
        "net_margin": df.net_margin(net_income, revenue),
        "leverage_ratio": df.leverage_ratio(liabilities, equity),
        "cashflow_efficiency": df.cashflow_efficiency(ocf, revenue),
        "revenue_yoy_growth": df.revenue_yoy_growth(revenue),
        "net_income_yoy_growth": df.net_income_yoy_growth(net_income),
    }


# As 31 derivadas computadas pelo oráculo (espelha as derivadas do FEATURE_SPECS).
_ALL_DERIVED_NAMES = sorted(_call_all_derived(None).keys())
_EXPECTED_DERIVED_FN_COUNT = 31


@pytest.mark.unit
def test_battery_covers_all_31_derived_functions() -> None:
    """A bateria cobre exatamente as 31 derivadas computadas (sanidade da malha)."""
    assert len(_ALL_DERIVED_NAMES) == _EXPECTED_DERIVED_FN_COUNT


@pytest.mark.unit
@pytest.mark.parametrize("name", _ALL_DERIVED_NAMES)
def test_global_causality_appending_future_bars_keeps_prefix(name: str) -> None:
    """A6/I6 GLOBAL — para TODA derivada, anexar barras futuras não altera o prefixo."""
    base = _call_all_derived(None)[name]
    with_future = _call_all_derived(_FUTURE)[name]
    assert with_future[: len(base)] == base


@pytest.mark.unit
@pytest.mark.parametrize("name", _ALL_DERIVED_NAMES)
def test_global_flag_and_regime_ranges(name: str) -> None:
    """A6 GLOBAL — flags/regimes ficam nos ranges esperados; volatilidades >= 0."""
    out = _call_all_derived(None)[name]
    if name in {"volume_spike_flag", "stress_tail_return_flag"}:
        assert all(v in (0, 1, None) for v in out)
    elif name == "volatility_regime":
        assert all(v in (0, 1, 2, None) for v in out)
    elif name == "trend_regime":
        assert all(v in (-1, 0, 1, None) for v in out)
    elif name in {
        "volatility_parkinson",
        "volatility_garman_klass",
        "downside_semivolatility",
        "vol_of_vol",
    }:
        assert all(v is None or (isinstance(v, float) and v >= 0.0) for v in out)


@pytest.mark.unit
def test_shift_is_never_negative_in_derived_helpers() -> None:
    """I6 — `_shift`/`_pct_change`/`log_return` rejeitam `n<=0` (nunca shift negativo)."""
    for fn in (df._shift, df._pct_change, df.log_return):
        with pytest.raises(ValueError, match="n > 0"):
            fn(_CLOSE, 0)
        with pytest.raises(ValueError, match="n > 0"):
            fn(_CLOSE, -3)


# =============================================================================
# Task 08 — ramos defensivos e bordas (cobertura dos guards)
# =============================================================================


@pytest.mark.unit
def test_pct_change_none_when_prev_is_zero() -> None:
    """C6 — `_pct_change` devolve `None` quando o valor base é 0 (divisão protegida)."""
    out = df._pct_change((0.0, 5.0, 10.0), 1)
    assert out[0] is None  # warmup
    assert out[1] is None  # prev == 0
    assert out[2] == pytest.approx(1.0)


@pytest.mark.unit
def test_quantile_linear_exact_position_no_interpolation() -> None:
    """`_quantile_linear` devolve o ponto exato quando `h` cai sobre um índice."""
    # [10,20,30]: q=0.5 → h=1.0 → ordered[1] = 20 (lo==hi).
    assert df._quantile_linear((30.0, 10.0, 20.0), 0.5) == pytest.approx(20.0)


@pytest.mark.unit
def test_ewm_holds_last_value_on_intermediate_missing() -> None:
    """`_ewm` mantém o último `y` quando há faltante intermediário (paridade adjust=False)."""
    out = df._ewm((2.0, None, 4.0), 10)
    assert out[0] == pytest.approx(2.0)  # seed
    assert out[1] == pytest.approx(2.0)  # faltante → mantém prev
    alpha = 2.0 / 11.0
    assert out[2] == pytest.approx(alpha * 4.0 + (1.0 - alpha) * 2.0)


@pytest.mark.unit
def test_ewm_rejects_non_positive_span() -> None:
    """`_ewm` rejeita `span <= 0`."""
    with pytest.raises(ValueError, match="span > 0"):
        df._ewm(_CLOSE, 0)


@pytest.mark.unit
def test_volume_zscore_matches_known_value() -> None:
    """`volume_zscore[t]` bate com `(v_t - mean(v_t-20..t-1))/std_pop` (witness, não só range).

    Fecha o buraco de mutação: o teste de warmup só prova `None`; sem este, uma mutação
    que sempre devolvesse `None` no ramo de valor passaria (cobertura sem asserção).
    """
    volume = [10.0, 12.0] * 10 + [30.0]  # 20 trailing (t-20..t-1) + corrente em t=20
    window = volume[0:20]
    mu = sum(window) / 20
    sd = (sum((x - mu) ** 2 for x in window) / 20) ** 0.5
    z = df.volume_zscore(volume)
    assert z[20] == pytest.approx((30.0 - mu) / sd)


@pytest.mark.unit
def test_volume_spike_flag_fires_on_real_spike() -> None:
    """`volume_spike_flag` produz `1` num spike genuíno (witness do ramo `> 3`).

    O teste de range admite tudo-zero; sem este, uma mutação que devolvesse sempre `0`
    sobreviveria.
    """
    volume = [100.0 + (1.0 if i % 2 else -1.0) for i in range(60)]
    volume[55] = 100_000.0  # spike muito acima do limiar de z-score 3
    flags = df.volume_spike_flag(volume)
    assert flags[55] == 1
    assert sum(flags) == 1  # só o spike dispara


@pytest.mark.unit
def test_volatility_regime_produces_all_three_buckets_with_known_value() -> None:
    """`volatility_regime` emite 0/1/2 e bate com a comparação ao tercil shiftado (A6).

    O teste de range sobrevive a uma mutação que devolva sempre `0`; aqui exigimos os
    três buckets presentes e fixamos um valor conhecido contra os quantis trailing.
    """
    n = 120
    vol20 = tuple(0.1 + 0.2 * abs(math.sin(i / 2.0)) for i in range(n))
    out = df.volatility_regime(vol20)
    assert {v for v in out if v is not None} == {0, 1, 2}
    # witness pontual em t=63: comparar vol20[63] aos tercis de vol20[0..62] (shift+window 63)
    window = list(vol20[0:63])
    q33 = df._quantile_linear(window, 1.0 / 3.0)
    q66 = df._quantile_linear(window, 2.0 / 3.0)
    v = vol20[63]
    expected = 0 if v <= q33 else (1 if v <= q66 else 2)
    assert out[63] == expected


@pytest.mark.unit
def test_trend_regime_produces_all_three_states() -> None:
    """`trend_regime` emite -1/0/1 (witness; range sozinho sobrevive a constante)."""
    n = 120
    ema10 = tuple(100.0 + 3.0 * math.sin(i / 4.0) for i in range(n))
    ema50 = tuple(99.0 + 0.2 * math.sin(i / 7.0) for i in range(n))
    out = df.trend_regime(ema10, ema50)
    assert {v for v in out if v is not None} == {-1, 0, 1}


@pytest.mark.unit
def test_trend_regime_zero_inside_deadband() -> None:
    """`trend_regime` = 0 quando o spread fica dentro do deadband (ramo central).

    Spread constante → deadband std = 0 → `s > 0`/`s < 0` decidem; usamos spread
    exatamente 0 num trecho para pinar o bucket 0 (fronteira `<=`/`>` do deadband).
    """
    n = 80
    # ema_10 == ema_50 em todo lugar → spread 0, deadband 0 → regime 0 (s não > 0 nem < 0)
    ema = tuple(100.0 + math.sin(i) for i in range(n))
    out = df.trend_regime(ema, ema)
    assert all(v in (0, None) for v in out)
    assert out[63] == 0  # fora do warmup, spread 0 → bucket central


@pytest.mark.unit
def test_stress_tail_return_flag_fires_on_tail_drop() -> None:
    """`stress_tail_return_flag` = 1 num retorno de cauda inferior (witness do ramo `<=`).

    O range sozinho sobrevive a tudo-zero; aqui forçamos uma queda abrupta após uma
    janela calma e exigimos a flag `1` exatamente na queda.
    """
    n = 80
    close = [100.0 + 0.01 * math.sin(i) for i in range(n)]  # janela quase plana
    close[70] = close[69] * 0.80  # -20% (cauda inferior óbvia)
    out = df.stress_tail_return_flag(tuple(close))
    assert out[70] == 1
    assert 1 in {v for v in out if v is not None}


@pytest.mark.unit
def test_length_mismatch_guards_raise() -> None:
    """Os guards de comprimento desalinhado levantam `ValueError` (defesa)."""
    with pytest.raises(ValueError, match="length mismatch"):
        df.amihud_illiquidity_proxy((1.0, 2.0), (1.0,))
    with pytest.raises(ValueError, match="length mismatch"):
        df.volatility_parkinson((1.0, 2.0), (1.0,))
    with pytest.raises(ValueError, match="length mismatch"):
        df.sentiment_x_volume((0.1, 0.2), (1.0,))
    with pytest.raises(ValueError, match="length mismatch"):
        df.net_margin((1.0, 2.0), (1.0,))
    with pytest.raises(ValueError, match="length mismatch"):
        df.trend_regime((1.0, 2.0), (1.0,))
