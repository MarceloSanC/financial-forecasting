"""Testes unitários de `indicator_formulas` (issue #32) — oráculo puro dos indicadores 3.1.

Casos ANALÍTICOS (a resposta é conhecida de antemão, não medida numa lib):

- EMA: série constante → EMA constante a partir de `N-1`; semente = SMA; passo
  recursivo `alpha = 2/(N+1)` conferido à mão numa série curta.
- RMA/RSI: série só de ganhos → RSI 100; só de perdas → RSI 0; ganhos = perdas → 50.
- MACD: série constante → MACD 0 e signal 0; posições de warmup 25/33.
- `volatility_20d`: retornos constantes → std 0; warmup 20; ddof=1 conferido à mão.
- Warmup/`None`: entrada mais curta que a janela → tudo `None`; `None` à esquerda
  desloca a semente (paridade `first_valid_index` da lib).

A paridade bit a bit com o `PandasTaIndicatorCalculator` é contrato, não unit —
`tests/contract/features/feature_engineering/test_indicator_formulas_parity.py`.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.feature_engineering.domain.services import (
    indicator_formulas as f,
)

pytestmark = pytest.mark.unit


# -- EMA / RMA ----------------------------------------------------------------


def test_ema_of_constant_series_is_the_constant_from_length_minus_one() -> None:
    """Série constante: `None` até `N-2`, depois exatamente a constante."""
    out = f.ema([5.0] * 12, 10)
    assert out[:9] == (None,) * 9
    assert out[9:] == (5.0, 5.0, 5.0)


def test_ema_seed_is_sma_and_step_is_the_recursion() -> None:
    """Semente = SMA dos 3 primeiros em `N-1`; passo `((1-a)*y + a*x) / ((1-a)+a)`, a=1/2."""
    out = f.ema([1.0, 2.0, 3.0, 7.0], 3)
    alpha = 2.0 / 4.0
    seed = (1.0 + 2.0 + 3.0) / 3.0
    step = ((1.0 - alpha) * seed + alpha * 7.0) / ((1.0 - alpha) + alpha)
    assert out == (None, None, seed, step)


def test_ema_shorter_than_length_is_all_none() -> None:
    assert f.ema([1.0, 2.0], 3) == (None, None)


def test_ema_leading_none_shifts_the_seed_like_first_valid_index() -> None:
    """`None` à esquerda: a semente cai em `first_valid + N - 1` (paridade da lib)."""
    out = f.ema([None, None, 1.0, 2.0, 3.0, 4.0], 3)
    assert out[:4] == (None, None, None, None)
    assert out[4] == pytest.approx(2.0)  # SMA de 1,2,3


def test_ema_rejects_non_positive_length() -> None:
    with pytest.raises(ValueError, match="length > 0"):
        f.ema([1.0, 2.0], 0)


def test_rma_uses_alpha_one_over_length() -> None:
    """Wilder: a=1/N. Série [1,1,1,5], N=3: semente 1, passo ((2/3)*1 + (1/3)*5)/1."""
    out = f.rma([1.0, 1.0, 1.0, 5.0], 3)
    alpha = 1.0 / 3.0
    expected = ((1.0 - alpha) * 1.0 + alpha * 5.0) / ((1.0 - alpha) + alpha)
    assert out == (None, None, 1.0, expected)


# -- RSI ----------------------------------------------------------------------


def test_rsi_is_100_for_monotonic_gains_and_0_for_monotonic_losses() -> None:
    up = f.rsi([float(i) for i in range(20)], 14)
    down = f.rsi([float(20 - i) for i in range(20)], 14)
    assert up[:13] == (None,) * 13
    assert all(value == pytest.approx(100.0) for value in up[13:])
    assert all(value == pytest.approx(0.0) for value in down[13:])


def test_rsi_is_symmetric_around_50_when_gains_mirror_losses() -> None:
    """Zigue-zague +1/-1: o RSI oscila num 2-ciclo simétrico em torno de 50.

    Em regime, a barra de ganho dá `100*G_hi/(G_hi+L_lo)` e a de perda
    `100*G_lo/(G_lo+L_hi)` com `G_hi == L_hi` e `G_lo == L_lo` (Wilder é linear) — a
    soma de duas barras consecutivas é 100 exato. A semente carrega a assimetria da
    janela ímpar (7 ganhos vs 6 perdas); a recursão `(13/14)^t` a apaga em 300 barras.
    """
    closes = [10.0 + (i % 2) for i in range(300)]
    out = f.rsi(closes, 14)
    assert out[-1] + out[-2] == pytest.approx(100.0, abs=1e-6)
    assert out[-1] != pytest.approx(50.0, abs=1e-3)  # 2-ciclo, não constante


def test_rsi_first_value_sits_at_length_minus_one() -> None:
    """A semente da RMA usa os 13 válidos entre os 14 primeiros (`diff` deixa None em 0)."""
    out = f.rsi([100.0 + math.sin(i) for i in range(30)], 14)
    assert out[12] is None
    assert out[13] is not None


def test_rsi_flat_series_is_none_not_division_by_zero() -> None:
    """Sem ganhos nem perdas o denominador é 0 → `None` (a lib devolve NaN)."""
    out = f.rsi([3.0] * 20, 14)
    assert out[13:] == (None,) * 7


# -- MACD ---------------------------------------------------------------------


def test_macd_of_constant_series_is_zero_with_warmups_25_and_33() -> None:
    line, signal = f.macd([50.0] * 40)
    assert line[:25] == (None,) * 25
    assert all(value == pytest.approx(0.0) for value in line[25:])
    assert signal[:33] == (None,) * 33
    assert all(value == pytest.approx(0.0) for value in signal[33:])


def test_macd_is_fast_minus_slow_with_independent_seeds() -> None:
    """A rápida NÃO é ressemeada em `slow-1`: `macd[t] == ema_12[t] - ema_26[t]`."""
    closes = [100.0 + 3.0 * math.sin(i / 5.0) for i in range(60)]
    line, _ = f.macd(closes)
    fast, slow = f.ema(closes, 12), f.ema(closes, 26)
    for t in range(25, 60):
        assert line[t] == pytest.approx(fast[t] - slow[t])


# -- volatility_20d -----------------------------------------------------------


def test_volatility_of_constant_returns_is_zero_after_warmup_20() -> None:
    """Crescimento geométrico constante → `pct_change` constante → std 0."""
    closes = [100.0 * (1.01**i) for i in range(30)]
    out = f.volatility_20d(closes)
    assert out[:20] == (None,) * 20
    assert all(value == pytest.approx(0.0, abs=1e-15) for value in out[20:])


def test_volatility_uses_sample_std_ddof_1() -> None:
    """Janela de 20 retornos alternando ±1% → std amostral = 0.01 * sqrt(20/19)."""
    closes = [100.0]
    for i in range(30):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    out = f.volatility_20d(closes)
    returns = [closes[t] / closes[t - 1] - 1.0 for t in range(11, 31)]
    mean = sum(returns) / 20
    expected = math.sqrt(sum((r - mean) ** 2 for r in returns) / 19)
    assert out[30] == pytest.approx(expected, rel=1e-12)


def test_volatility_none_inside_window_yields_none() -> None:
    closes: list[float | None] = [100.0 + i for i in range(30)]
    closes[25] = None
    out = f.volatility_20d(closes)
    assert out[24] is not None
    assert all(out[t] is None for t in range(25, 30))  # janela toca o buraco


def test_volatility_zero_previous_close_yields_none() -> None:
    """`pct_change` com base 0 → `None` (não `inf`)."""
    closes = [0.0, 1.0, *[1.0 + i for i in range(30)]]
    assert f.volatility_20d(closes)[20] is None


# -- `None` fora do contrato do port (entity garante close finito) — sem estado quebrado --


def test_ema_interior_none_yields_none_without_touching_the_state() -> None:
    """`None` interior sai como `None`; a recursão segue do último estado (não decai)."""
    out = f.ema([1.0, 2.0, 3.0, None, 3.0], 3)
    assert out[3] is None
    assert out[4] == pytest.approx(((0.5) * 2.0 + 0.5 * 3.0) / (0.5 + 0.5))


def test_rma_all_none_window_is_all_none_and_rejects_non_positive_length() -> None:
    assert f.rma([None, None, None, 1.0], 3) == (None,) * 4
    assert f.rma([1.0], 3) == (None,)  # mais curta que a janela
    with pytest.raises(ValueError, match="length > 0"):
        f.rma([1.0], 0)


def test_ema_all_none_window_after_first_valid_is_all_none() -> None:
    """Semente sem valor válido (janela toda `None` após o 1º válido isolado)."""
    assert f.ema([None, 1.0], 3) == (None, None)


def test_rsi_none_close_breaks_the_diff_pair_into_none() -> None:
    """`close[t]` ou `close[t-1]` faltante → ganho/perda `None` na posição `t`."""
    closes: list[float | None] = [100.0 + i for i in range(30)]
    closes[20] = None
    out = f.rsi(closes, 14)
    assert out[19] is not None
    assert out[20] is None
    assert out[21] is None  # o par (20, 21) também tem o `None`
