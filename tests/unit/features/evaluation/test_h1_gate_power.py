"""Unit test do `H1GatePower` (Stage 6.5, A4; ADR 6.5.0006 item 5, 6.5-POWER).

Reproduz a tabela do doc §8.5 em n = 500 (probabilidade de reprovar, 3 casas:
calibrado 0,041; locação 0,2sigma 0,840; 0,3sigma 0,996; cobertura 75 % 0,580; 85 %
0,536 — taxas de locação pelo `NormalDist`), iguala a soma dupla bruta da
multinomial em n pequeno (tolerância declarada abaixo) e prova que a aceitação
vem do dono (`WilsonBand`).
"""

from __future__ import annotations

import math
from statistics import NormalDist

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    h1_gate_power as h1_gate_power_module,
)
from financial_forecasting.features.evaluation.domain.services.h1_gate_power import H1GatePower
from financial_forecasting.features.evaluation.domain.services.wilson_band import WilsonBand
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    violation_rate_for,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
    ScenarioRole,
    TailDeviation,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload

_BRUTE_TOLERANCE = 1e-12
"""Decomposição condicional x soma dupla bruta (ADR 0.0.0021: tolerância declarada)."""

_SPEC = Preregistration.from_mapping(valid_payload()).h1_gate
_Z90 = NormalDist().inv_cdf(0.9)


def _deviation(lower: float, upper: float) -> TailDeviation:
    return TailDeviation(label="s", role=ScenarioRole.PRIMARY, lower_rate=lower, upper_rate=upper)


def _location(sigmas: float) -> TailDeviation:
    normal = NormalDist()
    return _deviation(normal.cdf(-_Z90 - sigmas), 1.0 - normal.cdf(_Z90 - sigmas))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("deviation", "expected"),
    [
        pytest.param(_deviation(0.10, 0.10), 0.041, id="calibrated"),
        pytest.param(_location(0.2), 0.840, id="location-0.2-sigma"),
        pytest.param(_location(0.3), 0.996, id="location-0.3-sigma"),
        pytest.param(_deviation(0.125, 0.125), 0.580, id="coverage-75"),
        pytest.param(_deviation(0.075, 0.075), 0.536, id="coverage-85"),
    ],
)
def test_power_doc_table_n500(deviation: TailDeviation, expected: float) -> None:
    failure = H1GatePower.failure_probability(n=500, spec=_SPEC, deviation=deviation)

    assert round(failure, 3) == expected


def _accepted(n: int, nominal: float) -> list[int]:
    return [
        c
        for c in range(n + 1)
        if WilsonBand.evaluate(
            horizon=1, count=c, n=n, nominal=nominal, band_level=_SPEC.gate_band_level
        ).contains_nominal
    ]


def _brute_failure(n: int, deviation: TailDeviation) -> float:
    p_l, p_u = deviation.lower_rate, deviation.upper_rate
    lower_ok = set(_accepted(n, violation_rate_for(HitKind.LOWER_TAIL, (_SPEC.lower_level,))))
    upper_ok = set(_accepted(n, violation_rate_for(HitKind.UPPER_TAIL, (_SPEC.upper_level,))))
    passing = 0.0
    for lower in range(n + 1):
        for upper in range(n + 1 - lower):
            if lower in lower_ok and upper in upper_ok:
                middle = n - lower - upper
                passing += (
                    math.factorial(n)
                    / (math.factorial(lower) * math.factorial(upper) * math.factorial(middle))
                    * p_l**lower
                    * p_u**upper
                    * (1.0 - p_l - p_u) ** middle
                )
    return 1.0 - passing


@pytest.mark.unit
@pytest.mark.parametrize("n", [5, 20])
@pytest.mark.parametrize(
    "deviation",
    [_deviation(0.10, 0.10), _deviation(0.2, 0.05), _location(0.2)],
    ids=["calibrated", "asymmetric", "location"],
)
def test_power_equals_brute_double_sum(n: int, deviation: TailDeviation) -> None:
    failure = H1GatePower.failure_probability(n=n, spec=_SPEC, deviation=deviation)

    assert failure == pytest.approx(_brute_failure(n, deviation), abs=_BRUTE_TOLERANCE)


class _AlwaysContains:
    @staticmethod
    def evaluate(**_: object) -> object:
        class _Report:
            contains_nominal = True

        return _Report()


@pytest.mark.unit
def test_power_acceptance_from_wilson_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    deviation = _deviation(0.125, 0.125)
    before = H1GatePower.failure_probability(n=200, spec=_SPEC, deviation=deviation)

    monkeypatch.setattr(h1_gate_power_module, "WilsonBand", _AlwaysContains)

    assert before > 0.1  # noqa: PLR2004 — o cenário reprova com frequência real
    after = H1GatePower.failure_probability(n=200, spec=_SPEC, deviation=deviation)
    assert after == pytest.approx(0.0, abs=_BRUTE_TOLERANCE)


@pytest.mark.unit
@pytest.mark.parametrize("n", [0, True, 2.0], ids=["zero", "bool", "float"])
def test_power_invalid_n_rejected(n: int) -> None:
    with pytest.raises(ValueError, match="n must be an int >= 1"):
        H1GatePower.failure_probability(n=n, spec=_SPEC, deviation=_deviation(0.1, 0.1))


# --- extras da auditoria de testes (rodada 1) -----------------------------------------

_TINY_N_TOLERANCE = 1e-15


@pytest.mark.unit
@pytest.mark.parametrize("n", [2, 3])
def test_power_brute_small_n_all_upper(n: int) -> None:
    """Auditoria P2: taxa superior alta (U pode esgotar o restante, u == n - l)."""
    deviation = _deviation(0.1, 0.6)

    failure = H1GatePower.failure_probability(n=n, spec=_SPEC, deviation=deviation)

    assert failure == pytest.approx(_brute_failure(n, deviation), abs=_TINY_N_TOLERANCE)
