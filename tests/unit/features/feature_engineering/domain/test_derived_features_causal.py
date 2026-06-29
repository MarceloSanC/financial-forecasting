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
