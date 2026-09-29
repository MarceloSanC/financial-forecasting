"""Unit test do `CoverageMetrics` (A5/A7/A1b/A10/I10, C3/C4/C5/C8; ADR 6.1.0004).

Fixtures analíticas (ADR 0.0.0021; concept I12): ĉ, PICP e MPIW não têm oráculo de
biblioteca — os valores esperados são contados à mão sobre séries pequenas.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    coverage_metrics as coverage_metrics_module,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    MPIW_LABEL,
    CoverageMetrics,
    CoverageReport,
    PairCoverage,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import CrpsScore
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    IntervalScore,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
    pair_nominal,
)

SeriesFactory = Callable[..., CoverageSeries]

# Tolerâncias declaradas (ADR 0.0.0021): ruído de soma float64.
_REL_TOL = 1e-12
_ABS_TOL = 1e-12
_TOLERANCE = 1e-9

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_SPREAD = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_WIDE = (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06)
_DIRAC = (0.004,) * 7
_HORIZON = 4
# Linha de amplitude exatamente 0.25 (diádica): degenerada com tolerância 0.25.
_DYADIC_SPREAD_ROW = (0.25, 0.25, 0.3125, 0.375, 0.4375, 0.5, 0.5)
_DYADIC_TOLERANCE = 0.25
_HALF = 0.5
_ONE_THIRD = 1 / 3
_TWO_THIRDS = 2 / 3
_ONE = 1.0


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _mixed_series(make_series: SeriesFactory, **kwargs: object) -> CoverageSeries:
    """T = 5: linhas 1 e 3 degeneradas; realizados sem empate com a grade."""
    grids = [_SPREAD, _DIRAC, _WIDE, _DIRAC, _SPREAD]
    realized = [0.015, 0.1, -0.05, -0.2, 0.035]
    return make_series(grids, realized, **kwargs)


# --- A5 — ĉ, PICP, MPIW, nominal ----------------------------------------------------


@pytest.mark.unit
def test_marginal_coverage_counts_tie_as_covered(make_series: SeriesFactory) -> None:
    """A5/I6: ĉ usa 1{y ≤ q̂} — y = q̂ conta como coberto."""
    series = make_series([_SPREAD], [0.0])  # y = q̂(0.5)

    per_level = dict(CoverageMetrics.evaluate(series, tolerance=_TOLERANCE).per_level)

    assert per_level[0.5] == _ONE
    assert per_level[0.25] == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("y", [-0.03, 0.03], ids=["y-at-lower", "y-at-upper"])
def test_picp_counts_interval_bounds_as_inside(make_series: SeriesFactory, y: float) -> None:
    """A5/I6: PICP usa [l ≤ y ≤ u] — as duas bordas contam como dentro."""
    series = make_series([_SPREAD], [y])

    pair = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE).per_pair[0]

    assert (pair.lower_level, pair.upper_level) == (0.05, 0.95)
    assert pair.picp == _ONE


@pytest.mark.unit
def test_picp_mpiw_and_marginal_coverage_by_hand(make_series: SeriesFactory) -> None:
    """A5: série mista — valores contados à mão sobre as 3 linhas não-degeneradas."""
    series = _mixed_series(make_series)

    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    # Linhas avaliadas: 0 (y=0.015, SPREAD), 2 (y=-0.05, WIDE), 4 (y=0.035, SPREAD).
    outer = report.per_pair[0]
    assert outer.picp == _TWO_THIRDS  # linhas 0 e 2 em [l, u]; 0.035 > 0.03 na linha 4
    assert _close(outer.mpiw, (0.06 + 0.12 + 0.06) / 3)  # MPIW na unidade de y
    per_level = dict(report.per_level)
    assert per_level[0.05] == 0.0  # nenhum y abaixo de q(0.05) nas 3 linhas
    assert per_level[0.5] == _ONE_THIRD  # só y = -0.05 ≤ 0.0
    assert per_level[0.95] == _TWO_THIRDS


@pytest.mark.unit
def test_picp_equals_difference_of_marginal_coverages_without_ties(
    make_series: SeriesFactory,
) -> None:
    """A5: sem empates, PICP(τ_l, τ_u) = ĉ(τ_u) - ĉ(τ_l) em todo par."""
    series = _mixed_series(make_series)

    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    coverage = dict(report.per_level)
    for pair in report.per_pair:
        assert _close(pair.picp, coverage[pair.upper_level] - coverage[pair.lower_level])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        ((0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.98), (0.96, 0.9, 0.8, 0.5)),
    ],
)
def test_nominal_is_exact_from_the_grid(
    make_series: SeriesFactory, levels: tuple[float, ...], expected: tuple[float, ...]
) -> None:
    """A5/I7: nominal = 1 - 2·τ_l por igualdade EXATA de float, derivado da grade."""
    grid = tuple(float(k) for k in range(len(levels)))
    series = make_series([grid], [0.5], levels=levels)

    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    assert tuple(pair.nominal for pair in report.per_pair) == expected


# --- Predicados FA7 com dono único (concept 6.3 I3) -------------------------------------


@pytest.mark.unit
def test_consumes_fa7_predicates_not_an_inline_copy(
    make_series: SeriesFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I3 (6.3): o serviço lê ĉ e PICP pelos predicados de `coverage_series.py` — trocar
    o nome no namespace do módulo muda o resultado, logo não há cópia própria da regra.

    Sem o patch, a série mista dá ĉ(0.05) = 0 e PICP externo = 2/3; com
    `is_at_or_below → True` todo ĉ vira 1.0 e com `is_inside_closed → False` todo PICP
    vira 0.0.
    """
    series = _mixed_series(make_series)
    baseline = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    assert dict(baseline.per_level)[0.05] == 0.0
    assert baseline.per_pair[0].picp == _TWO_THIRDS

    monkeypatch.setattr(coverage_metrics_module, "is_at_or_below", lambda *_: True)
    monkeypatch.setattr(coverage_metrics_module, "is_inside_closed", lambda *_: False)
    patched = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    assert all(coverage == _ONE for _, coverage in patched.per_level)
    assert all(pair.picp == 0.0 for pair in patched.per_pair)


