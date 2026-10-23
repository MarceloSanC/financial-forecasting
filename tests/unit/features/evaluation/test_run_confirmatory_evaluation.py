"""Unit test do use case `RunConfirmatoryEvaluation` (Stage 8.1 Task 13; A4, A5, A6b, A7).

Mundo de fakes: `InMemoryPreregistrationSource` com a revisão 0 ancorada,
`InMemoryGoldStore` + `InMemoryGoldGenerationReader`, `InMemoryJudgedGenerationStore`,
`InMemoryEvaluationEnvironment`, `InMemoryEvaluationWriterLock`, o `FakeGoldRefresh`
(publica gerações da fábrica do scorecard) e o `FakeScorecardBuilder` (delega ao
`BuildConfirmatoryScorecard` real sobre os mesmos fakes). Cada guarda reprovada tem
efeito zero: nenhum refresh, nenhum scorecard, nenhuma publicação, nenhum `preserve`,
nenhuma tentativa registrada e o lock liberado quando adquirido (I2).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    DEVIATION_TAG,
    ConfirmatoryRunStatus,
    DirtyCodeError,
    InferenceSummary,
    InvalidDeviationError,
    PriorAttemptCodeChangedError,
    PriorAttemptDivergenceError,
    PriorAttemptEnvironmentChangedError,
    PriorAttemptInputChangedError,
    RunConfirmatoryEvaluationCommand,
    RunConfirmatoryEvaluationResult,
)
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    PreregistrationChainError,
    PreregistrationHashMismatchError,
    PreregistrationNotAnchoredError,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_QUALITY_CHECKS,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    CONTENTS_NAME,
    GENERATION_MANIFEST,
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldPartition,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    CPU_CAPABILITY_KEY,
    IMAGE_ID_KEY,
    PLATFORM_KEY,
    PREREGISTRATION_DIRTY_KEY,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationExistsError,
    JudgedGenerationMismatchError,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JUDGED_TAG_PREFIX,
    JudgedRecord,
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.application.use_cases.build_confirmatory_scorecard import (  # noqa: E501
    BuildConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.application.use_cases.confirmatory_attestation import (  # noqa: E501
    attestation_body,
)
from financial_forecasting.features.evaluation.application.use_cases.run_confirmatory_evaluation import (  # noqa: E501
    RunConfirmatoryEvaluation,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.fakes.features.evaluation.fake_confirmatory_steps import (
    FakeGoldRefresh,
    FakeScorecardBuilder,
)
from tests.fakes.features.evaluation.in_memory_evaluation_environment import (
    CLEAN_SNAPSHOT,
    InMemoryEvaluationEnvironment,
)
from tests.fakes.features.evaluation.in_memory_evaluation_writer_lock import (
    InMemoryEvaluationWriterLock,
)
from tests.fakes.features.evaluation.in_memory_gold_generation_reader import (
    InMemoryGoldGenerationReader,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.features.evaluation.in_memory_judged_generation_store import (
    InMemoryJudgedGenerationStore,
)
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    valid_payload,
)
from tests.unit.features.evaluation._scorecard_factory import STARTED_AT, StoredGold, make_stored

pytestmark = pytest.mark.unit

_NAME = "test_plan"
_OTHER_REF = "test_plan-r9-ffffffffffff"
_COMMIT = CLEAN_SNAPSHOT["commit"]
_SUMMARY = InferenceSummary(
    runs=6, strict=6, tolerance=0, max_abs_diff=0.0, calib_rows_written=0, calib_rows_verified=12
)
_OTHER_SILVER = SilverContent(
    digest="ee" * 32,
    tables={"dim_run": "e1" * 32},
    units={"dim_run|sweep-01": "e1" * 32},
)
_DEVIATION = f"{DEVIATION_TAG} 2026-10-23 — re-run after an out-of-memory"


def _reference(payload: dict[str, object]) -> str:
    plan = Preregistration.from_mapping(payload)
    return plan.reference(
        PreregistrationHash.compute(hasher=FloatRefusingHasher(), payload=plan.as_payload())
    )


def _anchor(reference: str) -> PreregistrationAnchor:
    return PreregistrationAnchor(
        tag=f"preregistration/{reference}",
        commit=_COMMIT,
        comment_url="https://github.com/example/repo/issues/1#issuecomment-1",
        anchored_at=STARTED_AT - timedelta(days=1),
    )


class _TickClock:
    """Um segundo a mais por chamada (cada tentativa tem o seu `attempt_id`)."""

    def __init__(self) -> None:
        self._now = STARTED_AT + timedelta(hours=1)

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


class _World:
    """Os fakes de um cenário e a fábrica do use case."""

    def __init__(self) -> None:
        payload = valid_payload()
        self.ref = _reference(payload)
        self.plan = Preregistration.from_mapping(payload)
        self.source = InMemoryPreregistrationSource()
        self.source.add(_NAME, 0, payload, _anchor(self.ref))
        self.store = InMemoryGoldStore()
        self.reader = InMemoryGoldGenerationReader(self.store)
        self.judged = InMemoryJudgedGenerationStore(self.store)
        self.environment = InMemoryEvaluationEnvironment()
        self.lock = InMemoryEvaluationWriterLock()
        self.clock = _TickClock()
        self.refresh = FakeGoldRefresh(self.store, [self.generation()], clock=self.clock)
        scorecard = BuildConfirmatoryScorecard(
            source=self.source,
            reader=InMemoryGoldGenerationReader(self.store),
            hasher=FloatRefusingHasher(),
        )
        self.scorecard = FakeScorecardBuilder(scorecard)

    @property
    def partition(self) -> GoldPartition:
        return self.generation().manifest.partition

    def stored(self, reference: str | None = None, **kwargs: object) -> StoredGold:
        return make_stored(self.plan, reference=reference or self.ref, **kwargs)  # type: ignore[arg-type]

    def generation(self, reference: str | None = None, **kwargs: object) -> GoldGeneration:
        return self.stored(reference, **kwargs).generation()

    def publish(self, generation: GoldGeneration) -> None:
        self.store.publish(
            partition=generation.manifest.partition,
            tables=list(generation.tables.values()),
            manifest=generation.manifest,
        )

    def seal(self, reference: str) -> str:
        """Publica e sela uma cópia de `reference` direto no store (estado anterior)."""
        generation = self.generation(reference)
        self.publish(generation)
        sealed = self.judged.preserve(
            partition=generation.manifest.partition,
            preregistration_ref=reference,
            expected_manifest=generation.manifest,
            documents={RUN_RECORD_DOCUMENT: {"environment": {"commit": _COMMIT}}},
        )
        return sealed.generation_digest

    def use_case(self) -> RunConfirmatoryEvaluation:
        return RunConfirmatoryEvaluation(
            source=self.source,
            hasher=FloatRefusingHasher(),
            refresh_gold=self.refresh,
            build_scorecard=self.scorecard,
            judged_store=self.judged,
            gold_reader=self.reader,
            environment=self.environment,
            writer_lock=self.lock,
            clock=self.clock,
        )

    def command(self, **changes: object) -> RunConfirmatoryEvaluationCommand:
        fields: dict[str, Any] = {
            "name": _NAME,
            "revision": 0,
            "preregistration_ref": self.ref,
            "inference_summary": _SUMMARY,
        }
        fields.update(changes)
        return RunConfirmatoryEvaluationCommand(**fields)

    def run(self, **changes: object) -> RunConfirmatoryEvaluationResult:
        return self.use_case()(self.command(**changes))

    def effects(self) -> tuple[int, int, int, int, int]:
        return (
            len(self.refresh.calls),
            len(self.scorecard.calls),
            self.store.publishes,
            self.judged.preserves,
            self.judged.recorded,
        )


def _started(world: _World, reference: str, **changes: object) -> JudgedAttempt:
    at = STARTED_AT + timedelta(minutes=5)
    fields: dict[str, Any] = {
        "phase": AttemptPhase.STARTED,
        "attempt_id": at.isoformat(),
        "preregistration_ref": reference,
        "commit": _COMMIT,
        "code": {k: v for k, v in CLEAN_SNAPSHOT.items() if k.startswith("code.")},
        "environment": {k: v for k, v in CLEAN_SNAPSHOT.items() if k.startswith("env.")},
        "started_at": at,
    }
    fields.update(changes)
    return JudgedAttempt(**fields)


def _input_read(
    world: _World,
    silver: SilverContent,
    fingerprint: str,
    *,
    minutes: int = 5,
    result_digest: str | None = None,
) -> JudgedAttempt:
    return JudgedAttempt(
        phase=AttemptPhase.INPUT_READ,
        attempt_id=(STARTED_AT + timedelta(minutes=minutes)).isoformat(),
        preregistration_ref=world.ref,
        silver_content=silver,
        dataset_fingerprint=fingerprint,
        result_digest=result_digest or result_layer_digest(world.generation()),
    )


def _judged_record(reference: str, digest: str) -> JudgedRecord:
    return JudgedRecord(
        revision=0,
        preregistration_ref=reference,
        generation_digest=digest,
        refresh_status=RefreshStatus.COMPLETED,
        commit=_COMMIT,
        tag=f"{JUDGED_TAG_PREFIX}{reference}",
        comment_url="https://github.com/example/repo/issues/211#issuecomment-2",
        commented_at=STARTED_AT + timedelta(days=1),
        input_backup="data/backups/input",
        input_backup_sha256="1" * 64,
        judged_backup="data/backups/judged",
        judged_backup_sha256="2" * 64,
    )


# --- A4: guardas com efeito zero ------------------------------------------------------


def _chain_broken(world: _World) -> dict[str, Any]:
    payload = {
        **valid_payload(),
        "revision": 1,
        "amends": "test_plan-r0-000000000000",
        "justification": "a blinded fix",
        "blind_status": "blinded",
    }
    reference = _reference(payload)
    world.source.add(_NAME, 1, payload, _anchor(reference))
    return {"revision": 1, "preregistration_ref": reference}


def _hash_differs(world: _World) -> dict[str, Any]:
    return {"preregistration_ref": "test_plan-r0-000000000000"}


def _unanchored(world: _World) -> dict[str, Any]:
    world.source.add(_NAME, 0, valid_payload(), None)
    return {}


def _code_dirty(world: _World) -> dict[str, Any]:
    world.environment = InMemoryEvaluationEnvironment({CODE_DIRTY_KEY: "true"})
    return {}


def _preregistration_dirty(world: _World) -> dict[str, Any]:
    world.environment = InMemoryEvaluationEnvironment({PREREGISTRATION_DIRTY_KEY: "true"})
    return {}


def _judged_toml_of_other_revision(world: _World) -> dict[str, Any]:
    world.source.add_judged(_NAME, _judged_record(_OTHER_REF, "3" * 64))
    return {}


def _judged_toml_without_copy(world: _World) -> dict[str, Any]:
    world.source.add_judged(_NAME, _judged_record(world.ref, "3" * 64))
    return {}


def _judged_toml_with_other_digest(world: _World) -> dict[str, Any]:
    world.seal(world.ref)
    world.source.add_judged(_NAME, _judged_record(world.ref, "3" * 64))
    return {}


def _sealed_copy_of_other_revision(world: _World) -> dict[str, Any]:
    world.seal(_OTHER_REF)
    return {}


def _attempt_of_other_revision(world: _World) -> dict[str, Any]:
    world.judged.record_attempt(partition=world.partition, attempt=_started(world, _OTHER_REF))
    return {}


def _live_of_other_revision(world: _World) -> dict[str, Any]:
    world.publish(world.generation(_OTHER_REF))
    return {}


def _live_without_attempt(world: _World) -> dict[str, Any]:
    world.publish(world.generation())
    return {}


def _attempt_with_other_code(world: _World) -> dict[str, Any]:
    code = {**_started(world, world.ref).code, "code.src": "9" * 40}  # type: ignore[dict-item]
    world.judged.record_attempt(
        partition=world.partition, attempt=_started(world, world.ref, code=code)
    )
    return {}


def _attempt_with_other_environment(key: str, value: str) -> Callable[[_World], dict[str, Any]]:
    def arrange(world: _World) -> dict[str, Any]:
        environment = {**_started(world, world.ref).environment, key: value}  # type: ignore[dict-item]
        attempt = _started(world, world.ref, environment=environment)
        world.judged.record_attempt(partition=world.partition, attempt=attempt)
        return {}

    return arrange


def _deviation_without_tag(world: _World) -> dict[str, Any]:
    return {"deviation": "re-run after an out-of-memory"}


def _coherent_copy_with_other_digest(world: _World) -> dict[str, Any]:
    digest = world.seal(world.ref)
    world.source.add_judged(_NAME, _judged_record(world.ref, digest))
    world.judged.tamper(
        partition=world.partition,
        preregistration_ref=world.ref,
        path=RUN_RECORD_DOCUMENT,
        data=b'{"environment": {"commit": "rewritten"}}\n',
    )
    world.judged.rewrite_contents(partition=world.partition, preregistration_ref=world.ref)
    return {}


_GUARDS = [
    pytest.param(_chain_broken, PreregistrationChainError, False, id="G1-chain-broken"),
    pytest.param(_hash_differs, PreregistrationHashMismatchError, False, id="G1-hash-differs"),
    pytest.param(_unanchored, PreregistrationNotAnchoredError, False, id="G1-unanchored"),
    pytest.param(_code_dirty, DirtyCodeError, False, id="G2-code-dirty"),
    pytest.param(_preregistration_dirty, DirtyCodeError, False, id="G2-preregistration-dirty"),
    pytest.param(
        _judged_toml_of_other_revision,
        JudgedGenerationExistsError,
        True,
        id="G4a-judged-toml-of-other-revision",
    ),
    pytest.param(
        _judged_toml_without_copy,
        JudgedGenerationTamperedError,
        True,
        id="G4a-judged-toml-without-copy",
    ),
    pytest.param(
        _judged_toml_with_other_digest,
        JudgedGenerationTamperedError,
        True,
        id="G4a-judged-toml-with-other-digest",
    ),
    pytest.param(
        _sealed_copy_of_other_revision,
        JudgedGenerationExistsError,
        True,
        id="G4b-sealed-copy-of-other-revision",
    ),
    pytest.param(
        _attempt_of_other_revision,
        JudgedGenerationExistsError,
        True,
        id="G4c-attempt-of-other-revision",
    ),
    pytest.param(
        _live_of_other_revision, JudgedGenerationExistsError, True, id="G4d-live-of-other-revision"
    ),
    pytest.param(
        _live_without_attempt, JudgedGenerationTamperedError, True, id="G4d-live-without-attempt"
    ),
    pytest.param(
        _attempt_with_other_code,
        PriorAttemptCodeChangedError,
        True,
        id="G4e-attempt-with-other-code",
    ),
    pytest.param(
        _attempt_with_other_environment(IMAGE_ID_KEY, "sha256:" + "0" * 64),
        PriorAttemptEnvironmentChangedError,
        True,
        id="G4e-other-image-id",
    ),
    pytest.param(
        _attempt_with_other_environment(PLATFORM_KEY, "Windows-11"),
        PriorAttemptEnvironmentChangedError,
        True,
        id="G4e-other-platform",
    ),
    pytest.param(
        _attempt_with_other_environment(CPU_CAPABILITY_KEY, "AVX512"),
        PriorAttemptEnvironmentChangedError,
        True,
        id="G4e-other-cpu-capability",
    ),
    pytest.param(
        _deviation_without_tag, InvalidDeviationError, True, id="G4-deviation-without-tag"
    ),
    pytest.param(
        _coherent_copy_with_other_digest,
        JudgedGenerationTamperedError,
        True,
        id="G4a-coherent-copy-with-other-digest",
    ),
]


@pytest.mark.parametrize(("arrange", "error", "locked"), _GUARDS)
def test_guard_refuses_with_zero_effect(
    arrange: Callable[[_World], dict[str, Any]], error: type[Exception], locked: bool
) -> None:
    world = _World()
    changes = arrange(world)
    before = world.effects()

    with pytest.raises(error):
        world.run(**changes)

    assert world.effects() == before
    assert world.lock.acquired == (1 if locked else 0)
    assert world.lock.released == world.lock.acquired
    assert not world.lock.held


def test_guards_run_in_order() -> None:
    """G1 antes de G2 antes de G3 antes de G4: cada guarda só fala com as anteriores ok."""
    world = _World()
    _judged_toml_of_other_revision(world)
    world.lock.hold_by_other()
    world.environment = InMemoryEvaluationEnvironment({CODE_DIRTY_KEY: "true"})

    with pytest.raises(PreregistrationHashMismatchError):
        world.run(**_hash_differs(world))
    assert world.environment.snapshots == 0  # G2 não rodou

    with pytest.raises(DirtyCodeError):
        world.run()
    assert world.environment.snapshots == 1
    assert world.lock.acquired == 0  # G3 não rodou

    world.environment = InMemoryEvaluationEnvironment()
    with pytest.raises(ApplicationError, match="already held"):
        world.run()
    assert world.lock.acquired == 0

    with pytest.raises(JudgedGenerationExistsError):
        world.run(break_stale_lock=True)
    assert (world.lock.acquired, world.lock.released) == (1, 1)
    assert world.effects() == (0, 0, 0, 0, 0)


# --- conferências depois do E1 --------------------------------------------------------


def test_input_changed_raises_and_seals_nothing() -> None:
    world = _World()
    fingerprint = world.generation().manifest.dataset_fingerprint.value
    world.judged.record_attempt(partition=world.partition, attempt=_started(world, world.ref))
    world.judged.record_attempt(
        partition=world.partition, attempt=_input_read(world, _OTHER_SILVER, fingerprint)
    )

    with pytest.raises(PriorAttemptInputChangedError, match="another input"):
        world.run()

    assert world.judged.preserves == 0
    assert world.scorecard.calls == []
    phases = [a.phase for a in world.judged.attempts(partition=world.partition)]
    assert phases == [AttemptPhase.STARTED, AttemptPhase.INPUT_READ] * 2  # tentativa registrada
    assert not world.lock.held


def test_divergent_generation_with_equal_code_env_input_raises_and_seals_nothing() -> None:
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("crash after E1")
    with pytest.raises(GoldGenerationCorruptError):
        world.run()  # 1ª tentativa: geração viva desta revisão, nada selado
    stored = world.stored()
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "detail", "changed")
    world.refresh.generations = [stored.generation()]
    world.scorecard.error = None

    with pytest.raises(PriorAttemptDivergenceError, match="R-BIT"):
        world.run()

    assert world.judged.preserves == 0
    assert len(world.scorecard.calls) == 1  # só a da 1ª tentativa
    assert not world.lock.held


# --- A5: replay e tentativas ----------------------------------------------------------


def test_sealed_intact_is_already_judged_without_refresh_or_scorecard() -> None:
    world = _World()
    first = world.run()
    before = world.effects()

    again = world.run()

    assert first.status is ConfirmatoryRunStatus.JUDGED
    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert again.attestation_body == first.attestation_body
    assert again.generation_digest == first.generation_digest
    assert (again.scorecard, again.refresh_status) == (None, RefreshStatus.COMPLETED)
    assert world.effects() == before  # zero refresh, scorecard, publish, preserve, tentativa
    assert not world.lock.held


def test_committed_record_of_this_revision_with_same_digest_is_already_judged() -> None:
    world = _World()
    first = world.run()
    world.source.add_judged(_NAME, _judged_record(world.ref, first.generation_digest))
    recorded = world.judged.recorded

    again = world.run()

    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert world.judged.recorded == recorded


def test_crash_between_e1_and_e3_leaves_attempt_and_no_seal() -> None:
    world = _World()
    world.judged.fail_writes = {CONTENTS_NAME}

    with pytest.raises(OSError, match="injected write failure"):
        world.run()

    assert world.judged.judged_refs(partition=world.partition) == ()
    assert world.store.publishes == 1  # o E1 publicou: os números existem (I13)
    phases = [a.phase for a in world.judged.attempts(partition=world.partition)]
    assert phases == [AttemptPhase.STARTED, AttemptPhase.INPUT_READ]
    assert not world.lock.held


def test_rerun_same_code_env_input_completes_with_two_attempts_in_run_record() -> None:
    world = _World()
    world.judged.fail_writes = {CONTENTS_NAME}
    with pytest.raises(OSError):
        world.run()
    world.judged.fail_writes = set()

    result = world.run()

    assert result.status is ConfirmatoryRunStatus.JUDGED
    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    record = sealed.documents[RUN_RECORD_DOCUMENT]
    attempts = record["attempts"]
    assert [a["phase"] for a in attempts] == ["started", "input_read"] * 2  # type: ignore[attr-defined]
    assert len({a["attempt_id"] for a in attempts}) == 2  # type: ignore[attr-defined]  # noqa: PLR2004
    assert record["deviation"] is None


def test_rerun_with_changed_code_and_valid_deviation_records_it() -> None:
    world = _World()
    world.judged.fail_writes = {CONTENTS_NAME}
    with pytest.raises(OSError):
        world.run()
    world.judged.fail_writes = set()
    world.environment = InMemoryEvaluationEnvironment({"code.src": "9" * 40})
    with pytest.raises(PriorAttemptCodeChangedError):
        world.run()

    result = world.run(deviation=_DEVIATION)

    assert result.status is ConfirmatoryRunStatus.JUDGED
    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    record = sealed.documents[RUN_RECORD_DOCUMENT]
    assert record["deviation"] == _DEVIATION
    started = [
        a
        for a in world.judged.attempts(partition=world.partition)
        if a.phase is AttemptPhase.STARTED
    ]
    assert [a.deviation for a in started] == [None, _DEVIATION]
    assert started[-1].code["code.src"] == "9" * 40  # type: ignore[index]


def test_staging_leftover_removed() -> None:
    world = _World()
    world.judged.leave_staging(world.partition)

    result = world.run()

    assert result.status is ConfirmatoryRunStatus.JUDGED
    assert not world.judged.staging_exists(world.partition)
    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    assert not any("leftover" in path for path in sealed.files)


# --- A6b, A7 e propagação -------------------------------------------------------------


def test_scorecard_manifest_read_differs_raises_mismatch_nothing_sealed() -> None:
    world = _World()
    other = world.generation(started_at=STARTED_AT + timedelta(minutes=1)).manifest
    world.scorecard.manifest_read = other

    with pytest.raises(JudgedGenerationMismatchError, match="I8"):
        world.run()

    assert world.judged.preserves == 0
    assert world.judged.judged_refs(partition=world.partition) == ()
    assert not world.lock.held


_FAILED = FailedCheck(
    check="degeneracy_check",
    kind="summary",
    horizon=None,
    model=None,
    seed=None,
    occurrences=1,
    detail="",
)


def _blocked_world() -> _World:
    world = _World()
    blocked = world.generation(
        status=RefreshStatus.BLOCKED, checks=[("degeneracy_check", "error", "fail")]
    )
    world.refresh = FakeGoldRefresh(
        world.store, [blocked], clock=world.clock, failed_checks=(_FAILED,)
    )
    return world


def test_blocked_preserves_without_scorecard_and_with_failed_checks() -> None:
    world = _blocked_world()

    result = world.run()

    assert result.status is ConfirmatoryRunStatus.BLOCKED
    assert (result.refresh_status, result.scorecard, result.failed_checks) == (
        RefreshStatus.BLOCKED,
        None,
        (_FAILED,),
    )
    assert world.scorecard.calls == []
    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    assert SCORECARD_DOCUMENT not in sealed.documents
    assert sealed.documents[RUN_RECORD_DOCUMENT]["failed_checks"] == [dataclasses.asdict(_FAILED)]
    assert "degeneracy_check" in result.attestation_body


def test_blocked_second_call_is_already_judged() -> None:
    world = _blocked_world()
    first = world.run()

    again = world.run()

    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert again.refresh_status is RefreshStatus.BLOCKED
    assert again.attestation_body == first.attestation_body
    assert len(world.refresh.calls) == 1


def test_scorecard_error_propagates_with_attempt_recorded_and_nothing_sealed() -> None:
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("corrupt generation")

    with pytest.raises(GoldGenerationCorruptError, match="corrupt generation"):
        world.run()

    assert world.judged.preserves == 0
    assert world.judged.recorded == 2  # started + input_read  # noqa: PLR2004
    assert not world.lock.held
    assert world.lock.released == 1


def test_attempt_recorded_before_refresh() -> None:
    world = _World()
    seen: list[int] = []
    publish = world.refresh

    def refresh(command: RefreshGoldCommand) -> RefreshGoldResult:
        seen.append(world.judged.recorded)
        return publish(command)

    case = RunConfirmatoryEvaluation(
        source=world.source,
        hasher=FloatRefusingHasher(),
        refresh_gold=refresh,
        build_scorecard=world.scorecard,
        judged_store=world.judged,
        gold_reader=world.reader,
        environment=world.environment,
        writer_lock=world.lock,
        clock=world.clock,
    )
    case(world.command())

    assert seen == [1]  # a linha `started` já estava gravada quando o refresh começou
    first = world.judged.attempts(partition=world.partition)[0]
    assert first.phase is AttemptPhase.STARTED
    assert first.commit == _COMMIT
    assert first.prior_live_silver_content is None


def _fail_at(stage: str) -> Callable[[_World], None]:
    def arrange(world: _World) -> None:
        if stage == "G4":
            _attempt_of_other_revision(world)
        elif stage == "E1":
            world.refresh.error = RuntimeError("E1 failed")
        elif stage == "E2":
            world.scorecard.error = RuntimeError("E2 failed")
        else:
            world.judged.fail_writes = {RUN_RECORD_DOCUMENT}

    return arrange


@pytest.mark.parametrize("stage", ["G4", "E1", "E2", "E3"])
def test_lock_released_on_any_exception_after_g3(stage: str) -> None:
    world = _World()
    _fail_at(stage)(world)

    with pytest.raises((ApplicationError, RuntimeError, OSError)):
        world.run()

    assert (world.lock.acquired, world.lock.released) == (1, 1)
    assert not world.lock.held


def test_judged_returns_scorecard_digest_and_body() -> None:
    world = _World()

    result = world.run()

    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    assert result.status is ConfirmatoryRunStatus.JUDGED
    assert result.scorecard is not None
    assert result.scorecard.manifest_read == world.refresh.published[0]
    assert sealed.documents[SCORECARD_DOCUMENT] == result.scorecard.as_mapping()
    assert result.generation_digest == sealed.generation_digest
    assert result.attestation_body == attestation_body(sealed)
    assert result.partition == world.partition
    assert GENERATION_MANIFEST in sealed.files
    record = sealed.documents[RUN_RECORD_DOCUMENT]
    assert record["environment"] == dict(sorted(CLEAN_SNAPSHOT.items()))
    assert record["inference_summary"] == _SUMMARY.as_mapping()
    assert world.refresh.calls[0].parameters.preregistration_ref == world.ref


def test_rerun_after_crash_records_the_live_silver_content() -> None:
    """A 2ª tentativa grava o `silver_content` da geração viva desta revisão (I13)."""
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("crash after E1")
    with pytest.raises(GoldGenerationCorruptError):
        world.run()
    world.scorecard.error = None

    assert world.run().status is ConfirmatoryRunStatus.JUDGED
    started = [
        a
        for a in world.judged.attempts(partition=world.partition)
        if a.phase is AttemptPhase.STARTED
    ]
    live = world.refresh.generations[0].manifest.silver_content
    assert [a.prior_live_silver_content for a in started] == [None, live]


# --- CC5 (Checkpoint C bloco 5): referência = toda tentativa desde o último desvio -------


def _diverged_world() -> _World:
    """1ª tentativa cai depois do E1; a 2ª publica outro resultado e é recusada."""
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("crash after E1")
    with pytest.raises(GoldGenerationCorruptError):
        world.run()
    stored = world.stored()
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "detail", "changed")
    world.refresh.generations = [stored.generation()]
    world.scorecard.error = None
    with pytest.raises(PriorAttemptDivergenceError):
        world.run()
    return world


def test_rerun_with_new_clock_instants_is_not_a_divergence() -> None:
    """CC5-1: a 2ª tentativa tem outros `started_at`/`finished_at` e o mesmo resultado."""
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("crash after E1")
    with pytest.raises(GoldGenerationCorruptError):
        world.run()
    world.scorecard.error = None

    result = world.run()

    assert result.status is ConfirmatoryRunStatus.JUDGED
    first, second = world.refresh.published
    assert (first.started_at, first.finished_at) != (second.started_at, second.finished_at)
    digests = {
        a.result_digest
        for a in world.judged.attempts(partition=world.partition)
        if a.phase is AttemptPhase.INPUT_READ
    }
    assert len(digests) == 1


def test_third_run_after_divergence_needs_deviation() -> None:
    """CC5-2: divergência registrada → a 3ª corrida sem `--deviation` é recusada no G4."""
    world = _diverged_world()
    before = world.effects()

    with pytest.raises(PriorAttemptDivergenceError, match="already diverged"):
        world.run()  # o mesmo resultado da 2ª: sem a referência viva, ainda é recusado

    assert world.effects() == before  # recusa antes de qualquer efeito
    result = world.run(deviation=_DEVIATION)
    assert result.status is ConfirmatoryRunStatus.JUDGED


def test_deleting_the_live_generation_does_not_disable_the_comparison() -> None:
    """CC5-2 (variante): sem `current/`, a referência continua sendo o log de tentativas."""
    world = _World()
    world.scorecard.error = GoldGenerationCorruptError("crash after E1")
    with pytest.raises(GoldGenerationCorruptError):
        world.run()
    world.store._generations.clear()  # apagar current/ à mão
    stored = world.stored()
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "detail", "changed")
    world.refresh.generations = [stored.generation()]
    world.scorecard.error = None

    with pytest.raises(PriorAttemptDivergenceError, match="R-BIT"):
        world.run()
    assert world.judged.preserves == 0


def test_input_differs_from_the_first_attempt_not_only_the_last() -> None:
    """CC5-3: a entrada é conferida contra TODA tentativa do trecho, não só a última."""
    world = _World()
    fingerprint = world.generation().manifest.dataset_fingerprint.value
    live_silver = world.generation().manifest.silver_content
    for minutes, silver in ((1, _OTHER_SILVER), (2, live_silver)):
        at = STARTED_AT + timedelta(minutes=minutes)
        world.judged.record_attempt(
            partition=world.partition,
            attempt=_started(world, world.ref, attempt_id=at.isoformat(), started_at=at),
        )
        world.judged.record_attempt(
            partition=world.partition,
            attempt=_input_read(world, silver, fingerprint, minutes=minutes),
        )

    with pytest.raises(PriorAttemptInputChangedError, match="another input"):
        world.run()  # igual à última (2ª), diferente da 1ª
    assert world.judged.preserves == 0


def test_deviation_starts_a_new_reference_segment() -> None:
    """Depois de uma tentativa com `--deviation`, a referência são as tentativas dela em diante."""
    world = _diverged_world()
    world.judged.fail_writes = {CONTENTS_NAME}
    with pytest.raises(OSError):
        world.run(deviation=_DEVIATION)  # desvio registrado; cai no E3
    world.judged.fail_writes = set()

    result = world.run()  # sem desvio: o trecho começa na tentativa com desvio

    assert result.status is ConfirmatoryRunStatus.JUDGED


# --- CC6 (Checkpoint C final): queda antes do input_read e desvio que não chegou a ler ---


def _crash_before_input_read(world: _World) -> GoldGeneration:
    """1ª tentativa: o E1 publica e o processo cai antes de gravar a linha `input_read`."""
    real = world.judged.record_attempt
    state = {"armed": True}

    def flaky(*, partition: GoldPartition, attempt: JudgedAttempt) -> None:
        if attempt.phase is AttemptPhase.INPUT_READ and state["armed"]:
            state["armed"] = False
            raise OSError("killed after E1 publish")
        real(partition=partition, attempt=attempt)

    world.judged.record_attempt = flaky  # type: ignore[method-assign]
    with pytest.raises(OSError, match="killed"):
        world.run()
    phases = [a.phase for a in world.judged.attempts(partition=world.partition)]
    assert phases == [AttemptPhase.STARTED]
    return world.reader.read_generation(partition=world.partition)


def test_crash_before_input_read_makes_the_live_generation_the_reference() -> None:
    """CC6-1: sem `input_read`, o que o E1 publicou (a geração viva) é a referência."""
    world = _World()
    _crash_before_input_read(world)
    stored = world.stored()
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "detail", "changed")
    world.refresh.generations = [stored.generation()]

    with pytest.raises(PriorAttemptDivergenceError, match=r"\['live'\]"):
        world.run()  # sem --deviation: o resultado novo difere do publicado pela 1ª

    assert world.judged.preserves == 0
    with pytest.raises(PriorAttemptDivergenceError, match="already diverged"):
        world.run()  # a divergência ficou registrada: daí em diante, só com desvio


def test_crash_before_input_read_then_same_result_is_judged() -> None:
    """CC6-1: com o mesmo resultado da geração viva, a re-execução sela normalmente."""
    world = _World()
    live = _crash_before_input_read(world)

    result = world.run()

    assert result.status is ConfirmatoryRunStatus.JUDGED
    read = [
        a
        for a in world.judged.attempts(partition=world.partition)
        if a.phase is AttemptPhase.INPUT_READ
    ]
    assert [a.result_digest for a in read] == [result_layer_digest(live)]


def test_deviation_attempt_dying_before_input_read_does_not_reset_the_reference() -> None:
    """CC6-2: um desvio que caiu no E1 não recomeça o trecho; sem desvio, segue recusado."""
    world = _diverged_world()
    world.refresh.error = OSError("killed in E1")
    with pytest.raises(OSError):
        world.run(deviation=_DEVIATION)
    world.refresh.error = None
    before = world.effects()

    with pytest.raises(PriorAttemptDivergenceError, match="already diverged"):
        world.run()  # sem --deviation

    assert world.effects() == before
    result = world.run(deviation=_DEVIATION)
    assert result.status is ConfirmatoryRunStatus.JUDGED
    sealed = world.judged.find(partition=world.partition, preregistration_ref=world.ref)
    assert sealed is not None
    assert sealed.documents[RUN_RECORD_DOCUMENT]["deviation"] == _DEVIATION
