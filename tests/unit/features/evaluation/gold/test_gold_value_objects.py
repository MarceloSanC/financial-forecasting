"""Testes dos VOs de entrada e da montagem do gold (Stage 6.4 Task 03).

`ForecastRecord`, `CohortRun`, `RealizedReturns` e os VOs de `assembled_cohort.py`
(`AlignmentFinding`, `AlignmentReport`, `HorizonSamples`, `AssembledCohort`): um caso
parametrizado por ramo de validação, o lookup e o resumo do realizado, e a regra
"achados xor horizontes" do `AssembledCohort`.
"""

from __future__ import annotations

import dataclasses
import functools
import math
import operator
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
    AlignmentKind,
    AlignmentReport,
    AssembledCohort,
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)

SeriesFactory = Callable[..., CoverageSeries]

_TS = (
    "2024-01-02T00:00:00+00:00",
    "2024-01-03T00:00:00+00:00",
    "2024-01-04T00:00:00+00:00",
    "2024-01-05T00:00:00+00:00",
)
_N_ALIGNMENT_KINDS = 19

_RECORD = ForecastRecord(
    run_id="run-1",
    model="tft",
    seed=7,
    fold="f0",
    horizon=1,
    decision_idx=0,
    decision_timestamp=_TS[0],
    target_timestamp=_TS[1],
    split="test",
    quantile_level=0.5,
    value_raw=0.01,
    value_guardrail=0.01,
    guardrail_applied=False,
)

_RUN = CohortRun(
    run_id="run-1",
    model="tft",
    seed=7,
    fold="f0",
    feature_set_name="fs",
    config_signature="sig",
)


# --- ForecastRecord ---------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"run_id": ""}, "run_id must be a non-empty str", id="run-id-empty"),
        pytest.param({"model": 3}, "model must be a non-empty str", id="model-not-str"),
        pytest.param({"split": ""}, "split must be a non-empty str", id="split-empty"),
        pytest.param(
            {"decision_timestamp": None}, "decision_timestamp must be", id="decision-ts-none"
        ),
        pytest.param({"target_timestamp": ""}, "target_timestamp must be", id="target-ts-empty"),
        pytest.param({"seed": True}, "seed must be an int or None", id="seed-bool"),
        pytest.param({"seed": 1.0}, "seed must be an int or None", id="seed-float"),
        pytest.param({"fold": 0}, "fold must be a str or None", id="fold-int"),
        pytest.param({"horizon": 0}, "horizon must be an int >= 1", id="horizon-zero"),
        pytest.param({"horizon": True}, "horizon must be an int >= 1", id="horizon-bool"),
        pytest.param({"decision_idx": -1}, "decision_idx must be an int >= 0", id="idx-negative"),
        pytest.param({"decision_idx": False}, "decision_idx must be", id="idx-bool"),
        pytest.param({"quantile_level": math.nan}, "quantile_level must be", id="level-nan"),
        pytest.param({"quantile_level": 1}, "quantile_level must be", id="level-int"),
        pytest.param({"quantile_level": True}, "quantile_level must be", id="level-bool"),
        pytest.param({"value_raw": 1}, "value_raw must be a float", id="raw-int"),
        pytest.param({"value_guardrail": None}, "value_guardrail must be", id="guardrail-none"),
        pytest.param({"guardrail_applied": 1}, "guardrail_applied must be a bool", id="flag-int"),
    ],
)
def test_record_invalid_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_RECORD, **changes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_record_accepts_optional_identity_and_non_finite_values() -> None:
    """`seed`/`fold` `None` passam; a finitude de raw/guardrail é da `CoverageSeries`."""
    record = dataclasses.replace(_RECORD, seed=None, fold=None, value_raw=math.inf)
    assert (record.seed, record.fold) == (None, None)
    assert math.isinf(record.value_raw)


# --- CohortRun --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"run_id": ""}, "run_id must be a non-empty str", id="run-id"),
        pytest.param({"model": None}, "model must be a non-empty str", id="model"),
        pytest.param({"feature_set_name": ""}, "feature_set_name must be", id="feature-set"),
        pytest.param({"config_signature": 1}, "config_signature must be", id="signature"),
        pytest.param({"seed": False}, "seed must be an int or None", id="seed-bool"),
        pytest.param({"fold": b"f0"}, "fold must be a str or None", id="fold-bytes"),
    ],
)
def test_cohort_run_invalid_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_RUN, **changes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_cohort_run_accepts_deterministic_model() -> None:
    assert dataclasses.replace(_RUN, seed=None, fold=None).seed is None