# --- Rótulo descritivo do MPIW (concept 6.3 D10, I9, A11) --------------------------------


@pytest.mark.unit
def test_every_pair_carries_mpiw_label(make_series: SeriesFactory) -> None:
    """A11/I9: todo `PairCoverage` devolvido pelo serviço traz `MPIW_LABEL`."""
    report = CoverageMetrics.evaluate(_mixed_series(make_series), tolerance=_TOLERANCE)

    assert report.per_pair
    assert all(pair.mpiw_label == MPIW_LABEL for pair in report.per_pair)
    assert MPIW_LABEL == "MPIW — sharpness descritiva, não-inferencial"


@pytest.mark.unit
@pytest.mark.parametrize("label", ["MPIW", "", MPIW_LABEL + " "], ids=["bare", "empty", "padded"])
def test_divergent_mpiw_label_raises(label: str) -> None:
    """A11/I9: rótulo diferente de `MPIW_LABEL` (exato) ergue na construção."""
    with pytest.raises(ValueError, match="must carry MPIW_LABEL"):
        PairCoverage(
            lower_level=0.05, upper_level=0.95, nominal=0.9, picp=_HALF, mpiw=0.1, mpiw_label=label
        )


# --- interval_widths e C8 ---------------------------------------------------------------


@pytest.mark.unit
def test_mpiw_and_widths_ignore_degenerate_row_with_nonzero_width(
    make_series: SeriesFactory,
) -> None:
    """MPIW e `interval_widths` somam SÓ as linhas não-degeneradas (numerador e
    denominador): a linha degenerada tem largura 0.25 ≠ 0 (tolerância 0.25, diádica),
    então uma soma sobre as T linhas com denominador das mantidas daria outro valor."""
    wide = (-0.5, -0.25, -0.125, 0.0, 0.125, 0.25, 0.5)  # largura do par externo 1.0
    series = make_series([wide, _DYADIC_SPREAD_ROW, wide], [0.0, 0.3, 0.1])

    report = CoverageMetrics.evaluate(series, tolerance=_DYADIC_TOLERANCE)
    widths = CoverageMetrics.interval_widths(series, tolerance=_DYADIC_TOLERANCE, pair=(0.05, 0.95))

    assert report.degeneracy.degenerate == (False, True, False)
    assert report.per_pair[0].mpiw == 1.0
    assert widths == (1.0, 1.0)


