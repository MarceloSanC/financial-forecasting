"""Testes dos DTOs da geração julgada e do registro de tentativas (Stage 8.1 Task 08).

O formato com dono único (`CONTENTS.sha256` no formato `sha256sum`, linhas do
`ATTEMPTS.jsonl`) e as invariantes de `JudgedGeneration` e `JudgedAttempt` (ADRs
8.1.0003 item 5b, 8.1.0004 item 1). A conferência contra disco é do contrato da Task 09.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    CONTENTS_NAME,
    GENERATION_MANIFEST,
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
    JudgedGeneration,
    attempts_jsonl,
    contents_listing,
    document_bytes,
    generation_digest_of,
    judged_generation_from,
    parse_attempts_jsonl,
    parse_contents_listing,
    verify_listing,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshStatus,
)
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT
from tests.unit.features.evaluation.gold.test_refresh_gold_dtos import _manifest

_A, _B, _C = "a" * 64, "b" * 64, "c" * 64
_REF = "aapl_confirmatory-r3-0123456789ab"
_PARTITION = GoldPartition("AAPL", "sweep-01")
_STARTED_AT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _started(**changes: object) -> JudgedAttempt:
    fields: dict[str, Any] = {
        "phase": AttemptPhase.STARTED,
        "attempt_id": _STARTED_AT.isoformat(),
        "preregistration_ref": _REF,
        "commit": _COMMIT,
        "code": {"code.src": _A, "code.uv_lock": _B},
        "environment": {"env.image_id": "sha256:" + _C, "env.platform": "linux-x86_64"},
        "started_at": _STARTED_AT,
        "deviation": None,
        "prior_live_silver_content": None,
    }
    fields.update(changes)
    return JudgedAttempt(**fields)


def _input_read(**changes: object) -> JudgedAttempt:
    fields: dict[str, Any] = {
        "phase": AttemptPhase.INPUT_READ,
        "attempt_id": _STARTED_AT.isoformat(),
        "preregistration_ref": _REF,
        "silver_content": SAMPLE_SILVER_CONTENT,
        "dataset_fingerprint": _C,
    }
    fields.update(changes)
    return JudgedAttempt(**fields)


@pytest.mark.unit
def test_contents_listing_format_is_sha256sum() -> None:
    listing = contents_listing(
        {"generation/b.parquet": _B, "Z.json": _C, "generation/a.parquet": _A}
    )

    assert (
        listing
        == (f"{_C}  Z.json\n{_A}  generation/a.parquet\n{_B}  generation/b.parquet\n").encode()
    )
    # ordenado pelos bytes do caminho (maiúsculas antes de minúsculas), UTF-8, LF
    accented = contents_listing({"é.json": _A, "z.json": _B})
    assert accented == f"{_B}  z.json\n{_A}  é.json\n".encode()
    assert generation_digest_of(listing) == hashlib.sha256(listing).hexdigest()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(f"{_A}  a.json\r\n".encode(), "LF line endings", id="crlf"),
        pytest.param(f"{_A}  a.json".encode(), "end with a LF", id="no-final-lf"),
        pytest.param(f"{'A' * 64}  a.json\n".encode(), "line 1 is not", id="upper-hex"),
        pytest.param(f"{_A} a.json\n".encode(), "line 1 is not", id="one-space"),
        pytest.param(f"{_A}  a.json\n{_B}  a.json\n".encode(), "twice", id="duplicate"),
        pytest.param(f"{_A}  b.json\n{_B}  a.json\n".encode(), "not sorted", id="unsorted"),
        pytest.param(f"{_A}  ../x.json\n".encode(), "relative POSIX", id="escape"),
        pytest.param(f"{_A}  dir\\x.json\n".encode(), "relative POSIX", id="backslash"),
        pytest.param(f"{_A}  {CONTENTS_NAME}\n".encode(), "does not list itself", id="self"),
        pytest.param(b"\xff\xfe", "not UTF-8", id="bytes"),
    ],
)
def test_parse_listing_rejects_crlf_bad_hex_duplicate_or_unsorted(
    data: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_contents_listing(data)


@pytest.mark.unit
def test_listing_round_trip() -> None:
    files = {"generation/MANIFEST.json": _A, RUN_RECORD_DOCUMENT: _B, SCORECARD_DOCUMENT: _C}

    assert parse_contents_listing(contents_listing(files)) == files
    assert parse_contents_listing(b"") == {}
    with pytest.raises(ValueError, match="sha256"):
        contents_listing({"a.json": "xyz"})


@pytest.mark.unit
def test_verify_listing_names_missing_extra_altered_and_empty_generation() -> None:
    files = {GENERATION_MANIFEST: _A, RUN_RECORD_DOCUMENT: _B}
    listing = contents_listing(files)

    assert verify_listing(listing, files) == files
    with pytest.raises(ValueError, match="missing"):
        verify_listing(listing, {GENERATION_MANIFEST: _A})
    with pytest.raises(ValueError, match="extra"):
        verify_listing(listing, {**files, "x.json": _C})
    with pytest.raises(ValueError, match="differ from their sha256"):
        verify_listing(listing, {**files, RUN_RECORD_DOCUMENT: _C})
    only_documents = {RUN_RECORD_DOCUMENT: _B}
    with pytest.raises(ValueError, match="empty generation/"):
        verify_listing(contents_listing(only_documents), only_documents)


@pytest.mark.unit
def test_attempt_round_trip_started_and_input_read() -> None:
    started = _started(
        deviation="[deviation] reprocessed", prior_live_silver_content=SAMPLE_SILVER_CONTENT
    )
    attempts = (started, _input_read(), _started())

    assert JudgedAttempt.from_mapping(started.as_mapping()) == started
    assert parse_attempts_jsonl(attempts_jsonl(attempts)) == attempts
    assert attempts_jsonl(attempts).count(b"\n") == len(attempts)
    assert set(_input_read().as_mapping()) == {
        "phase",
        "attempt_id",
        "preregistration_ref",
        "silver_content",
        "dataset_fingerprint",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(
            lambda: _input_read(silver_content=None), "needs a SilverContent", id="ir-no-silver"
        ),
        pytest.param(
            lambda: _input_read(dataset_fingerprint="x"), "dataset_fingerprint", id="ir-fp"
        ),
        pytest.param(lambda: _input_read(commit=_COMMIT), "cannot carry", id="ir-commit"),
        pytest.param(lambda: _started(code=None), "attempt code must be", id="st-no-code"),
        pytest.param(lambda: _started(environment={}), "attempt environment", id="st-no-env"),
        pytest.param(lambda: _started(code={"src": _A}), "start with 'code.'", id="st-code-key"),
        pytest.param(
            lambda: _started(environment={"image_id": "x"}), "start with 'env.'", id="st-env-key"
        ),
        pytest.param(lambda: _started(commit="abc"), "40 lowercase hex", id="st-commit"),
        pytest.param(lambda: _started(attempt_id="other"), "isoformat", id="st-attempt-id"),
        pytest.param(
            lambda: _started(started_at=datetime(2026, 10, 23)),
            "timezone-aware",
            id="st-naive",
        ),
        pytest.param(
            lambda: _started(silver_content=SAMPLE_SILVER_CONTENT), "cannot carry", id="st-silver"
        ),
        pytest.param(lambda: _started(deviation=""), "deviation", id="st-deviation"),
    ],
)
def test_attempt_phase_fields_validated(build: Any, message: str) -> None:  # noqa: ANN401
    with pytest.raises(ValueError, match=message):
        build()


@pytest.mark.unit
def test_attempt_from_mapping_rejects_extra_or_missing_key() -> None:
    mapping = _input_read().as_mapping()

    with pytest.raises(ValueError, match="exactly the keys"):
        JudgedAttempt.from_mapping({**mapping, "commit": _COMMIT})
    with pytest.raises(ValueError, match="exactly the keys"):
        JudgedAttempt.from_mapping({k: v for k, v in mapping.items() if k != "dataset_fingerprint"})
    with pytest.raises(ValueError, match="is not a valid AttemptPhase"):
        JudgedAttempt.from_mapping({**mapping, "phase": "finished"})


def _generation(**changes: object) -> JudgedGeneration:
    fields: dict[str, Any] = {
        "preregistration_ref": _REF,
        "partition": _PARTITION,
        "generation_digest": _A,
        "refresh_status": RefreshStatus.COMPLETED,
        "files": {GENERATION_MANIFEST: _B, RUN_RECORD_DOCUMENT: _C},
        "manifest": _manifest(),
        "documents": {RUN_RECORD_DOCUMENT: {"commit": _COMMIT}},
    }
    fields.update(changes)
    return JudgedGeneration(**fields)


@pytest.mark.unit
def test_judged_generation_requires_non_empty_files_and_hex_digest() -> None:
    generation = _generation()
    assert generation.files[GENERATION_MANIFEST] == _B

    with pytest.raises(ValueError, match="non-empty Mapping"):
        _generation(files={})
    with pytest.raises(ValueError, match="generation_digest"):
        _generation(generation_digest="A" * 64)
    with pytest.raises(ValueError, match="sha256 of"):
        _generation(files={GENERATION_MANIFEST: "x"})
    with pytest.raises(ValueError, match=r"documents must hold run_record.json"):
        _generation(documents={SCORECARD_DOCUMENT: {}})
    with pytest.raises(ValueError, match="documents must hold"):
        _generation(documents={RUN_RECORD_DOCUMENT: {}, "other.json": {}})
    with pytest.raises(ValueError, match="refresh_status"):
        _generation(refresh_status="COMPLETED")
    with pytest.raises(dataclasses.FrozenInstanceError):
        generation.generation_digest = _B  # type: ignore[misc]


@pytest.mark.unit
def test_judged_generation_from_reads_manifest_and_documents() -> None:
    manifest = _manifest()
    data = {
        GENERATION_MANIFEST: document_bytes(manifest.as_mapping()),
        RUN_RECORD_DOCUMENT: document_bytes({"commit": _COMMIT}),
    }
    actual = {path: hashlib.sha256(content).hexdigest() for path, content in data.items()}
    listing = contents_listing(actual)

    generation = judged_generation_from(
        partition=_PARTITION,
        preregistration_ref=_REF,
        listing=listing,
        actual=actual,
        read=data.__getitem__,
    )

    assert generation.manifest == manifest
    assert generation.documents == {RUN_RECORD_DOCUMENT: {"commit": _COMMIT}}
    assert generation.generation_digest == generation_digest_of(listing)
    assert generation.refresh_status is manifest.status
    assert document_bytes({"b": 1, "a": [1.5]}) == b'{\n  "a": [\n    1.5\n  ],\n  "b": 1\n}\n'
