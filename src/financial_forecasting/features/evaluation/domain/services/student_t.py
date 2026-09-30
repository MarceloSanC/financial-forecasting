"""CDF da t de Student em stdlib — o p-valor do teste de Diebold-Mariano (doc §6.3).

Função pura `student_t_cdf(x, df)` = P(T_df ≤ x), cauda inferior (concept 6.2 §4, I4,
C5; ADR `6_2_0002`). Segue os **mesmos ramos** do oráculo, R `src/nmath/pt.c`:

- x = 0 → ½;
- `nx = 1 + (x/df)·x > 1e100` → termo assintótico de A&S 26.5.4 em log
  (I_z(a, b) ≈ z^a / (a·B(a, b)), z = 1/nx, a = df/2, b = ½) — o ramo do `pt.c` que
  evita o estouro de `x*x`; o erro relativo desprezado é O(1/nx) < 1e-100;
- `df > x²` → P(|T| > |x|) = 1 - I_{x²/(df+x²)}(½, df/2);
- senão → P(|T| > |x|) = I_{df/(df+x²)}(df/2, ½);
- cauda inferior = ½·P; x > 0 → 1 - ½·P.

Os dois ramos centrais são a mesma quantidade pela simetria DLMF 8.17.4. O argumento e
o seu complemento são calculados **direto** (`x²/(df+x²)` e `df/(df+x²)`), nunca como
`1 - n/(n+x²)` (que cancela em |x| pequeno), e o par (I, 1 - I) sai de
`_regularized_beta_pair` com o termo da fração contínua calculado direto do lado que a
simetria 8.17.4 escolhe — a cauda nunca é `½·(1 - I)` por subtração de dois números
próximos de 1 (armadilha medida no technical 6.2 §1: df = 999, x = -10 daria 0 em vez
de 8,35e-23). O ramo de aproximação normal do `pt.c` (df > 4e5) não é reproduzido: o DM
usa df = T - 1 ≤ alguns milhares.

Domínio validado (medição A14 contra `mpmath`, technical 6.2 §7): **df ≤ ~1e4** — erro
absoluto ≤ 1,5e-14 e relativo na cauda ≤ 6,4e-13. Acima disso a precisão degrada
devagar (df 1e5: rel 6e-12; df 1e7: rel 5e-10, abs 1e-11) — fora do uso do DM.

Função especial: I_z(a, b) pela fração contínua DLMF 8.17.22 (coeficientes 8.17.23),
avaliada pelo método de Lentz modificado, com prefator z^a(1 - z)^b/(a·B(a, b)) em log;
log B(a, b) pelo `lbeta.c` do R (correção de Stirling no argumento grande — sem ela a
subtração `lgamma(df/2) - lgamma(df/2 + ½)` limitava o erro absoluto a ~4e-13 em
df ~ 2000; medição A14 no technical 6.2 §7). Não convergir em `_MAX_ITERATIONS` ergue
`ArithmeticError` — nunca devolve valor parcial.

Referências: NIST DLMF §8.17 (8.17.4, 8.17.22, 8.17.23); R `src/nmath/pt.c`,
`src/nmath/lbeta.c` e `src/nmath/lgammacor.c`; Abramowitz & Stegun 26.5.4.
"""

from __future__ import annotations

import math
import sys

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)

# Teto de iterações do Lentz: ~12x o máximo medido (86 iterações, df ≤ 2500, no pior
# ponto — x logo abaixo do limiar da simetria 8.17.4, z = 3/(df + 5); technical 6.2 §7).
# Constante de módulo para que o teste de C5 force a não-convergência por `monkeypatch`.
_MAX_ITERATIONS = 1000

# Critério de parada do Lentz: |Δ_m - 1| ≤ ε da máquina (float64).
_EPSILON = sys.float_info.epsilon

# Piso anti-divisão-por-zero do Lentz modificado (menor normal / ε).
_TINY = sys.float_info.min / sys.float_info.epsilon

# Limiar do ramo assintótico do `pt.c` (`nx > 1e100`).
_ASYMPTOTIC_NX = 1e100

# `_log_beta`: a partir daqui o argumento grande usa a correção de Stirling (R
# `lbeta.c`/`lgammacor.c`); coeficientes B_{2k}/(2k(2k - 1)), k = 1..8.
_STIRLING_MIN = 10.0
_STIRLING_COEFFICIENTS = (
    1.0 / 12.0,
    -1.0 / 360.0,
    1.0 / 1260.0,
    -1.0 / 1680.0,
    1.0 / 1188.0,
    -691.0 / 360360.0,
    1.0 / 156.0,
    -3617.0 / 122400.0,
)