@pytest.mark.unit
def test_interval_widths_on_non_degenerate_rows(make_series: SeriesFactory) -> None:
    """`interval_widths`: T - n_degenerate larguras u - l, na ordem da série, média = MPIW."""
    series = _mixed_series(make_series)

    widths = CoverageMetrics.interval_widths(series, tolerance=_TOLERANCE, pair=(0.1, 0.9))

    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    assert len(widths) == series.n_points - report.degeneracy.n_degenerate
    assert all(_close(a, b) for a, b in zip(widths, (0.04, 0.08, 0.04), strict=True))
    assert _close(sum(widths) / len(widths), report.per_pair[1].mpiw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "pair", [(0.05, 0.9), (0.9, 0.1), (0.1, 0.9 + 1e-12)], ids=["mixed", "reversed", "near"]
)
def test_interval_widths_rejects_unknown_pair(
    make_series: SeriesFactory, pair: tuple[float, float]
) -> None:
    """C8: par fora de `symmetric_pairs` (igualdade exata de float) ergue."""
    series = _mixed_series(make_series)

    with pytest.raises(ValueError, match="is not one of the series symmetric pairs"):
        CoverageMetrics.interval_widths(series, tolerance=_TOLERANCE, pair=pair)


# --- A7 / C5 / ADR 6.1.0004 --------------------------------------------------------------


@pytest.mark.unit
def test_mixed_series_proper_scores_on_all_rows_coverage_on_non_degenerate(
    make_series: SeriesFactory,
) -> None:
    """A7: proper scores com `n_points = T`; cobertura com `n_evaluated = T - n_degenerate`."""
    series = _mixed_series(make_series)

    coverage = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    assert PinballScore.score(series).n_points == series.n_points
    assert CrpsScore.score(series).n_points == series.n_points
    assert IntervalScore.score(series).n_points == series.n_points
    assert coverage.n_evaluated == series.n_points - coverage.degeneracy.n_degenerate
    assert coverage.n_evaluated == series.n_points - 2
    assert coverage.applicable is True


@pytest.mark.unit
def test_fully_degenerate_series_is_not_applicable(make_series: SeriesFactory) -> None:
    """A7/C5: 100 % degenerada → `applicable = False`, listas vazias; proper scores finitos
    (caso declarado dos baselines pontuais)."""
    series = make_series([_DIRAC, _DIRAC, _DIRAC], [0.01, -0.02, 0.004])

    report = CoverageMetrics.evaluate(series, tolerance=0.0)

    assert report.applicable is False
    assert report.n_evaluated == 0
    assert report.per_level == ()
    assert report.per_pair == ()
    assert math.isfinite(PinballScore.score(series).grid_mean)
    assert math.isfinite(CrpsScore.score(series).crps_q)
    assert all(math.isfinite(p.mean_score) for p in IntervalScore.score(series).per_pair)


@pytest.mark.unit
def test_embedded_degeneracy_is_the_gate_of_the_same_series(make_series: SeriesFactory) -> None:
    """ADR 6.1.0004: `CoverageReport.degeneracy` == o gate da mesma série e tolerância."""
    series = _mixed_series(make_series)

    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)

    assert report.degeneracy == DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)


@pytest.mark.unit
def test_different_masks_give_different_reports(make_series: SeriesFactory) -> None:
    """C4: mesmo T e horizonte, máscaras diferentes → relatórios diferentes."""
    first = make_series([_SPREAD, _DIRAC, _SPREAD], [0.0, 0.0, 0.0])
    second = make_series([_DIRAC, _SPREAD, _SPREAD], [0.0, 0.0, 0.0])

    report_a = CoverageMetrics.evaluate(first, tolerance=_TOLERANCE)
    report_b = CoverageMetrics.evaluate(second, tolerance=_TOLERANCE)

    assert report_a.degeneracy.degenerate != report_b.degeneracy.degenerate
    assert report_a != report_b


