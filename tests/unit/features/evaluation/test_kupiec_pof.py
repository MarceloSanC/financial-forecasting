"""Unit test do kernel `kupiec_pof` (Kupiec 1995 expr. (6) ≡ LR_uc) e do `xlogy`.

Prova (concept 6.3 A5, I10, I13, C3; ADRs 6.3.0001 item 3, 6.3.0005) com fixtures
analíticas (ADR 0.0.0021) — o oráculo R entra só nos testes de integração (Task 11):

- igualdade com a expressão (6) escrita **aqui**, pela forma de produto, em n pequeno;
- a Table 2 de Kupiec (p = 0.02: maior T que rejeita por excesso para x = 1..4) e as
  regiões de não-rejeição a 5 % medidas no technical §1;
- contagem real (média entre seeds) entre os vizinhos inteiros;
- o piso I13 numa entrada real cujo LR bruto sai negativo;
- um caso de C3 por ramo.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.chi_square import (
    chi_square_sf,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import (
    kupiec_pof,
    xlogy,
)

# Tolerância declarada (ADR 0.0.0021), absoluta: log-somas x log de produto em float64
# (diferença máxima medida na grade do teste da expressão (6): 5.7e-14, em LR ≈ 237).
_ABS_TOL = 1e-12
_SIGNIFICANCE = 0.05
_KUPIEC_RATE = 0.02
# Piso I13 (technical §1): x/n = 0.4 e p = o float imediatamente abaixo de 0.4.
_FLOOR_RATE = 0.39999999999999997
_FLOOR_BAND = -1e-9
# A5: x = 4, T = 500, p = 0.02 arredondado a 2 casas (technical §1: 4.742845480299913).
_X4_T500_ROUNDED = 4.74


def _expression_6(x: float, n: float, p: float) -> float:
    """Kupiec (1995) expr. (6), literal, pela forma de produto (só n pequeno)."""
    return -2 * math.log((1 - p) ** (n - x) * p**x) + 2 * math.log(
        (1 - x / n) ** (n - x) * (x / n) ** x
    )


def _close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= _ABS_TOL


def _rejects(x: int, n: int, p: float = _KUPIEC_RATE) -> bool:
    lr = kupiec_pof(violations=x, observations=n, violation_rate=p)
    return chi_square_sf(lr, df=1) < _SIGNIFICANCE


# --- A5 — expressão (6) -----------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("n", [10, 25, 60])
@pytest.mark.parametrize("p", [0.02, 0.05, 0.3])
def test_kupiec_expression_6_matches_the_product_form(n: int, p: float) -> None:
    """A5: igual (1e-12) à expressão (6) escrita no teste, x = 1..n-1, n ≤ 60."""
    for x in range(1, n):
        actual = kupiec_pof(violations=x, observations=n, violation_rate=p)
        assert _close(actual, _expression_6(x, n, p)), (x, n, p)


@pytest.mark.unit
def test_kupiec_expression_zero_violations_is_closed_form() -> None:
    """A5: x = 0 → -2·n·log(1 - p) (0·log 0 = 0 no termo de x/n)."""
    n = 500
    expected = -2 * n * math.log(1 - _KUPIEC_RATE)

    actual = kupiec_pof(violations=0, observations=n, violation_rate=_KUPIEC_RATE)

    assert _close(actual, expected)
    assert _close(actual, 20.202707317519465)  # technical §1


@pytest.mark.unit
def test_kupiec_expression_all_violations_uses_zero_log_zero() -> None:
    """0·log 0 = 0 também no termo (n - x)·log(1 - x/n) com x = n."""
    n = 5
    expected = -2 * n * math.log(_KUPIEC_RATE)

    assert _close(kupiec_pof(violations=n, observations=n, violation_rate=_KUPIEC_RATE), expected)


@pytest.mark.unit
@pytest.mark.parametrize("y", [0.0, 0.5, 1.0], ids=["zero", "half", "one"])
def test_kupiec_expression_xlogy_convention(y: float) -> None:
    """`xlogy(0, y) = 0` para todo y (inclusive log 0); senão `x·log y`."""
    assert xlogy(0.0, y) == 0.0
    if y > 0.0:
        assert xlogy(3.0, y) == 3.0 * math.log(y)


@pytest.mark.unit
def test_kupiec_expression_value_at_four_in_five_hundred() -> None:
    """A5: x = 4, T = 500, p = 0.02 → 4,74 (technical §1: 4.742845480299913)."""
    actual = kupiec_pof(violations=4, observations=500, violation_rate=_KUPIEC_RATE)

    assert round(actual, 2) == _X4_T500_ROUNDED


# --- A5 — Table 2 e regiões de não-rejeição -----------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("x", "largest_rejecting_t"), [(1, 3), (2, 17), (3, 38), (4, 63)], ids=["x1", "x2", "x3", "x4"]
)
def test_kupiec_table2_largest_rejecting_sample(x: int, largest_rejecting_t: int) -> None:
    """A5: Kupiec (1995) Table 2, p = 0.02 — maior T com x/T > p que rejeita a 5 %."""
    excess_side = [t for t in range(x, 50 * x) if x / t > _KUPIEC_RATE]

    rejecting = [t for t in excess_side if _rejects(x, t)]

    assert max(rejecting) == largest_rejecting_t
    assert not _rejects(x, largest_rejecting_t + 1)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n", "low", "high"),
    [(250, 2, 9), (500, 5, 16), (1000, 12, 29)],
    ids=["T250", "T500", "T1000"],
)
def test_kupiec_region_of_non_rejection_is_contiguous(n: int, low: int, high: int) -> None:
    """A5: região de não-rejeição a 5 % (p = 0.02) é exatamente [low, high]."""
    accepted = [x for x in range(n + 1) if not _rejects(x, n)]

    assert accepted == list(range(low, high + 1))


# --- A5/I10 — contagem real ----------------------------------------------------------------


@pytest.mark.unit
def test_kupiec_real_count_lies_between_integer_neighbours() -> None:
    """A5/I10: x = 10.5 (média entre seeds), n = 500 — p·n = 10, lado crescente: o
    valor fica estritamente entre os de x = 10 e x = 11 e bate com a expressão (6)."""
    at_10 = kupiec_pof(violations=10, observations=500, violation_rate=_KUPIEC_RATE)
    at_11 = kupiec_pof(violations=11, observations=500, violation_rate=_KUPIEC_RATE)
    at_10_5 = kupiec_pof(violations=10.5, observations=500, violation_rate=_KUPIEC_RATE)

    assert at_10 < at_10_5 < at_11
    assert _close(at_10_5, _expression_6(10.5, 500, _KUPIEC_RATE))


@pytest.mark.unit
def test_kupiec_real_count_with_real_observations() -> None:
    """ADR 6.3.0005: n real (média de pontos não-degenerados) — x = 10.5, n = 500.5."""
    actual = kupiec_pof(violations=10.5, observations=500.5, violation_rate=_KUPIEC_RATE)

    assert _close(actual, _expression_6(10.5, 500.5, _KUPIEC_RATE))


# --- A5/I13 — piso ---------------------------------------------------------------------------


@pytest.mark.unit
def test_kupiec_floor_exact_null_gives_unsigned_zero() -> None:
    """I13: x = n·p exato (10 = 500·0.02) dá LR bruto `-2·(a - a) = -0.0`; o piso
    normaliza para +0.0 (nenhum relatório carrega zero com sinal)."""
    actual = kupiec_pof(violations=10, observations=500, violation_rate=_KUPIEC_RATE)

    assert actual == 0.0
    assert math.copysign(1.0, actual) == 1.0


@pytest.mark.unit
def test_kupiec_floor_clamps_negative_raw_statistic() -> None:
    """A5/I13: x = 2, n = 5, p = 0.39999999999999997 — o LR bruto (mesma ordem de
    operações do kernel) é negativo dentro da faixa do piso; o kernel devolve 0.0."""
    x, n = 2, 5
    observed = x / n
    raw = -2.0 * (
        (xlogy(n - x, 1.0 - _FLOOR_RATE) + xlogy(x, _FLOOR_RATE))
        - (xlogy(n - x, 1.0 - observed) + xlogy(x, observed))
    )
    assert _FLOOR_BAND <= raw < 0.0  # premissa: o piso de fato atua

    assert kupiec_pof(violations=x, observations=n, violation_rate=_FLOOR_RATE) == 0.0


# --- C3 — um caso por ramo -----------------------------------------------------------------


_VALID = {"violations": 4, "observations": 500, "violation_rate": _KUPIEC_RATE}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"observations": 0}, "observations must be > 0"),
        ({"observations": -5}, "observations must be > 0"),
        ({"violations": -1}, r"violations must be in \[0, observations"),
        ({"violations": 501}, r"violations must be in \[0, observations"),
        ({"violation_rate": 0.0}, r"violation_rate must be in \(0, 1\)"),
        ({"violation_rate": 1.0}, r"violation_rate must be in \(0, 1\)"),
        ({"violation_rate": 1.5}, r"violation_rate must be in \(0, 1\)"),
        ({"violations": math.nan}, "violations must be a finite number"),
        ({"violations": math.inf}, "violations must be a finite number"),
        ({"violations": True}, "violations must be a finite number"),
        ({"observations": math.nan}, "observations must be a finite number"),
        ({"observations": math.inf}, "observations must be a finite number"),
        ({"observations": True}, "observations must be a finite number"),
        ({"violation_rate": math.nan}, "violation_rate must be a finite number"),
        ({"violation_rate": math.inf}, "violation_rate must be a finite number"),
        ({"violation_rate": True}, "violation_rate must be a finite number"),
    ],
    ids=[
        "observations-zero",
        "observations-negative",
        "violations-negative",
        "violations-above-observations",
        "rate-zero",
        "rate-one",
        "rate-above-one",
        "violations-nan",
        "violations-inf",
        "violations-bool",
        "observations-nan",
        "observations-inf",
        "observations-bool",
        "rate-nan",
        "rate-inf",
        "rate-bool",
    ],
)
def test_kupiec_invalid_argument_raises(overrides: dict[str, float], match: str) -> None:
    """C3: cada argumento inválido ergue `ValueError`, com mensagem que nomeia o campo."""
    with pytest.raises(ValueError, match=match):
        kupiec_pof(**{**_VALID, **overrides})