_MIN_DF = 1.0
_HALF = 0.5


def student_t_cdf(x: float, df: float) -> float:
    """P(T_df ≤ x) para a t de Student com `df` graus de liberdade.

    Args:
        x: ponto de avaliação, finito.
        df: graus de liberdade, finito e ≥ 1 (não precisa ser inteiro).

    Returns:
        A CDF (cauda inferior) em [0, 1].

    Raises:
        ValueError: `x` ou `df` não-finito, não-número ou `bool`; `df < 1` (C5).
        ArithmeticError: a fração contínua não convergiu em `_MAX_ITERATIONS` (C5).
    """
    if not is_finite_number(x):
        raise ValueError(f"x must be a finite number, got {x!r}")
    if not is_finite_number(df) or df < _MIN_DF:
        raise ValueError(f"df must be a finite number >= {_MIN_DF}, got {df!r}")
    if x == 0.0:
        return _HALF
    tail = _two_sided_tail(float(x), float(df))
    lower = _HALF * tail
    return lower if x < 0.0 else 1.0 - lower


# Quantil por bisseção sobre a CDF (Stage 6.5, technical §1 "Quantil da t"): intervalo,
# tolerância relativa no x e teto de iterações (2e6 / 2^61 < 1e-12 — 61 bastam).
_QUANTILE_BOUND = 1e6
_QUANTILE_RTOL = 1e-12
_QUANTILE_MAX_ITERATIONS = 200


def student_t_quantile(p: float, df: float) -> float:
    """O x com P(T_df ≤ x) = p — bisseção sobre `student_t_cdf` (dono da CDF).

    Sem aproximação nova: a bisseção em [-1e6, 1e6] para quando o intervalo fica
    ≤ 1e-12·max(1, |x|) (consumidor único: o IC do efeito do DM, p = 0,975).

    Raises:
        ValueError: `p` fora de (0, 1), não-finito ou `bool`; `df` como na CDF.
        ArithmeticError: o quantil cai fora de [-1e6, 1e6] ou não converge.
    """
    if not is_finite_number(p) or not 0.0 < p < 1.0:
        raise ValueError(f"p must be a finite number in (0, 1), got {p!r}")
    if not is_finite_number(df) or df < _MIN_DF:
        raise ValueError(f"df must be a finite number >= {_MIN_DF}, got {df!r}")
    if p == _HALF:
        return 0.0
    low, high = -_QUANTILE_BOUND, _QUANTILE_BOUND
    if not student_t_cdf(low, df) <= p <= student_t_cdf(high, df):
        raise ArithmeticError(f"the t quantile of p={p!r}, df={df!r} is outside [-1e6, 1e6]")
    for _ in range(_QUANTILE_MAX_ITERATIONS):
        middle = (low + high) / 2.0
        if student_t_cdf(middle, df) < p:
            low = middle
        else:
            high = middle
        if high - low <= _QUANTILE_RTOL * max(1.0, abs(middle)):
            return (low + high) / 2.0
    raise ArithmeticError(  # pragma: no cover - 61 iterações bastam; salvaguarda
        f"the t quantile bisection did not converge in {_QUANTILE_MAX_ITERATIONS} steps"
    )


def _two_sided_tail(x: float, df: float) -> float:
    """P(|T_df| > |x|) pelos ramos do `pt.c` (x ≠ 0)."""
    if (x / df) * x > _ASYMPTOTIC_NX:
        # A&S 26.5.4 em log, como o `pt.c`: z = 1/nx ≈ df/x², a = df/2, b = ½.
        log_tail = (
            -_HALF * df * (2.0 * math.log(abs(x)) - math.log(df))
            - _log_beta(_HALF * df, _HALF)
            - math.log(_HALF * df)
        )
        return math.exp(log_tail)
    x2 = x * x
    if df > x2:
        _, one_minus_i = _regularized_beta_pair(x2 / (df + x2), df / (df + x2), _HALF, _HALF * df)
        return one_minus_i
    i_value, _ = _regularized_beta_pair(df / (df + x2), x2 / (df + x2), _HALF * df, _HALF)
    return i_value


