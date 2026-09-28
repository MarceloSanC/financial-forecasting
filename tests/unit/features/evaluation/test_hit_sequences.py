"""Unit test do construtor `HitSequences` (intervalo, cauda inferior, cauda superior).

Prova (concept 6.3 A2, I2, I3, I4, C2, C7; ADRs 6.3.0001 item 2, 6.3.0004 item 4,
6.1.0004) com fixtures analíticas contadas à mão (ADR 0.0.0021):

- empates FA7 pelos predicados de dono único; vetor pós-guardrail;
- taxa nominal exata pela regra do `kind`, a partir da grade;
- máscara = `DegeneracyGate` da mesma série e tolerância, como lacuna `None`;
  variante "sem lacunas" explícita; série 100 % degenerada toda `None`;
- identidades de contagem com o `CoverageMetrics` da mesma série (1e-12);
- C2 (par/nível inexistente, tolerância inválida) e a assinatura sem default.
"""

from __future__ import annotations

import inspect
import math
import random
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    hit_sequences as hit_sequences_module,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
)
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
    pair_miscoverage,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
)

SeriesFactory = Callable[..., CoverageSeries]

# Tolerâncias declaradas (ADR 0.0.0021): identidade de float64 e a tolerância do gate.
_ABS_TOL = 1e-12
_TOLERANCE = 1e-9
_SPREAD = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_DIRAC = (0.004,) * 7
_OUTER_PAIR = (0.05, 0.95)
_MEDIAN = 0.5
_WIDE_LEVELS = (0.02, 0.05, 0.5, 0.95, 0.98)
# Série aleatória das identidades de contagem: seed e tamanho declarados.
_IDENTITY_SEED = 20260928
_IDENTITY_T = 60
_IDENTITY_DEGENERATE_EVERY = 7


def _mixed_series(make_series: SeriesFactory) -> CoverageSeries:
    """T = 5: linhas 1 e 3 degeneradas (Dirac); sem empate com a grade."""
    grids = [_SPREAD, _DIRAC, _SPREAD, _DIRAC, _SPREAD]
    return make_series(grids, [0.015, 0.1, -0.05, -0.2, 0.035])


def _all_builders(
    series: CoverageSeries, *, tolerance: float, include_degenerate: bool = False
) -> tuple[HitSequence, HitSequence, HitSequence]:
    """Intervalo do par externo, cauda inferior em 0.05 e superior em 0.95."""
    return (
        HitSequences.interval(
            series, pair=_OUTER_PAIR, tolerance=tolerance, include_degenerate=include_degenerate
        ),
        HitSequences.lower_tail(
            series, level=0.05, tolerance=tolerance, include_degenerate=include_degenerate
        ),
        HitSequences.upper_tail(
            series, level=0.95, tolerance=tolerance, include_degenerate=include_degenerate
        ),
    )


# --- I3 — empates FA7 -------------------------------------------------------------------------


@pytest.mark.unit
def test_fa7_ties_follow_the_single_owner_rule(make_series: SeriesFactory) -> None:
    """A2/I3: y = l e y = u não violam o intervalo; y = q̂_τ viola a cauda inferior e
    não a superior (linhas 0 e 1: bordas do par externo; linha 2: y = q̂(0.5))."""
    series = make_series([_SPREAD, _SPREAD, _SPREAD], [-0.03, 0.03, 0.0])

    interval = HitSequences.interval(series, pair=_OUTER_PAIR, tolerance=_TOLERANCE)
    lower = HitSequences.lower_tail(series, level=_MEDIAN, tolerance=_TOLERANCE)
    upper = HitSequences.upper_tail(series, level=_MEDIAN, tolerance=_TOLERANCE)

    assert interval.violations == (False, False, False)
    assert lower.violations[2] is True
    assert upper.violations[2] is False
    assert lower.violations == (True, False, True)
    assert upper.violations == (False, True, False)


# --- I2 — taxas da grade ----------------------------------------------------------------------


