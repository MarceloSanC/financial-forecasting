"""Testes do registry de quality checks e dos quatro checks (Stage 6.4 Task 05; A4).

`QualityCheckResult`/`BlockEstimate` (um caso por ramo), `QualityCheckRegistry` (ordem,
nome duplicado, `is_blocking`), `alignment_check` (traduz o relatório),
`statistical_preconditions` (passo de domínio + check), `degeneracy_check` (taxa na
`model_full`) e `realized_provenance`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping

import pytest

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks import (
    statistical_preconditions_check as preconditions_module,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.alignment_check import (  # noqa: E501
    AlignmentCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.degeneracy_check import (  # noqa: E501
    DegeneracyCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.realized_provenance_check import (  # noqa: E501
    RealizedProvenanceCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    QualityCheckRegistry,
    result_of,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.statistical_preconditions_check import (  # noqa: E501
    StatisticalPreconditionsCheck,
    block_request_defect,
    models_suffice,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
    AlignmentKind,
    AlignmentReport,
    AssembledCohort,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
    UndefinedReason,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)
from tests.unit.features.evaluation.gold.conftest import (
    Cohort,
    make_cohort,
    of_series,
    replace_records,
    targets_of,
)

_TOLERANCE = 1e-9
_FINGERPRINT = DatasetFingerprint(value="f" * 64)
_DEFICITS: Mapping[str, int] = {}


def _assembled(cohort: Cohort, deficits: Mapping[str, int] = _DEFICITS) -> AssembledCohort:
    return SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 2),
        window_deficits=deficits,
        required_models=frozenset({"tft"}),
    )


def _paired(assembled: AssembledCohort) -> dict[int, PairedLossSeries]:
    return {
        samples.horizon: paired_pinball_losses(
            {model: samples.common[model] for model in samples.models}
        )
        for samples in assembled.horizons
    }


def _defined(series: PairedLossSeries) -> tuple[BlockEstimate, ...]:
    return tuple(
        BlockEstimate(pair=pair, value=2.5, reason=None, detail="") for pair in series.model_pairs()
    )


def _context(
    cohort: Cohort,
    *,
    deficits: Mapping[str, int] = _DEFICITS,
    estimates: Mapping[int, tuple[BlockEstimate, ...]] | None = None,
) -> QualityCheckContext:
    assembled = _assembled(cohort, deficits)
    paired = _paired(assembled)
    return QualityCheckContext(
        assembled=assembled,
        paired=paired,
        block_estimates=(
            {h: _defined(series) for h, series in paired.items()}
            if estimates is None
            else estimates
        ),
        tolerance=_TOLERANCE,
        dataset_fingerprint=_FINGERPRINT,
        realized=cohort.realized,
    )


def _failed_context(cohort: Cohort) -> QualityCheckContext:
    broken = replace_records(
        cohort,
        lambda r: (
            r.model == "gbm"
            and r.horizon == 1
            and r.target_timestamp == targets_of(cohort, "gbm", None, 1)[4]
        ),
        lambda r: dataclasses.replace(r, decision_idx=r.decision_idx + 1),
    )
    context = _context(broken, estimates={})
    assert context.assembled.alignment.findings
    return context


# --- QualityCheckResult / BlockEstimate ------------------------------------------------

_RESULT = QualityCheckResult(
    check="c",
    severity=CheckSeverity.ERROR,
    outcome=CheckOutcome.FAIL,
    kind="k",
    horizon=1,
    model="tft",
    seed=1,
    occurrences=2,
    value=0.5,
    detail="d",
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"check": ""}, "check must be a non-empty str", id="check"),
        pytest.param({"kind": None}, "kind must be a non-empty str", id="kind"),
        pytest.param({"detail": ""}, "detail must be a non-empty str", id="detail"),
        pytest.param({"severity": "error"}, "severity must be a CheckSeverity", id="severity"),
        pytest.param({"outcome": "fail"}, "outcome must be a CheckOutcome", id="outcome"),
        pytest.param({"outcome": CheckOutcome.REPORTED}, "not allowed", id="error-reported"),
        pytest.param(
            {"severity": CheckSeverity.WARN, "outcome": CheckOutcome.FAIL},
            "not allowed",
            id="warn-fail",
        ),
        pytest.param(
            {"severity": CheckSeverity.WARN, "outcome": CheckOutcome.PASS},
            "not allowed",
            id="warn-pass",
        ),
        pytest.param({"horizon": 0}, "horizon must be an int >= 1", id="horizon"),
        pytest.param({"model": ""}, "model must be a non-empty str", id="model"),
        pytest.param({"seed": True}, "seed must be an int or None", id="seed"),
        pytest.param({"occurrences": 0}, "occurrences must be an int >= 1", id="occ-zero"),
        pytest.param({"occurrences": True}, "occurrences must be", id="occ-bool"),
        pytest.param({"value": math.nan}, "value must be a finite number", id="value-nan"),
        pytest.param({"value": True}, "value must be a finite number", id="value-bool"),
    ],
)
def test_result_invalid_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_RESULT, **changes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_result_accepts_scopeless_and_valueless() -> None:
    result = dataclasses.replace(
        _RESULT,
        severity=CheckSeverity.WARN,
        outcome=CheckOutcome.SKIPPED,
        horizon=None,
        model=None,
        seed=None,
        value=None,
    )
    assert not result.is_blocking


_DEFINED = BlockEstimate(pair=("a", "b"), value=3.0, reason=None, detail="")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"pair": ["a", "b"]}, "pair must be a", id="pair-list"),
        pytest.param({"pair": ("a",)}, "pair must be a", id="pair-single"),
        pytest.param({"pair": ("a", "")}, "pair model must be", id="pair-empty"),
        pytest.param({"pair": ("a", "a")}, "two distinct models", id="pair-same"),
        pytest.param({"value": None}, "exactly one of value and reason", id="neither"),
        pytest.param(
            {"reason": UndefinedReason.INVALID_SERIES, "detail": "x"},
            "exactly one of value and reason",
            id="both",
        ),
        pytest.param({"value": -0.5}, "finite number >= 0", id="negative"),
        pytest.param({"value": math.inf}, "finite number >= 0", id="inf"),
        pytest.param({"value": True}, "finite number >= 0", id="bool"),
        pytest.param({"detail": None}, "detail must be a str", id="detail-none"),
        pytest.param(
            {"value": None, "reason": "invalid_series", "detail": "x"},
            "reason must be an UndefinedReason",
            id="reason-str",
        ),
        pytest.param(
            {"value": None, "reason": UndefinedReason.BACKEND_ARITHMETIC, "detail": ""},
            "detail must be a non-empty str",
            id="reason-no-detail",
        ),
    ],
)
def test_block_estimate_invalid_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_DEFINED, **changes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_block_estimate_undefined_accepted() -> None:
    estimate = BlockEstimate(
        pair=("a", "b"), value=None, reason=UndefinedReason.INVALID_SERIES, detail="too short"
    )
    assert not estimate.is_defined
    assert _DEFINED.is_defined


# --- registry ---------------------------------------------------------------------------


class _Recording:
    def __init__(self, name: str, calls: list[str], severity: CheckSeverity) -> None:
        self.name = name
        self.severity = severity
        self._calls = calls

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        self._calls.append(self.name)
        outcome = (
            CheckOutcome.PASS if self.severity is CheckSeverity.ERROR else CheckOutcome.REPORTED
        )
        return (result_of(self, outcome, "probe", detail=f"ran {self.name}"),)


@pytest.mark.unit
def test_registry_runs_in_order() -> None:
    calls: list[str] = []
    names = ("zeta", "alpha", "mid")
    registry = QualityCheckRegistry(
        [_Recording(name, calls, CheckSeverity.ERROR) for name in names]
    )
    results = registry.run(_context(make_cohort()))
    assert calls == list(names)
    assert tuple(r.check for r in results) == names
    assert registry.names == names


@pytest.mark.unit
def test_registry_duplicate_name_raises() -> None:
    calls: list[str] = []
    with pytest.raises(ValueError, match=r"repeated: \['a'\]"):
        QualityCheckRegistry(
            [
                _Recording("a", calls, CheckSeverity.ERROR),
                _Recording("b", calls, CheckSeverity.WARN),
                _Recording("a", calls, CheckSeverity.WARN),
            ]
        )


@pytest.mark.unit
def test_registry_foreign_result_raises() -> None:
    """Um check que devolve resultado de outro nome/severidade é erro de programação."""

    class _Liar(_Recording):
        def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
            return (dataclasses.replace(_RESULT, check="other"),)

    with pytest.raises(ValueError, match="returned a result of 'other'"):
        QualityCheckRegistry([_Liar("liar", [], CheckSeverity.ERROR)]).run(_context(make_cohort()))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("severity", "outcome", "blocking"),
    [
        pytest.param(CheckSeverity.ERROR, CheckOutcome.FAIL, True, id="error-fail"),
        pytest.param(CheckSeverity.ERROR, CheckOutcome.PASS, False, id="error-pass"),
        pytest.param(CheckSeverity.ERROR, CheckOutcome.SKIPPED, False, id="error-skipped"),
        pytest.param(CheckSeverity.WARN, CheckOutcome.REPORTED, False, id="warn-reported"),
        pytest.param(CheckSeverity.WARN, CheckOutcome.SKIPPED, False, id="warn-skipped"),
    ],
)
def test_is_blocking_rule(severity: CheckSeverity, outcome: CheckOutcome, blocking: bool) -> None:
    result = dataclasses.replace(_RESULT, severity=severity, outcome=outcome)
    other = dataclasses.replace(_RESULT, severity=CheckSeverity.WARN, outcome=CheckOutcome.REPORTED)
    assert QualityCheckRegistry.is_blocking([other, result]) is blocking
    assert QualityCheckRegistry.is_blocking([]) is False


# --- alignment_check -------------------------------------------------------------------


def _finding(detail: str, *, seed: int | None = 1) -> AlignmentFinding:
    return AlignmentFinding(
        kind=AlignmentKind.INTERIOR_GAP, horizon=1, model="tft", seed=seed, detail=detail
    )


@pytest.mark.unit
def test_alignment_translates_report() -> None:
    """3 achados do mesmo (tipo, escopo) → 1 FAIL com `occurrences == 3` e o 1º detalhe."""
    report = AlignmentReport(
        findings=(_finding("first"), _finding("second"), _finding("third"), _finding("x", seed=2)),
        common_points=((1, 30),),
    )
    base = _context(make_cohort())
    context = dataclasses.replace(
        base,
        assembled=AssembledCohort(alignment=report, horizons=()),
        paired={},
        block_estimates={},
    )
    results = AlignmentCheck().run(context)
    assert [
        (r.outcome, r.kind, r.horizon, r.model, r.seed, r.occurrences, r.detail) for r in results
    ] == [
        (CheckOutcome.FAIL, "interior_gap", 1, "tft", 1, 3, "first"),
        (CheckOutcome.FAIL, "interior_gap", 1, "tft", 2, 1, "x"),
    ]
    assert all(r.severity is CheckSeverity.ERROR and r.check == "alignment_check" for r in results)
    assert QualityCheckRegistry.is_blocking(results)


@pytest.mark.unit
def test_alignment_pass_per_horizon() -> None:
    context = _context(make_cohort())
    results = AlignmentCheck().run(context)
    assert [(r.outcome, r.horizon, r.value) for r in results] == [
        (CheckOutcome.PASS, h, float(t)) for h, t in context.assembled.alignment.common_points
    ]
    assert not QualityCheckRegistry.is_blocking(results)


# --- statistical_preconditions ---------------------------------------------------------


def _single_model_cohort() -> Cohort:
    return make_cohort(seeds={"tft": (1, 2)})


@pytest.mark.unit
def test_preconditions_k_below_min() -> None:
    cohort = _single_model_cohort()
    assembled = _assembled(cohort)
    assert assembled.alignment.findings == ()
    assert not models_suffice(assembled.horizons[0].models)
    context = QualityCheckContext(
        assembled=assembled,
        paired={},
        block_estimates={},
        tolerance=_TOLERANCE,
        dataset_fingerprint=_FINGERPRINT,
        realized=cohort.realized,
    )
    results = StatisticalPreconditionsCheck().run(context)
    assert [(r.outcome, r.kind, r.horizon, r.value) for r in results] == [
        (CheckOutcome.FAIL, "insufficient_models", h, 1.0) for h in (1, 2)
    ]
    assert models_suffice(("a", "b"))


def _undefined(pair: tuple[str, str], reason: UndefinedReason, detail: str) -> BlockEstimate:
    return BlockEstimate(pair=pair, value=None, reason=reason, detail=detail)


def _three_model_cohort() -> Cohort:
    return make_cohort(seeds={"gbm": (None,), "naive": (None,), "tft": (1,)})


@pytest.mark.unit
def test_preconditions_constant_differential() -> None:
    """Diferencial constante: o passo devolve o motivo e o check agrega por horizonte."""
    assert block_request_defect((0.5,) * 20) is UndefinedReason.CONSTANT_DIFFERENTIAL
    base = _context(_three_model_cohort())
    series = base.paired[1]
    estimates = tuple(
        _undefined(pair, UndefinedReason.CONSTANT_DIFFERENTIAL, "d constant")
        if pair != series.model_pairs()[2]
        else BlockEstimate(pair=pair, value=1.5, reason=None, detail="")
        for pair in series.model_pairs()
    )
    context = dataclasses.replace(base, block_estimates={**base.block_estimates, 1: estimates})
    results = [r for r in StatisticalPreconditionsCheck().run(context) if r.horizon == 1]
    assert [(r.outcome, r.kind, r.occurrences) for r in results] == [
        (CheckOutcome.FAIL, "constant_differential", 2)
    ]
    assert str(series.model_pairs()[0]) in results[0].detail


@pytest.mark.unit
def test_preconditions_invalid_series() -> None:
    """Série de diferencial com 10 pontos (< 11): `INVALID_SERIES` no passo e no check."""
    assert block_request_defect(tuple(float(i % 3) for i in range(10))) is (
        UndefinedReason.INVALID_SERIES
    )
    assert block_request_defect((0.0, math.nan) * 6) is UndefinedReason.INVALID_SERIES
    base = _context(make_cohort())
    pair = base.paired[2].model_pairs()[0]
    estimates = (
        _undefined(pair, UndefinedReason.INVALID_SERIES, "10 points"),
        *base.block_estimates[2][1:],
    )
    context = dataclasses.replace(base, block_estimates={**base.block_estimates, 2: estimates})
    failed = [
        r for r in StatisticalPreconditionsCheck().run(context) if r.outcome is CheckOutcome.FAIL
    ]
    assert [(r.kind, r.horizon, r.occurrences) for r in failed] == [("invalid_series", 2, 1)]


@pytest.mark.unit
def test_preconditions_undefined_estimate() -> None:
    """`BACKEND_ARITHMETIC` (convertido pelo use case) → FAIL com esse `kind`."""
    base = _context(make_cohort())
    pairs = base.paired[1].model_pairs()
    estimates = tuple(
        _undefined(pair, UndefinedReason.BACKEND_ARITHMETIC, "ZeroDivisionError") for pair in pairs
    )
    context = dataclasses.replace(base, block_estimates={**base.block_estimates, 1: estimates})
    failed = [
        r for r in StatisticalPreconditionsCheck().run(context) if r.outcome is CheckOutcome.FAIL
    ]
    assert [(r.kind, r.horizon, r.occurrences) for r in failed] == [
        ("backend_arithmetic", 1, len(pairs))
    ]
    assert QualityCheckRegistry.is_blocking(failed)


@pytest.mark.unit
def test_preconditions_skipped() -> None:
    results = StatisticalPreconditionsCheck().run(_failed_context(make_cohort()))
    assert [(r.outcome, r.kind) for r in results] == [(CheckOutcome.SKIPPED, "assembly_failed")]


@pytest.mark.unit
def test_preconditions_pass() -> None:
    cohort = make_cohort()
    assert block_request_defect(tuple(float(i % 4) for i in range(20))) is None
    results = StatisticalPreconditionsCheck().run(_context(cohort))
    assert [(r.outcome, r.horizon) for r in results] == [
        (CheckOutcome.PASS, 1),
        (CheckOutcome.PASS, 2),
    ]


@pytest.mark.unit
def test_step_delegates_to_owners(monkeypatch: pytest.MonkeyPatch) -> None:
    """O passo consulta os donos da 6.2 (troca por monkeypatch muda o resultado)."""
    good = tuple(float(i % 4) for i in range(20))
    assert block_request_defect(good) is None
    monkeypatch.setattr(preconditions_module, "is_constant", lambda _values: True)
    assert block_request_defect(good) is UndefinedReason.CONSTANT_DIFFERENTIAL
    monkeypatch.undo()

    def _reject(_series: object) -> None:
        raise ValueError("rejected by the owner")

    monkeypatch.setattr(preconditions_module, "validate_block_length_request", _reject)
    assert block_request_defect(good) is UndefinedReason.INVALID_SERIES
    monkeypatch.undo()
    monkeypatch.setattr(preconditions_module, "MIN_MODELS", 3)
    assert not models_suffice(("a", "b"))


@pytest.mark.unit
def test_context_estimates_must_match_pairs() -> None:
    base = _context(make_cohort())
    with pytest.raises(ValueError, match="must cover the pairs"):
        dataclasses.replace(base, block_estimates={1: ()})
    with pytest.raises(ValueError, match="tolerance must be"):
        dataclasses.replace(base, tolerance=-1.0)
    with pytest.raises(ValueError, match="paired must be a Mapping"):
        dataclasses.replace(base, paired=[])


# --- degeneracy_check ------------------------------------------------------------------


@pytest.mark.unit
def test_degeneracy_reported() -> None:
    context = _context(make_cohort())
    results = DegeneracyCheck().run(context)
    expected = [
        (samples.horizon, model, seed)
        for samples in context.assembled.horizons
        for model in samples.models
        for seed in samples.seeds[model]
    ]
    assert [(r.horizon, r.model, r.seed) for r in results] == expected
    assert all(r.outcome is CheckOutcome.REPORTED and r.value == 0.0 for r in results)
    assert not QualityCheckRegistry.is_blocking(results)


@pytest.mark.unit
def test_degeneracy_uses_model_full() -> None:
    """GBM com um ponto degenerado FORA da interseção: a taxa é a da `full`."""
    cohort = make_cohort(prefixes={"tft": 2})
    first = targets_of(cohort, "gbm", None, 1)[0]
    cohort = replace_records(
        cohort,
        lambda r: of_series("gbm", None, 1)(r) and r.target_timestamp == first,
        lambda r: dataclasses.replace(r, value_raw=0.01, value_guardrail=0.01),
    )
    context = _context(cohort, deficits={"tft": 2})
    samples = context.assembled.horizons[0]
    full, common = samples.full["gbm"][0], samples.common["gbm"][0]
    assert full.n_points > common.n_points
    [gbm] = [r for r in DegeneracyCheck().run(context) if (r.horizon, r.model) == (1, "gbm")]
    full_rate = DegeneracyGate.evaluate(full, tolerance=_TOLERANCE).rate
    common_rate = DegeneracyGate.evaluate(common, tolerance=_TOLERANCE).rate
    assert gbm.value == full_rate == 1 / full.n_points
    assert common_rate == 0.0
    assert gbm.value != common_rate


@pytest.mark.unit
def test_degeneracy_point_baseline() -> None:
    """Baseline pontual (grade toda igual em todo ponto): taxa 1.0 (C8)."""
    cohort = replace_records(
        make_cohort(),
        lambda r: r.model == "gbm",
        lambda r: dataclasses.replace(r, value_raw=0.002, value_guardrail=0.002),
    )
    results = [r for r in DegeneracyCheck().run(_context(cohort)) if r.model == "gbm"]
    assert [(r.horizon, r.value) for r in results] == [(1, 1.0), (2, 1.0)]


@pytest.mark.unit
def test_degeneracy_skipped() -> None:
    results = DegeneracyCheck().run(_failed_context(make_cohort()))
    assert [(r.outcome, r.kind, r.severity) for r in results] == [
        (CheckOutcome.SKIPPED, "assembly_failed", CheckSeverity.WARN)
    ]
    assert "finding" in results[0].detail


# --- realized_provenance ---------------------------------------------------------------


@pytest.mark.unit
def test_provenance_reported() -> None:
    cohort = make_cohort()
    [result] = RealizedProvenanceCheck().run(_context(cohort))
    realized = cohort.realized
    assert (result.outcome, result.severity, result.kind) == (
        CheckOutcome.REPORTED,
        CheckSeverity.WARN,
        "target_return_fsum",
    )
    assert result.value == math.fsum(realized.returns)
    for piece in (
        _FINGERPRINT.value,
        f"n_sessions={realized.n_sessions}",
        realized.first_timestamp,
        realized.last_timestamp,
    ):
        assert piece in result.detail