def _regularized_beta_pair(z: float, one_minus_z: float, a: float, b: float) -> tuple[float, float]:
    """(I_z(a, b), 1 - I_z(a, b)), com o termo da fração contínua calculado direto.

    `z` e `one_minus_z` chegam calculados em separado pelo chamador (sem cancelamento).
    Abaixo do limiar (a + 1)/(a + b + 2) a fração contínua converge rápido em z e dá
    I; acima, a simetria 8.17.4 dá 1 - I = I_{1-z}(b, a) direto.
    """
    if z <= 0.0:
        # |x| < ~1e-154: x² sai 0 em float64 e I_0 = 0 (a CDF arredonda para ½). O
        # complemento nunca é 0 aqui — df/(df + x²) e x²/(df + x²) com x ≠ 0 finito e x²
        # abaixo do limiar assintótico são > 0.
        return 0.0, 1.0
    # log de z e de 1 - z pelo lado sem perda: log1p(-w) quando w ≤ ½ (a fração pequena
    # entra direto, sem passar pelo complemento arredondado perto de 1).
    log_z = math.log(z) if z <= _HALF else math.log1p(-one_minus_z)
    log_one_minus_z = math.log1p(-z) if z <= _HALF else math.log(one_minus_z)
    log_prefactor = a * log_z + b * log_one_minus_z - _log_beta(a, b)
    prefactor = math.exp(log_prefactor)
    if z < (a + 1.0) / (a + b + 2.0):
        i_value = prefactor * _continued_fraction(a, b, z) / a
        return i_value, 1.0 - i_value
    complement = prefactor * _continued_fraction(b, a, one_minus_z) / b
    return 1.0 - complement, complement


def _continued_fraction(a: float, b: float, z: float) -> float:
    """Fração contínua de I_z(a, b) (DLMF 8.17.22/8.17.23) pelo Lentz modificado.

    Devolve 1/(1 + d₁/(1 + d₂/(1 + …))), com
    d_{2m} = m(b - m)z / ((a + 2m - 1)(a + 2m)) e
    d_{2m+1} = -(a + m)(a + b + m)z / ((a + 2m)(a + 2m + 1)).

    Raises:
        ArithmeticError: sem convergência em `_MAX_ITERATIONS` iterações.
    """
    c = 1.0
    d = _floor(1.0 - (a + b) * z / (a + 1.0))
    d = 1.0 / d
    result = d
    for m in range(1, _MAX_ITERATIONS + 1):
        two_m = 2 * m
        even = m * (b - m) * z / ((a + two_m - 1.0) * (a + two_m))
        d = 1.0 / _floor(1.0 + even * d)
        c = _floor(1.0 + even / c)
        result *= d * c
        odd = -(a + m) * (a + b + m) * z / ((a + two_m) * (a + two_m + 1.0))
        d = 1.0 / _floor(1.0 + odd * d)
        c = _floor(1.0 + odd / c)
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= _EPSILON:
            return result
    raise ArithmeticError(
        f"incomplete beta continued fraction did not converge in {_MAX_ITERATIONS} "
        f"iterations (a={a}, b={b}, z={z})"
    )


def _floor(value: float) -> float:
    """Piso do Lentz modificado: troca |valor| < `_TINY` por `_TINY`."""
    return _TINY if abs(value) < _TINY else value


def _log_beta(a: float, b: float) -> float:
    """log B(a, b), como o R `src/nmath/lbeta.c`.

    Com um argumento pequeno (< 10) e o outro grande (≥ 10) — o caso da t, (½, df/2)
    —, `lgamma(q) - lgamma(p + q)` subtrai dois números ~ q·log q e perde ~log₁₀(q·log q)
    dígitos; o ramo do `lbeta.c` isola a parte de Stirling:
    lgamma(p) + [corr(q) - corr(p + q)] + p - p·log(p + q) + (q - ½)·log1p(-p/(p + q)).
    Nos demais casos, a soma direta de `math.lgamma`.
    """
    small, large = min(a, b), max(a, b)
    if large < _STIRLING_MIN or small >= _STIRLING_MIN:
        return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    total = small + large
    correction = _stirling_correction(large) - _stirling_correction(total)
    return (
        math.lgamma(small)
        + correction
        + small
        - small * math.log(total)
        + (large - _HALF) * math.log1p(-small / total)
    )


def _stirling_correction(x: float) -> float:
    """lgamma(x) - [(x - ½)·log x - x + ½·log 2π] pela série de Stirling (x ≥ 10).

    Σ B_{2k}/(2k(2k - 1)·x^{2k-1}), k = 1..8 — a grandeza do `lgammacor` do R (que a
    avalia por série de Chebyshev); o primeiro termo desprezado é < 2e-18 em x = 10.
    """
    inverse_square = 1.0 / (x * x)
    total = 0.0
    for coefficient in reversed(_STIRLING_COEFFICIENTS):
        total = total * inverse_square + coefficient
    return total / x