@pytest.mark.unit
def test_invalid_tolerance_raises(make_series: SeriesFactory) -> None:
    """C3 via o gate interno."""
    with pytest.raises(ValueError, match="tolerance must be"):
        CoverageMetrics.evaluate(_mixed_series(make_series), tolerance=-1.0)


@pytest.mark.unit
@pytest.mark.parametrize("method", ["evaluate", "interval_widths"])
def test_tolerance_is_keyword_only_without_default(method: str) -> None:
    """ADR 6.1.0003: `tolerance` keyword-only e sem default nos dois métodos."""
    parameter = inspect.signature(getattr(CoverageMetrics, method)).parameters["tolerance"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


# --- I10 — largura do IS x MPIW -------------------------------------------------------


@pytest.mark.unit
def test_is_mean_width_equals_mpiw_without_degeneracy(make_series: SeriesFactory) -> None:
    """I10: taxa 0 → `mean_width` do IS ≈ `mpiw` do mesmo par."""
    series = make_series([_SPREAD, _WIDE, _SPREAD], [0.0, 0.01, -0.02])

    coverage = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    interval = IntervalScore.score(series)

    assert coverage.degeneracy.rate == 0.0
    for is_pair, cov_pair in zip(interval.per_pair, coverage.per_pair, strict=True):
        assert _close(is_pair.mean_width, cov_pair.mpiw)


@pytest.mark.unit
def test_is_mean_width_differs_from_mpiw_with_degenerate_row(make_series: SeriesFactory) -> None:
    """I10/D8: uma linha degenerada de largura 0 → `mean_width` (T linhas) ≠ `mpiw`."""
    series = make_series([_SPREAD, _DIRAC, _SPREAD], [0.0, 0.0, 0.0])

    coverage = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    interval = IntervalScore.score(series)

    assert _close(interval.per_pair[0].mean_width, 0.12 / 3)
    assert _close(coverage.per_pair[0].mpiw, 0.06)
    assert not _close(interval.per_pair[0].mean_width, coverage.per_pair[0].mpiw)


# --- A1b — pontua-se o rearranjado ----------------------------------------------------


@pytest.mark.unit
def test_coverage_scores_guardrail_not_raw(make_series: SeriesFactory) -> None:
    """A1b: extremos trocados no bruto — ĉ(0.05) sobre o rearranjado é 0 e sobre o bruto
    seria 1 (y = 0.02 ≤ raw 0.03 no nível 0.05)."""
    raw = (0.03, -0.02, -0.01, 0.0, 0.01, 0.02, -0.03)
    series = make_series([raw], [0.02])
    assert series.realized[0] <= raw[0]  # premissa: no bruto ĉ(0.05) seria 1

    per_level = dict(CoverageMetrics.evaluate(series, tolerance=_TOLERANCE).per_level)

    assert per_level[0.05] == 0.0
    assert per_level[0.95] == _ONE


# --- A10 ------------------------------------------------------------------------------


@pytest.mark.unit
def test_every_report_carries_horizon_and_all_points(make_series: SeriesFactory) -> None:
    """A10: os cinco relatórios de uma mesma série trazem `horizon` e `n_points = T`."""
    series = _mixed_series(make_series, horizon=_HORIZON)

    reports = (
        PinballScore.score(series),
        CrpsScore.score(series),
        IntervalScore.score(series),
        DegeneracyGate.evaluate(series, tolerance=_TOLERANCE),
        CoverageMetrics.evaluate(series, tolerance=_TOLERANCE),
    )

    for report in reports:
        assert report.horizon == series.horizon
        assert report.n_points == series.n_points


# --- C4 — CoverageReport mal-formado, um teste por ramo -------------------------------


def _valid_report(make_series: SeriesFactory) -> CoverageReport:
    return CoverageMetrics.evaluate(_mixed_series(make_series), tolerance=_TOLERANCE)


def _not_applicable_report(make_series: SeriesFactory) -> CoverageReport:
    series = make_series([_DIRAC, _DIRAC], [0.0, 0.0])
    return CoverageMetrics.evaluate(series, tolerance=0.0)


@pytest.mark.unit
def test_report_with_degeneracy_of_other_length_raises(make_series: SeriesFactory) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match=r"degeneracy\.n_points"):
        dataclasses.replace(report, n_points=report.n_points + 1)


