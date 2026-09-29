"""Unit test de `student_t_cdf` contra formas fechadas (A3 unit, C5; ADR 6.2.0002).

Oráculo analítico (ADR 0.0.0021): x = 0 → ½; as CDFs em forma fechada de df = 1
(Cauchy), df = 2 e df = 3; o argumento complementar sem cancelamento perto de 0;
monotonicidade. As caudas usam formas **sem cancelamento** (nunca ½ - algo ≈ ½), para
que a checagem relativa seja do código e não da referência. Para df sem forma fechada
(20-2499), valores de referência **literais** calculados com `mpmath` 1.3.0 (60 dígitos,
`betainc` regularizada) e colados aqui com 20 dígitos — constantes, não I/O. O
cruzamento com `scipy.stats.t` fica na suíte de contrato do `InferenceBackend` (Task
10), e com o R `pt` nas fixtures (Task 08) — unit não importa biblioteca.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from financial_forecasting.features.evaluation.domain.services import student_t
from financial_forecasting.features.evaluation.domain.services.student_t import student_t_cdf

# Tolerâncias declaradas (technical 6.2 §1): abs ≤ 1e-14 contra as formas fechadas;
# na cauda inferior (x < 0) também rel ≤ 1e-12 contra a forma sem cancelamento.
_ABS_TOL = 1e-14
_TAIL_REL_TOL = 1e-12
_SYMMETRY_ABS_TOL = 1e-15
_HALF = 0.5
_COMPLEMENT_REL_TOL = 1e-6

# Grade do technical (Task 02): caudas extremas, centro e lado positivo.
_CLOSED_FORM_X = (-1e150, -1e6, -10.0, -1.0, -1e-9, 0.3, 7.0)

# (df, x, P(T_df <= x)) — mpmath 1.3.0, mp.dps = 60: ½·I_{df/(df+x²)}(df/2, ½) para x < 0
# e o complemento para x > 0. Centro, ±1,65 (p ≈ 0,05, onde vive a decisão do DM), o
# ponto x = -1,73 em df = 999 (perto do limiar da simetria 8.17.4) e a cauda profunda —
# df = 999, x = -10 é a armadilha ½·(1 - I) do technical §1 (daria 0).
_MPMATH_REFERENCE = (
    (20.0, 0.25, 5.9743134151989769158e-1),
    (20.0, -1.65, 5.7280412268939645441e-2),
    (20.0, 1.65, 9.4271958773106035456e-1),
    (20.0, -10.0, 1.5818908793571940812e-9),
    (30.0, 0.25, 5.978542954597124503e-1),
    (30.0, -1.65, 5.4687967392435585272e-2),
    (30.0, 1.65, 9.4531203260756441473e-1),
    (30.0, -10.0, 2.2876257041148065963e-11),
    (59.0, 0.25, 5.9827210364217897885e-1),
    (59.0, -1.65, 5.2128677618981229138e-2),
    (59.0, 1.65, 9.4787132238101877086e-1),
    (59.0, -12.0, 9.0020326933915706779e-18),
    (249.0, 0.25, 5.9860325895648702543e-1),
    (249.0, -1.65, 5.0101884672115977524e-2),
    (249.0, 1.65, 9.4989811532788402248e-1),
    (249.0, -20.0, 5.1138751504307993103e-54),
    (999.0, 0.25, 5.9868062617328365844e-1),
    (999.0, -1.65, 4.9628642125508738581e-2),
    (999.0, 1.65, 9.5037135787449126142e-1),
    (999.0, -1.73, 4.1969562676202073584e-2),
    (999.0, -10.0, 8.3541094134356452121e-23),
    (999.0, -30.0, 8.3641360655859234298e-142),
    (2499.0, 0.25, 5.9869605123972352333e-1),
    (2499.0, -1.65, 4.95343033193071325e-2),
    (2499.0, 1.65, 9.504656966806928675e-1),
    (2499.0, -40.0, 3.74860566389012121e-271),
)
_LOWER_TAIL_REFERENCE = tuple(row for row in _MPMATH_REFERENCE if row[1] < 0.0)

# Ramo assintótico (|x| com x² estourando float64). df = 2: F ≈ 1/(2x²) cai em
# subnormal (5e-321 em x = -1e160, 3 dígitos) e em 0 em x = -1e200.
_HUGE_X = (-1e160, -1e200)
_SUBNORMAL_REL_TOL = 1e-2
_LOG_BETA_ABS_TOL = 1e-14


def _df1_reference(x: float) -> float:
    """Cauchy: ½ + arctan(x)/π em |x| ≤ 1; nas caudas, via arctan(1/x) sem cancelamento."""
    if x < -1.0:
        return -math.atan(1.0 / x) / math.pi
    if x <= 1.0:
        return 0.5 + math.atan(x) / math.pi
    return 1.0 - math.atan(1.0 / x) / math.pi


def _df2_reference(x: float) -> float:
    """df = 2: ½ + x/(2√(2+x²)); a cauda x < 0 como 1/(√(2+x²)(√(2+x²) - x))."""
    root = math.sqrt(2.0 + x * x)
    if x < 0.0:
        return 1.0 / (root * (root - x))
    return 1.0 - 1.0 / (root * (root + x))


def _df3_reference(x: float) -> float:
    """df = 3: ½ + (1/π)[(x/√3)/(1 + x²/3) + arctan(x/√3)]."""
    u = x / math.sqrt(3.0)
    return 0.5 + (u / (1.0 + u * u) + math.atan(u)) / math.pi


def _assert_matches(actual: float, expected: float, x: float) -> None:
    assert abs(actual - expected) <= _ABS_TOL, (x, actual, expected)
    if x < 0.0:
        assert abs(actual - expected) <= _TAIL_REL_TOL * expected, (x, actual, expected)


@pytest.mark.unit
@pytest.mark.parametrize("df", [1.0, 2.0, 30.0, 2500.0])
def test_t_zero_half_exact(df: float) -> None:
    assert student_t_cdf(0.0, df) == _HALF


@pytest.mark.unit
@pytest.mark.parametrize("x", [-1e-200, 1e-200])
def test_t_zero_half_when_x_squared_underflows(x: float) -> None:
    """|x| tão pequeno que x² = 0 em float64: a CDF arredonda para ½ (e não erra no log)."""
    assert student_t_cdf(x, 7.0) == _HALF


@pytest.mark.unit
@pytest.mark.parametrize("x", _CLOSED_FORM_X)
def test_t_df1_closed_form_cauchy(x: float) -> None:
    _assert_matches(student_t_cdf(x, 1.0), _df1_reference(x), x)


@pytest.mark.unit
@pytest.mark.parametrize("x", _CLOSED_FORM_X)
def test_t_df2_closed_form(x: float) -> None:
    _assert_matches(student_t_cdf(x, 2.0), _df2_reference(x), x)


@pytest.mark.unit
@pytest.mark.parametrize("x", [-5.0, -2.5, -1.0, -0.1, 0.0, 0.4, 1.7, 3.0, 5.0])
def test_t_df3_closed_form(x: float) -> None:
    assert abs(student_t_cdf(x, 3.0) - _df3_reference(x)) <= _ABS_TOL


@pytest.mark.unit
@pytest.mark.parametrize(("df", "x", "expected"), _MPMATH_REFERENCE)
def test_t_mpmath_reference_values(df: float, x: float, expected: float) -> None:
    _assert_matches(student_t_cdf(x, df), expected, x)


@pytest.mark.unit
@pytest.mark.parametrize(("df", "x", "expected"), _LOWER_TAIL_REFERENCE)
def test_t_symmetry_upper_side_vs_independent_reference(
    df: float, x: float, expected: float
) -> None:
    """1 - F(|x|) (o ramo x > 0 do código) contra a referência mpmath de F(-|x|)."""
    assert abs((1.0 - student_t_cdf(-x, df)) - expected) <= _SYMMETRY_ABS_TOL


@pytest.mark.unit
@pytest.mark.parametrize("x", _HUGE_X)
def test_t_asymptotic_branch_df1_huge_x(x: float) -> None:
    """x² = inf em float64: sem o ramo `nx > 1e100` do `pt.c` a CDF sairia 0."""
    expected = -math.atan(1.0 / x) / math.pi
    actual = student_t_cdf(x, 1.0)
    assert abs(actual - expected) <= _TAIL_REL_TOL * expected
    assert student_t_cdf(-x, 1.0) == 1.0


@pytest.mark.unit
def test_t_asymptotic_branch_df2_subnormal_tail() -> None:
    assert math.isclose(student_t_cdf(-1e160, 2.0), 5e-321, rel_tol=_SUBNORMAL_REL_TOL)
    assert student_t_cdf(-1e200, 2.0) == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("n", [500, 1000, 1250])
def test_t_log_beta_matches_exact_central_binomial(n: int) -> None:
    """log B(n, ½) = log(4ⁿ/(n·C(2n, n))) — divisão inteira exata, arredondada uma vez.

    A soma ingênua `lgamma(n) + lgamma(½) - lgamma(n + ½)` erra ~1e-12 aqui (subtração
    de dois números ~ n·log n); o ramo de Stirling do `lbeta.c` fica em ~1e-16.
    """
    exact = math.log(4**n / (n * math.comb(2 * n, n)))
    assert abs(student_t._log_beta(float(n), 0.5) - exact) <= _LOG_BETA_ABS_TOL
    assert abs(student_t._log_beta(0.5, float(n)) - exact) <= _LOG_BETA_ABS_TOL


@pytest.mark.unit
def test_t_complement_no_cancel_near_zero() -> None:
    """½ - F(-1e-9) ≈ 1e-9·f(0): a versão com 1 - n/(n + x²) devolveria 0."""
    df = 30.0
    log_density_at_zero = (
        math.lgamma((df + 1.0) / 2.0) - math.lgamma(df / 2.0) - 0.5 * math.log(df * math.pi)
    )
    expected = 1e-9 * math.exp(log_density_at_zero)
    actual = 0.5 - student_t_cdf(-1e-9, df)
    assert actual > 0.0
    assert math.isclose(actual, expected, rel_tol=_COMPLEMENT_REL_TOL)


@pytest.mark.unit
@pytest.mark.parametrize("df", [1.0, 2.0, 59.0, 2499.0])
def test_t_monotone_increasing(df: float) -> None:
    grid = [-6.0 + 12.0 * i / 199 for i in range(200)]
    values = [student_t_cdf(x, df) for x in grid]
    assert all(later > earlier for earlier, later in pairwise(values))
    assert all(0.0 < value < 1.0 for value in values)


@pytest.mark.unit
@pytest.mark.parametrize("df", [0.5, 0.0, -1.0, math.nan, math.inf, True, None], ids=repr)
def test_t_invalid_input_df(df: object) -> None:
    with pytest.raises(ValueError, match="df"):
        student_t_cdf(1.0, df)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("x", [math.nan, math.inf, -math.inf, None, True], ids=repr)
def test_t_invalid_input_x(x: object) -> None:
    with pytest.raises(ValueError, match="x must"):
        student_t_cdf(x, 5.0)  # type: ignore[arg-type]


@pytest.mark.unit
def test_t_not_converge_raises_arithmetic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Teto de iterações atingido ergue — nunca devolve o valor parcial (C5)."""
    monkeypatch.setattr(student_t, "_MAX_ITERATIONS", 1)
    with pytest.raises(ArithmeticError, match="did not converge"):
        student_t_cdf(-1.5, 5.0)