@pytest.mark.unit
def test_grid_rates_are_exact_from_the_kind_rule(make_series: SeriesFactory) -> None:
    """A2/I2: (0.05, 0.95) → pair_miscoverage(0.05) = 0.1; cauda inferior 0.02 → 0.02;
    superior 0.98 → 1 - 0.98 — igualdade exata, grade (0.02, 0.05, 0.5, 0.95, 0.98)."""
    grid = (-0.04, -0.03, 0.0, 0.03, 0.04)
    series = make_series([grid, grid], [0.0, 0.01], levels=_WIDE_LEVELS)

    interval = HitSequences.interval(series, pair=_OUTER_PAIR, tolerance=_TOLERANCE)
    lower = HitSequences.lower_tail(series, level=0.02, tolerance=_TOLERANCE)
    upper = HitSequences.upper_tail(series, level=0.98, tolerance=_TOLERANCE)

    assert interval.violation_rate == pair_miscoverage(0.05) == 0.1  # noqa: PLR2004
    assert (interval.kind, interval.levels) == (HitKind.INTERVAL, _OUTER_PAIR)
    assert lower.violation_rate == 0.02  # noqa: PLR2004
    assert (lower.kind, lower.levels) == (HitKind.LOWER_TAIL, (0.02,))
    assert upper.violation_rate == 1 - 0.98
    assert (upper.kind, upper.levels) == (HitKind.UPPER_TAIL, (0.98,))


# --- I4 — máscara da própria série ------------------------------------------------------------


@pytest.mark.unit
def test_gate_mask_is_the_gate_of_the_same_series(make_series: SeriesFactory) -> None:
    """A2/I4: posições `None` == `DegeneracyGate.evaluate(series, tolerance).degenerate`;
    `tolerance`/`degeneracy_rate` gravados iguais aos do gate; horizonte e timestamps
    são os da série."""
    series = make_series(
        [_SPREAD, _DIRAC, _SPREAD, _DIRAC, _SPREAD], [0.015, 0.1, -0.05, -0.2, 0.035], horizon=7
    )
    gate = DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)

    for sequence in _all_builders(series, tolerance=_TOLERANCE):
        assert tuple(v is None for v in sequence.violations) == gate.degenerate
        assert sequence.tolerance == gate.tolerance
        assert sequence.degeneracy_rate == gate.rate
        assert sequence.includes_degenerate is False
        assert sequence.horizon == series.horizon
        assert sequence.target_timestamps == series.target_timestamps


@pytest.mark.unit
def test_without_gaps_variant_has_no_none_on_mixed_series(make_series: SeriesFactory) -> None:
    """A2/I4: `include_degenerate=True` não mascara (série mista) — pedido explícito."""
    series = _mixed_series(make_series)
    gate = DegeneracyGate.evaluate(series, tolerance=_TOLERANCE)

    for sequence in _all_builders(series, tolerance=_TOLERANCE, include_degenerate=True):
        assert None not in sequence.violations
        assert sequence.includes_degenerate is True
        assert sequence.degeneracy_rate == gate.rate


@pytest.mark.unit
@pytest.mark.parametrize("include_degenerate", [False, True], ids=["masked", "without-gaps"])
def test_all_none_when_degenerate_series(
    make_series: SeriesFactory, *, include_degenerate: bool
) -> None:
    """A2/C7: série 100 % degenerada → toda `None`, também com `include_degenerate=True`."""
    series = make_series([_DIRAC, _DIRAC, _DIRAC], [0.01, -0.02, 0.004])

    for sequence in _all_builders(series, tolerance=0.0, include_degenerate=include_degenerate):
        assert sequence.violations == (None, None, None)
        assert sequence.n_observed == 0
        assert sequence.degeneracy_rate == 1.0


# --- I3 — identidades de contagem com o CoverageMetrics ---------------------------------------


def _random_series(make_series: SeriesFactory) -> CoverageSeries:
    """Série aleatória (seed declarada) com uma linha degenerada a cada 7."""
    rng = random.Random(_IDENTITY_SEED)
    grids: list[tuple[float, ...]] = []
    for t in range(_IDENTITY_T):
        if t % _IDENTITY_DEGENERATE_EVERY == 0:
            grids.append((rng.uniform(-0.01, 0.01),) * 7)
        else:
            grids.append(tuple(sorted(rng.gauss(0.0, 0.02) for _ in range(7))))
    realized = [rng.gauss(0.0, 0.02) for _ in range(_IDENTITY_T)]
    return make_series(grids, realized)


@pytest.mark.unit
def test_count_identities_with_coverage_metrics(make_series: SeriesFactory) -> None:
    """A2/I3: mesma série e tolerância — cauda inferior x/n = ĉ(τ), superior = 1 - ĉ(τ),
    intervalo = 1 - PICP (1e-12)."""
    series = _random_series(make_series)
    report = CoverageMetrics.evaluate(series, tolerance=_TOLERANCE)
    assert report.degeneracy.n_degenerate > 0  # premissa: há lacunas

    coverage = dict(report.per_level)
    for level in series.levels:
        lower = HitSequences.lower_tail(series, level=level, tolerance=_TOLERANCE)
        upper = HitSequences.upper_tail(series, level=level, tolerance=_TOLERANCE)
        assert lower.n_observed == report.n_evaluated
        assert abs(lower.n_violations / lower.n_observed - coverage[level]) <= _ABS_TOL
        assert abs(upper.n_violations / upper.n_observed - (1 - coverage[level])) <= _ABS_TOL
    for pair_report in report.per_pair:
        pair = (pair_report.lower_level, pair_report.upper_level)
        interval = HitSequences.interval(series, pair=pair, tolerance=_TOLERANCE)
        rate = interval.n_violations / interval.n_observed
        assert abs(rate - (1 - pair_report.picp)) <= _ABS_TOL


