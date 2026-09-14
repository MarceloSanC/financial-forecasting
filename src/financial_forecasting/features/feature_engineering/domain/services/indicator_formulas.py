"""`IndicatorFormulas` — os indicadores canônicos da 3.1 em Python puro (oráculo).

Segunda implementação independente (ADR 0.0.0021) dos indicadores trailing que o
`PandasTaIndicatorCalculator` produz via `pandas-ta-classic`: `ema_N`, `rsi_14`
(Wilder/RMA), `macd`/`macd_signal` e `volatility_20d`. Existe para fechar a metade
"indicadores canônicos (3.1)" do oráculo que o port `DatasetAssemblerPort` promete
(concept 3.5 I2/D3) e que o validador in-process do `DatasetAssembler` não entregava
(issue #32): sem ela, as derivadas que consomem indicadores (`vol_of_vol`,
`volatility_regime`, `trend_regime`, `sentiment_x_volatility`) eram re-derivadas a
partir de colunas nunca conferidas — checagem tautológica nesse eixo.

As fórmulas são as de concept 3.1 §4, replicadas na MESMA ordem de operações da lib
(verificado no container, `pandas-ta-classic` 0.6.52 / `pandas` 2.3.3), de modo que a
saída em `float64` arredondada a `float32` coincide BIT A BIT com a do adapter nas
séries sintéticas e num passeio aleatório de 4000 barras (0 divergências > 1 ulp32):

- **EMA(N)** — semente = SMA dos `N` primeiros valores a partir do 1º válido,
  colocada em `first_valid + N - 1`; depois `ewm(span=N, adjust=False)`:
  `y_t = ((1-a)*y_{t-1} + a*x_t) / ((1-a)+a)`, `a = 2/(N+1)`. O denominador `(1-a)+a`
  é o que o pandas divide de fato (não é exatamente 1.0 em ponto flutuante) — mantido
  para a paridade bit a bit.
- **RMA(N)** (Wilder) — mesma recursão com `a = 1/N`; a semente é a média dos valores
  VÁLIDOS entre os `N` primeiros (o `diff` deixa `None` na posição 0) e fica FIXA em
  `N-1` — `ta.rma` não usa `first_valid_index`, diferente de `ta.ema`.
- **RSI(14)** — `100 * rma(ganhos) / (rma(ganhos) + |rma(perdas)|)`.
- **MACD(12, 26, 9)** — `ema_12 - ema_26` (cada uma semeada no seu próprio
  lookback; a rápida NÃO é ressemeada em `slow-1`) e `signal = ema_9(macd)` semeada
  nos 9 primeiros valores válidos do MACD.
- **`volatility_20d`** — `std(ddof=1)` rolling(20) de `pct_change(1)`.

Convenções: entrada `Sequence[float | int | None]`, saída `tuple[float | None, ...]`
alinhada 1:1 com `None` no warmup (paridade `NaN`), como em `derived_features.py`.
`None` intermediário (fora do warmup) é propagado como `None` na saída — o adapter
real nunca produz esse caso (candles sem `close` são rejeitados na entity).

Pureza (I1): importa SÓ stdlib (`math`/`collections.abc`). `import pandas`/`numpy`
aqui REPROVA `domain-purity` no import-linter.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from financial_forecasting.features.feature_engineering.domain.services.derived_features import (
    Number,
    OutSeq,
)

# Defaults do MACD (concept 3.1 §4 — `ta.macd(close)` sem argumentos = 12/26/9).
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
# Comprimento do RSI e janela da volatilidade realizada (concept 3.1 §4).
RSI_LENGTH = 14
VOLATILITY_WINDOW = 20
# Escala do RSI.
_RSI_SCALE = 100.0


def _as_float(x: Number) -> float | None:
    """`None`/`NaN` → `None`; senão `float(x)`."""
    if x is None:
        return None
    value = float(x)
    return None if math.isnan(value) else value


def _ewm_recursion(
    values: Sequence[float | None], alpha: float, seed_position: int, seed: float
) -> OutSeq:
    """`ewm(alpha, adjust=False)` a partir de `seed` em `seed_position`; `None` antes.

    Passo: `y_t = ((1-a)*y_{t-1} + a*x_t) / ((1-a)+a)` — o quociente é o que o pandas
    calcula em `adjust=False` (`old_wt + new_wt` no denominador), mantido de
    propósito para a paridade bit a bit. `None` interior (fora do contrato do port —
    a entity `Candle` garante `close` finito) sai como `None` sem alterar o estado.
    """
    out: list[float | None] = [None] * len(values)
    previous = seed
    out[seed_position] = previous
    old_weight = 1.0 - alpha
    for t in range(seed_position + 1, len(values)):
        current = values[t]
        if current is None:
            continue
        previous = (old_weight * previous + alpha * current) / (old_weight + alpha)
        out[t] = previous
    return tuple(out)


def _mean_of_valid(block: Sequence[float | None]) -> float | None:
    """Média simples dos valores não-`None` de `block` (paridade `Series.mean()` com NaN)."""
    valid = [value for value in block if value is not None]
    return None if not valid else sum(valid) / len(valid)


def ema(close: Sequence[Number], length: int) -> OutSeq:
    """EMA recursiva, `alpha = 2/(length+1)`, semente SMA em `first_valid + length - 1`.

    Paridade `ta.ema`: a semente é a média dos `length` valores a partir do PRIMEIRO
    válido (`first_valid_index`), colocada em `first_valid + length - 1`; antes dela a
    saída é `None`.
    """
    if length <= 0:
        raise ValueError(f"ema requires length > 0, got {length!r}")
    values = [_as_float(x) for x in close]
    n = len(values)
    first = next((index for index, value in enumerate(values) if value is not None), None)
    if first is None or first + length > n:
        return (None,) * n
    # A janela começa no 1º válido, então tem >= 1 valor: a média sempre existe.
    window = [value for value in values[first : first + length] if value is not None]
    return _ewm_recursion(
        values, 2.0 / (length + 1.0), first + length - 1, sum(window) / len(window)
    )


def rma(seq: Sequence[Number], length: int) -> OutSeq:
    """Média móvel de Wilder (`alpha = 1/length`), semente em `length - 1`.

    Paridade `ta.rma`: a semente é a média dos valores VÁLIDOS entre os `length`
    primeiros (posições `0..length-1`, ignorando `None` — o `diff` do RSI deixa `None`
    na posição 0), colocada FIXAMENTE em `length - 1` (não usa `first_valid_index`,
    ao contrário de `ta.ema`).
    """
    if length <= 0:
        raise ValueError(f"rma requires length > 0, got {length!r}")
    values = [_as_float(x) for x in seq]
    n = len(values)
    if n < length:
        return (None,) * n
    seed = _mean_of_valid(values[:length])
    if seed is None:
        return (None,) * n
    return _ewm_recursion(values, 1.0 / length, length - 1, seed)


def rsi(close: Sequence[Number], length: int = RSI_LENGTH) -> OutSeq:
    """RSI de Wilder: `100 * rma(ganhos) / (rma(ganhos) + |rma(perdas)|)` (C6 — não SMA)."""
    values = [_as_float(x) for x in close]
    gains: list[float | None] = [None]
    losses: list[float | None] = [None]
    for t in range(1, len(values)):
        current, previous = values[t], values[t - 1]
        if current is None or previous is None:
            gains.append(None)
            losses.append(None)
            continue
        delta = current - previous
        gains.append(delta if delta > 0 else 0.0)
        losses.append(delta if delta < 0 else 0.0)
    gain_avg = rma(gains, length)
    loss_avg = rma(losses, length)
    out: list[float | None] = []
    for up, down in zip(gain_avg, loss_avg, strict=True):
        if up is None or down is None:
            out.append(None)
        else:
            denominator = up + abs(down)
            out.append(None if denominator == 0.0 else _RSI_SCALE * up / denominator)
    return tuple(out)


def macd(
    close: Sequence[Number],
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> tuple[OutSeq, OutSeq]:
    """`(macd, macd_signal)` = `(ema_fast - ema_slow, ema_signal(macd))`, defaults 12/26/9."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    line: list[float | None] = [
        None if (a is None or b is None) else a - b for a, b in zip(fast_ema, slow_ema, strict=True)
    ]
    return tuple(line), ema(line, signal)


def volatility_20d(close: Sequence[Number], window: int = VOLATILITY_WINDOW) -> OutSeq:
    """`std(ddof=1)` rolling(`window`) de `pct_change(1)`; `None` nas `window` primeiras."""
    values = [_as_float(x) for x in close]
    n = len(values)
    returns: list[float | None] = [None]
    for t in range(1, n):
        current, previous = values[t], values[t - 1]
        if current is None or previous is None or previous == 0.0:
            returns.append(None)
        else:
            returns.append((current - previous) / previous)
    out: list[float | None] = [None] * n
    for t in range(window, n):
        block = returns[t - window + 1 : t + 1]
        if any(value is None for value in block):
            continue
        sample = [value for value in block if value is not None]
        mean = sum(sample) / window
        variance = sum((value - mean) ** 2 for value in sample) / (window - 1)
        out[t] = math.sqrt(variance)
    return tuple(out)
