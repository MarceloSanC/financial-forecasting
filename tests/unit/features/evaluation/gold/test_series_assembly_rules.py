"""Regras de alinhamento do `SeriesAssembly` como funções públicas (Stage 7.2, Task 13).

Um par por regra: `None` (ou tupla vazia) na entrada conforme e a violação com `kind` e
`detail` na não conforme. O último teste confere que os achados de um cohort com as
violações são os mesmos, campo a campo, que a 6.4 espera (o refactor não muda nada).
"""

from __future__ import annotations

import dataclasses

from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    RuleViolation,
    SeriesAssembly,
    duplicate_levels,
    index_violations,
    missing_levels,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
    AlignmentKind,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from tests.unit.features.evaluation.gold._cohort_factory import (
    add_records,
    at_point,
    drop_records,
    make_cohort,
    session,
)

_TARGET = session(10)


def _record(level: float = 0.1, **changes: object) -> ForecastRecord:
    base = ForecastRecord(
        run_id="tft-s1-f0",
        model="tft",
        seed=1,
        fold="f0",
        horizon=1,
        decision_idx=9,
        decision_timestamp=session(9),
        target_timestamp=_TARGET,
        split="test",
        quantile_level=level,
        value_raw=0.0,
        value_guardrail=0.0,
        guardrail_applied=False,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def test_duplicate_levels_rule() -> None:
    clean = {0.1: (_record(0.1),), 0.9: (_record(0.9),)}
    assert duplicate_levels(clean, target_timestamp=_TARGET) is None
    repeated = {0.1: (_record(0.1), _record(0.1)), 0.9: (_record(0.9),)}
    assert duplicate_levels(repeated, target_timestamp=_TARGET) == RuleViolation(
        AlignmentKind.DUPLICATE_POINT, f"target {_TARGET!r}: levels [0.1] observed more than once"
    )


def test_index_violations_realized_missing() -> None:
    realized = make_cohort().realized
    ok = index_violations(
        target_timestamp=_TARGET, decisions=[(session(9), 9)], horizon=1, realized=realized
    )
    assert ok == ()
    outside = session(999)
    assert index_violations(
        target_timestamp=outside, decisions=[(session(9), 9)], horizon=1, realized=realized
    ) == (
        RuleViolation(
            AlignmentKind.REALIZED_MISSING, f"target {outside!r} is not a session of the dataset"
        ),
    )


def test_index_violations_decision_index_mismatch() -> None:
    realized = make_cohort().realized
    assert index_violations(
        target_timestamp=_TARGET, decisions=[(session(9), 8)], horizon=1, realized=realized
    ) == (
        RuleViolation(
            AlignmentKind.DECISION_INDEX_MISMATCH,
            f"target {_TARGET!r}: decision {session(9)!r} has dataset index 9 but decision_idx 8",
        ),
    )


def test_index_violations_horizon_label_mismatch() -> None:
    realized = make_cohort().realized
    assert index_violations(
        target_timestamp=_TARGET, decisions=[(session(8), 8)], horizon=1, realized=realized
    ) == (
        RuleViolation(
            AlignmentKind.HORIZON_LABEL_MISMATCH,
            f"target {_TARGET!r} is 2 sessions after decision {session(8)!r}, not h=1",
        ),
    )
    # decisões repetidas contam uma vez, em ordem
    twice = index_violations(
        target_timestamp=_TARGET,
        decisions=[(session(8), 8), (session(8), 8)],
        horizon=1,
        realized=realized,
    )
    assert len(twice) == 1


def test_missing_levels_rule() -> None:
    assert missing_levels(present=[0.1, 0.9], expected=[0.9, 0.1], target_timestamp=_TARGET) is None
    assert missing_levels(
        present=[0.1], expected=[0.1, 0.5, 0.9], target_timestamp=_TARGET
    ) == RuleViolation(
        AlignmentKind.GRID_INCOMPLETE, f"target {_TARGET!r}: missing levels [0.5, 0.9]"
    )


def test_series_assembly_findings_unchanged() -> None:
    cohort = make_cohort()
    tft = [r for r in cohort.records if r.model == "tft" and r.seed == 1 and r.horizon == 1]
    point = sorted({r.target_timestamp for r in tft})[3]
    rows = [r for r in tft if r.target_timestamp == point]
    duplicate = rows[0]
    shifted = dataclasses.replace(rows[1], decision_idx=rows[1].decision_idx - 1)
    broken = add_records(drop_records(cohort, at_point("tft", 1, 1, point)), *rows[2:])
    broken = add_records(broken, duplicate, duplicate, shifted)
    result = SeriesAssembly.assemble(
        broken.records,
        broken.runs,
        broken.realized,
        horizons=(1, 2),
        window_deficits={},
        required_models=frozenset({"tft"}),
    )
    decision = rows[1].decision_timestamp
    expected = {
        AlignmentFinding(
            kind=AlignmentKind.DUPLICATE_POINT,
            horizon=1,
            model="tft",
            seed=1,
            detail=f"target {point!r}: levels [{duplicate.quantile_level}] observed more than once",
        ),
        AlignmentFinding(
            kind=AlignmentKind.DECISION_INDEX_MISMATCH,
            horizon=1,
            model="tft",
            seed=1,
            detail=(
                f"target {point!r}: decision {decision!r} has dataset index "
                f"{rows[1].decision_idx} but decision_idx {rows[1].decision_idx - 1}"
            ),
        ),
    }
    assert set(result.alignment.findings) == expected
    assert result.horizons == ()
