"""Integração do `RunConfirmatoryEvaluation` com os stores reais (Stage 8.1 Task 14).

Mundo sintético do e2e de H3 da 7.3 (`test_h3_refresh_end_to_end`): silver lido pelo
`ParquetAnalyticsRepository`, a cadeia r0 → r3 congelada e ancorada no
`config/preregistration/` temporário (com `[conformal]` e `[h3]`), o `RefreshGold` e o
`BuildConfirmatoryScorecard` do `wire_dependencies`, o `ParquetGoldStore` real (cópia
julgada e geração viva), o `TomlPreregistrationSource` real e o `JsonCohortProgressLedger`
real como lock; só o ambiente é o fake (a foto do git real é do contrato da Task 11).
Critérios A9, A7 (real), A5 (real) e G4(a) real. Nenhum teste lê o cohort real.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    ConfirmatoryRunStatus,
    InferenceSummary,
    RunConfirmatoryEvaluationCommand,
    RunConfirmatoryEvaluationResult,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    ATTEMPTS_NAME,
    GENERATION_DIR,
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JUDGED_TAG_PREFIX,
)
from financial_forecasting.features.evaluation.application.use_cases.run_confirmatory_evaluation import (  # noqa: E501
    RunConfirmatoryEvaluation,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.fakes.features.evaluation.in_memory_evaluation_environment import (
    CLEAN_SNAPSHOT,
    InMemoryEvaluationEnvironment,
)
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _ANCHORED_AT,
    _ASSET,
)
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import (
    _COHORT,
    _TEST_FIRST,
)
from tests.integration.features.evaluation.test_h3_refresh_end_to_end import (
    _HASH,
    _SUSTAINED,
    _r3,
    _World,
    _world,
    _write_ablation,
    _write_attribution,
)
from tests.integration.features.evaluation.test_profiles_end_to_end import _freeze
from tests.unit.features.evaluation._preregistration_payload import to_toml

pytestmark = pytest.mark.integration

_PARTITION = GoldPartition(_ASSET, _COHORT)
_SUMMARY = InferenceSummary(
    runs=8, strict=8, tolerance=0, max_abs_diff=0.0, calib_rows_written=0, calib_rows_verified=40
)


@dataclass(frozen=True)
class _Judged:
    root: Path
    world: _World
    name: str
    reference: str
    first: RunConfirmatoryEvaluationResult

    @property
    def store(self) -> ParquetGoldStore:
        return self.world.deps.refresh_gold._gold_store  # type: ignore[attr-defined,no-any-return]

    @property
    def partition_dir(self) -> Path:
        return self.root / "data" / "gold" / f"asset={_ASSET}" / f"parent_sweep_id={_COHORT}"

    def sealed(self) -> JudgedGeneration:
        sealed = self.store.find(partition=_PARTITION, preregistration_ref=self.reference)
        assert sealed is not None
        return sealed

    def run(self) -> RunConfirmatoryEvaluationResult:
        return _run(self.world, self.name, self.reference)


def _use_case(world: _World) -> RunConfirmatoryEvaluation:
    deps = world.deps
    gold_store = deps.refresh_gold._gold_store  # type: ignore[attr-defined]
    return RunConfirmatoryEvaluation(
        source=deps.build_confirmatory_scorecard._source,
        hasher=deps.hasher,
        refresh_gold=deps.refresh_gold,
        build_scorecard=deps.build_confirmatory_scorecard,
        judged_store=gold_store,
        gold_reader=gold_store,
        environment=InMemoryEvaluationEnvironment(),
        writer_lock=deps.cohort_ledger,
        clock=SystemClock(),
    )


def _run(world: _World, name: str, reference: str) -> RunConfirmatoryEvaluationResult:
    return _use_case(world)(
        RunConfirmatoryEvaluationCommand(
            name=name, revision=3, preregistration_ref=reference, inference_summary=_SUMMARY
        )
    )


def _judged_world(root: Path, *, drop: tuple[int, int, int] | None = None) -> _Judged:
    world = _world(root, drop=drop)
    r2_plan = world.plans[2]
    _write_attribution(world.deps, r2_plan, _SUSTAINED, str(_HASH))
    _write_ablation(world.deps, r2_plan, "ablation-judged", _SUSTAINED)
    plan, reference = _r3(world, cohort_id="ablation-judged")
    _freeze(root, {**plan.as_payload()}, 3)
    first = _run(world, plan.name, reference)
    return _Judged(root, world, plan.name, reference, first)


@pytest.fixture(scope="module")
def judged(tmp_path_factory: pytest.TempPathFactory) -> _Judged:
    return _judged_world(tmp_path_factory.mktemp("judged"))


@pytest.fixture(scope="module")
def blocked(tmp_path_factory: pytest.TempPathFactory) -> _Judged:
    return _judged_world(tmp_path_factory.mktemp("blocked"), drop=(1, 1, _TEST_FIRST + 10))


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_judged_copy_equals_scorecard_mapping_and_current_bytes(judged: _Judged) -> None:
    """A9: JUDGED; scorecard da cópia = `as_mapping()`; `generation/` = `current/` byte a byte."""
    first = judged.first
    assert first.status is ConfirmatoryRunStatus.JUDGED
    assert first.scorecard is not None
    sealed = judged.sealed()
    assert sealed.documents[SCORECARD_DOCUMENT] == first.scorecard.as_mapping()
    copy_dir = judged.partition_dir / "judged" / judged.reference
    current = _files(judged.partition_dir / "current")
    assert current
    assert _files(copy_dir / GENERATION_DIR) == current
    stored = json.loads((copy_dir / SCORECARD_DOCUMENT).read_text(encoding="utf-8"))
    assert stored == first.scorecard.as_mapping()
    # o manifesto da cópia carrega a identidade do silver consumido
    assert sealed.manifest.silver_content.digest
    assert {"dim_run", "fact_oos_predictions", "realized"} <= set(
        sealed.manifest.silver_content.tables
    )
    assert sealed.manifest.started_at >= _ANCHORED_AT  # I3
    anchor = judged.world.deps.build_confirmatory_scorecard._source.read(
        name=judged.name, revision=3
    ).anchor
    assert anchor is not None
    assert sealed.manifest.started_at >= anchor.anchored_at
    # uma tentativa: as linhas `started` e `input_read` com o mesmo `attempt_id`
    attempts = judged.store.attempts(partition=_PARTITION)
    assert [a.phase for a in attempts] == [AttemptPhase.STARTED, AttemptPhase.INPUT_READ]
    assert len({a.attempt_id for a in attempts}) == 1
    assert attempts[1].silver_content == sealed.manifest.silver_content
    lines = (judged.partition_dir / "judged" / ATTEMPTS_NAME).read_text(encoding="utf-8")
    assert len(lines.splitlines()) == 2  # noqa: PLR2004
    record = sealed.documents[RUN_RECORD_DOCUMENT]
    assert record["environment"] == dict(sorted(CLEAN_SNAPSHOT.items()))
    assert record["inference_summary"] == _SUMMARY.as_mapping()
    assert first.generation_digest == sealed.generation_digest


def test_second_call_already_judged_with_same_digest_and_body(judged: _Judged) -> None:
    """A5 real: a segunda chamada não roda o refresh e devolve o mesmo corpo."""
    before = _files(judged.partition_dir)

    again = judged.run()

    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert again.generation_digest == judged.first.generation_digest
    assert again.attestation_body == judged.first.attestation_body
    assert _files(judged.partition_dir) == before  # nada escrito, nem tentativa


@pytest.fixture
def judged_toml(judged: _Judged) -> Iterator[Path]:
    path = judged.root / "config" / "preregistration" / f"{judged.name}-r3.judged.toml"
    yield path
    path.unlink(missing_ok=True)


def _record(judged: _Judged, digest: str) -> dict[str, object]:
    return {
        "preregistration_ref": judged.reference,
        "generation_digest": digest,
        "refresh_status": RefreshStatus.COMPLETED.value,
        "commit": CLEAN_SNAPSHOT["commit"],
        "tag": f"{JUDGED_TAG_PREFIX}{judged.reference}",
        "comment_url": "https://github.com/example/repo/issues/211#issuecomment-2",
        "commented_at": _ANCHORED_AT.replace(year=2030),
        "input_backup": "data/backups/input",
        "input_backup_sha256": "1" * 64,
        "judged_backup": "data/backups/judged",
        "judged_backup_sha256": "2" * 64,
    }


def test_committed_judged_toml_with_first_digest_is_already_judged(
    judged: _Judged, judged_toml: Path
) -> None:
    """G4(a) real: o `.judged.toml` com o digest da 1ª chamada → ALREADY_JUDGED."""
    judged_toml.write_text(
        to_toml(_record(judged, judged.first.generation_digest)), encoding="utf-8"
    )
    attempts = (judged.partition_dir / "judged" / ATTEMPTS_NAME).read_bytes()

    again = judged.run()

    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert (judged.partition_dir / "judged" / ATTEMPTS_NAME).read_bytes() == attempts


def test_committed_judged_toml_with_other_digest_is_tampered(
    judged: _Judged, judged_toml: Path
) -> None:
    """G4(a) real: o registro commitado manda; outro digest → adulterada, nada escrito."""
    judged_toml.write_text(to_toml(_record(judged, "3" * 64)), encoding="utf-8")
    before = _files(judged.partition_dir)

    with pytest.raises(JudgedGenerationTamperedError, match="committed record"):
        judged.run()

    assert _files(judged.partition_dir) == before


def test_blocked_world_seals_without_scorecard_then_already_judged(blocked: _Judged) -> None:
    """A7 real: BLOCKED selado sem scorecard, checks no run_record; depois ALREADY_JUDGED."""
    first = blocked.first
    assert first.status is ConfirmatoryRunStatus.BLOCKED
    assert first.scorecard is None
    assert first.failed_checks
    sealed = blocked.sealed()
    assert SCORECARD_DOCUMENT not in sealed.documents
    record = sealed.documents[RUN_RECORD_DOCUMENT]
    assert [c["check"] for c in record["failed_checks"]] == [  # type: ignore[attr-defined]
        check.check for check in first.failed_checks
    ]
    assert set(sealed.manifest.silver_content.tables) == {
        "dim_run",
        "fact_oos_predictions",
        "realized",
    }

    again = blocked.run()

    assert again.status is ConfirmatoryRunStatus.ALREADY_JUDGED
    assert again.refresh_status is RefreshStatus.BLOCKED
    assert again.attestation_body == first.attestation_body