# --- I3 — pós-guardrail e consumo dos predicados ----------------------------------------------


@pytest.mark.unit
def test_scores_guardrail_not_raw(make_series: SeriesFactory) -> None:
    """A2/I3: extremos trocados no bruto — pelo pós-guardrail, y = 0.02 não viola a cauda
    inferior em 0.05 (q̂ = -0.03) nem o par externo; pelo bruto (q̂ = 0.03) violaria."""
    raw = (0.03, -0.02, -0.01, 0.0, 0.01, 0.02, -0.03)
    guardrail = tuple(sorted(raw))
    series = make_series([raw], [0.02], direct=True, guardrail_grids=[guardrail])
    assert series.realized[0] <= raw[0]  # premissa: pelo bruto a cauda inferior violaria

    lower = HitSequences.lower_tail(series, level=0.05, tolerance=_TOLERANCE)
    interval = HitSequences.interval(series, pair=_OUTER_PAIR, tolerance=_TOLERANCE)

    assert lower.violations == (False,)
    assert interval.violations == (False,)


@pytest.mark.unit
def test_consumes_predicates_not_an_inline_copy(
    make_series: SeriesFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2/I3: trocar os predicados no namespace do módulo muda as violações — o
    construtor não tem cópia própria da regra FA7."""
    series = _mixed_series(make_series)
    monkeypatch.setattr(hit_sequences_module, "is_at_or_below", lambda *_: True)
    monkeypatch.setattr(hit_sequences_module, "is_inside_closed", lambda *_: False)

    interval, lower, upper = _all_builders(series, tolerance=_TOLERANCE)

    assert interval.violations == (True, None, True, None, True)
    assert lower.violations == (True, None, True, None, True)
    assert upper.violations == (False, None, False, None, False)


# --- C2 ---------------------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_pair_or_level_raises(make_series: SeriesFactory) -> None:
    """A2/C2: par (0.05, 0.98) e nível 0.3 inexistentes (igualdade exata) erguem."""
    grid = (-0.04, -0.03, 0.0, 0.03, 0.04)
    series = make_series([grid], [0.0], levels=_WIDE_LEVELS)

    with pytest.raises(ValueError, match="is not one of the series symmetric pairs"):
        HitSequences.interval(series, pair=(0.05, 0.98), tolerance=_TOLERANCE)
    with pytest.raises(ValueError, match="is not one of the series levels"):
        HitSequences.lower_tail(series, level=0.3, tolerance=_TOLERANCE)
    with pytest.raises(ValueError, match="is not one of the series levels"):
        HitSequences.upper_tail(series, level=0.3, tolerance=_TOLERANCE)


@pytest.mark.unit
@pytest.mark.parametrize("tolerance", [-1.0, math.nan], ids=["negative", "nan"])
@pytest.mark.parametrize("builder", ["interval", "lower_tail", "upper_tail"])
def test_invalid_tolerance_raises(
    make_series: SeriesFactory, tolerance: float, builder: str
) -> None:
    """A2/C2: tolerância -1/`nan` ergue pelo C3 do gate, nos três construtores."""
    series = _mixed_series(make_series)
    kwargs: dict[str, object] = {"pair": _OUTER_PAIR} if builder == "interval" else {"level": 0.05}

    with pytest.raises(ValueError, match="tolerance must be a finite number >= 0"):
        getattr(HitSequences, builder)(series, tolerance=tolerance, **kwargs)


@pytest.mark.unit
@pytest.mark.parametrize("builder", ["interval", "lower_tail", "upper_tail"])
def test_tolerance_signature_is_keyword_only_without_default(builder: str) -> None:
    """ADR 6.1.0003: `tolerance` keyword-only e sem default; `include_degenerate=False`."""
    parameters = inspect.signature(getattr(HitSequences, builder)).parameters

    assert parameters["tolerance"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["tolerance"].default is inspect.Parameter.empty
    assert parameters["include_degenerate"].default is False
