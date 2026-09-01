"""`DerivedFeatures` — as ~38 derivadas em Python puro (domain service, oráculo causal).

Computa as derivadas do old (`build_tft_dataset_use_case.py:146-285`) em Python puro
(`math` stdlib, sobre sequências/tuplas) — sem pandas/numpy. É o **oráculo causal**
independente que a 3.5 (pandas) valida (ADR 3.4.0001 / 0.0.0021): duas implementações
independentes da mesma fórmula, conferidas por teste de paridade.

Cada função recebe sequências alinhadas no tempo (uma barra por timestamp, já
forward-filled pela 3.5 quando for o caso) e devolve uma `tuple` alinhada 1:1 com a
entrada, com `None` nas posições de warmup (paridade `rolling(min_periods=n)` /
`NaN` do pandas).

Convenção de tradução pandas → puro (concept 3.4 §4/§5):

- `rolling(window=n, min_periods=n)` → `None` nas `n-1` primeiras posições;
- `std(ddof=0)` → variância populacional (divide por `n`);
- `ewm(span=s, adjust=False)` → recursão `alpha = 2/(s+1)`;
- `pct_change(n, fill_method=None)` → `(x_t - x_{t-n})/x_{t-n}`, `None` se faltante;
- `shift(n)` com `n>0` sempre (nunca negativo — I6);
- `clip(lower=0)` antes de `sqrt` (C8);
- `_safe_ratio` → `None` se denominador é `None`/`0`/`NaN` (C6).

Este módulo (Task 04) traz os helpers + o grupo de preço/retorno/liquidez. Os grupos
de volatilidade/regimes (Task 05) e sentimento/fundamento/YoY (Task 06) acumulam aqui.
O grupo de candle (issue #67) acumulou por último e é o único cujo CONSUMIDOR é o
adapter `pandas_ta` em vez do `DatasetAssembler` — ver o cabeçalho do Grupo 4.

Pureza (I1): importa SÓ stdlib (`collections.abc`/`math`). `import pandas`/`numpy`
aqui REPROVA `domain-purity` no import-linter.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Tipo de uma sequência de entrada (valores observados ou `None`/`NaN` faltantes).
Number = float | int | None
# Tipo de uma sequência de saída (valor computado ou `None` no warmup/erro).
OutSeq = tuple[float | None, ...]

# Limiar de z-score acima do qual o volume é considerado "spike" (verbatim old).
_VOLUME_SPIKE_THRESHOLD = 3.0


# =============================================================================
# Helpers internos puros (tradução pandas → Python puro)
# =============================================================================


def _is_missing(x: Number) -> bool:
    """`True` se `x` é `None` ou `NaN` (faltante — paridade `pd.isna` para escalar)."""
    return x is None or (isinstance(x, float) and math.isnan(x))


def _as_float(x: Number) -> float | None:
    """Converte para `float`, devolvendo `None` se faltante (paridade `to_numeric`)."""
    if _is_missing(x):
        return None
    return float(x)  # type: ignore[arg-type]


def _safe_ratio(num: Number, den: Number) -> float | None:
    """Divisão protegida: `None` se `num`/`den` faltante ou `den == 0` (C6).

    Paridade com `_safe_ratio` do old (`build_tft_dataset_use_case.py:265-271`):
    nunca propaga `inf`/`NaN`; denominador `None`/`0`/`NaN` → `None`.
    """
    n = _as_float(num)
    d = _as_float(den)
    if n is None or d is None or d == 0.0:
        return None
    return n / d


def _shift(seq: Sequence[Number], n: int) -> OutSeq:
    """`seq.shift(n)` com `n>0`: `None` nas `n` primeiras posições, depois `seq[t-n]`.

    `n` deve ser positivo (I6: nunca shift negativo — olhar o futuro vazaria).
    """
    if n <= 0:
        raise ValueError(f"_shift requires n > 0 (causal), got {n!r}")
    out: list[float | None] = []
    for t in range(len(seq)):
        out.append(None if t < n else _as_float(seq[t - n]))
    return tuple(out)


def _pct_change(seq: Sequence[Number], n: int) -> OutSeq:
    """`seq.pct_change(n, fill_method=None)`: `(x_t - x_{t-n}) / x_{t-n}`.

    `None` nas `n` primeiras posições e onde `x_t`/`x_{t-n}` for faltante ou
    `x_{t-n} == 0` (C6).
    """
    if n <= 0:
        raise ValueError(f"_pct_change requires n > 0, got {n!r}")
    out: list[float | None] = []
    for t in range(len(seq)):
        if t < n:
            out.append(None)
            continue
        cur = _as_float(seq[t])
        prev = _as_float(seq[t - n])
        if cur is None or prev is None or prev == 0.0:
            out.append(None)
        else:
            out.append((cur - prev) / prev)
    return tuple(out)


def _mean(window: Sequence[float]) -> float:
    """Média aritmética de uma janela não-vazia (já sem faltantes)."""
    return math.fsum(window) / len(window)


def _std_pop(window: Sequence[float]) -> float:
    """Desvio-padrão POPULACIONAL (ddof=0) de uma janela não-vazia.

    Divide por `n` (não `n-1`) — paridade `pandas.std(ddof=0)`.
    """
    mu = _mean(window)
    var = math.fsum((x - mu) ** 2 for x in window) / len(window)
    return math.sqrt(max(var, 0.0))


def _rolling_window(seq: Sequence[Number], t: int, n: int) -> list[float] | None:
    """Janela trailing `seq[t-n+1 .. t]` como floats, ou `None` se inválida.

    `None` quando há menos de `n` observações (warmup, paridade `min_periods=n`) ou
    qualquer valor da janela é faltante (paridade: `NaN` na janela → `NaN` no agregado).
    """
    if t + 1 < n:
        return None
    window: list[float] = []
    for i in range(t - n + 1, t + 1):
        v = _as_float(seq[i])
        if v is None:
            return None
        window.append(v)
    return window


def _rolling_mean(seq: Sequence[Number], n: int) -> OutSeq:
    """`seq.rolling(n, min_periods=n).mean()` → `None` nas `n-1` primeiras (C7)."""
    return tuple(
        None if (w := _rolling_window(seq, t, n)) is None else _mean(w) for t in range(len(seq))
    )


def _rolling_std_pop(seq: Sequence[Number], n: int) -> OutSeq:
    """`seq.rolling(n, min_periods=n).std(ddof=0)` → `None` nas `n-1` primeiras."""
    return tuple(
        None if (w := _rolling_window(seq, t, n)) is None else _std_pop(w) for t in range(len(seq))
    )


def _rolling_max(seq: Sequence[Number], n: int) -> OutSeq:
    """`seq.rolling(n, min_periods=n).max()` → `None` nas `n-1` primeiras."""
    return tuple(
        None if (w := _rolling_window(seq, t, n)) is None else max(w) for t in range(len(seq))
    )


def _quantile_linear(window: Sequence[float], q: float) -> float:
    """Quantil `q` com interpolação LINEAR (default do pandas/numpy).

    Ordena a janela, calcula a posição `h = q*(n-1)` e interpola linearmente entre
    os vizinhos `floor(h)` e `ceil(h)` — paridade `pandas.rolling(...).quantile(q)`
    (interpolation="linear"). Janela não-vazia.
    """
    ordered = sorted(window)
    if len(ordered) == 1:
        return ordered[0]
    h = q * (len(ordered) - 1)
    lo = math.floor(h)
    hi = math.ceil(h)
    if lo == hi:
        return ordered[lo]
    frac = h - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _rolling_quantile(seq: Sequence[Number], n: int, q: float) -> OutSeq:
    """`seq.rolling(n, min_periods=n).quantile(q)` (linear) → `None` no warmup."""
    return tuple(
        None if (w := _rolling_window(seq, t, n)) is None else _quantile_linear(w, q)
        for t in range(len(seq))
    )


# =============================================================================
# Grupo 1 — preço / retorno / liquidez (Task 04)
# =============================================================================


def log_return(close: Sequence[Number], n: int) -> OutSeq:
    """`log(close_t / close_t-n)` → `None` nas `n` primeiras / faltantes / `<=0` (I6)."""
    if n <= 0:
        raise ValueError(f"log_return requires n > 0, got {n!r}")
    out: list[float | None] = []
    for t in range(len(close)):
        if t < n:
            out.append(None)
            continue
        cur = _as_float(close[t])
        prev = _as_float(close[t - n])
        if cur is None or prev is None or cur <= 0.0 or prev <= 0.0:
            out.append(None)
        else:
            out.append(math.log(cur / prev))
    return tuple(out)


def log_return_1d(close: Sequence[Number]) -> OutSeq:
    """`log(close_t / close_t-1)` (warmup 1)."""
    return log_return(close, 1)


def log_return_5d(close: Sequence[Number]) -> OutSeq:
    """`log(close_t / close_t-5)` (warmup 5)."""
    return log_return(close, 5)


def log_return_21d(close: Sequence[Number]) -> OutSeq:
    """`log(close_t / close_t-21)` (warmup 21)."""
    return log_return(close, 21)


def momentum(close: Sequence[Number], n: int) -> OutSeq:
    """`close_t / close_t-n - 1` = `pct_change(n)` (warmup `n`)."""
    return _pct_change(close, n)


def momentum_5d(close: Sequence[Number]) -> OutSeq:
    """`close_t / close_t-5 - 1` (warmup 5)."""
    return momentum(close, 5)


def momentum_21d(close: Sequence[Number]) -> OutSeq:
    """`close_t / close_t-21 - 1` (warmup 21)."""
    return momentum(close, 21)


def momentum_63d(close: Sequence[Number]) -> OutSeq:
    """`close_t / close_t-63 - 1` (warmup 63)."""
    return momentum(close, 63)


def _negate(seq: OutSeq) -> OutSeq:
    """Nega elemento a elemento, preservando `None`."""
    return tuple(None if v is None else -v for v in seq)


def reversal_1d(close: Sequence[Number]) -> OutSeq:
    """`-1 * pct_change_1(close)` (warmup 1)."""
    return _negate(_pct_change(close, 1))


def reversal_5d(close: Sequence[Number]) -> OutSeq:
    """`-1 * momentum_5d(close)` (warmup 5)."""
    return _negate(momentum_5d(close))


def drawdown_lookback(close: Sequence[Number]) -> OutSeq:
    """`close_t / rolling_max(close, 63)_t - 1` (warmup 63).

    `None` no warmup, onde `close_t` é faltante, ou onde o `rolling_max` é `0`.
    """
    rmax = _rolling_max(close, 63)
    out: list[float | None] = []
    for t in range(len(close)):
        cur = _as_float(close[t])
        mx = rmax[t]
        if cur is None or mx is None or mx == 0.0:
            out.append(None)
        else:
            out.append(cur / mx - 1.0)
    return tuple(out)


def amihud_illiquidity_proxy(close: Sequence[Number], volume: Sequence[Number]) -> OutSeq:
    """`abs(pct_change_1(close)) / volume_t` (warmup 1).

    `None` no warmup, onde `pct_change` é faltante, ou onde `volume_t <= 0`
    (paridade `np.where(volume > 0, ..., NaN)` do old).
    """
    if len(close) != len(volume):
        raise ValueError("amihud_illiquidity_proxy: close and volume length mismatch")
    pct = _pct_change(close, 1)
    out: list[float | None] = []
    for t in range(len(close)):
        ret = pct[t]
        vol = _as_float(volume[t])
        if ret is None or vol is None or vol <= 0.0:
            out.append(None)
        else:
            out.append(abs(ret) / vol)
    return tuple(out)


def volume_zscore(volume: Sequence[Number]) -> OutSeq:
    """`(volume_t - mean(volume_t-20..t-1)) / std_pop(volume_t-20..t-1)`.

    Causalidade (I6): a estatística trailing usa `volume.shift(1)` numa janela de 20
    (`volume_t-20..t-1`); o numerador é o `volume_t` corrente. Warmup efetivo = 20
    (estatística) + corrente. `None` no warmup ou onde `std == 0` (C6).
    """
    shifted = _shift(volume, 1)
    trailing_mean = _rolling_mean(shifted, 20)
    trailing_std = _rolling_std_pop(shifted, 20)
    out: list[float | None] = []
    for t in range(len(volume)):
        cur = _as_float(volume[t])
        mu = trailing_mean[t]
        sd = trailing_std[t]
        if cur is None or mu is None or sd is None or sd <= 0.0:
            out.append(None)
        else:
            out.append((cur - mu) / sd)
    return tuple(out)


def volume_spike_flag(volume: Sequence[Number]) -> tuple[int, ...]:
    """`1 if volume_zscore_t > 3 else 0`.

    Paridade com o old (`(zscore > 3.0).astype(int64)`): no pandas `NaN > 3.0` é
    `False`, então posições de warmup/`None` viram `0` (não `None`). Saída sempre
    em `{0, 1}` (I6).
    """
    z = volume_zscore(volume)
    return tuple(1 if (v is not None and v > _VOLUME_SPIKE_THRESHOLD) else 0 for v in z)


# =============================================================================
# Grupo 2 — volatilidades + regimes (Task 05)
# =============================================================================

_LN2 = math.log(2.0)
_GK_COEF = 2.0 * _LN2 - 1.0  # coeficiente de Garman-Klass (verbatim old)
_TREND_DEADBAND_FACTOR = 0.10  # deadband do trend_regime (verbatim old)
_TAIL_Q = 0.10  # quantil de cauda do stress flag (verbatim old)
_REGIME_Q33 = 1.0 / 3.0
_REGIME_Q66 = 2.0 / 3.0
_VOL_WINDOW = 20
_REGIME_WINDOW = 63


def _log_ratio_seq(num: Sequence[Number], den: Sequence[Number]) -> OutSeq:
    """`ln(num_t / den_t)` por posição; `None` se faltante ou qualquer termo `<= 0`.

    Paridade com `np.where((num>0)&(den>0), np.log(num/den), np.nan)` do old.
    """
    if len(num) != len(den):
        raise ValueError("_log_ratio_seq: length mismatch")
    out: list[float | None] = []
    for a, b in zip(num, den, strict=True):
        x = _as_float(a)
        y = _as_float(b)
        if x is None or y is None or x <= 0.0 or y <= 0.0:
            out.append(None)
        else:
            out.append(math.log(x / y))
    return tuple(out)


def _sqrt_clip(value: float | None) -> float | None:
    """`sqrt(max(value, 0))` (C8 — clip antes da raiz); `None` propaga `None`."""
    if value is None:
        return None
    return math.sqrt(max(value, 0.0))


def volatility_parkinson(high: Sequence[Number], low: Sequence[Number]) -> OutSeq:
    """`sqrt(rolling_mean(ln(h/l)^2, 20) / (4*ln2))` (warmup 20, C8)."""
    log_hl = _log_ratio_seq(high, low)
    sq = tuple(None if v is None else v * v for v in log_hl)
    park_var = _rolling_mean(sq, _VOL_WINDOW)
    return tuple(None if v is None else _sqrt_clip(v / (4.0 * _LN2)) for v in park_var)


def volatility_garman_klass(
    open_: Sequence[Number],
    high: Sequence[Number],
    low: Sequence[Number],
    close: Sequence[Number],
) -> OutSeq:
    """`sqrt(rolling_mean(0.5*ln(h/l)^2 - (2ln2-1)*ln(c/o)^2, 20))` (warmup 20, C8)."""
    log_hl = _log_ratio_seq(high, low)
    log_co = _log_ratio_seq(close, open_)
    term: list[float | None] = []
    for hl, co in zip(log_hl, log_co, strict=True):
        if hl is None or co is None:
            term.append(None)
        else:
            term.append(0.5 * hl * hl - _GK_COEF * co * co)
    gk_var = _rolling_mean(term, _VOL_WINDOW)
    return tuple(_sqrt_clip(v) for v in gk_var)


def downside_semivolatility(close: Sequence[Number]) -> OutSeq:
    """`sqrt(rolling_mean(min(pct_change_1, 0)^2, 20))` (warmup 20, C8)."""
    pct = _pct_change(close, 1)
    downside_sq = tuple(None if v is None else min(v, 0.0) ** 2 for v in pct)
    var = _rolling_mean(downside_sq, _VOL_WINDOW)
    return tuple(_sqrt_clip(v) for v in var)


def vol_of_vol(volatility_20d: Sequence[Number]) -> OutSeq:
    """`rolling_std_pop(volatility_20d, 20)` (warmup nominal 20; efetivo 40 — I7).

    `volatility_20d` chega como sequência de entrada (computada pela 3.1 na 3.5); as
    suas próprias 20 posições de warmup somam às 20 da janela `std` → warmup efetivo
    40 quando a entrada vem crua do preço.
    """
    return _rolling_std_pop(volatility_20d, _VOL_WINDOW)


def volatility_regime(volatility_20d: Sequence[Number]) -> tuple[int | None, ...]:
    """Regime 0/1/2 dos tercis trailing SHIFTADOS de `volatility_20d` (janela 63).

    Causalidade (I6): os tercis (`q33`/`q66`) usam `volatility_20d.shift(1).rolling(63)`;
    o valor corrente `vol_t` é comparado ao threshold de `t-1..t-63`. `None` quando
    `vol_t` é faltante ou os quantis estão em warmup (C7). Saída em `{0, 1, 2}` ou `None`.
    """
    shifted = _shift(volatility_20d, 1)
    q33 = _rolling_quantile(shifted, _REGIME_WINDOW, _REGIME_Q33)
    q66 = _rolling_quantile(shifted, _REGIME_WINDOW, _REGIME_Q66)
    out: list[int | None] = []
    for t in range(len(volatility_20d)):
        v = _as_float(volatility_20d[t])
        lo = q33[t]
        hi = q66[t]
        if v is None or lo is None or hi is None:
            out.append(None)
        elif v <= lo:
            out.append(0)
        elif v <= hi:
            out.append(1)
        else:
            out.append(2)
    return tuple(out)


def trend_regime(ema_10: Sequence[Number], ema_50: Sequence[Number]) -> tuple[int | None, ...]:
    """Regime -1/0/1 do spread `ema_10 - ema_50` com deadband trailing (janela 63).

    Causalidade (I6): `deadband = 0.10 * std_pop(spread.shift(1), 63)`; o spread
    corrente é comparado ao deadband de `t-1..t-63`. `None` quando o spread corrente
    é faltante ou o deadband está em warmup. Saída em `{-1, 0, 1}` ou `None`.
    """
    if len(ema_10) != len(ema_50):
        raise ValueError("trend_regime: ema_10 and ema_50 length mismatch")
    spread: list[float | None] = []
    for a, b in zip(ema_10, ema_50, strict=True):
        x = _as_float(a)
        y = _as_float(b)
        spread.append(None if x is None or y is None else x - y)
    deadband_std = _rolling_std_pop(_shift(spread, 1), _REGIME_WINDOW)
    out: list[int | None] = []
    for t in range(len(spread)):
        s = spread[t]
        sd = deadband_std[t]
        if s is None or sd is None:
            out.append(None)
            continue
        deadband = sd * _TREND_DEADBAND_FACTOR
        if s > deadband:
            out.append(1)
        elif s < -deadband:
            out.append(-1)
        else:
            out.append(0)
    return tuple(out)


def stress_tail_return_flag(close: Sequence[Number]) -> tuple[int | None, ...]:
    """Flag 1 quando `pct_change_1 <= trailing q10 SHIFTADO (janela 63)`.

    Causalidade (I6): `tail_q10 = pct_change_1.shift(1).rolling(63).quantile(0.10)`;
    o retorno corrente é comparado ao limiar de `t-1..t-63`. `None` quando o retorno
    corrente é faltante ou o quantil está em warmup. Saída em `{0, 1}` ou `None`.
    """
    ret1 = _pct_change(close, 1)
    tail_q10 = _rolling_quantile(_shift(ret1, 1), _REGIME_WINDOW, _TAIL_Q)
    out: list[int | None] = []
    for t in range(len(close)):
        r = ret1[t]
        thr = tail_q10[t]
        if r is None or thr is None:
            out.append(None)
        else:
            out.append(1 if r <= thr else 0)
    return tuple(out)


# =============================================================================
# Grupo 3 — sentimento dinâmico + fundamento derivado + YoY (Task 06)
# =============================================================================

_SENTIMENT_EMA_SPAN = 10
_SENTIMENT_SURPRISE_WINDOW = 5
_YOY_WINDOW = 252


def _ewm(seq: Sequence[Number], span: int) -> OutSeq:
    """`seq.ewm(span=span, adjust=False).mean()` recursivo — `alpha = 2/(span+1)`.

    Paridade `ewm(adjust=False)`: `y_0 = x_0`; `y_t = alpha*x_t + (1-alpha)*y_{t-1}`.
    Propaga `None` antes do PRIMEIRO valor não-faltante (paridade do pandas com NaN
    inicial); a partir daí a recursão segue ignorando faltantes intermediários
    (mantém o último `y` — não há valor novo para misturar).
    """
    if span <= 0:
        raise ValueError(f"_ewm requires span > 0, got {span!r}")
    alpha = 2.0 / (span + 1.0)
    out: list[float | None] = []
    prev: float | None = None
    for x in seq:
        v = _as_float(x)
        if prev is None:
            # antes do 1º valor válido → None; no 1º valor válido → seed y_0 = x_0.
            prev = v
            out.append(v)
        elif v is None:
            out.append(prev)
        else:
            prev = alpha * v + (1.0 - alpha) * prev
            out.append(prev)
    return tuple(out)


def sentiment_lag(sentiment: Sequence[Number], n: int) -> OutSeq:
    """`sentiment_score.shift(n)` (puro shift causal — tag `lagged_causal`)."""
    return _shift(sentiment, n)


def sentiment_lag_1(sentiment: Sequence[Number]) -> OutSeq:
    """`sentiment_score` deslocado 1 (warmup 1)."""
    return _shift(sentiment, 1)


def sentiment_lag_3(sentiment: Sequence[Number]) -> OutSeq:
    """`sentiment_score` deslocado 3 (warmup 3)."""
    return _shift(sentiment, 3)


def sentiment_lag_5(sentiment: Sequence[Number]) -> OutSeq:
    """`sentiment_score` deslocado 5 (warmup 5)."""
    return _shift(sentiment, 5)


def sentiment_ema(sentiment: Sequence[Number]) -> OutSeq:
    """`ewm(span=10, adjust=False)` sobre `sentiment_score` (warmup 1, verbatim old)."""
    return _ewm(sentiment, _SENTIMENT_EMA_SPAN)


def sentiment_surprise(sentiment: Sequence[Number]) -> OutSeq:
    """`sentiment_t - rolling_mean(sentiment.shift(1), 5)` (warmup 5).

    A baseline usa `sentiment.shift(1)` numa janela de 5 (`t-5..t-1`); o termo
    corrente é `sentiment_t`. `None` no warmup ou onde algum termo é faltante.
    """
    baseline = _rolling_mean(_shift(sentiment, 1), _SENTIMENT_SURPRISE_WINDOW)
    out: list[float | None] = []
    for t in range(len(sentiment)):
        cur = _as_float(sentiment[t])
        base = baseline[t]
        out.append(None if cur is None or base is None else cur - base)
    return tuple(out)


def _elementwise_product(a: Sequence[Number], b: Sequence[Number]) -> OutSeq:
    """Produto elemento a elemento; `None` onde qualquer fator é faltante."""
    if len(a) != len(b):
        raise ValueError("_elementwise_product: length mismatch")
    out: list[float | None] = []
    for x, y in zip(a, b, strict=True):
        fx = _as_float(x)
        fy = _as_float(y)
        out.append(None if fx is None or fy is None else fx * fy)
    return tuple(out)


def sentiment_x_volatility(sentiment: Sequence[Number], volatility_20d: Sequence[Number]) -> OutSeq:
    """`sentiment_score * volatility_20d` (warmup herdado de `volatility_20d`)."""
    return _elementwise_product(sentiment, volatility_20d)


def sentiment_x_volume(sentiment: Sequence[Number], volume: Sequence[Number]) -> OutSeq:
    """`sentiment_score * volume` (sem warmup)."""
    return _elementwise_product(sentiment, volume)


def _ratio_seq(num: Sequence[Number], den: Sequence[Number]) -> OutSeq:
    """`_safe_ratio` por posição (denom `None`/`0`/`NaN` → `None`, C6)."""
    if len(num) != len(den):
        raise ValueError("_ratio_seq: length mismatch")
    return tuple(_safe_ratio(a, b) for a, b in zip(num, den, strict=True))


def net_margin(net_income: Sequence[Number], revenue: Sequence[Number]) -> OutSeq:
    """`net_income / revenue` (protegido, C6)."""
    return _ratio_seq(net_income, revenue)


def leverage_ratio(
    total_liabilities: Sequence[Number],
    total_shareholder_equity: Sequence[Number],
) -> OutSeq:
    """`total_liabilities / total_shareholder_equity` (protegido, C6)."""
    return _ratio_seq(total_liabilities, total_shareholder_equity)


def cashflow_efficiency(operating_cash_flow: Sequence[Number], revenue: Sequence[Number]) -> OutSeq:
    """`operating_cash_flow / revenue` (protegido, C6)."""
    return _ratio_seq(operating_cash_flow, revenue)


def revenue_yoy_growth(revenue: Sequence[Number]) -> OutSeq:
    """`pct_change(revenue, 252, fill_method=None)` (YoY; warmup 252 — ADR 3.3.0002)."""
    return _pct_change(revenue, _YOY_WINDOW)


def net_income_yoy_growth(net_income: Sequence[Number]) -> OutSeq:
    """`pct_change(net_income, 252, fill_method=None)` (YoY; warmup 252)."""
    return _pct_change(net_income, _YOY_WINDOW)


# =============================================================================
# Grupo 4 — OHLC do mesmo timestamp / candle (issue #67)
# =============================================================================
#
# Estas duas fórmulas moravam inline no adapter `pandas_ta`
# (`out["candle_range"] = frame["high"] - frame["low"]`) — aritmética de domínio
# escrita em infraestrutura, sem uma única chamada de biblioteca com conteúdo.
# A issue #67 as traz para cá; o adapter passa a CHAMAR estas funções.
#
# Repartição (Humble Object): o DOMÍNIO é dono da FÓRMULA — a parte testável e
# portável; o ADAPTER é dono da FRONTEIRA DE DTYPE — o `astype("float32")` que o
# invariante I4 de `IndicatorSpec` exige do port `IndicatorCalculator`, parte
# não-portável. Cada lado fica com o que lhe cabe.
#
# Diferença em relação aos Grupos 1-3: estas NÃO entram no laço de re-derivação
# do `_validate_anti_leakage` (`DatasetAssembler`). O validador compara com
# tolerância `1e-9`, e o valor que o dataset carrega vem do port já coagido a
# `float32` — a quantização diverge do `float64` puro em até ~5e-8, acima da
# tolerância. Cobri-las pelo validador exige adotar o `float64`, o que MUDA o
# dataset; isso migrou para a issue #65, que carrega o bump de `pipeline_version`
# e a regeneração de artefato.
#
# Causalidade: tag `same_timestamp_ohlc_derived` — dependem SÓ da barra `t`
# (nenhuma janela, nenhum shift), logo warmup 0 e causalidade trivial (I6).


def candle_range(high: Sequence[Number], low: Sequence[Number]) -> OutSeq:
    """`high_t - low_t` — amplitude da barra (warmup 0, `same_timestamp_ohlc_derived`).

    `None` onde `high_t` ou `low_t` é faltante (paridade com o `NaN` que a subtração
    de `Series` propaga no pandas).
    """
    if len(high) != len(low):
        raise ValueError("candle_range: high and low length mismatch")
    out: list[float | None] = []
    for high_value, low_value in zip(high, low, strict=True):
        top = _as_float(high_value)
        bottom = _as_float(low_value)
        out.append(None if top is None or bottom is None else top - bottom)
    return tuple(out)


def candle_body(open_: Sequence[Number], close: Sequence[Number]) -> OutSeq:
    """`abs(close_t - open_t)` — corpo da barra (warmup 0, `same_timestamp_ohlc_derived`).

    `None` onde `open_t` ou `close_t` é faltante (paridade com o `NaN` que a subtração
    de `Series` propaga no pandas).
    """
    if len(open_) != len(close):
        raise ValueError("candle_body: open_ and close length mismatch")
    out: list[float | None] = []
    for open_value, close_value in zip(open_, close, strict=True):
        opening = _as_float(open_value)
        closing = _as_float(close_value)
        out.append(None if opening is None or closing is None else abs(closing - opening))
    return tuple(out)
