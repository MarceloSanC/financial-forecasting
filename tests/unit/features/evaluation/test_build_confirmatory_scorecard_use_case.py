"""Unit test do use case `BuildConfirmatoryScorecard` (Stage 6.5, A6, A8, I5, I12, I13).

Com `InMemoryPreregistrationSource`, `InMemoryGoldGenerationReader` (sobre o
`InMemoryGoldStore`) e o dublê de hasher que recusa float: cadeia → hash → âncora antes
de ler o gold (espião no leitor), partição derivada do plano, `BLOCKED` recusado,
erros propagados, prontidão com a razão exata (nunca o desfecho nem a declaração de
cegamento), cadeia no resultado, veredito independente do perfil e `as_mapping`
JSON-safe.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    GoldNotReadyError,
    PreregistrationChainError,
    PreregistrationHashMismatchError,
    PreregistrationNotAnchoredError,
    ProfileState,
    ReadinessReason,
    ScorecardProfile,
    ScorecardResult,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
    PreregistrationNotFoundError,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    build_confirmatory_scorecard as use_case_module,
)
from financial_forecasting.features.evaluation.application.use_cases.build_confirmatory_scorecard import (  # noqa: E501
    BuildConfirmatoryScorecard,
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
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    valid_payload,
)
from tests.unit.features.evaluation._scorecard_factory import (
    STARTED_AT,
    Counts,
    make_stored,
)

_NAME = "test_plan"


def _reference(payload: dict[str, object]) -> str:
    plan = Preregistration.from_mapping(payload)
    return plan.reference(
        PreregistrationHash.compute(hasher=FloatRefusingHasher(), payload=plan.as_payload())
    )


def _anchor(reference: str, at: datetime = STARTED_AT - timedelta(days=1)) -> PreregistrationAnchor:
    return PreregistrationAnchor(
        tag=f"preregistration/{reference}",
        commit="0123456789abcdef0123456789abcdef01234567",
        comment_url="https://github.com/example/repo/issues/1#issuecomment-1",
        anchored_at=at,
    )


class _World:
    """O source, o store/leitor e o use case de um cenário."""

    def __init__(self) -> None:
        self.source = InMemoryPreregistrationSource()
        self.store = InMemoryGoldStore()
        self.reader = InMemoryGoldGenerationReader(self.store)
        self.use_case = BuildConfirmatoryScorecard(
            source=self.source, reader=self.reader, hasher=FloatRefusingHasher()
        )

    def add(
        self, revision: int, payload: dict[str, object], *, anchored: datetime | None | bool = True
    ) -> str:
        reference = _reference(payload)
        anchor = None
        if anchored is True:
            anchor = _anchor(reference)
        elif isinstance(anchored, datetime):
            anchor = _anchor(reference, anchored)
        self.source.add(_NAME, revision, payload, anchor)
        return reference

    def publish(self, payload: dict[str, object], reference: str, **kwargs: object) -> None:
        stored = make_stored(Preregistration.from_mapping(payload), reference=reference, **kwargs)  # type: ignore[arg-type]
        generation = stored.generation()
        self.store.publish(
            partition=generation.manifest.partition,
            tables=list(generation.tables.values()),
            manifest=generation.manifest,
        )

    def run(self, revision: int, reference: str) -> ScorecardResult:
        return self.use_case(
            BuildConfirmatoryScorecardCommand(
                name=_NAME, revision=revision, preregistration_ref=reference
            )
        )


def _r1(reference0: str, **changes: object) -> dict[str, object]:
    return {
        **valid_payload(),
        "revision": 1,
        "amends": reference0,
        "justification": "a blinded fix",
        "blind_status": "blinded",
        **changes,
    }


def _ready_world(**publish: object) -> tuple[_World, str]:
    world = _World()
    reference = world.add(0, valid_payload())
    world.publish(valid_payload(), reference, **publish)
    return world, reference


@pytest.mark.unit
def test_hash_mismatch_before_reader() -> None:
    world, _ = _ready_world()

    with pytest.raises(PreregistrationHashMismatchError, match="the command expects"):
        world.run(0, "test_plan-r0-000000000000")
    assert world.reader.reads == []


@pytest.mark.unit
@pytest.mark.parametrize("case", ["amends-wrong", "revision-differs", "name-differs"])
def test_chain_broken_before_reader(case: str) -> None:
    world = _World()
    reference0 = world.add(0, valid_payload())
    if case == "amends-wrong":
        payload = _r1("test_plan-r0-000000000000")
        reference1 = world.add(1, payload)
        revision = 1
    elif case == "revision-differs":
        payload = _r1(reference0, revision=2)
        reference1 = world.add(1, payload)
        revision = 1
    else:
        payload = {**valid_payload(), "name": "other_plan"}
        reference1 = world.add(0, payload)
        revision = 0

    with pytest.raises(PreregistrationChainError):
        world.run(revision, reference1)
    assert world.reader.reads == []


@pytest.mark.unit
def test_unanchored_before_reader() -> None:
    world = _World()
    reference0 = world.add(0, valid_payload(), anchored=None)
    payload = _r1(reference0)
    reference1 = world.add(1, payload)

    with pytest.raises(PreregistrationNotAnchoredError, match=r"revisions \[0\]"):
        world.run(1, reference1)
    assert world.reader.reads == []


@pytest.mark.unit
def test_validation_order_chain_hash_anchor() -> None:
    world = _World()
    world.add(0, valid_payload(), anchored=None)
    world.add(1, _r1("test_plan-r0-000000000000"), anchored=None)

    with pytest.raises(PreregistrationChainError):
        world.run(1, "test_plan-r1-000000000000")
    world2 = _World()
    world2.add(0, valid_payload(), anchored=None)
    with pytest.raises(PreregistrationHashMismatchError):
        world2.run(0, "test_plan-r0-000000000000")
    assert world.reader.reads == world2.reader.reads == []


@pytest.mark.unit
def test_reader_reads_derived_partition() -> None:
    world, reference = _ready_world()

    world.run(0, reference)

    plan = Preregistration.from_mapping(valid_payload())
    assert world.reader.reads == [GoldPartition(plan.asset, plan.cohort.cohort_id)]


@pytest.mark.unit
def test_command_has_no_partition() -> None:
    fields = {field.name for field in dataclasses.fields(BuildConfirmatoryScorecardCommand)}

    assert "partition" not in fields
    assert fields == {"name", "revision", "preregistration_ref"}


@pytest.mark.unit
def test_blocked_gold_not_ready() -> None:
    world, reference = _ready_world(
        status=RefreshStatus.BLOCKED,
        checks=[("degeneracy_check", "error", "fail"), ("alignment_check", "error", "pass")],
    )

    with pytest.raises(GoldNotReadyError, match="degeneracy_check") as raised:
        world.run(0, reference)
    assert [check.check for check in raised.value.failed_checks] == ["degeneracy_check"]


@pytest.mark.unit
def test_not_found_propagates() -> None:
    world, reference = _ready_world()

    with pytest.raises(PreregistrationNotFoundError):
        world.run(1, reference)


class _BrokenReader:
    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        raise RuntimeError(f"disk on fire for {partition}")


@pytest.mark.unit
def test_programming_error_propagates() -> None:
    world, reference = _ready_world()
    use_case = BuildConfirmatoryScorecard(
        source=world.source, reader=_BrokenReader(), hasher=FloatRefusingHasher()
    )

    with pytest.raises(RuntimeError, match="disk on fire"):
        use_case(
            BuildConfirmatoryScorecardCommand(name=_NAME, revision=0, preregistration_ref=reference)
        )


@pytest.mark.unit
def test_ready_false_gold_before_anchor() -> None:
    world = _World()
    reference = world.add(0, valid_payload(), anchored=STARTED_AT + timedelta(seconds=1))
    world.publish(valid_payload(), reference)

    result = world.run(0, reference)

    assert result.academic_decision_ready is False
    assert result.readiness_reasons == (ReadinessReason.GOLD_BEFORE_ANCHOR,)


@pytest.mark.unit
def test_ready_false_unblinded_amendment() -> None:
    world = _World()
    reference0 = world.add(0, valid_payload())
    payload = _r1(reference0, blind_status="unblinded")
    reference1 = world.add(1, payload)
    world.publish(payload, reference1)

    result = world.run(1, reference1)

    assert result.readiness_reasons == (ReadinessReason.AMENDED_AFTER_UNBLINDING,)
    assert result.academic_decision_ready is False


_REQUIRED = ("degeneracy_check", "alignment_check", "statistical_preconditions")


@pytest.mark.unit
@pytest.mark.parametrize("skipped", _REQUIRED)
def test_ready_false_required_check_skipped(skipped: str) -> None:
    checks = [(name, "error", "skipped" if name == skipped else "pass") for name in _REQUIRED]
    world, reference = _ready_world(checks=checks)

    result = world.run(0, reference)

    assert result.readiness_reasons == (ReadinessReason.REQUIRED_CHECK_SKIPPED,)


@pytest.mark.unit
def test_ready_false_required_check_skipped_only_required() -> None:
    """Checkpoint C bloco 3, R2/L1: check fora dos exigidos `SKIPPED` não tira a prontidão."""
    checks = [(name, "error", "pass") for name in _REQUIRED]
    world, reference = _ready_world(checks=[*checks, ("realized_provenance", "warn", "skipped")])

    result = world.run(0, reference)

    assert result.academic_decision_ready is True


@pytest.mark.unit
def test_ready_false_gold_before_anchor_of_judged_revision() -> None:
    """Checkpoint C bloco 3, M1: vale a âncora da revisão julgada, não a da r0."""
    world = _World()
    reference0 = world.add(0, valid_payload())  # ancorada antes do gold
    payload = _r1(reference0)
    reference1 = world.add(1, payload, anchored=STARTED_AT + timedelta(seconds=1))
    world.publish(payload, reference1)

    result = world.run(1, reference1)

    assert result.readiness_reasons == (ReadinessReason.GOLD_BEFORE_ANCHOR,)


@pytest.mark.unit
def test_ready_false_unblinded_amendment_anywhere_in_chain() -> None:
    """Checkpoint C bloco 3, R1: uma emenda `unblinded` em qualquer revisão da cadeia."""
    world = _World()
    reference0 = world.add(0, valid_payload())
    reference1 = world.add(1, _r1(reference0, blind_status="unblinded"))
    payload2 = _r1(reference1, revision=2, justification="a later blinded fix")
    reference2 = world.add(2, payload2)
    world.publish(payload2, reference2)

    result = world.run(2, reference2)

    assert result.readiness_reasons == (ReadinessReason.AMENDED_AFTER_UNBLINDING,)
    assert result.revision_chain == (reference0, reference1, reference2)


@pytest.mark.unit
def test_ready_true_refutation() -> None:
    def miscalibrated(
        _m: str, _s: int | None, _h: int, _sample: str, _k: str
    ) -> tuple[int, int, float]:
        return 80, 250, 0.0

    counts: Counts = miscalibrated
    world, reference = _ready_world(counts=counts)

    result = world.run(0, reference)

    assert not any(horizon.h1.passed for horizon in result.verdict.horizons)
    assert result.verdict.study_success_h1 is False
    assert result.academic_decision_ready is True
    assert result.readiness_reasons == ()


@pytest.mark.unit
def test_ready_true_started_at_anchor() -> None:
    world = _World()
    reference = world.add(0, valid_payload(), anchored=STARTED_AT)
    world.publish(valid_payload(), reference)

    result = world.run(0, reference)

    assert result.academic_decision_ready is True
    assert result.anchor.anchored_at == result.manifest_read.started_at


@pytest.mark.unit
def test_blinding_echoed_not_conjoined() -> None:
    payload = {**valid_payload(), "blinding_statement": "the 6.4 run is recorded in its §7"}
    world = _World()
    reference = world.add(0, payload)
    world.publish(payload, reference)

    result = world.run(0, reference)

    assert result.blinding_statement == "the 6.4 run is recorded in its §7"
    assert result.academic_decision_ready is True
    plain_world, plain_reference = _ready_world()
    plain = plain_world.run(0, plain_reference)
    assert plain.blinding_statement is None
    assert plain.academic_decision_ready is True


@pytest.mark.unit
def test_chain_listed_in_result() -> None:
    world = _World()
    reference0 = world.add(0, valid_payload())
    payload = _r1(reference0)
    reference1 = world.add(1, payload)
    world.publish(payload, reference1)

    result = world.run(1, reference1)

    assert result.revision_chain == (reference0, reference1)
    assert result.preregistration_ref == reference1
    assert result.readiness_reasons == ()


@pytest.mark.unit
def test_verdict_unchanged_by_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    world, reference = _ready_world()
    baseline = world.run(0, reference)
    other = ScorecardProfile(
        horizons=(),
        declared_not_built=("sharpness_diagram",),
        profile_states=(("sharpness_diagram", ProfileState.NOT_BUILT_HERE),),
    )
    monkeypatch.setattr(use_case_module, "build_profile", lambda **_: other)

    changed = world.run(0, reference)

    assert changed.profile == other
    assert changed.verdict == baseline.verdict
    assert changed.profile != baseline.profile


@pytest.mark.unit
def test_result_mapping_json_safe() -> None:
    world, reference = _ready_world()

    mapping = world.run(0, reference).as_mapping()

    decoded = json.loads(json.dumps(mapping))
    assert decoded["preregistration_ref"] == reference
    assert decoded["anchor"]["anchored_at"] == (STARTED_AT - timedelta(days=1)).isoformat()
    assert decoded["verdict"]["horizons"][0]["h2"] in {
        "not_applicable",
        "beats_naive_only",
        "no_skill_over_naive",
        "beats_naive_ties_strong",
        "beats_naive_and_strong",
    }
    assert decoded["manifest_read"]["status"] == "COMPLETED"
    assert decoded["readiness_reasons"] == []


# --- aplicação da auditoria da Stage (F4) ---------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("revision", [0, 1])
def test_unanchored_before_reader_tag_mismatch(revision: int) -> None:
    """Auditoria F4: a âncora tem de ser a tag da referência calculada da própria revisão."""
    world = _World()
    reference0 = world.add(0, valid_payload())
    payload = _r1(reference0)
    reference1 = _reference(payload)
    stale = _anchor("test_plan-r9-000000000000")
    if revision == 0:
        world.source.add(_NAME, 0, valid_payload(), stale)
        world.source.add(_NAME, 1, payload, _anchor(reference1))
    else:
        world.source.add(_NAME, 1, payload, stale)

    with pytest.raises(PreregistrationNotAnchoredError, match=rf"revisions \[{revision}\]"):
        world.run(1, reference1)
    assert world.reader.reads == []
