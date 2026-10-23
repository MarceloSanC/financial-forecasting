"""Testes dos DTOs da corrida confirmatória (Stage 8.1 Task 12; concept §4, D3, D6).

Status, resumo do `infer` com chaves exatas, forma do comando e do resultado, o
marcador do `--deviation` e o `run_record.json` (dono único das chaves que o corpo de
atestação lê).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    DEVIATION_TAG,
    RUN_RECORD_ATTEMPTS,
    RUN_RECORD_ENVIRONMENT,
    RUN_RECORD_FAILED_CHECKS,
    SEEDS_REFERENCE,
    ConfirmatoryRunStatus,
    InferenceSummary,
    InvalidDeviationError,
    RunConfirmatoryEvaluationCommand,
    RunConfirmatoryEvaluationResult,
    check_deviation,
    run_record_document,
    sealed_status,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    AttemptPhase,
    JudgedAttempt,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldPartition,
    RefreshStatus,
)

_SUMMARY = {
    "runs": 60,
    "strict": 58,
    "tolerance": 2,
    "max_abs_diff": 1.5e-7,
    "calib_rows_written": 0,
    "calib_rows_verified": 1200,
}
_REF = "aapl_confirmatory-r3-00fd83d9cd39"
_PARTITION = GoldPartition("AAPL", "aapl_confirmatory-r0-665f45d9169a")
_DIGEST = "e" * 64
_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _summary(**changes: object) -> InferenceSummary:
    return InferenceSummary.from_mapping({**_SUMMARY, **changes})


def _command(**changes: object) -> RunConfirmatoryEvaluationCommand:
    fields: dict[str, Any] = {
        "name": "aapl_confirmatory",
        "revision": 3,
        "preregistration_ref": _REF,
        "inference_summary": _summary(),
    }
    fields.update(changes)
    return RunConfirmatoryEvaluationCommand(**fields)


def _result(**changes: object) -> RunConfirmatoryEvaluationResult:
    fields: dict[str, Any] = {
        "status": ConfirmatoryRunStatus.BLOCKED,
        "preregistration_ref": _REF,
        "partition": _PARTITION,
        "generation_digest": _DIGEST,
        "refresh_status": RefreshStatus.BLOCKED,
        "scorecard": None,
        "failed_checks": (),
        "attestation_body": "## corpo\n",
    }
    fields.update(changes)
    return RunConfirmatoryEvaluationResult(**fields)


@pytest.mark.unit
def test_status_values() -> None:
    assert [status.value for status in ConfirmatoryRunStatus] == [
        "JUDGED",
        "BLOCKED",
        "ALREADY_JUDGED",
    ]
    assert sealed_status(RefreshStatus.COMPLETED) is ConfirmatoryRunStatus.JUDGED
    assert sealed_status(RefreshStatus.BLOCKED) is ConfirmatoryRunStatus.BLOCKED


@pytest.mark.unit
def test_command_validates_name_revision_ref_and_deviation_type() -> None:
    command = _command(deviation=f"{DEVIATION_TAG} rerun with a fixed lock")
    assert (command.break_stale_lock, command.revision) == (False, 3)

    for changes, message in (
        ({"name": ""}, "name must be a non-empty str"),
        ({"preregistration_ref": None}, "preregistration_ref must be a non-empty str"),
        ({"revision": -1}, "revision must be an int >= 0"),
        ({"revision": True}, "revision must be an int >= 0"),
        ({"revision": 3.0}, "revision must be an int >= 0"),
        ({"break_stale_lock": 1}, "break_stale_lock must be a bool"),
        ({"deviation": ""}, "deviation must be a non-empty str or None"),
        ({"deviation": 7}, "deviation must be a non-empty str or None"),
        ({"inference_summary": dict(_SUMMARY)}, "inference_summary must be an InferenceSummary"),
    ):
        with pytest.raises(ValueError, match=message):
            _command(**changes)


@pytest.mark.unit
def test_deviation_must_cite_the_tag() -> None:
    check_deviation(None)
    check_deviation(f"see {DEVIATION_TAG} 2026-10-23")
    with pytest.raises(InvalidDeviationError, match=r"must cite a \[deviation\]"):
        check_deviation("rerun because of an out-of-memory")


@pytest.mark.unit
def test_inference_summary_from_mapping_exact_keys() -> None:
    summary = InferenceSummary.from_mapping(_SUMMARY)
    assert summary.as_mapping() == _SUMMARY
    assert InferenceSummary.from_mapping(summary.as_mapping()) == summary

    with pytest.raises(ValueError, match="exactly the keys"):
        InferenceSummary.from_mapping({**_SUMMARY, "extra": 1})
    with pytest.raises(ValueError, match="exactly the keys"):
        InferenceSummary.from_mapping({k: v for k, v in _SUMMARY.items() if k != "runs"})
    with pytest.raises(ValueError, match="must be a Mapping"):
        InferenceSummary.from_mapping([("runs", 1)])  # type: ignore[arg-type]
    for changes, message in (
        ({"runs": -1}, "inference runs must be an int >= 0"),
        ({"calib_rows_verified": True}, "calib_rows_verified must be an int >= 0"),
        ({"strict": 57}, r"must equal runs \(60\)"),
        ({"max_abs_diff": math.nan}, "max_abs_diff must be a finite number >= 0"),
        ({"max_abs_diff": -1e-9}, "max_abs_diff must be a finite number >= 0"),
        ({"max_abs_diff": True}, "max_abs_diff must be a finite number >= 0"),
    ):
        with pytest.raises(ValueError, match=message):
            _summary(**changes)


@pytest.mark.unit
def test_result_status_must_match_refresh_and_scorecard() -> None:
    assert _result().status is ConfirmatoryRunStatus.BLOCKED
    already = _result(
        status=ConfirmatoryRunStatus.ALREADY_JUDGED, refresh_status=RefreshStatus.COMPLETED
    )
    assert already.scorecard is None

    for changes, message in (
        ({"status": "BLOCKED"}, "status must be a ConfirmatoryRunStatus"),
        ({"refresh_status": RefreshStatus.COMPLETED}, "does not match refresh"),
        (
            {"status": ConfirmatoryRunStatus.JUDGED, "refresh_status": RefreshStatus.COMPLETED},
            "a scorecard comes with JUDGED",
        ),
        ({"generation_digest": "E" * 64}, "generation_digest"),
        ({"attestation_body": ""}, "attestation_body must be a non-empty str"),
        ({"failed_checks": []}, "failed_checks must be a tuple"),
        ({"partition": ("AAPL", "x")}, "partition must be a GoldPartition"),
    ):
        with pytest.raises(ValueError, match=message):
            _result(**changes)


@pytest.mark.unit
def test_run_record_document_is_json_safe_with_every_part() -> None:
    started_at = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
    attempt = JudgedAttempt(
        phase=AttemptPhase.STARTED,
        attempt_id=started_at.isoformat(),
        preregistration_ref=_REF,
        commit=_COMMIT,
        code={"code.src": "a" * 40},
        environment={"env.image_id": "sha256:" + "d" * 64},
        started_at=started_at,
    )
    failed = FailedCheck(
        check="alignment",
        kind="summary",
        horizon=1,
        model=None,
        seed=None,
        occurrences=2,
        detail="gap",
    )
    record = run_record_document(
        preregistration_ref=_REF,
        partition=_PARTITION,
        environment={"env.image_id": "sha256:" + "d" * 64, "commit": _COMMIT},
        inference_summary=_summary(),
        deviation=None,
        attempts=[attempt],
        refresh_status=RefreshStatus.BLOCKED,
        rows_by_table={"gold_quality_checks": 4},
        profile_error_units=0,
        conformal_error_units=1,
        failed_checks=[failed],
    )

    assert json.loads(json.dumps(record)) == record
    assert list(record[RUN_RECORD_ENVIRONMENT]) == ["commit", "env.image_id"]  # type: ignore[call-overload]
    assert record[RUN_RECORD_ATTEMPTS] == [attempt.as_mapping()]
    assert record[RUN_RECORD_FAILED_CHECKS] == [
        {
            "check": "alignment",
            "kind": "summary",
            "horizon": 1,
            "model": None,
            "seed": None,
            "occurrences": 2,
            "detail": "gap",
        }
    ]
    assert record["inference_summary"] == _SUMMARY
    assert record["refresh"] == {
        "status": "BLOCKED",
        "rows_by_table": {"gold_quality_checks": 4},
        "profile_error_units": 0,
        "conformal_error_units": 1,
    }
    assert record["seeds"] == dict(SEEDS_REFERENCE)
    assert record["partition"] == {"asset": "AAPL", "parent_sweep_id": _PARTITION.parent_sweep_id}
