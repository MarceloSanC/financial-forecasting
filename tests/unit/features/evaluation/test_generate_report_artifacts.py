"""Use case `GenerateReportArtifacts` com fakes (Stage 8.3, Task 10; A1-A5, A11, A13, I9).

Mundo: a cadeia r0-r3 com as referências **calculadas** (`InMemoryPreregistrationSource`
com âncoras e o `.judged.toml`), a cópia selada (`InMemoryJudgedGenerationStore` sobre um
`InMemoryGoldStore` cuja geração viva é depois trocada — `current/` diferente da cópia), o
silver e a grade do cohort (`FakeSilverTableReader`, `FakeTrainingGridReader`) coerentes com
o `silver_content` julgado, `InMemoryEvaluationEnvironment`, `InMemoryFigureRenderer` e
`InMemoryReportArtifactSink`. Toda recusa afirma `sink.writes == 0` e
`renderer.calls == 0` (CB-9).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    DirtyCodeError,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldTable,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_IDS,
    DossierEntry,
    DossierEntryKind,
    GenerateReportArtifactsCommand,
    ReportArtifactsError,
    ReportSourceMismatchError,
    SilverContentMismatchError,
    StatusLabel,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationNotFoundError,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.application.use_cases.generate_report_artifacts import (  # noqa: E501
    GenerateReportArtifacts,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    reliability_figure,
    sharpness_figure,
)
from financial_forecasting.features.evaluation.application.use_cases.report_silver import (
    VerifiedSilver,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.fakes.features.evaluation.fake_silver_table_reader import (
    SILVER_COLUMNS,
    FakeSilverTableReader,
)
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader
from tests.fakes.features.evaluation.in_memory_evaluation_environment import (
    InMemoryEvaluationEnvironment,
)
from tests.fakes.features.evaluation.in_memory_figure_renderer import (
    FAKE_PDF_HEADER,
    InMemoryFigureRenderer,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.features.evaluation.in_memory_judged_generation_store import (
    InMemoryJudgedGenerationStore,
)
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.fakes.features.evaluation.in_memory_report_artifact_sink import (
    InMemoryReportArtifactSink,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    r1_payload,
    r2_payload,
    valid_payload,
)
from tests.unit.features.evaluation._report_inputs import (
    CANDIDATE_SEEDS,
    ReportWorld,
    make_silver,
    make_world,
    report_payload,
)

pytestmark = pytest.mark.unit

_NAME = "test_plan"
_ASSET = "AAPL"
_GRID_COLUMNS = ("feat_a", "target_return")
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_STARTED_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
_RESULT_DIGEST = "7c" * 32
_BLINDING = "Nenhum número confirmatório foi lido antes da âncora."
_HASHER = FloatRefusingHasher()


class _GridHasher:
    """Dublê mínimo do `Hasher` do fingerprint da grade (sem fake por desenho, #70)."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        return sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()

    def hash_text(self, text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()


def _dataset(silver: VerifiedSilver) -> list[dict[str, object]]:
    realized = silver.realized
    return [
        {"timestamp": datetime.fromisoformat(ts), "feat_a": 1.0, "target_return": value}
        for ts, value in zip(realized.timestamps, realized.returns, strict=True)
    ]


def _silver_rows(
    silver: VerifiedSilver, parent_sweep_id: str
) -> dict[str, list[dict[str, object]]]:
    runs = {run.run_id: run for run in silver.runs}
    dim_run = [
        {
            "run_id": run.run_id,
            "asset": _ASSET,
            "parent_sweep_id": parent_sweep_id,
            "feature_set_name": run.feature_set_name,
            "config_signature": run.config_signature,
            "fold": run.fold,
            "seed": run.seed,
            "model_version": run.model,
            "split_fingerprint": silver.split_fingerprints[run.run_id],
        }
        for run in silver.runs
    ]
    facts = [
        {
            "run_id": r.run_id,
            "model_version": r.model,
            "asset": _ASSET,
            "feature_set_name": runs[r.run_id].feature_set_name,
            "split": r.split,
            "horizon": r.horizon,
            "decision_idx": r.decision_idx,
            "timestamp_utc": r.decision_timestamp,
            "target_timestamp_utc": r.target_timestamp,
            "quantile_level": r.quantile_level,
            "value_raw": r.value_raw,
            "value_guardrail": r.value_guardrail,
            "guardrail_applied": int(r.guardrail_applied),
            "year": 2024,
        }
        for r in silver.records
    ]
    return {"dim_run": dim_run, "fact_oos_predictions": facts}


def _content(
    rows: Mapping[str, list[dict[str, object]]], silver: VerifiedSilver, sweep: str
) -> SilverContent:
    accumulator = SilverContentAccumulator(hasher=_HASHER)
    accumulator.add_dim_run(
        columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=sweep, rows=rows["dim_run"]
    )
    accumulator.add_facts(
        table="fact_oos_predictions",
        columns=SILVER_COLUMNS["fact_oos_predictions"],
        rows=rows["fact_oos_predictions"],
    )
    accumulator.add_realized(asset=_ASSET, realized=silver.realized)
    return accumulator.result()


def _reference(payload: dict[str, object]) -> str:
    plan = Preregistration.from_mapping(payload)
    return plan.reference(PreregistrationHash.compute(hasher=_HASHER, payload=plan.as_payload()))


@dataclass
class _World:
    world: ReportWorld
    silver: VerifiedSilver
    ref: str
    source: InMemoryPreregistrationSource
    live: InMemoryGoldStore
    judged: InMemoryJudgedGenerationStore
    reader: FakeSilverTableReader
    grid: FakeTrainingGridReader
    silver_rows: dict[str, list[dict[str, object]]]
    renderer: InMemoryFigureRenderer
    sink: InMemoryReportArtifactSink

    def use_case(
        self, environment: InMemoryEvaluationEnvironment | None = None
    ) -> GenerateReportArtifacts:
        return GenerateReportArtifacts(
            judged_store=self.judged,
            preregistration_source=self.source,
            silver_reader=self.reader,
            grid_reader=self.grid,
            hasher=_HASHER,
            environment=environment or InMemoryEvaluationEnvironment(),
            renderer=self.renderer,
            sink=self.sink,
        )

    def command(self, **changes: object) -> GenerateReportArtifactsCommand:
        kwargs: dict[str, object] = {
            "name": _NAME,
            "revision": 3,
            "preregistration_ref": self.ref,
            "cohort_seeds": CANDIDATE_SEEDS,
            "register": (
                DossierEntry(
                    kind=DossierEntryKind.DEVIATION,
                    title="Errata",
                    summary="s",
                    pointer="docs/stages/8.1-confirmatory-run/technical.md#o1",
                ),
                DossierEntry(
                    kind=DossierEntryKind.INTERNAL,
                    title="Evidência anterior",
                    summary="s",
                    pointer="docs/reports/equivalence_audit.md",
                ),
            ),
        }
        kwargs.update(changes)
        return GenerateReportArtifactsCommand(**kwargs)  # type: ignore[arg-type]

    def run(self, **changes: object) -> object:
        return self.use_case()(self.command(**changes))

    def nothing_happened(self) -> bool:
        return self.sink.writes == 0 and self.renderer.calls == 0


def _scorecard(world: ReportWorld) -> dict[str, object]:
    scorecard = copy.deepcopy(world.scorecard)
    for verdict in scorecard["verdict"]["horizons"]:  # type: ignore[index]
        verdict["h2"] = "beats_naive_only"
        verdict["primary_winner"] = None
    scorecard["academic_decision_ready"] = True
    scorecard["readiness_reasons"] = []
    return scorecard


def _make(  # noqa: PLR0913 — um eixo por variação do mundo
    *,
    scorecard: bool = True,
    judged_record: bool = True,
    seal: bool = True,
    input_read: bool = True,
    mutate_world: Callable[[ReportWorld], None] | None = None,
    record_digest: str | None = None,
) -> _World:
    probe = make_silver(make_world())
    dataset = _dataset(probe)
    grid_hasher = _GridHasher()
    fingerprint = grid_fingerprint(
        build_training_grid(dataset, columns=_GRID_COLUMNS), hasher=grid_hasher, asset_id=_ASSET
    )
    payloads = [valid_payload(), r1_payload(), r2_payload(), report_payload()]
    refs: list[str] = []
    for revision, payload in enumerate(payloads):
        payload["blinding_statement"] = _BLINDING
        payload["realized"] = {**payload["realized"], "dataset_fingerprint": fingerprint}  # type: ignore[dict-item]
        if revision > 0:
            payload["amends"] = refs[-1]
        refs.append(_reference(payload))
    plan = Preregistration.from_mapping(payloads[-1])
    ref = refs[-1]
    world = make_world(plan=plan, reference=ref)
    silver = make_silver(world)
    sweep = plan.cohort.cohort_id
    rows = _silver_rows(silver, sweep)
    world.silver_content = _content(rows, silver, sweep)
    if mutate_world is not None:
        mutate_world(world)
    generation = world.generation()
    live = InMemoryGoldStore()
    live.publish(
        partition=generation.manifest.partition,
        tables=list(generation.tables.values()),
        manifest=generation.manifest,
    )
    judged = InMemoryJudgedGenerationStore(live)
    partition = generation.manifest.partition
    digest = "00" * 32
    if seal:
        documents: dict[str, Mapping[str, object]] = {
            RUN_RECORD_DOCUMENT: {"seeds": {"gold": "manifest"}}
        }
        if scorecard:
            documents[SCORECARD_DOCUMENT] = _scorecard(world)
        sealed = judged.preserve(
            partition=partition,
            preregistration_ref=ref,
            expected_manifest=generation.manifest,
            documents=documents,
        )
        digest = sealed.generation_digest
    judged.record_attempt(
        partition=partition,
        attempt=JudgedAttempt(
            phase=AttemptPhase.STARTED,
            attempt_id=_STARTED_AT.isoformat(),
            preregistration_ref=ref,
            commit=_COMMIT,
            code={"code.src": "e1" * 32, "code.uv_lock": "e2" * 32},
            environment={"env.image_id": "sha256:" + "ab" * 32},
            started_at=_STARTED_AT,
        ),
    )
    if input_read:
        judged.record_attempt(
            partition=partition,
            attempt=JudgedAttempt(
                phase=AttemptPhase.INPUT_READ,
                attempt_id=_STARTED_AT.isoformat(),
                preregistration_ref=ref,
                silver_content=world.silver_content,
                dataset_fingerprint=fingerprint,
                result_digest=_RESULT_DIGEST,
            ),
        )
    source = InMemoryPreregistrationSource()
    for revision, payload in enumerate(payloads):
        source.add(
            _NAME,
            revision,
            payload,
            PreregistrationAnchor(
                tag=f"preregistration/{refs[revision]}",
                commit=_COMMIT,
                comment_url=f"https://github.com/o/r/issues/1#issuecomment-{revision}",
                anchored_at=_STARTED_AT - timedelta(days=10 - revision),
            ),
        )
    if judged_record:
        source.add_judged(
            _NAME,
            JudgedRecord(
                revision=3,
                preregistration_ref=ref,
                generation_digest=record_digest or digest,
                refresh_status=RefreshStatus.COMPLETED,
                commit=_COMMIT,
                tag=f"confirmatory-run/{ref}",
                comment_url="https://github.com/o/r/issues/2#issuecomment-9",
                commented_at=_STARTED_AT + timedelta(days=1),
                input_backup="backups/input",
                input_backup_sha256="11" * 32,
                judged_backup="backups/judged",
                judged_backup_sha256="22" * 32,
            ),
        )
    return _World(
        world=world,
        silver=silver,
        ref=ref,
        source=source,
        live=live,
        judged=judged,
        reader=FakeSilverTableReader(rows),
        grid=FakeTrainingGridReader({_ASSET: dataset}, columns=_GRID_COLUMNS, hasher=grid_hasher),
        silver_rows=rows,
        renderer=InMemoryFigureRenderer(),
        sink=InMemoryReportArtifactSink(),
    )


@pytest.fixture
def harness() -> _World:
    return _make()


# ------------------------------------------------------------------------------ sucesso


def test_ten_figures_in_catalog_order_and_one_write(harness: _World) -> None:
    result = harness.run()
    assert [fid for fid, _ in result.figures] == list(FIGURE_IDS)  # type: ignore[attr-defined]
    assert harness.sink.writes == 1
    assert harness.renderer.rendered == list(FIGURE_IDS)
    assert [fid for fid, _, _ in harness.sink.figures] == list(FIGURE_IDS)
    assert result.register_entries == 2  # type: ignore[attr-defined]  # noqa: PLR2004


def test_specs_come_from_judged_copy_never_current(harness: _World) -> None:
    expected = reliability_figure(harness.world.inputs()).spec.data_digest
    generation = harness.world.generation()
    tables = []
    for table in generation.tables.values():
        rows = [dict(r) for r in table.rows]
        if table.name == "gold_calibration_table":
            for row in rows:
                row["wilson_estimate"] = 0.5
        tables.append(GoldTable(table.name, table.key, tuple(rows)))
    harness.live.publish(
        partition=generation.manifest.partition, tables=tables, manifest=generation.manifest
    )
    result = harness.run()
    assert dict(result.figures)["reliability_diagram"] == expected  # type: ignore[attr-defined]


def test_records_carry_data_digest_generation_digest_code_and_renderer(harness: _World) -> None:
    result = harness.run()
    records = harness.sink.records
    digests = dict(result.figures)  # type: ignore[attr-defined]
    sharpness = sharpness_figure(harness.world.inputs(), harness.silver)
    for figure_id, record in records.items():
        assert record.data_digest == digests[figure_id]
        assert record.generation_digest == result.generation_digest  # type: ignore[attr-defined]
        assert dict(record.code) == {"code.src": "a" * 40, "code.uv_lock": "b" * 40}
        assert dict(record.renderer) == {"format": "pdf", "renderer": "in-memory"}
        if figure_id != "sharpness_diagram":
            assert dict(record.excluded_degenerate) == {}
    assert dict(records["sharpness_diagram"].excluded_degenerate) == dict(
        sharpness.excluded_degenerate
    )
    assert records["sharpness_diagram"].data_digest == sharpness.spec.data_digest

    def bump(world: ReportWorld) -> None:
        row = world.rows["gold_metrics_by_run"][0]
        row["value"] = float(row["value"]) + 0.001  # type: ignore[arg-type]

    changed = _make(mutate_world=bump).run()
    assert dict(changed.figures)["quantile_score_plot"] != digests["quantile_score_plot"]  # type: ignore[attr-defined]


def test_confirmatory_label_on_gate_tails_and_dm_rows_where_h1_passes(
    harness: _World,
) -> None:
    harness.run()
    confirmatory = []
    # o fake renderiza a serialização canônica: as dez specs voltam dos bytes do sink
    for figure_id, content, _ in harness.sink.figures:
        spec = json.loads(content.removeprefix(FAKE_PDF_HEADER))
        for panel in spec["panels"]:
            if panel["label"]["status"] == StatusLabel.CONFIRMATORY.value:
                confirmatory.append((figure_id, panel["panel_id"], "panel"))
            for series in panel["series"]:
                if series["label"]["status"] == StatusLabel.CONFIRMATORY.value:
                    confirmatory.append((figure_id, panel["panel_id"], series["series_id"]))
    assert confirmatory == [
        ("reliability_diagram", "h1", "gate_lower_tail"),
        ("reliability_diagram", "h1", "gate_upper_tail"),
        ("reliability_diagram", "h7", "gate_lower_tail"),
        ("reliability_diagram", "h7", "gate_upper_tail"),
        ("dm_candidate_vs_comparators", "h1", "panel"),
        ("dm_candidate_vs_comparators", "h1", "dm_cells"),
    ]


def test_result_lists_ids_and_digests(harness: _World) -> None:
    result = harness.run()
    assert result.preregistration_ref == harness.ref  # type: ignore[attr-defined]
    assert all(len(digest) == 64 for _, digest in result.figures)  # type: ignore[attr-defined]  # noqa: PLR2004
    assert harness.sink.dossier is not None


# ------------------------------------------------------------------------------- recusas


def test_dirty_tree_raises_before_any_read_or_write(harness: _World) -> None:
    environment = InMemoryEvaluationEnvironment({"code_dirty": "true"})
    with pytest.raises(DirtyCodeError):
        harness.use_case(environment)(harness.command())
    assert harness.source.reads == []
    assert harness.reader.reads == []
    assert harness.nothing_happened()


def test_no_committed_record_raises() -> None:
    harness = _make(judged_record=False)
    with pytest.raises(ReportArtifactsError, match="no committed judged record"):
        harness.run()
    assert harness.nothing_happened()


def test_record_digest_other_than_find_raises_tampered() -> None:
    harness = _make(record_digest="ee" * 32)
    with pytest.raises(JudgedGenerationTamperedError):
        harness.run()
    assert harness.nothing_happened()


def test_missing_copy_raises_not_found() -> None:
    harness = _make(seal=False)
    with pytest.raises(JudgedGenerationNotFoundError):
        harness.run()
    assert harness.nothing_happened()


def test_tampered_copy_propagates(harness: _World) -> None:
    partition = harness.world.generation().manifest.partition
    harness.judged.tamper(
        partition=partition,
        preregistration_ref=harness.ref,
        path="generation/gold_dm_results.parquet",
        data=b"{}",
    )
    with pytest.raises(JudgedGenerationTamperedError):
        harness.run()
    assert harness.nothing_happened()


def test_copy_without_scorecard_raises() -> None:
    harness = _make(scorecard=False)
    with pytest.raises(ReportArtifactsError, match="scorecard"):
        harness.run()
    assert harness.nothing_happened()


def test_no_input_read_raises() -> None:
    harness = _make(input_read=False)
    with pytest.raises(ReportArtifactsError, match="input_read"):
        harness.run()
    assert harness.nothing_happened()


def test_silver_mismatch_writes_nothing(harness: _World) -> None:
    calib = next(r for r in harness.silver_rows["fact_oos_predictions"])
    calib["value_raw"] = float(calib["value_raw"]) + 1.0  # type: ignore[arg-type]
    harness.reader = FakeSilverTableReader(harness.silver_rows)
    with pytest.raises(SilverContentMismatchError):
        harness.run()
    assert harness.nothing_happened()


def test_dm_mismatch_writes_nothing() -> None:
    def flip(world: ReportWorld) -> None:
        row = next(
            r for r in world.rows["gold_dm_results"] if r["variance_estimator"] == "rectangular"
        )
        row["rejected"] = not row["rejected"]

    harness = _make(mutate_world=flip)
    with pytest.raises(ReportSourceMismatchError, match="gold_dm_results"):
        harness.run()
    assert harness.nothing_happened()


def test_seed_mismatch_writes_nothing(harness: _World) -> None:
    with pytest.raises(ReportSourceMismatchError, match="seeds"):
        harness.run(cohort_seeds=(2, 1))
    assert harness.nothing_happened()


def test_nothing_rendered_when_any_build_step_fails() -> None:
    def break_vsn(world: ReportWorld) -> None:
        world.rows["gold_h3_vsn"] = [r for r in world.rows["gold_h3_vsn"] if r["kind"] != "family"]

    harness = _make(mutate_world=break_vsn)
    with pytest.raises(ReportSourceMismatchError, match="gold_h3_vsn"):
        harness.run()
    assert harness.nothing_happened()


def test_sink_failure_propagates(harness: _World) -> None:
    harness.sink = InMemoryReportArtifactSink(fail_with=OSError("disk full"))
    with pytest.raises(OSError, match="disk full"):
        harness.run()
    assert harness.sink.writes == 0
