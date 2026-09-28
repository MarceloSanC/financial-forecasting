"""Unit test da banda de Wilson (`wilson_interval`, `WilsonBand`, `WilsonBandReport`).

Prova (concept 6.3 A4, I1, I4, I7, I10, C3, C7, C9; doc §4.4; ADR 6.3.0005) com
fixtures analíticas (ADR 0.0.0021) — valores de fronteira medidos no technical §1:

- BCD 2001 Eq. (4): [0.011, 0.036] (c = 10, n = 500) e [0.013, 0.031] (c = 20,
  n = 1000) a 95 %;
- região contém-o-nominal a τ = 0.02, n = 500: c ∈ [4, 16], falso em 3 e 17;
- equivariância c ↔ n - c; contagem real entre os vizinhos inteiros;
- n = 0 → não aplicável; aviso de dependência serial em h > 1;
- um caso por ramo de C3 (kernel e `evaluate`) e de C9 (`__post_init__`).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    wilson_band as wilson_band_module,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBand,
    WilsonBandReport,
    wilson_interval,
)

# Tolerância declarada (ADR 0.0.0021): identidade de float64.
_ABS_TOL = 1e-12
_BAND_95 = 0.95
_NOMINAL = 0.02
_N_500 = 500
# BCD Eq. (4), c = 10, n = 500, 95 % (technical §1, medido em float64).
_C10_N500 = (0.01089918359621081, 0.03642018324687933)


def _report(**overrides: object) -> WilsonBandReport:
    """Relatório válido (c = 10, n = 500, 95 %, h = 1) com campos trocados."""
    base = WilsonBand.evaluate(horizon=1, count=10, n=_N_500, nominal=_NOMINAL, band_level=_BAND_95)
    return dataclasses.replace(base, **overrides)


# --- A4 — BCD Eq. (4) -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "n", "expected"),
    [(10, 500, [0.011, 0.036]), (20, 1000, [0.013, 0.031])],
    ids=["c10-n500", "c20-n1000"],
)
def test_wilson_bcd_rounded_band(count: int, n: int, expected: list[float]) -> None:
    """A4/I7: a banda a 95 % arredondada a 3 casas (doc §4.4, ordem de grandeza)."""
    lower, upper = wilson_interval(count=count, n=n, band_level=_BAND_95)

    assert [round(lower, 3), round(upper, 3)] == expected


@pytest.mark.unit
def test_wilson_bcd_matches_the_eq4_value_measured_in_the_technical() -> None:
    """A4: c = 10, n = 500 bate com o valor da Eq. (4) medido no §1 (1e-12)."""
    lower, upper = wilson_interval(count=10, n=_N_500, band_level=_BAND_95)

    assert abs(lower - _C10_N500[0]) <= _ABS_TOL
    assert abs(upper - _C10_N500[1]) <= _ABS_TOL


# --- A4 — região contém-o-nominal -------------------------------------------------------------


@pytest.mark.unit
def test_wilson_region_contains_nominal_exactly_on_four_to_sixteen() -> None:
    """A4: τ = 0.02, n = 500, 95 % — contém o nominal em c ∈ [4, 16], não em 3 e 17."""
    verdicts = {
        c: WilsonBand.evaluate(
            horizon=1, count=c, n=_N_500, nominal=_NOMINAL, band_level=_BAND_95
        ).contains_nominal
        for c in range(3, 18)
    }

    assert all(verdicts[c] is True for c in range(4, 17))
    assert verdicts[3] is False
    assert verdicts[17] is False


# --- A4 — equivariância e contagem real -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "n"), [(10, 500), (3, 40), (0.7, 12.5)], ids=["c10-n500", "c3-n40", "real"]
)
def test_wilson_equivariance_under_count_complement(count: float, n: float) -> None:
    """A4: a banda de n - c é (1 - upper(c), 1 - lower(c)) (1e-12)."""
    lower, upper = wilson_interval(count=count, n=n, band_level=_BAND_95)
    lower_c, upper_c = wilson_interval(count=n - count, n=n, band_level=_BAND_95)

    assert abs(lower_c - (1.0 - upper)) <= _ABS_TOL
    assert abs(upper_c - (1.0 - lower)) <= _ABS_TOL


@pytest.mark.unit
def test_wilson_real_count_lies_between_integer_neighbours() -> None:
    """A4/I10: c = 10.5 (média entre seeds) dá limites estritamente entre os de 10 e 11."""
    low_10, up_10 = wilson_interval(count=10, n=_N_500, band_level=_BAND_95)
    low_mid, up_mid = wilson_interval(count=10.5, n=_N_500, band_level=_BAND_95)
    low_11, up_11 = wilson_interval(count=11, n=_N_500, band_level=_BAND_95)

    assert low_10 < low_mid < low_11
    assert up_10 < up_mid < up_11


@pytest.mark.unit
def test_wilson_real_count_and_real_n_in_evaluate() -> None:
    """ADR 6.3.0005: `evaluate` aceita c e n reais (médias entre seeds)."""
    report = WilsonBand.evaluate(
        horizon=1, count=10.5, n=499.5, nominal=_NOMINAL, band_level=_BAND_95
    )

    assert report.applicable is True
    assert report.estimate == 10.5 / 499.5


# --- C7 — n = 0 -------------------------------------------------------------------------------


@pytest.mark.unit
def test_wilson_not_applicable_on_fully_degenerate_series() -> None:
    """A4/C7: n = 0 → `applicable = False` e campos de banda `None` (não erro)."""
    report = WilsonBand.evaluate(horizon=1, count=0, n=0, nominal=_NOMINAL, band_level=_BAND_95)

    assert report.applicable is False
    assert report.estimate is None
    assert report.lower is None
    assert report.upper is None
    assert report.contains_nominal is None


@pytest.mark.unit
def test_wilson_not_applicable_requires_zero_count() -> None:
    """C3: n = 0 com count ≠ 0 ergue."""
    with pytest.raises(ValueError, match="count must be 0 when n == 0"):
        WilsonBand.evaluate(horizon=1, count=1, n=0, nominal=_NOMINAL, band_level=_BAND_95)


# --- I1 — horizonte e aviso -------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("horizon", "warning"), [(1, False), (7, True)], ids=["h1", "h7"])
def test_wilson_horizon_carried_and_drives_serial_warning(horizon: int, *, warning: bool) -> None:
    """A4/I1: o relatório traz o horizonte passado; h > 1 liga o aviso."""
    report = WilsonBand.evaluate(
        horizon=horizon, count=10, n=_N_500, nominal=_NOMINAL, band_level=_BAND_95
    )

    assert report.horizon == horizon
    assert report.serial_dependence_warning is warning


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [0, True, 1.0], ids=["zero", "bool", "float"])
def test_wilson_horizon_invalid_in_evaluate_raises(horizon: int) -> None:
    """A4: `horizon` 0, `True` ou não-`int` erguem em `evaluate`."""
    with pytest.raises(ValueError, match="horizon must be an int >= 1"):
        WilsonBand.evaluate(
            horizon=horizon, count=10, n=_N_500, nominal=_NOMINAL, band_level=_BAND_95
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("nominal", "match"),
    [
        (0.0, r"nominal must be in \(0, 1\)"),
        (1.0, r"nominal must be in \(0, 1\)"),
        (math.nan, "nominal must be a finite number"),
        (True, "nominal must be a finite number"),
    ],
    ids=["zero", "one", "nan", "bool"],
)
def test_wilson_nominal_invalid_in_evaluate_raises(nominal: float, match: str) -> None:
    """A4: `nominal` fora de (0, 1), `nan` ou `bool` ergue em `evaluate`."""
    with pytest.raises(ValueError, match=match):
        WilsonBand.evaluate(horizon=1, count=10, n=_N_500, nominal=nominal, band_level=_BAND_95)


# --- C3 — kernel ------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"count": -1}, r"count must be in \[0, n="),
        ({"count": 501}, r"count must be in \[0, n="),
        ({"n": -5}, "n must be > 0"),
        ({"count": 0, "n": 0}, "n must be > 0"),
        ({"band_level": 0.0}, r"band_level must be in \(0, 1\)"),
        ({"band_level": 1.0}, r"band_level must be in \(0, 1\)"),
        ({"count": math.nan}, "count must be a finite number"),
        ({"n": math.inf}, "n must be a finite number"),
        ({"count": True}, "count must be a finite number"),
        ({"band_level": math.nan}, "band_level must be a finite number"),
        ({"band_level": True}, "band_level must be a finite number"),
    ],
    ids=[
        "count-negative",
        "count-above-n",
        "n-negative",
        "n-zero",
        "band-level-zero",
        "band-level-one",
        "count-nan",
        "n-inf",
        "count-bool",
        "band-level-nan",
        "band-level-bool",
    ],
)
def test_wilson_invalid_kernel_argument_raises(kwargs: dict[str, float], match: str) -> None:
    """A4/C3: um caso por ramo do kernel (validador único de contagem)."""
    arguments = {"count": 10, "n": _N_500, "band_level": _BAND_95, **kwargs}
    with pytest.raises(ValueError, match=match):
        wilson_interval(**arguments)


@pytest.mark.unit
def test_wilson_invalid_band_level_in_evaluate_raises() -> None:
    """C3: `band_level` inválido também ergue em `evaluate` (inclusive com n = 0)."""
    with pytest.raises(ValueError, match=r"band_level must be in \(0, 1\)"):
        WilsonBand.evaluate(horizon=1, count=0, n=0, nominal=_NOMINAL, band_level=1.0)


# --- C9 — relatório incoerente, um caso por ramo ----------------------------------------------


@pytest.mark.unit
def test_wilson_incoherent_valid_report_round_trips() -> None:
    """Sanidade: o relatório do serviço atravessa o `__post_init__`."""
    report = _report()

    assert dataclasses.replace(report) == report


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"contains_nominal": False}, "contains_nominal must be"),
        ({"applicable": False}, r"applicable must be \(n > 0\)"),
        ({"estimate": 0.03}, "estimate must be count / n"),
        ({"lower": 0.04}, "must satisfy 0 <= lower <= upper <= 1"),
        ({"lower": -0.01, "contains_nominal": True}, "must satisfy 0 <= lower <= upper <= 1"),
        ({"upper": 1.01}, "must satisfy 0 <= lower <= upper <= 1"),
        ({"serial_dependence_warning": True}, "serial_dependence_warning must be"),
        ({"nominal": 0.0}, r"nominal must be in \(0, 1\)"),
        ({"nominal": 1.0}, r"nominal must be in \(0, 1\)"),
        ({"band_level": 1.0}, r"band_level must be in \(0, 1\)"),
        ({"horizon": 0}, "horizon must be an int >= 1"),
        ({"horizon": True}, "horizon must be an int >= 1"),
        ({"estimate": None}, "needs estimate, lower and upper"),
        ({"contains_nominal": None}, "needs contains_nominal"),
        ({"count": 501}, r"count must be in \[0, n="),
    ],
    ids=[
        "contains-nominal-inverted",
        "not-applicable-with-n",
        "estimate-not-c-over-n",
        "lower-above-upper",
        "lower-below-zero",
        "upper-above-one",
        "warning-incoherent-with-horizon",
        "nominal-zero",
        "nominal-one",
        "band-level-one",
        "horizon-zero",
        "horizon-bool",
        "applicable-without-band",
        "applicable-without-verdict",
        "count-above-n",
    ],
)
def test_wilson_incoherent_applicable_report_raises(
    overrides: dict[str, object], match: str
) -> None:
    """C9: cada ramo do `__post_init__` sobre um relatório aplicável ergue."""
    with pytest.raises(ValueError, match=match):
        _report(**overrides)


def _not_applicable() -> WilsonBandReport:
    return WilsonBand.evaluate(horizon=1, count=0, n=0, nominal=_NOMINAL, band_level=_BAND_95)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"lower": 0.01}, "must have estimate, lower, upper and contains_nominal set to None"),
        ({"contains_nominal": True}, "set to None"),
        ({"applicable": True}, r"applicable must be \(n > 0\)"),
        ({"count": 1}, "needs n == 0 and count == 0"),
        ({"n": -1}, "needs n == 0 and count == 0"),
        ({"n": False}, "needs n == 0 and count == 0"),
        ({"count": False}, "needs n == 0 and count == 0"),
    ],
    ids=[
        "band-filled-when-not-applicable",
        "verdict-filled-when-not-applicable",
        "applicable-with-n-zero",
        "not-applicable-with-count",
        "not-applicable-with-negative-n",
        "not-applicable-with-bool-n",
        "not-applicable-with-bool-count",
    ],
)
def test_wilson_incoherent_not_applicable_report_raises(
    overrides: dict[str, object], match: str
) -> None:
    """C9: ramos do relatório não aplicável (n = 0)."""
    report = _not_applicable()
    with pytest.raises(ValueError, match=match):
        dataclasses.replace(report, **overrides)


# --- Pontas da banda, κ exato e consumo do validador único ----------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "bound", "expected"), [(0, 0, 0.0), (_N_500, 1, 1.0)], ids=["c-zero", "c-equals-n"]
)
def test_wilson_bcd_band_is_clamped_to_unit_interval(
    count: int, bound: int, expected: float
) -> None:
    """c = 0 e c = n: a ponta sai exatamente 0.0 / 1.0 (sem -5.55e-17 nem 1.0000000000000002)
    e a banda inteira fica em [0, 1] — a banda persistida é uma proporção."""
    band = wilson_interval(count=count, n=_N_500, band_level=_BAND_95)

    assert band[bound] == expected
    assert 0.0 <= band[0] <= band[1] <= 1.0


@pytest.mark.unit
def test_wilson_bcd_band_level_next_to_one_has_finite_kappa() -> None:
    """κ = -Φ⁻¹((1 - nível)/2): nível = 0.9999999999999999 não degenera em Φ⁻¹(1.0)."""
    lower, upper = wilson_interval(count=10, n=_N_500, band_level=math.nextafter(1.0, 0.0))

    assert 0.0 < lower < 10 / _N_500 < upper < 1.0


@pytest.mark.unit
def test_wilson_invalid_counts_go_through_the_single_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 6.3.0005 item 1: o kernel valida pelo `validate_real_count` (trocar o nome no
    módulo muda o erro) — nenhuma cópia da regra de contagem real."""

    def _reject(*_: object, **__: object) -> None:
        raise ValueError("single validator called")

    monkeypatch.setattr(wilson_band_module, "validate_real_count", _reject)

    with pytest.raises(ValueError, match="single validator called"):
        wilson_interval(count=10, n=_N_500, band_level=_BAND_95)