# --- RealizedReturns --------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("timestamps", "returns", "message"),
    [
        pytest.param(list(_TS), (0.0,) * 4, "timestamps must be a tuple", id="ts-list"),
        pytest.param(_TS, [0.0] * 4, "returns must be a tuple", id="returns-list"),
        pytest.param((), (), "at least one session", id="empty"),
        pytest.param(_TS, (0.0,) * 3, "must align", id="length"),
        pytest.param((_TS[0], ""), (0.0, 0.0), r"timestamps\[1\] must be", id="ts-empty"),
        pytest.param((_TS[0], 5), (0.0, 0.0), r"timestamps\[1\] must be", id="ts-not-str"),
        pytest.param((_TS[1], _TS[0]), (0.0, 0.0), "strictly increasing", id="ts-order"),
        pytest.param((_TS[0], _TS[0]), (0.0, 0.0), "strictly increasing", id="ts-repeat"),
        pytest.param(_TS[:2], (0.0, math.nan), r"returns\[1\] must be a finite", id="nan"),
        pytest.param(_TS[:2], (0.0, math.inf), r"returns\[1\] must be a finite", id="inf"),
        pytest.param(_TS[:2], (0.0, True), r"returns\[1\] must be a finite", id="bool"),
    ],
)
def test_realized_invalid_raises(timestamps: object, returns: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RealizedReturns(timestamps=timestamps, returns=returns)  # type: ignore[arg-type]


@pytest.mark.unit
def test_realized_lookup_present_and_absent() -> None:
    realized = RealizedReturns(timestamps=_TS, returns=(0.1, -0.2, 0.3, -0.4))
    assert [realized.index_of(ts) for ts in _TS] == [0, 1, 2, 3]
    assert realized.realized_at(_TS[2]) == 0.3  # noqa: PLR2004 — o retorno da sessão 2
    assert realized.index_of("2024-01-06T00:00:00+00:00") is None
    with pytest.raises(ValueError, match="no realized return for session"):
        realized.realized_at("2024-01-06T00:00:00+00:00")


@pytest.mark.unit
def test_realized_summary_uses_fsum() -> None:
    """`returns_fsum` é `math.fsum`: `[0.1]*10` soma 1.0 exato (a soma ingênua não soma).

    A referência é a dobra ingênua (`reduce(add)`), não o `sum` builtin: desde o Python
    3.12 o `sum` de floats é compensado (Neumaier) e também dá 1.0 aqui (technical 6.4 §7).
    """
    timestamps = tuple(f"2024-02-{day:02d}T00:00:00+00:00" for day in range(1, 11))
    realized = RealizedReturns(timestamps=timestamps, returns=(0.1,) * 10)
    assert functools.reduce(operator.add, realized.returns) != 1.0
    assert realized.returns_fsum == 1.0
    assert realized.n_sessions == len(timestamps)
    assert (realized.first_timestamp, realized.last_timestamp) == (timestamps[0], timestamps[-1])


@pytest.mark.unit
def test_realized_equality_ignores_index_cache() -> None:
    first = RealizedReturns(timestamps=_TS, returns=(0.1, -0.2, 0.3, -0.4))
    assert first == RealizedReturns(timestamps=_TS, returns=(0.1, -0.2, 0.3, -0.4))
    assert dataclasses.replace(first) == first


# --- AlignmentFinding / AlignmentReport -------------------------------------------------

_FINDING = AlignmentFinding(
    kind=AlignmentKind.INTERIOR_GAP, horizon=1, model="tft", seed=7, detail="gap at 3"
)


@pytest.mark.unit
def test_alignment_kinds_are_the_nineteen_rules() -> None:
    assert len(AlignmentKind) == _N_ALIGNMENT_KINDS
    assert AlignmentKind("common_sample_too_short") is AlignmentKind.COMMON_SAMPLE_TOO_SHORT


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"kind": "interior_gap"}, "kind must be an AlignmentKind", id="kind-str"),
        pytest.param({"horizon": 0}, "horizon must be an int >= 1", id="horizon"),
        pytest.param({"model": ""}, "model must be a non-empty str", id="model"),
        pytest.param({"seed": True}, "seed must be an int or None", id="seed"),
        pytest.param({"detail": ""}, "detail must be a non-empty str", id="detail"),
    ],
)
def test_finding_invalid_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_FINDING, **changes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_finding_accepts_cohort_scope() -> None:
    """Achado de cohort (ex. `orphan_run`) não tem horizonte, modelo nem seed."""
    finding = AlignmentFinding(
        kind=AlignmentKind.ORPHAN_RUN, horizon=None, model=None, seed=None, detail="run-9"
    )
    assert finding.horizon is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("findings", "common_points", "message"),
    [
        pytest.param([_FINDING], (), "findings must be a tuple", id="findings-list"),
        pytest.param(("x",), (), "findings must be a tuple of AlignmentFinding", id="finding-type"),
        pytest.param((), [(1, 5)], "common_points must be a tuple", id="points-list"),
        pytest.param((), ((1, 5, 0),), r"\(horizon, T\) pairs", id="triple"),
        pytest.param((), ((0, 5),), "horizon must be an int >= 1", id="horizon-zero"),
        pytest.param((), ((7, 5), (1, 5)), "strictly increasing", id="order"),
        pytest.param((), ((1, 5), (1, 5)), "strictly increasing", id="repeat"),
        pytest.param((), ((1, 0),), "T must be an int >= 1", id="t-zero"),
        pytest.param((), ((1, True),), "T must be an int >= 1", id="t-bool"),
    ],
)
def test_alignment_report_invalid_raises(
    findings: object, common_points: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AlignmentReport(findings=findings, common_points=common_points)  # type: ignore[arg-type]


# --- HorizonSamples / AssembledCohort ---------------------------------------------------


def _grid(shift: float) -> tuple[float, ...]:
    return tuple(shift + step for step in (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3))


def _series(
    make_series: SeriesFactory, timestamps: tuple[str, ...], *, horizon: int = 1
) -> CoverageSeries:
    return make_series(
        [_grid(0.01 * i) for i in range(len(timestamps))],
        [0.0] * len(timestamps),
        horizon=horizon,
        timestamps=timestamps,
    )


def _samples_fields(make_series: SeriesFactory, **changes: object) -> dict[str, object]:
    full = _series(make_series, _TS)
    common = _series(make_series, _TS[1:])
    fields: dict[str, object] = {
        "horizon": 1,
        "models": ("gbm", "tft"),
        "levels": full.levels,
        "seeds": {"gbm": (None,), "tft": (1, 2)},
        "full": {"gbm": (full,), "tft": (full, full)},
        "common": {"gbm": (common,), "tft": (common, common)},
        "n_common": 3,
        "common_first_target_timestamp": _TS[1],
        "common_last_target_timestamp": _TS[3],
    }
    fields.update(changes)
    return fields


def _samples(make_series: SeriesFactory, **changes: object) -> HorizonSamples:
    return HorizonSamples(**_samples_fields(make_series, **changes))  # type: ignore[arg-type]


def _incoherent_cases() -> list[object]:
    def full(ms: SeriesFactory, horizon: int = 1) -> CoverageSeries:
        return _series(ms, _TS, horizon=horizon)

    def common(ms: SeriesFactory, ts: tuple[str, ...] = _TS[1:]) -> CoverageSeries:
        return _series(ms, ts)

    return [
        pytest.param(lambda ms: {"horizon": 0}, "horizon must be", id="horizon"),
        pytest.param(lambda ms: {"models": ()}, "models must be a non-empty tuple", id="no-models"),
        pytest.param(lambda ms: {"models": ["gbm", "tft"]}, "non-empty tuple", id="models-list"),
        pytest.param(lambda ms: {"models": ("tft", "gbm")}, "sorted and unique", id="unsorted"),
        pytest.param(lambda ms: {"models": ("gbm", "")}, "model must be a non-empty", id="empty"),
        pytest.param(lambda ms: {"n_common": 0}, "n_common must be an int >= 1", id="n-zero"),
        pytest.param(lambda ms: {"n_common": True}, "n_common must be", id="n-bool"),
        pytest.param(
            lambda ms: {"common_first_target_timestamp": ""}, "common_first", id="first-empty"
        ),
        pytest.param(
            lambda ms: {"common_last_target_timestamp": None}, "common_last", id="last-none"
        ),
        pytest.param(
            lambda ms: {"seeds": {"gbm": (None,)}}, "seeds keys must be the models", id="seed-keys"
        ),
        pytest.param(
            lambda ms: {"full": {"gbm": (full(ms),), "tft": (full(ms),), "x": ()}},
            "full keys must be the models",
            id="full-keys",
        ),
        pytest.param(
            lambda ms: {"seeds": {"gbm": (), "tft": (1, 2)}}, "seeds must be a non-empty", id="s0"
        ),
        pytest.param(
            lambda ms: {"seeds": {"gbm": (None,), "tft": (True, 2)}}, "seed must be", id="s-bool"
        ),
        pytest.param(
            lambda ms: {"seeds": {"gbm": (None,), "tft": (2, 1)}}, "sorted and unique", id="s-ord"
        ),
        pytest.param(
            lambda ms: {"seeds": {"gbm": (None,), "tft": (1, 1)}}, "sorted and unique", id="s-rep"
        ),
        pytest.param(
            lambda ms: {"full": {"gbm": (full(ms),), "tft": (full(ms),)}},
            "one series per seed",
            id="full-count",
        ),
        pytest.param(
            lambda ms: {"common": {"gbm": [common(ms)], "tft": (common(ms), common(ms))}},
            "one series per seed",
            id="common-list",
        ),
        pytest.param(
            lambda ms: {"full": {"gbm": ("x",), "tft": (full(ms), full(ms))}},
            "expected a CoverageSeries",
            id="not-series",
        ),
        pytest.param(
            lambda ms: {"full": {"gbm": (full(ms, horizon=2),), "tft": (full(ms), full(ms))}},
            "series horizon 2 != 1",
            id="series-horizon",
        ),
        pytest.param(lambda ms: {"levels": (0.1, 0.5, 0.9)}, "series levels", id="series-levels"),
        pytest.param(
            lambda ms: {"common": {"gbm": (common(ms, _TS),), "tft": (common(ms), common(ms))}},
            "must have T=3 points",
            id="common-length",
        ),
        pytest.param(
            lambda ms: {"common_first_target_timestamp": _TS[0]},
            "must have T=3 points",
            id="common-first",
        ),
        pytest.param(
            lambda ms: {"common_last_target_timestamp": _TS[2]},
            "must have T=3 points",
            id="common-last",
        ),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(("changes", "message"), _incoherent_cases())
def test_samples_incoherent_raises(
    make_series: SeriesFactory,
    changes: Callable[[SeriesFactory], dict[str, object]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _samples(make_series, **changes(make_series))


@pytest.mark.unit
def test_samples_coherent_accepted(make_series: SeriesFactory) -> None:
    samples = _samples(make_series)
    assert samples.n_common == samples.common["tft"][1].n_points


def _report(
    *findings: AlignmentFinding, points: tuple[tuple[int, int], ...] = ((1, 3),)
) -> AlignmentReport:
    return AlignmentReport(findings=findings, common_points=points)


@pytest.mark.unit
def test_findings_xor_horizons(make_series: SeriesFactory) -> None:
    """Achado **e** horizontes ergue; nenhum achado **e** nenhum horizonte ergue."""
    samples = _samples(make_series)
    with pytest.raises(ValueError, match="if and only if"):
        AssembledCohort(alignment=_report(_FINDING), horizons=(samples,))
    with pytest.raises(ValueError, match="if and only if"):
        AssembledCohort(alignment=_report(), horizons=())
    assert AssembledCohort(alignment=_report(_FINDING), horizons=()).horizons == ()
    assert AssembledCohort(alignment=_report(), horizons=(samples,)).horizons == (samples,)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(lambda s: ("report", (s,)), "must be an AlignmentReport", id="alignment"),
        pytest.param(lambda s: (_report(), [s]), "tuple of HorizonSamples", id="horizons-list"),
        pytest.param(
            lambda s: (_report(), (s, s)),
            "strictly increasing",
            id="repeat",
        ),
        pytest.param(
            lambda s: (_report(points=((1, 4),)), (s,)), "must equal alignment", id="t-diff"
        ),
    ],
)
def test_findings_xor_horizons_structure_raises(
    make_series: SeriesFactory,
    build: Callable[[HorizonSamples], tuple[object, object]],
    message: str,
) -> None:
    alignment, horizons = build(_samples(make_series))
    with pytest.raises(ValueError, match=message):
        AssembledCohort(alignment=alignment, horizons=horizons)  # type: ignore[arg-type]
