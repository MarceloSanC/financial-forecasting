"""Dossiê citável e interno e o seu Markdown (Stage 8.3, Task 09; A12, A17; D8, D9, I8).

Fontes sintéticas: a cadeia r0-r3 (payloads de teste com `blinding_statement`), o
`JudgedRecord`, as tentativas `started`/`input_read`, o `run_record` e o scorecard
`Mapping` do mundo de `_report_inputs`, o manifesto, o `dim_run`, registros de figura e um
registro curado com uma entrada de cada kind.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    AttemptPhase,
    JudgedAttempt,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CITABLE_82_ANCHORS,
    CITABLE_SECTIONS,
    FIGURE_CATALOG,
    DossierBlock,
    DossierEntry,
    DossierEntryKind,
    FigureRecord,
    SourceKind,
    SourceRef,
    TraceabilityDossier,
    Visibility,
    find_forbidden,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationAnchor,
    PreregistrationRecord,
)
from financial_forecasting.features.evaluation.application.use_cases.dossier_markdown import (
    link_target,
    render,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    JudgedRevision,
)
from financial_forecasting.features.evaluation.application.use_cases.report_dossier import (
    ORDERING_CAVEAT,
    build_dossier,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from tests.unit.features.evaluation._preregistration_payload import (
    r1_payload,
    r2_payload,
    r3_payload,
    valid_payload,
)
from tests.unit.features.evaluation._report_inputs import make_world
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT

BLINDING = (
    "Declaração de cegamento: nenhum número confirmatório foi lido antes da âncora.\n"
    'Ressalva "literal" | com acento — e quebra de linha.'
)
REF = "test_plan-r3-0123456789ab"
CODE_SRC = "c5" * 32
UV_LOCK = "a1" * 32
HEAD_COMMIT = "f" * 40
RESULT_DIGEST = "7c" * 32
GENERATION_DIGEST = "96" * 32
IMAGE = "sha256:" + "ab" * 32
STARTED_AT = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
_CHAIN = tuple(f"test_plan-r{r}-0123456789ab" for r in range(4))
_82 = "docs/stages/8.2-equivalence-audit/technical.md"


def _anchor(revision: int) -> PreregistrationAnchor:
    return PreregistrationAnchor(
        tag=f"preregistration/{_CHAIN[revision]}",
        commit=f"{revision}" * 40,
        comment_url=f"https://github.com/o/r/issues/1#issuecomment-{revision}",
        anchored_at=datetime(2026, 10, 1 + revision, 12, 0, tzinfo=UTC),
    )


def _chain() -> JudgedRevision:
    payloads = [valid_payload(), r1_payload(), r2_payload(), r3_payload()]
    records = []
    for revision, payload in enumerate(payloads):
        payload["blinding_statement"] = BLINDING
        if revision > 0:
            payload["amends"] = _CHAIN[revision - 1]
        records.append(PreregistrationRecord(payload=payload, anchor=_anchor(revision)))
    plans = tuple(Preregistration.from_mapping(r.payload) for r in records)
    return JudgedRevision(
        records=tuple(records),
        plans=plans,
        chain=_CHAIN,
        anchor=records[-1].anchor,  # type: ignore[arg-type]
    )


def _judged_record() -> JudgedRecord:
    return JudgedRecord(
        revision=3,
        preregistration_ref=REF,
        generation_digest=GENERATION_DIGEST,
        refresh_status=RefreshStatus.COMPLETED,
        commit="06" * 20,
        tag=f"confirmatory-run/{REF}",
        comment_url="https://github.com/o/r/issues/2#issuecomment-9",
        commented_at=datetime(2026, 10, 21, 8, 0, tzinfo=UTC),
        input_backup="backups/input",
        input_backup_sha256="11" * 32,
        judged_backup="backups/judged",
        judged_backup_sha256="22" * 32,
    )


def _attempts() -> tuple[JudgedAttempt, ...]:
    started = JudgedAttempt(
        phase=AttemptPhase.STARTED,
        attempt_id=STARTED_AT.isoformat(),
        preregistration_ref=REF,
        commit="06" * 20,
        code={"code.src": "e1" * 32, "code.uv_lock": "e2" * 32, "code.cohort_file": "e3" * 32},
        environment={"env.image_id": IMAGE, "env.platform": "linux", "env.cpu_count": "6"},
        started_at=STARTED_AT,
    )
    read = JudgedAttempt(
        phase=AttemptPhase.INPUT_READ,
        attempt_id=STARTED_AT.isoformat(),
        preregistration_ref=REF,
        silver_content=SAMPLE_SILVER_CONTENT,
        dataset_fingerprint="fe" * 32,
        result_digest=RESULT_DIGEST,
    )
    return (started, read)


def _scorecard() -> dict[str, object]:
    scorecard = copy.deepcopy(make_world().scorecard)
    for verdict in scorecard["verdict"]["horizons"]:  # type: ignore[index]
        verdict["h2"] = "beats_naive_only" if verdict["horizon"] == 1 else "not_applicable"
        verdict["primary_winner"] = "tft_quantile" if verdict["horizon"] == 1 else None
    scorecard["academic_decision_ready"] = True
    scorecard["readiness_reasons"] = []
    return scorecard


def _figure_record(figure_id: str) -> FigureRecord:
    return FigureRecord(
        figure_id=figure_id,
        data_digest="d0" * 32,
        generation_digest=GENERATION_DIGEST,
        preregistration_ref=REF,
        revision=3,
        partition=GoldPartition(asset="AAPL", parent_sweep_id="test_cohort-r0-0123456789ab"),
        sources=(
            SourceRef(
                kind=SourceKind.GOLD_TABLE,
                name="gold_metrics_by_run",
                filter={"sample": "common"},
                fields=("value",),
            ),
        ),
        silver_units={},
        excluded_degenerate={},
        omissions=FIGURE_CATALOG[figure_id].omissions,
        code={"code.src": CODE_SRC, "code.uv_lock": UV_LOCK},
        renderer={"format": "pdf"},
    )


def _register() -> tuple[DossierEntry, ...]:
    return (
        DossierEntry(
            kind=DossierEntryKind.DEVIATION,
            title="Errata O1 da 8.1",
            summary="a corrida rodou em 060537fc",
            pointer="docs/stages/8.1-confirmatory-run/technical.md#o1",
        ),
        DossierEntry(
            kind=DossierEntryKind.FINDING,
            title="Achado aberto",
            summary="um achado sem resolução",
            pointer="docs/stages/7.2-conformal/technical.md#finding",
            status="open",
        ),
        DossierEntry(
            kind=DossierEntryKind.PRE_ANCHOR,
            title="Computação pré-âncora da 6.4",
            summary="tabelas computadas num container descartado, sem valor lido",
            pointer="docs/adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md",
        ),
        DossierEntry(
            kind=DossierEntryKind.ENVIRONMENT,
            title="Treino (CPU)",
            summary="ambiente do treino do cohort",
            pointer="docs/stages/5.5-cohort/technical.md#ambiente",
        ),
        DossierEntry(
            kind=DossierEntryKind.REPRODUCTION,
            title="Reprodução R1/R2/R3",
            summary="R1: 100 comparados, 0 diferentes; R2: max |Δ| 0; R3: 0",
            pointer="docs/reports/reproduction_audit.md#4-comparação-por-classe-e-por-tabela",
        ),
        *(
            DossierEntry(
                kind=DossierEntryKind.DEVIATION, title=f"8.2 âncora {i}", summary="s", pointer=a
            )
            for i, a in enumerate(sorted(CITABLE_82_ANCHORS)[:2])
        ),
        *(
            DossierEntry(kind=DossierEntryKind.INTERNAL, title=title, summary="s", pointer=pointer)
            for title, pointer in (
                (
                    "registro de hashes da evidência anterior",
                    "docs/reports/prior_evidence_registry.toml",
                ),
                ("relatório de equivalência", "docs/reports/equivalence_audit.md"),
                ("B3 / ADR 8.2.0004", "docs/adr/8_2_0004-b3.md"),
                ("[finding] do PICP 80 %", f"{_82}#picp"),
                ("erratas F2-F5", f"{_82}#f2-f5"),
                ("E4 do andaime", f"{_82}#e4"),
                (
                    "limite da §5 do reproduction_audit.md",
                    "docs/reports/reproduction_audit.md#5-ambiente",
                ),
            )
        ),
    )


def _build(**overrides: object) -> TraceabilityDossier:
    world = make_world()
    kwargs: dict[str, object] = {
        "plan_chain": _chain(),
        "judged_record": _judged_record(),
        "attempts": _attempts(),
        "result_digest": RESULT_DIGEST,
        "run_record": {"seeds": {"gold": "manifest", "training": "cohort spec"}},
        "scorecard": _scorecard(),
        "manifest": world.generation().manifest,
        "runs": (
            CohortRun(
                run_id="run-1",
                model="tft_quantile",
                seed=1,
                fold="0",
                feature_set_name="fs-core",
                config_signature="cfg",
            ),
        ),
        "records": tuple(
            _figure_record(fid) for fid in ("reliability_diagram", "loss_differential_acf")
        ),
        "register": _register(),
        "snapshot": {
            "commit": HEAD_COMMIT,
            "code.src": CODE_SRC,
            "code.uv_lock": UV_LOCK,
            "code_dirty": "false",
        },
    }
    kwargs.update(overrides)
    return build_dossier(**kwargs)  # type: ignore[arg-type]


def _section(dossier: TraceabilityDossier, section_id: str) -> tuple[DossierBlock, ...]:
    return next(s for s in dossier.sections if s.section_id == section_id).blocks


def _all_rows(blocks: tuple[DossierBlock, ...]) -> dict[str, str]:
    return {field: value for block in blocks for field, value in block.rows}


@pytest.fixture
def dossier() -> TraceabilityDossier:
    return _build()


@pytest.mark.unit
def test_citable_has_exactly_the_closed_sections(dossier: TraceabilityDossier) -> None:
    assert [s.section_id for s in dossier.sections_of(Visibility.CITABLE)] == [
        sid for sid, _ in CITABLE_SECTIONS
    ]
    markdown = render(dossier, Visibility.CITABLE)
    assert [line[3:] for line in markdown.splitlines() if line.startswith("## ")] == [
        title for _, title in CITABLE_SECTIONS
    ]


@pytest.mark.unit
def test_blinding_statement_byte_for_byte(dossier: TraceabilityDossier) -> None:
    rows = _all_rows(_section(dossier, "blinding_statement"))
    assert rows["blinding_statement"] == BLINDING
    assert BLINDING in render(dossier, Visibility.CITABLE)


@pytest.mark.unit
def test_blind_status_of_each_amendment_and_ordering_caveat(dossier: TraceabilityDossier) -> None:
    blocks = _section(dossier, "preregistration_chain")
    assert [b.heading for b in blocks] == ["r0", "r1", "r2", "r3"]
    for block in blocks[1:]:
        assert dict(block.rows)["blind_status"] == "blinded"
    assert "blind_status" not in dict(blocks[0].rows)
    assert dict(blocks[0].rows)["instante do servidor"] == "2026-10-01T12:00:00+00:00"
    assert ORDERING_CAVEAT in _all_rows(_section(dossier, "pre_anchor_computation")).values()
    assert "no statement is made about computations before it" in render(
        dossier, Visibility.CITABLE
    )


@pytest.mark.unit
def test_power_next_to_each_h1_claim(dossier: TraceabilityDossier) -> None:
    claims = {b.heading: dict(b.rows) for b in _section(dossier, "claim_pointers")}
    for h in (1, 7):
        power = claims[f"H1 em h+{h}"]["poder declarado"]
        assert "width_5pp_wide (primary, n = 200): P(reprovar) = " in power
    assert len(_section(dossier, "declared_power")) == 2  # noqa: PLR2004


@pytest.mark.unit
def test_one_pointer_per_verdict_claim(dossier: TraceabilityDossier) -> None:
    blocks = _section(dossier, "claim_pointers")
    assert [b.heading for b in blocks] == [
        "H1 em h+1",
        "H1 em h+7",
        "H2 em h+1",
        "H2 em h+7",
        "Vencedor primário",
        "Sucesso do estudo",
        "Leitura de H3",
        "Benchmark conformal",
    ]
    for block in blocks:
        rows = dict(block.rows)
        assert {"tabela/documento", "chave", "campo"} <= set(rows), block.heading
    claims = {b.heading: dict(b.rows) for b in blocks}
    assert claims["H1 em h+1"]["valor"] == "sim"
    assert claims["H1 em h+7"]["valor"] == "não"
    assert claims["Vencedor primário"]["valor"] == "h+1: tft_quantile; h+7: —"
    assert claims["Leitura de H3"]["tabela/documento"] == "gold_h3_reading"


@pytest.mark.unit
def test_reproduction_section_has_claim_identities_and_pointer_to_sections_1_to_4(
    dossier: TraceabilityDossier,
) -> None:
    blocks = _section(dossier, "reproduction")
    rows = dict(blocks[0].rows)
    assert rows["generation_digest"] == GENERATION_DIGEST
    assert rows["result_digest"] == RESULT_DIGEST
    assert rows["commit do .judged.toml"] == "06" * 20
    assert rows["imagem"] == IMAGE
    assert blocks[0].pointer == "docs/reports/reproduction_audit.md#1-claim"
    assert [b.heading for b in blocks[1:]] == ["Reprodução R1/R2/R3"]
    assert blocks[1].pointer is not None and "#4-" in blocks[1].pointer


@pytest.mark.unit
def test_register_entries_routed_by_kind(dossier: TraceabilityDossier) -> None:
    internal = [b.heading for b in _section(dossier, "internal")]
    citable = [b.heading for s in dossier.sections_of(Visibility.CITABLE) for b in s.blocks]
    for entry in _register():
        if entry.kind is DossierEntryKind.INTERNAL:
            assert entry.title in internal and entry.title not in citable
        else:
            assert entry.title in citable and entry.title not in internal


@pytest.mark.unit
def test_open_findings_listed_resolved_absent(dossier: TraceabilityDossier) -> None:
    deviations = {b.heading: dict(b.rows) for b in _section(dossier, "deviations")}
    assert deviations["Achado aberto"]["status"] == "open"
    assert "Errata O1 da 8.1" in deviations
    with pytest.raises(ValueError, match="needs status"):
        DossierEntry(
            kind=DossierEntryKind.FINDING,
            title="r",
            summary="s",
            pointer="docs/x.md",
            status="resolved",
        )


@pytest.mark.unit
def test_figures_section_lists_records_and_omissions(dossier: TraceabilityDossier) -> None:
    blocks = {b.heading: b for b in _section(dossier, "figures")}
    acf = dict(blocks["loss_differential_acf"].rows)
    assert acf["arquivo"] == "figures/loss_differential_acf.pdf"
    assert acf["data_digest"] == "d0" * 32
    assert acf["omissões declaradas"] == FIGURE_CATALOG["loss_differential_acf"].omissions[0]
    assert blocks["reliability_diagram"].pointer == "docs/reports/figures/reliability_diagram.json"


@pytest.mark.unit
def test_environment_commits_and_seeds_from_attempt_and_plan(dossier: TraceabilityDossier) -> None:
    environment = _all_rows(_section(dossier, "environment"))
    assert environment["env.image_id"] == IMAGE
    code = _all_rows(_section(dossier, "code_commits"))
    assert code["commit"] == "06" * 20
    assert code["code.cohort_file"] == "e3" * 32
    assert code["code.src"] == CODE_SRC  # do gerador, no bloco "Como regenerar"
    assert code["regra"] == f"regenerar em qualquer commit com code.src = {CODE_SRC}"
    seeds = _all_rows(_section(dossier, "seeds"))
    assert seeds["treino: tft_quantile"] == "1, 2, 3, 4, 5, 6, 7, 8, 9, 10"
    assert seeds["MCS"] == "127"
    assert seeds["bootstrap de H3"] == "129"


@pytest.mark.unit
def test_no_generation_instant_host_or_absolute_path(dossier: TraceabilityDossier) -> None:
    first = render(dossier, Visibility.CITABLE) + render(dossier, Visibility.INTERNAL)
    second = render(_build(), Visibility.CITABLE) + render(_build(), Visibility.INTERNAL)
    assert first == second
    assert HEAD_COMMIT not in first
    assert not [t for t in first.split() if len(t) > 1 and t.startswith(("/", "C:", "\\\\"))]


@pytest.mark.unit
def test_citable_text_free_of_prior_evidence_terms(dossier: TraceabilityDossier) -> None:
    citable = render(dossier, Visibility.CITABLE)
    assert find_forbidden(citable) == ()
    assert "reproduction_audit.md#5" not in citable
    assert "§5" not in citable


@pytest.mark.unit
def test_citable_anchors_of_82_pass_the_second_barrier(dossier: TraceabilityDossier) -> None:
    citable = render(dossier, Visibility.CITABLE)
    for anchor in sorted(CITABLE_82_ANCHORS)[:2]:
        assert anchor in citable
    assert find_forbidden(citable) == ()


@pytest.mark.unit
def test_internal_lists_required_items(dossier: TraceabilityDossier) -> None:
    internal = render(dossier, Visibility.INTERNAL)
    assert internal.startswith("# Interno, fora do texto do TCC")
    for needle in (
        "registro de hashes da evidência anterior",
        "equivalence_audit.md",
        "B3 / ADR 8.2.0004",
        "[finding] do PICP 80 %",
        "erratas F2-F5",
        "E4 do andaime",
        "limite da §5 do reproduction_audit.md",
    ):
        assert needle in internal


@pytest.mark.unit
def test_citable_block_pointer_passes_the_first_barrier(dossier: TraceabilityDossier) -> None:
    sections = list(dossier.sections)
    bad = replace(
        sections[0],
        blocks=(DossierBlock(heading="x", rows=(), pointer="docs/reports/equivalence_audit.md"),),
    )
    with pytest.raises(ValueError, match="A17"):
        TraceabilityDossier(sections=(bad, *sections[1:]))
    internal = replace(
        sections[-1],
        blocks=(DossierBlock(heading="x", rows=(), pointer="docs/reports/equivalence_audit.md"),),
    )
    assert TraceabilityDossier(sections=(*sections[:-1], internal)).sections[-1].blocks


@pytest.mark.unit
def test_markdown_is_lf_and_ends_with_newline(dossier: TraceabilityDossier) -> None:
    for visibility in Visibility:
        markdown = render(dossier, visibility)
        assert "\r" not in markdown
        assert markdown.endswith("\n") and not markdown.endswith("\n\n")
        assert "Como regenerar: regenerar em qualquer commit com code.src = " in markdown
    assert link_target("docs/reports/figures/x.json") == "figures/x.json"
    assert link_target("docs/stages/8.1/technical.md#a") == "../stages/8.1/technical.md#a"
    assert link_target("config/preregistration/p.toml") == "../../config/preregistration/p.toml"


@pytest.mark.unit
def test_missing_started_attempt_raises() -> None:
    from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (  # noqa: PLC0415
        ReportSourceMismatchError,
    )

    with pytest.raises(ReportSourceMismatchError, match="started"):
        _build(attempts=_attempts()[1:])