@pytest.mark.unit
def test_report_with_degeneracy_of_other_horizon_raises(make_series: SeriesFactory) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match=r"degeneracy\.horizon"):
        dataclasses.replace(report, horizon=report.horizon + 1)


@pytest.mark.unit
def test_report_with_inconsistent_n_evaluated_raises(make_series: SeriesFactory) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match="n_evaluated="):
        dataclasses.replace(report, n_evaluated=report.n_evaluated + 1)


@pytest.mark.unit
def test_applicable_with_zero_evaluated_raises(make_series: SeriesFactory) -> None:
    report = _not_applicable_report(make_series)
    with pytest.raises(ValueError, match="applicable=True requires n_evaluated > 0"):
        dataclasses.replace(report, applicable=True)


@pytest.mark.unit
def test_not_applicable_with_evaluated_rows_raises(make_series: SeriesFactory) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match="applicable=False requires n_evaluated == 0"):
        dataclasses.replace(report, applicable=False, per_level=(), per_pair=())


@pytest.mark.unit
def test_not_applicable_with_per_level_raises(make_series: SeriesFactory) -> None:
    report = _not_applicable_report(make_series)
    with pytest.raises(ValueError, match="must have per_level"):
        dataclasses.replace(report, per_level=((0.05, 0.0), (0.95, 1.0)))


@pytest.mark.unit
def test_not_applicable_with_per_pair_raises(make_series: SeriesFactory) -> None:
    report = _not_applicable_report(make_series)
    pair = PairCoverage(lower_level=0.05, upper_level=0.95, nominal=0.9, picp=1.0, mpiw=0.1)
    with pytest.raises(ValueError, match="must have per_pair"):
        dataclasses.replace(report, per_pair=(pair,))


@pytest.mark.unit
@pytest.mark.parametrize("size", [0, 1], ids=["empty", "one-level"])
def test_applicable_with_per_level_of_wrong_size_raises(
    make_series: SeriesFactory, size: int
) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match="must equal the gate levels"):
        dataclasses.replace(report, per_level=report.per_level[:size])


@pytest.mark.unit
def test_applicable_with_per_pair_of_wrong_size_raises(make_series: SeriesFactory) -> None:
    report = _valid_report(make_series)
    with pytest.raises(ValueError, match="one entry per symmetric pair of the gate"):
        dataclasses.replace(report, per_pair=report.per_pair[:-1])


@pytest.mark.unit
def test_coherent_grid_that_differs_from_the_gate_raises(make_series: SeriesFactory) -> None:
    """C4: `per_level` (K = 5) e `per_pair` (2 pares) coerentes ENTRE SI, mas o gate
    embutido tem 3 pares (K = 7) — a grade do relatório tem de ser a do gate."""
    report = _valid_report(make_series)
    levels = (0.05, 0.1, 0.5, 0.9, 0.95)
    per_level = tuple((level, _HALF) for level in levels)
    per_pair = tuple(
        PairCoverage(
            lower_level=low, upper_level=high, nominal=pair_nominal(low), picp=_HALF, mpiw=0.1
        )
        for low, high in ((0.05, 0.95), (0.1, 0.9))
    )

    with pytest.raises(ValueError, match="must equal the gate levels"):
        dataclasses.replace(report, per_level=per_level, per_pair=per_pair)


@pytest.mark.unit
def test_per_level_with_other_levels_than_the_gate_raises(make_series: SeriesFactory) -> None:
    """C4: K = 7 como o gate, mas com τ que não são os dos pares do gate."""
    report = _valid_report(make_series)
    levels = (0.05, 0.1, 0.2, 0.5, 0.8, 0.9, 0.95)

    with pytest.raises(ValueError, match="must equal the gate levels"):
        dataclasses.replace(report, per_level=tuple((level, _HALF) for level in levels))


