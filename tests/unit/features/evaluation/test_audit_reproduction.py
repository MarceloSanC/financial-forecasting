"""Use case `AuditReproduction` com fakes (Stage 8.2, Task 04; concept A3, A5/A6 em uso).

Mundo: `InMemoryPreregistrationSource` com a revisão 0 ancorada e o `.judged.toml`
(`add_judged`); raiz julgada = `InMemoryGoldStore` + `InMemoryJudgedGenerationStore` com a
cópia selada (scorecard e `run_record`) e o `ATTEMPTS.jsonl`; raiz reproduzida = outro
`InMemoryGoldStore` lido pelo `InMemoryGoldGenerationReader`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifestNotFoundError,
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    AuditReproductionCommand,
    ReproductionComparison,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationNotFoundError,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JUDGED_TAG_PREFIX,
    JudgedRecord,
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.application.use_cases.audit_reproduction import (
    AuditReproduction,
    ReproductionAuditError,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
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
from tests.unit.features.evaluation._scorecard_factory import STARTED_AT, make_stored
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT

pytestmark = pytest.mark.unit

_NAME = "test_plan"
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_SCORECARD: dict[str, object] = {
    "manifest_read": {"started_at": "2026-10-05T12:00:00+00:00", "n_runs": 6},
    "verdict": {"h1": "sustained", "p": 0.25},
}


def _input_read(ref: str, digest: str, minutes: int) -> JudgedAttempt:
    return JudgedAttempt(
        phase=AttemptPhase.INPUT_READ,
        attempt_id=(STARTED_AT + timedelta(minutes=minutes)).isoformat(),
        preregistration_ref=ref,
        silver_content=SAMPLE_SILVER_CONTENT,
        dataset_fingerprint="ab" * 32,
        result_digest=digest,
    )


class _World:
    """A raiz julgada selada, o plano com o registro e a raiz reproduzida."""

    def __init__(self, *, scorecard: bool = True) -> None:
        payload = valid_payload()
        self.plan = Preregistration.from_mapping(payload)
        self.ref = self.plan.reference(
            PreregistrationHash.compute(
                hasher=FloatRefusingHasher(), payload=self.plan.as_payload()
            )
        )
        self.source = InMemoryPreregistrationSource()
        self.source.add(
            _NAME,
            0,
            payload,
            PreregistrationAnchor(
                tag=f"preregistration/{self.ref}",
                commit=_COMMIT,
                comment_url="https://github.com/example/repo/issues/1#issuecomment-1",
                anchored_at=STARTED_AT - timedelta(days=1),
            ),
        )
        self.generation = make_stored(self.plan, reference=self.ref).generation()
        self.judged_gold = InMemoryGoldStore()
        _publish(self.judged_gold, self.generation)
        self.judged = InMemoryJudgedGenerationStore(self.judged_gold)
        documents: dict[str, dict[str, object]] = {RUN_RECORD_DOCUMENT: {"commit": _COMMIT}}
        if scorecard:
            documents[SCORECARD_DOCUMENT] = _SCORECARD
        sealed = self.judged.preserve(
            partition=self.partition,
            preregistration_ref=self.ref,
            expected_manifest=self.generation.manifest,
            documents=documents,
        )
        self.digest = result_layer_digest(self.generation)
        self.judged.record_attempt(
            partition=self.partition, attempt=_input_read(self.ref, self.digest, 5)
        )
        self.source.add_judged(_NAME, _record(self.ref, sealed.generation_digest))
        self.reproduced_gold = InMemoryGoldStore()
        _publish(self.reproduced_gold, self.generation)
        self.reader = InMemoryGoldGenerationReader(self.reproduced_gold)
        self.judged.preserves = self.judged.recorded = 0  # efeitos contados só no use case

    @property
    def partition(self) -> GoldPartition:
        return self.generation.manifest.partition

    def run(self, scorecard: dict[str, object] | None = None) -> ReproductionComparison:
        use_case = AuditReproduction(
            source=self.source,
            hasher=FloatRefusingHasher(),
            judged_store=self.judged,
            reproduced_reader=self.reader,
        )
        return use_case(
            AuditReproductionCommand(
                name=_NAME,
                revision=0,
                preregistration_ref=self.ref,
                reproduced_scorecard=_SCORECARD if scorecard is None else scorecard,
            )
        )


def _publish(store: InMemoryGoldStore, generation: GoldGeneration) -> None:
    store.publish(
        partition=generation.manifest.partition,
        tables=list(generation.tables.values()),
        manifest=generation.manifest,
    )


def _record(ref: str, digest: str) -> JudgedRecord:
    return JudgedRecord(
        revision=0,
        preregistration_ref=ref,
        generation_digest=digest,
        refresh_status=RefreshStatus.COMPLETED,
        commit=_COMMIT,
        tag=f"{JUDGED_TAG_PREFIX}{ref}",
        comment_url="https://github.com/example/repo/issues/211#issuecomment-2",
        commented_at=STARTED_AT + timedelta(days=1),
        input_backup="data/backups/input",
        input_backup_sha256="1" * 64,
        judged_backup="data/backups/judged",
        judged_backup_sha256="2" * 64,
    )


def test_reproduced_equal_to_judged_is_bit_identical() -> None:
    world = _World()

    comparison = world.run()

    assert comparison.bit_identical is True
    assert comparison.expected_result_digest == world.digest
    assert comparison.preregistration_ref == world.ref


def test_reproduced_scorecard_comes_from_the_command() -> None:
    altered = {**_SCORECARD, "verdict": {"h1": "sustained", "p": 0.5}}

    comparison = _World().run(altered)

    assert comparison.scorecard.paths == ("verdict.p",)
    assert comparison.bit_identical is False


def test_expected_digest_is_last_input_read_of_the_ref() -> None:
    world = _World()
    later = "cd" * 32
    world.judged.record_attempt(
        partition=world.partition, attempt=_input_read("test_plan-r9-ffffffffffff", "ef" * 32, 7)
    )
    world.judged.record_attempt(partition=world.partition, attempt=_input_read(world.ref, later, 9))

    comparison = world.run()

    assert comparison.expected_result_digest == later
    assert comparison.digests_equal is False
    assert comparison.bit_identical is False


def test_without_input_read_raises_audit_error() -> None:
    world = _World()
    world.judged._attempts.clear()

    with pytest.raises(ReproductionAuditError, match="no input_read"):
        world.run()


def test_without_committed_record_raises_audit_error() -> None:
    world = _World()
    world.source._judged.clear()

    with pytest.raises(ReproductionAuditError, match="no committed judged record"):
        world.run()


def test_record_digest_other_than_copy_raises_tampered() -> None:
    world = _World()
    world.source.add_judged(_NAME, _record(world.ref, "ee" * 32))

    with pytest.raises(JudgedGenerationTamperedError, match="names digest"):
        world.run()


def test_without_judged_copy_raises_not_found() -> None:
    world = _World()
    world.judged._sealed.clear()

    with pytest.raises(JudgedGenerationNotFoundError, match=world.ref):
        world.run()


def test_copy_without_scorecard_raises_audit_error() -> None:
    with pytest.raises(ReproductionAuditError, match=SCORECARD_DOCUMENT):
        _World(scorecard=False).run()


def test_partition_comes_from_the_resolved_plan() -> None:
    world = _World()
    expected = refresh_command_from(world.plan, world.ref).partition

    comparison = world.run()

    assert comparison.partition == expected
    assert world.reader.reads == [expected]


def test_reproduced_other_partition_or_missing_generation_propagates() -> None:
    world = _World()
    world.reproduced_gold = InMemoryGoldStore()
    other = GoldPartition("MSFT", world.partition.parent_sweep_id)
    world.reader = InMemoryGoldGenerationReader(world.reproduced_gold)
    with pytest.raises(GoldManifestNotFoundError):
        world.run()

    stored = make_stored(world.plan, reference=world.ref)
    stored.partition = other
    stored.manifest["asset"] = other.asset
    for rows in stored.rows.values():
        for row in rows:
            row["asset"] = other.asset
    _publish(world.reproduced_gold, stored.generation())
    with pytest.raises(GoldManifestNotFoundError):
        world.run()


def test_reads_never_write() -> None:
    world = _World()
    publishes = (world.judged_gold.publishes, world.reproduced_gold.publishes)

    world.run()

    assert (world.judged.preserves, world.judged.recorded) == (0, 0)
    assert (world.judged_gold.publishes, world.reproduced_gold.publishes) == publishes


def test_command_validates_shape() -> None:
    for changes, message in (
        ({"name": ""}, "name must be a non-empty str"),
        ({"revision": -1}, "revision must be an int >= 0"),
        ({"preregistration_ref": ""}, "preregistration_ref must be"),
        ({"reproduced_scorecard": [1]}, "reproduced_scorecard must be a Mapping"),
    ):
        fields: dict[str, object] = {
            "name": _NAME,
            "revision": 0,
            "preregistration_ref": "test_plan-r0-0123456789ab",
            "reproduced_scorecard": {},
            **changes,
        }
        with pytest.raises(ValueError, match=message):
            AuditReproductionCommand(**fields)  # type: ignore[arg-type]
