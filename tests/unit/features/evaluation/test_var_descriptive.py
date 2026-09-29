"""Unit test do `VarDescriptive` - VaR descritivo por cauda como re-rotulação.

Prova (concept 6.3 A9, I1, I2, I9, C7, C9; doc §7.5, conv. 24): um `VarTailBacktest`
por τ ≠ 0.5 na ordem da grade, `kind` e `var_level` pela regra do τ, cada backtest
igual ao `ChristoffersenTest.evaluate(HitSequences....)` montado no teste, o rótulo
descritivo validado e a série 100 % degenerada com toda cauda não aplicável.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
    IndependenceStatus,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.services.var_descriptive import (
    VAR_DESCRIPTIVE_LABEL,
    VarDescriptive,
    VarDescriptiveReport,
    VarTailBacktest,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
)

SeriesFactory = Callable[..., CoverageSeries]

_LEVELS = (0.02, 0.05, 0.5, 0.95, 0.98)
_GRID = (-0.04, -0.03, 0.0, 0.03, 0.04)
_DIRAC = (0.001,) * 5
_TOLERANCE = 1e-9
_MIN_VIOLATIONS = 1
_H7 = 7
_VAR_98 = 0.98


def _series(make_series: SeriesFactory, *, horizon: int = 1) -> CoverageSeries:
    """T = 8, uma linha degenerada; violações nas duas caudas."""
    grids = [_GRID, _GRID, _DIRAC, _GRID, _GRID, _GRID, _GRID, _GRID]
    realized = [-0.05, 0.0, 0.0, 0.035, -0.035, 0.045, 0.0, -0.041]
    return make_series(grids, realized, levels=_LEVELS, horizon=horizon)


def _report(make_series: SeriesFactory, *, horizon: int = 1) -> VarDescriptiveReport:
    return VarDescriptive.backtest(
        _series(make_series, horizon=horizon),
        tolerance=_TOLERANCE,
        min_violations=_MIN_VIOLATIONS,
    )


@pytest.mark.unit
def test_grid_order_one_tail_per_non_median_level(make_series: SeriesFactory) -> None:
    """A9: 4 caudas na ordem da grade; 0.02/0.05 inferiores, 0.95/0.98 superiores."""
    report = _report(make_series)

    assert tuple(tail.level for tail in report.tails) == (0.02, 0.05, 0.95, 0.98)
    assert tuple(tail.kind for tail in report.tails) == (
        HitKind.LOWER_TAIL,
        HitKind.LOWER_TAIL,
        HitKind.UPPER_TAIL,
        HitKind.UPPER_TAIL,
    )


@pytest.mark.unit
def test_var_level_relabels_both_extreme_tails_as_98(make_series: SeriesFactory) -> None:
    """A9/I9: `var_level == 0.98` para τ = 0.02 (1 - τ) e para τ = 0.98 (τ), exato."""
    tails = {tail.level: tail for tail in _report(make_series).tails}

    assert tails[0.02].var_level == _VAR_98
    assert tails[0.98].var_level == _VAR_98
    assert tails[0.05].var_level == 1.0 - 0.05
    assert tails[0.95].var_level == 0.95  # noqa: PLR2004


@pytest.mark.unit
def test_matches_evaluate_of_the_tail_hit_sequence(make_series: SeriesFactory) -> None:
    """A9: cada backtest == `ChristoffersenTest.evaluate(HitSequences.<cauda>(...))`."""
    series = _series(make_series)

    report = VarDescriptive.backtest(series, tolerance=_TOLERANCE, min_violations=_MIN_VIOLATIONS)

    for tail in report.tails:
        build = HitSequences.lower_tail if tail.level < 0.5 else HitSequences.upper_tail  # noqa: PLR2004
        sequence = build(series, level=tail.level, tolerance=_TOLERANCE)
        expected = ChristoffersenTest.evaluate(sequence, min_violations=_MIN_VIOLATIONS)
        assert tail.backtest == expected
        assert tail.backtest.includes_degenerate is False  # só a variante mascarada


@pytest.mark.unit
def test_descriptive_label_is_required(make_series: SeriesFactory) -> None:
    """A9/I9: rótulo exato no relatório; rótulo divergente ergue."""
    report = _report(make_series)

    assert report.label == VAR_DESCRIPTIVE_LABEL
    assert VAR_DESCRIPTIVE_LABEL == "VaR descritivo — sem claim de gestão de risco"
    with pytest.raises(ValueError, match="must carry VAR_DESCRIPTIVE_LABEL"):
        VarDescriptiveReport(horizon=1, tails=report.tails, label="VaR")


@pytest.mark.unit
def test_all_tails_not_applicable_on_fully_degenerate_series(make_series: SeriesFactory) -> None:
    """A9/C7: série 100 % degenerada → toda cauda sem POF e com NO_TRANSITIONS."""
    series = make_series([_DIRAC, _DIRAC, _DIRAC], [0.01, -0.02, 0.0], levels=_LEVELS)

    report = VarDescriptive.backtest(series, tolerance=0.0, min_violations=_MIN_VIOLATIONS)

    assert len(report.tails) == 4  # noqa: PLR2004
    for tail in report.tails:
        assert tail.backtest.statistics.kupiec_pof is None
        assert tail.backtest.statistics.independence_status is IndependenceStatus.NO_TRANSITIONS


@pytest.mark.unit
def test_var_horizon_is_the_series_horizon(make_series: SeriesFactory) -> None:
    """A9/I1: `report.horizon == series.horizon`; cauda de outro horizonte ergue."""
    report = _report(make_series, horizon=_H7)

    assert report.horizon == _H7
    assert all(tail.backtest.horizon == _H7 for tail in report.tails)
    with pytest.raises(ValueError, match="every tail backtest must have horizon=1"):
        VarDescriptiveReport(horizon=1, tails=report.tails)


@pytest.mark.unit
def test_var_horizon_invalid_raises(make_series: SeriesFactory) -> None:
    report = _report(make_series)

    with pytest.raises(ValueError, match="horizon must be an int >= 1"):
        dataclasses.replace(report, horizon=0)


def _tails(make_series: SeriesFactory) -> dict[float, VarTailBacktest]:
    return {tail.level: tail for tail in _report(make_series).tails}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "overrides", "match"),
    [
        (0.02, {"var_level": 0.02}, "var_level must be 0.98"),
        (0.02, {"kind": HitKind.UPPER_TAIL}, "kind must be lower_tail"),
        (0.98, {"kind": HitKind.LOWER_TAIL}, "kind must be upper_tail"),
        (0.02, {"level": 0.5}, r"level 0\.5 \(the median\) is not a VaR tail"),
        (0.02, {"level": 1.5}, r"level must be in \(0, 1\)"),
        (0.02, {"level": 0.05, "var_level": 1.0 - 0.05}, "backtest must be of the same tail"),
    ],
    ids=[
        "var-level-wrong",
        "kind-swapped-lower",
        "kind-swapped-upper",
        "median-level",
        "level-outside-unit",
        "backtest-of-another-level",
    ],
)
def test_tail_incoherent_raises(
    make_series: SeriesFactory, level: float, overrides: dict[str, object], match: str
) -> None:
    """A9/C9: cada ramo do `VarTailBacktest.__post_init__`."""
    tail = _tails(make_series)[level]

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(tail, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_tail_incoherent_backtest_kind_mismatch_raises(make_series: SeriesFactory) -> None:
    """C9: cauda superior com o backtest da inferior do mesmo τ ergue."""
    series = _series(make_series)
    lower_backtest = ChristoffersenTest.evaluate(
        HitSequences.lower_tail(series, level=0.95, tolerance=_TOLERANCE), min_violations=0
    )

    with pytest.raises(ValueError, match="backtest must be of the same tail"):
        VarTailBacktest(
            kind=HitKind.UPPER_TAIL, level=0.95, var_level=0.95, backtest=lower_backtest
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tails_of", "match"),
    [("empty", "needs at least one tail"), ("reversed", "must follow the grid order")],
    ids=["empty-tails", "tails-out-of-order"],
)
def test_tail_incoherent_report_raises(
    make_series: SeriesFactory, tails_of: str, match: str
) -> None:
    """A9/C9: `tails = ()` e caudas fora da ordem da grade erguem."""
    report = _report(make_series)
    tails = () if tails_of == "empty" else tuple(reversed(report.tails))

    with pytest.raises(ValueError, match=match):
        VarDescriptiveReport(horizon=1, tails=tails)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["tolerance", "min_violations"])
def test_var_signature_keyword_only_without_default(name: str) -> None:
    """A9: `tolerance` e `min_violations` keyword-only e sem default."""
    parameter = inspect.signature(VarDescriptive.backtest).parameters[name]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


# --- C9 — variante mascarada, série inteira e parâmetros comuns (Checkpoint C bloco 3) ------


@pytest.mark.unit
def test_tail_incoherent_without_gaps_variant_raises(make_series: SeriesFactory) -> None:
    """C9: a cauda de VaR é a variante mascarada — backtest "sem lacunas" ergue."""
    series = _series(make_series)
    backtest = ChristoffersenTest.evaluate(
        HitSequences.lower_tail(series, level=0.02, tolerance=_TOLERANCE, include_degenerate=True),
        min_violations=_MIN_VIOLATIONS,
    )

    with pytest.raises(ValueError, match="masked variant of the whole series"):
        VarTailBacktest(kind=HitKind.LOWER_TAIL, level=0.02, var_level=_VAR_98, backtest=backtest)


@pytest.mark.unit
def test_tail_incoherent_dgt_subseries_raises(make_series: SeriesFactory) -> None:
    """C9: a cauda de VaR é a série inteira — backtest de sub-série DGT ergue."""
    series = _series(make_series, horizon=_H7)
    sub = HitSequences.lower_tail(series, level=0.02, tolerance=_TOLERANCE).dgt_partition()[0]
    backtest = ChristoffersenTest.evaluate(sub, min_violations=_MIN_VIOLATIONS)

    with pytest.raises(ValueError, match="masked variant of the whole series"):
        VarTailBacktest(kind=HitKind.LOWER_TAIL, level=0.02, var_level=_VAR_98, backtest=backtest)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tolerance", "min_violations"),
    [(0.5, _MIN_VIOLATIONS), (_TOLERANCE, 0)],
    ids=["other-tolerance", "other-min-violations"],
)
def test_tail_incoherent_report_mixed_settings_raise(
    make_series: SeriesFactory, tolerance: float, min_violations: int
) -> None:
    """C9: todas as caudas compartilham a mesma tolerância e o mesmo `min_violations`."""
    series = _series(make_series)
    report = _report(make_series)
    other = VarDescriptive.backtest(series, tolerance=tolerance, min_violations=min_violations)
    tails = (report.tails[0], *other.tails[1:])

    with pytest.raises(ValueError, match="same tolerance and min_violations"):
        VarDescriptiveReport(horizon=1, tails=tails)
