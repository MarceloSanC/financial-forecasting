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