@pytest.mark.unit
def test_per_level_missing_the_median_raises(make_series: SeriesFactory) -> None:
    """C4: K = 7 no gate; `per_level` sem o 0.5 (6 níveis, pares intactos) ergue."""
    report = _valid_report(make_series)
    per_level = tuple(entry for entry in report.per_level if entry[0] != _HALF)

    with pytest.raises(ValueError, match="must equal the gate levels"):
        dataclasses.replace(report, per_level=per_level)


@pytest.mark.unit
def test_per_level_with_wrong_central_level_raises(make_series: SeriesFactory) -> None:
    """C4: nível central 0.3 no lugar de 0.5 (pares intactos) ergue."""
    report = _valid_report(make_series)
    per_level = tuple(
        (0.3, cov) if level == _HALF else (level, cov) for level, cov in report.per_level
    )

    with pytest.raises(ValueError, match="must equal the gate levels"):
        dataclasses.replace(report, per_level=per_level)


@pytest.mark.unit
@pytest.mark.parametrize("coverage", [-0.1, 1.5, math.nan], ids=["negative", "above-one", "nan"])
def test_per_level_coverage_outside_unit_interval_raises(
    make_series: SeriesFactory, coverage: float
) -> None:
    report = _valid_report(make_series)
    per_level = ((report.per_level[0][0], coverage), *report.per_level[1:])

    with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
        dataclasses.replace(report, per_level=per_level)


@pytest.mark.unit
@pytest.mark.parametrize("picp", [-0.1, 1.5, math.nan], ids=["negative", "above-one", "nan"])
def test_pair_coverage_with_picp_outside_unit_interval_raises(picp: float) -> None:
    with pytest.raises(ValueError, match="picp must be a fraction"):
        PairCoverage(lower_level=0.05, upper_level=0.95, nominal=0.9, picp=picp, mpiw=0.1)


@pytest.mark.unit
@pytest.mark.parametrize("mpiw", [-0.1, math.nan], ids=["negative", "nan"])
def test_pair_coverage_with_negative_mpiw_raises(mpiw: float) -> None:
    with pytest.raises(ValueError, match="mpiw must be a width"):
        PairCoverage(lower_level=0.05, upper_level=0.95, nominal=0.9, picp=_HALF, mpiw=mpiw)


@pytest.mark.unit
def test_pair_coverage_with_nominal_not_from_grid_raises() -> None:
    """I7 por construção: nominal ≠ 1 - 2·τ_l ergue."""
    with pytest.raises(ValueError, match="nominal must be 1 - 2"):
        PairCoverage(lower_level=0.05, upper_level=0.95, nominal=0.95, picp=_HALF, mpiw=0.1)


@pytest.mark.unit
def test_valid_report_round_trips(make_series: SeriesFactory) -> None:
    """Sanidade: o relatório do serviço atravessa o `__post_init__` (replace sem mudança)."""
    report = _valid_report(make_series)

    assert dataclasses.replace(report) == report


def _centered_grid(width: float) -> tuple[float, ...]:
    """Grade de 7 níveis centrada em 0 cujo par (0.05, 0.95) tem largura `width` exata."""
    half = width / 2
    return (-half, -half / 2, -half / 4, 0.0, half / 4, half / 2, half)


@pytest.mark.unit
def test_interval_widths_preserve_series_order(make_series: SeriesFactory) -> None:
    """`interval_widths` devolve as larguras na ORDEM da série (não ordenadas nem
    invertidas), pulando a linha degenerada — sequência não-palíndroma, Dirac no meio."""
    grids = [
        _centered_grid(0.02),
        _centered_grid(0.06),
        _DIRAC,
        _centered_grid(0.04),
        _centered_grid(0.10),
    ]
    series = make_series(grids, [0.0, 0.0, 0.0, 0.0, 0.0])

    widths = CoverageMetrics.interval_widths(series, tolerance=0.0, pair=(0.05, 0.95))

    assert widths == (0.02, 0.06, 0.04, 0.10)
