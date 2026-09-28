"""Unit test do `DegeneracyGate` (A6/A1b/A10, C3/C4/C6; ADR 0.0.0011 e 6.1.0003).

Fixtures analíticas: amplitudes **diádicas** (0.25, 0.125, exatamente representáveis
em float64) para a fronteira da tolerância, de modo que `≤` é testado sem ruído de
arredondamento.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
    DegeneracyReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_SPREAD = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_DIRAC = (0.004,) * 7
# Grade de 0.25 a 0.5: amplitude 0.25 exata (diádica).
_DYADIC = (0.25, 0.25, 0.3125, 0.375, 0.4375, 0.5, 0.5)
_DYADIC_SPREAD = 0.25
_HALF_DYADIC_SPREAD = 0.125
# Só o par interno (0.25, 0.75) colapsa; os extremos seguem abertos.
_INNER_COLLAPSE = (-0.03, -0.02, 0.0, 0.0, 0.0, 0.02, 0.03)
_TOLERANCE = 1e-9
_HORIZON = 2
_HALF = 0.5
_THIRD = 1 / 3


def _report(**overrides: object) -> DegeneracyReport:
    """Um `DegeneracyReport` coerente de 2 linhas, com campos sobrescrevíveis."""
    fields: dict[str, object] = {
        "horizon": 1,
        "n_points": 2,
        "target_timestamps": ("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00"),
        "tolerance": 0.0,
        "degenerate": (True, False),
        "n_degenerate": 1,
        "rate": 0.5,
        "pair_collapse_rates": ((0.05, 0.95, 0.0),),
    }
    fields.update(overrides)
    return DegeneracyReport(**fields)  # type: ignore[arg-type]


# --- A6 — veredito por linha -------------------------------------------------------


@pytest.mark.unit
def test_dirac_row_is_degenerate_with_zero_tolerance(make_series: SeriesFactory) -> None:
    """A6: todos os quantis iguais → degenerada mesmo com `tolerance = 0.0`."""
    series = make_series([_DIRAC, _SPREAD], [0.0, 0.0])

    report = DegeneracyGate.evaluate(series, tolerance=0.0)

    assert report.degenerate == (True, False)


@pytest.mark.unit
def test_dyadic_boundary_marks_at_equal_tolerance(make_series: SeriesFactory) -> None:
    """A6: amplitude 0.25 com `tolerance = 0.25` → marca (a regra é `≤`)."""
    series = make_series([_DYADIC], [0.3])

    assert DegeneracyGate.evaluate(series, tolerance=_DYADIC_SPREAD).degenerate == (True,)


@pytest.mark.unit
def test_dyadic_boundary_does_not_mark_below(make_series: SeriesFactory) -> None:
    """A6: amplitude 0.25 com `tolerance = 0.125` → não marca."""
    series = make_series([_DYADIC], [0.3])

    assert DegeneracyGate.evaluate(series, tolerance=_HALF_DYADIC_SPREAD).degenerate == (False,)


@pytest.mark.unit
def test_inner_pair_collapse_is_diagnostic_only(make_series: SeriesFactory) -> None:
    """A6: colapso só do par interno não marca a linha e aparece em `pair_collapse_rates`."""
    series = make_series([_INNER_COLLAPSE, _SPREAD], [0.0, 0.0])

    report = DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)

    assert report.degenerate == (False, False)
    assert report.pair_collapse_rates == (
        (0.05, 0.95, 0.0),
        (0.1, 0.9, 0.0),
        (0.25, 0.75, _HALF),
    )


@pytest.mark.unit
def test_rate_on_mixed_series(make_series: SeriesFactory) -> None:
    """A6: série mista 1 de 3 degenerada → `n_degenerate = 1`, `rate = 1/3`; a taxa de
    colapso por par conta só entre as 2 não-degeneradas."""
    series = make_series([_SPREAD, _DIRAC, _INNER_COLLAPSE], [0.0, 0.0, 0.0])

    report = DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)

    assert report.degenerate == (False, True, False)
    assert report.n_degenerate == 1
    assert report.rate == _THIRD
    assert report.pair_collapse_rates[-1] == (0.25, 0.75, _HALF)


@pytest.mark.unit
def test_same_verdict_for_same_raw_values_in_different_order(make_series: SeriesFactory) -> None:
    """A6/I9: mesmos valores brutos em ordens diferentes (via `from_raw`) → mesmo veredito."""
    shuffled = (0.02, -0.03, 0.0, 0.03, -0.01, 0.01, -0.02)
    ordered = make_series([_SPREAD], [0.0])
    crossed = make_series([shuffled], [0.0])

    for tolerance in (0.0, 0.05, 0.06, 0.1):
        first = DegeneracyGate.evaluate(ordered, tolerance=tolerance)
        second = DegeneracyGate.evaluate(crossed, tolerance=tolerance)
        assert first.degenerate == second.degenerate


@pytest.mark.unit
def test_fully_degenerate_series_has_none_pair_rates(make_series: SeriesFactory) -> None:
    """A6/C6: série 100 % degenerada → taxa 1 e `None` (não 0 nem nan) por par."""
    series = make_series([_DIRAC, _DIRAC], [0.0, 0.01])

    report = DegeneracyGate.evaluate(series, tolerance=0.0)

    assert report.rate == 1.0
    assert all(rate is None for _, _, rate in report.pair_collapse_rates)
    assert [pair[:2] for pair in report.pair_collapse_rates] == list(series.symmetric_pairs)


@pytest.mark.unit
def test_gate_never_excludes_or_alters_rows(make_series: SeriesFactory) -> None:
    """I8/I9: o gate não altera a série; a máscara tem uma entrada por linha."""
    series = make_series([_SPREAD, _DIRAC], [0.0, 0.0])
    before = [series.scored_values(i) for i in range(series.n_points)]

    report = DegeneracyGate.evaluate(series, tolerance=0.0)

    assert len(report.degenerate) == series.n_points
    assert [series.scored_values(i) for i in range(series.n_points)] == before


# --- C3 — tolerância inválida ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "tolerance",
    [-1e-9, math.nan, math.inf, -math.inf, None, True],
    ids=["negative", "nan", "inf", "-inf", "none", "bool"],
)
def test_invalid_tolerance_raises(make_series: SeriesFactory, tolerance: object) -> None:
    series = make_series([_SPREAD], [0.0])

    with pytest.raises(ValueError, match="tolerance must be a finite number >= 0"):
        DegeneracyGate.evaluate(series, tolerance=tolerance)  # type: ignore[arg-type]


@pytest.mark.unit
def test_tolerance_is_keyword_only_without_default() -> None:
    """ADR 6.1.0003: `tolerance` keyword-only e sem default."""
    parameter = inspect.signature(DegeneracyGate.evaluate).parameters["tolerance"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


# --- Rastro de auditoria e A10 ---------------------------------------------------------


@pytest.mark.unit
def test_report_carries_audit_trail_horizon_and_all_points(make_series: SeriesFactory) -> None:
    """Rastro: timestamps e tolerância da chamada; A10: `horizon` e `n_points = T`."""
    series = make_series([_SPREAD, _DIRAC, _SPREAD], [0.0, 0.0, 0.0], horizon=_HORIZON)

    report = DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)

    assert report.target_timestamps == series.target_timestamps
    assert report.tolerance == _TOLERANCE
    assert report.horizon == series.horizon
    assert report.n_points == series.n_points


# --- A1b — pontua-se o rearranjado ----------------------------------------------------


@pytest.mark.unit
def test_gate_scores_guardrail_not_raw(make_series: SeriesFactory) -> None:
    """A1b: extremos trocados no bruto → no raw o par (0.05, 0.95) teria
    `q_u - q_l = -0.06 ≤ tolerance`; no rearranjado é 0.06 e não colapsa. O veredito
    por linha (amplitude) é o mesmo nos dois vetores (I9)."""
    raw = (0.03, -0.02, -0.01, 0.0, 0.01, 0.02, -0.03)
    series = make_series([raw], [0.0])
    tolerance = 0.001
    assert raw[-1] - raw[0] <= tolerance  # premissa: no bruto o par "colapsaria"

    report = DegeneracyGate.evaluate(series, tolerance=tolerance)

    assert report.pair_collapse_rates[0] == (0.05, 0.95, 0.0)
    assert report.degenerate == ((max(raw) - min(raw)) <= tolerance,)


# --- C4 — DegeneracyReport mal-formado, um teste por ramo -----------------------------


@pytest.mark.unit
def test_report_with_mask_of_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="degenerate mask has 3 rows"):
        _report(degenerate=(True, False, False))


@pytest.mark.unit
def test_report_with_timestamps_of_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="target_timestamps has 1 rows"):
        _report(target_timestamps=("2024-01-02T00:00:00+00:00",))


@pytest.mark.unit
def test_report_with_inconsistent_n_degenerate_raises() -> None:
    with pytest.raises(ValueError, match="differs from the mask sum"):
        _report(n_degenerate=2, rate=1.0)


@pytest.mark.unit
def test_report_with_inconsistent_rate_raises() -> None:
    with pytest.raises(ValueError, match=r"rate=0.25 differs"):
        _report(rate=0.25)


@pytest.mark.unit
def test_report_with_zero_points_raises() -> None:
    with pytest.raises(ValueError, match="n_points >= 1"):
        _report(n_points=0, degenerate=(), target_timestamps=(), n_degenerate=0, rate=0.0)


@pytest.mark.unit
def test_well_formed_report_is_accepted() -> None:
    assert _report().rate == _HALF
