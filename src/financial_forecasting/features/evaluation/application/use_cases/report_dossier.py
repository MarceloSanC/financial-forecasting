"""Montagem do dossiê de rastreabilidade citável e interno (Stage 8.3, D8, D9, I8, I12).

`build_dossier` é **puro**: lê só fontes persistidas — a cadeia do pré-registro (com as
âncoras e o `blinding_statement`), o `.judged.toml`, as tentativas do `ATTEMPTS.jsonl`, o
`run_record.json` e o scorecard da cópia, o manifesto, o `dim_run` do cohort, os registros
das figuras e o registro curado — e monta as seções de `CITABLE_SECTIONS` (na ordem das
camadas do D8) e a interna. Nada é transcrito à mão; o que não está em dado persistido vem
do registro curado, com ponteiro.

Determinismo (I8): nenhum instante da geração, host, caminho absoluto nem commit HEAD. A
foto do ambiente do **gerador** entra só por `code.src`/`code.uv_lock` ("regenerar em
qualquer commit com `code.src = <x>`"). Instantes **persistidos** (âncoras,
`commented_at`, `started_at`) são dado e entram.

Visibilidade pela fonte (A17): entrada `internal` do registro vai só ao interno; as demais
só ao citável. O `TraceabilityDossier` recusa ponteiro proibido em seção citável.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    RUN_RECORD_SEEDS,
    SEEDS_REFERENCE,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_COVERAGE,
    GOLD_H3_READING,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CITABLE_SECTIONS,
    INTERNAL_SECTION,
    DossierBlock,
    DossierEntry,
    DossierEntryKind,
    DossierSection,
    FigureRecord,
    ReportSourceMismatchError,
    TraceabilityDossier,
    Visibility,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    ENV_PREFIX,
    IMAGE_ID_KEY,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    JudgedRevision,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun

REGENERATE_HEADING: Final = "Como regenerar"
"""O bloco de `code_commits` cujo `comando` o Markdown repete no topo dos dois arquivos."""
ORDERING_CAVEAT: Final = (
    "a ordem provada é a do ADR 6.5.0003 item 4: a âncora precede a geração julgada; "
    '"no statement is made about computations before it"'
)
CODE_SRC: Final = "code.src"
CODE_UV_LOCK: Final = "code.uv_lock"
_ADR_ORDER: Final = "docs/adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md"
_REPRODUCTION_AUDIT: Final = "docs/reports/reproduction_audit.md"

Row = tuple[str, str]


def _text(value: object) -> str:
    """Valor de célula em texto (bool/None/número pelo `str`, como no documento)."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sim" if value else "não"
    return str(value)


def _get(mapping: object, *path: str | int) -> object:
    current = mapping
    try:
        for step in path:
            current = current[step]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise ReportSourceMismatchError(
            f"{SCORECARD_DOCUMENT} lacks {'.'.join(map(str, path))}"
        ) from error
    return current


def _horizons(scorecard: Mapping[str, object], part: str) -> list[Mapping[str, object]]:
    entries = _get(scorecard, part, "horizons")
    if not isinstance(entries, list) or not all(isinstance(e, Mapping) for e in entries):
        raise ReportSourceMismatchError(f"{SCORECARD_DOCUMENT}: {part}.horizons is not a list")
    return entries


def _block(heading: str, rows: Sequence[Row], pointer: str | None = None) -> DossierBlock:
    return DossierBlock(heading=heading, rows=tuple(rows), pointer=pointer)


def _entry_block(entry: DossierEntry) -> DossierBlock:
    rows: list[Row] = [("resumo", entry.summary)]
    if entry.status is not None:
        rows.append(("status", entry.status))
    return _block(entry.title, rows, entry.pointer)


def _entries(register: Sequence[DossierEntry], *kinds: DossierEntryKind) -> list[DossierBlock]:
    return [_entry_block(entry) for entry in register if entry.kind in kinds]


# --------------------------------------------------------------------------------------
# Camada 1 — veredito, afirmações e poder declarado
# --------------------------------------------------------------------------------------


def _power_text(profile: Mapping[str, object]) -> str:
    scenarios = _get(profile, "power")
    if not isinstance(scenarios, list):
        raise ReportSourceMismatchError(f"{SCORECARD_DOCUMENT}: power is not a list")
    return "; ".join(
        f"{_get(s, 'label')} ({_get(s, 'role')}, n = {_get(s, 'n')}): "
        f"P(reprovar) = {_get(s, 'failure_probability')}"
        for s in scenarios
    )


def _pointer_rows(document: str, key: str, field: str) -> list[Row]:
    return [("tabela/documento", document), ("chave", key), ("campo", field)]


def _claim_blocks(scorecard: Mapping[str, object]) -> list[DossierBlock]:
    verdicts = _horizons(scorecard, "verdict")
    profiles = {_get(p, "horizon"): p for p in _horizons(scorecard, "profile")}
    blocks: list[DossierBlock] = []
    for verdict in verdicts:
        h = _get(verdict, "horizon")
        blocks.append(
            _block(
                f"H1 em h+{h}",
                [
                    ("afirmação", f"o gate H1 de h+{h} passa"),
                    ("valor", _text(_get(verdict, "h1", "passed"))),
                    ("poder declarado", _power_text(profiles[h])),
                    *_pointer_rows(
                        SCORECARD_DOCUMENT, f"verdict.horizons[horizon={h}]", "h1.passed"
                    ),
                ],
            )
        )
    for verdict in verdicts:
        h = _get(verdict, "horizon")
        blocks.append(
            _block(
                f"H2 em h+{h}",
                [
                    ("afirmação", f"desfecho de H2 em h+{h}"),
                    ("valor", _text(_get(verdict, "h2"))),
                    *_pointer_rows(SCORECARD_DOCUMENT, f"verdict.horizons[horizon={h}]", "h2"),
                ],
            )
        )
    blocks.append(
        _block(
            "Vencedor primário",
            [
                ("afirmação", "vencedor primário por horizonte"),
                (
                    "valor",
                    "; ".join(
                        f"h+{_get(v, 'horizon')}: {_text(_get(v, 'primary_winner'))}"
                        for v in verdicts
                    ),
                ),
                *_pointer_rows(SCORECARD_DOCUMENT, "verdict.horizons[]", "primary_winner"),
            ],
        )
    )
    blocks.append(
        _block(
            "Sucesso do estudo",
            [
                ("afirmação", "H1 não rejeitado em pelo menos um horizonte"),
                ("valor", _text(_get(scorecard, "verdict", "study_success_h1"))),
                *_pointer_rows(SCORECARD_DOCUMENT, "verdict", "study_success_h1"),
            ],
        )
    )
    blocks.append(
        _block(
            "Leitura de H3",
            [
                ("afirmação", "leitura descritiva de H3 (C4/C5)"),
                *_pointer_rows(GOLD_H3_READING.name, "reading_rule", "label, status"),
            ],
        )
    )
    blocks.append(
        _block(
            "Benchmark conformal",
            [
                ("afirmação", "cobertura empírica (não garantida) do CQR e do nativo"),
                *_pointer_rows(
                    GOLD_CONFORMAL_COVERAGE.name,
                    "horizon, variant, kind, lower_level, upper_level, seed, band_level",
                    "coverage, mpiw, label",
                ),
            ],
        )
    )
    return blocks


def _power_blocks(scorecard: Mapping[str, object]) -> list[DossierBlock]:
    blocks: list[DossierBlock] = []
    for profile in _horizons(scorecard, "profile"):
        scenarios = _get(profile, "power")
        if not isinstance(scenarios, list):
            raise ReportSourceMismatchError(f"{SCORECARD_DOCUMENT}: power is not a list")
        blocks.append(
            _block(
                f"Poder do gate H1 em h+{_get(profile, 'horizon')}",
                [
                    (
                        str(_get(s, "label")),
                        f"{_get(s, 'role')}; n = {_get(s, 'n')}; P(reprovar) = "
                        f"{_get(s, 'failure_probability')}; independência assumida = "
                        f"{_text(_get(s, 'assumes_independence'))}",
                    )
                    for s in scenarios
                ],
            )
        )
    return blocks


# --------------------------------------------------------------------------------------
# Camadas 2 a 5 — identidade, pré-registro, geração julgada, ambiente
# --------------------------------------------------------------------------------------


def _identity_blocks(
    plan_chain: JudgedRevision, manifest: GoldManifest, runs: Sequence[CohortRun]
) -> list[DossierBlock]:
    plan = plan_chain.plan
    rows: list[Row] = [
        ("cohort", f"{plan.cohort.cohort_id} (hash {plan.cohort.cohort_hash})"),
        ("partição", f"{manifest.partition.asset}/{manifest.partition.parent_sweep_id}"),
        ("fingerprint do dataset", manifest.dataset_fingerprint.value),
        ("hash de conteúdo do silver lido", manifest.silver_content.digest),
    ]
    if plan.h3 is not None:
        rows += [
            ("feature_set_hash", plan.h3.feature_set_hash),
            (
                "cohort da ablação",
                f"{plan.h3.ablation_cohort_id} (hash {plan.h3.ablation_cohort_hash})",
            ),
        ]
    run_rows: list[Row] = [
        (
            run.run_id,
            f"{run.model}; seed {_text(run.seed)}; fold {_text(run.fold)}; "
            f"feature_set {run.feature_set_name}; config_signature {run.config_signature}",
        )
        for run in sorted(runs, key=lambda r: r.run_id)
    ]
    return [_block("Entrada", rows), _block("Runs do cohort (dim_run)", run_rows)]


def _chain_blocks(plan_chain: JudgedRevision) -> list[DossierBlock]:
    blocks: list[DossierBlock] = []
    for index, (record, plan, reference) in enumerate(
        zip(plan_chain.records, plan_chain.plans, plan_chain.chain, strict=True)
    ):
        rows: list[Row] = [("preregistration_ref", reference)]
        anchor = record.anchor
        if anchor is not None:
            rows += [
                ("tag", anchor.tag),
                ("commit da âncora", anchor.commit),
                ("comentário de âncora", anchor.comment_url),
                ("instante do servidor", anchor.anchored_at.isoformat()),
            ]
        if plan.amendment is not None:
            rows += [
                ("emenda de", plan.amendment.amends),
                ("blind_status", plan.amendment.blind_status.value),
            ]
        if index == len(plan_chain.chain) - 1:
            rows.append(("revisão julgada", "sim"))
        blocks.append(
            _block(
                f"r{plan.revision}",
                rows,
                f"config/preregistration/{plan.name}-r{plan.revision}.toml",
            )
        )
    return blocks


def _pre_anchor_blocks(register: Sequence[DossierEntry]) -> list[DossierBlock]:
    return [
        _block(
            "Ressalva de ordem",
            [("ressalva", ORDERING_CAVEAT)],
            _ADR_ORDER,
        ),
        *_entries(register, DossierEntryKind.PRE_ANCHOR),
    ]


def _blinding_blocks(plan_chain: JudgedRevision) -> list[DossierBlock]:
    plan = plan_chain.plan
    statement = plan.blinding_statement
    if statement is None:
        raise ReportSourceMismatchError("the judged revision has no blinding_statement")
    return [
        _block(
            "Declaração de cegamento (transcrição)",
            [("blinding_statement", statement)],
            f"config/preregistration/{plan.name}-r{plan.revision}.toml",
        )
    ]


def _judged_blocks(
    plan_chain: JudgedRevision,
    judged_record: JudgedRecord,
    scorecard: Mapping[str, object],
    manifest: GoldManifest,
) -> list[DossierBlock]:
    reasons = _get(scorecard, "readiness_reasons")
    plan = plan_chain.plan
    return [
        _block(
            "Cópia selada",
            [
                ("preregistration_ref", judged_record.preregistration_ref),
                ("generation_digest", judged_record.generation_digest),
                ("estado", judged_record.refresh_status.value),
                (
                    "manifesto lido",
                    f"{manifest.partition.asset}/{manifest.partition.parent_sweep_id}",
                ),
                ("academic_decision_ready", _text(_get(scorecard, "academic_decision_ready"))),
                (
                    "motivos",
                    ", ".join(map(str, reasons)) if isinstance(reasons, list) and reasons else "—",
                ),
                ("commit da corrida", judged_record.commit),
                ("tag", judged_record.tag),
                ("comentário de atestação", judged_record.comment_url),
                ("instante do comentário", judged_record.commented_at.isoformat()),
                (
                    "backup de entrada",
                    f"{judged_record.input_backup} ({judged_record.input_backup_sha256})",
                ),
                (
                    "backup julgado",
                    f"{judged_record.judged_backup} ({judged_record.judged_backup_sha256})",
                ),
            ],
            f"config/preregistration/{plan.name}-r{plan.revision}.judged.toml",
        )
    ]


def _last_started(attempts: Sequence[JudgedAttempt], ref: str) -> JudgedAttempt:
    started = [
        a for a in attempts if a.phase is AttemptPhase.STARTED and a.preregistration_ref == ref
    ]
    if not started:
        raise ReportSourceMismatchError(f"no started attempt line of {ref}")
    return started[-1]


def _environment_blocks(
    started: JudgedAttempt, register: Sequence[DossierEntry]
) -> list[DossierBlock]:
    environment = started.environment or {}
    rows: list[Row] = [
        (key, environment[key]) for key in sorted(environment) if key.startswith(ENV_PREFIX)
    ]
    return [
        _block("Avaliação (corrida julgada)", rows),
        *_entries(register, DossierEntryKind.ENVIRONMENT),
    ]


def _code_blocks(
    started: JudgedAttempt, snapshot: Mapping[str, str], command: str
) -> list[DossierBlock]:
    code = started.code or {}
    try:
        generator = [(CODE_SRC, snapshot[CODE_SRC]), (CODE_UV_LOCK, snapshot[CODE_UV_LOCK])]
    except KeyError as error:
        raise ReportSourceMismatchError(f"the generator snapshot lacks {error}") from error
    return [
        _block(
            "Corrida julgada",
            [
                ("commit", _text(started.commit)),
                (
                    "início (persistido)",
                    _text(started.started_at and started.started_at.isoformat()),
                ),
                *((key, code[key]) for key in sorted(code)),
            ],
        ),
        _block(
            REGENERATE_HEADING,
            [
                *generator,
                ("regra", f"regenerar em qualquer commit com code.src = {snapshot[CODE_SRC]}"),
                ("comando", command),
            ],
        ),
    ]


def _seed_blocks(
    plan_chain: JudgedRevision, run_record: Mapping[str, object]
) -> list[DossierBlock]:
    plan = plan_chain.plan
    rows: list[Row] = [
        (f"treino: {model}", "sem seed" if spec.seeds is None else ", ".join(map(str, spec.seeds)))
        for model, spec in sorted(plan.seeds.items())
    ]
    rows += [
        ("MCS", str(plan.mcs.seed)),
        ("Monte Carlo de Christoffersen", str(plan.monte_carlo.seed)),
    ]
    if plan.h3 is not None:
        rows += [
            ("permutação de H3", str(plan.h3.permutation_seed)),
            ("bootstrap de H3", str(plan.h3.bootstrap_seed)),
            ("ablação de H3", ", ".join(map(str, plan.h3.ablation_seeds))),
        ]
    reference = run_record.get(RUN_RECORD_SEEDS, SEEDS_REFERENCE)
    if isinstance(reference, Mapping):
        rows += [(f"referência ({key})", str(value)) for key, value in sorted(reference.items())]
    return [_block("Seeds", rows)]


# --------------------------------------------------------------------------------------
# Camadas 6 a 8 — figuras, reprodução, desvios; e o interno
# --------------------------------------------------------------------------------------


def _figure_blocks(records: Sequence[FigureRecord]) -> list[DossierBlock]:
    blocks: list[DossierBlock] = []
    for record in records:
        rows: list[Row] = [
            ("arquivo", f"figures/{record.figure_id}.pdf"),
            ("data_digest", record.data_digest),
            *(
                (
                    f"fonte: {source.kind.value} {source.name}",
                    f"filtro {dict(source.filter)}; campos {', '.join(source.fields)}",
                )
                for source in record.sources
            ),
            ("omissões declaradas", "; ".join(record.omissions) or "nenhuma"),
            ("unidades do silver", str(len(record.silver_units))),
        ]
        blocks.append(
            _block(record.figure_id, rows, f"docs/reports/figures/{record.figure_id}.json")
        )
    return blocks


def _reproduction_blocks(
    judged_record: JudgedRecord,
    result_digest: str,
    started: JudgedAttempt,
    register: Sequence[DossierEntry],
) -> list[DossierBlock]:
    environment = started.environment or {}
    return [
        _block(
            "Identidade reproduzida",
            [
                ("generation_digest", judged_record.generation_digest),
                ("result_digest", result_digest),
                ("commit do .judged.toml", judged_record.commit),
                ("imagem", environment.get(IMAGE_ID_KEY, "—")),
            ],
            f"{_REPRODUCTION_AUDIT}#1-claim",
        ),
        *_entries(register, DossierEntryKind.REPRODUCTION),
    ]


def build_dossier(  # noqa: PLR0913 — as fontes persistidas do dossiê (D8), uma por argumento
    *,
    plan_chain: JudgedRevision,
    judged_record: JudgedRecord,
    attempts: Sequence[JudgedAttempt],
    result_digest: str,
    run_record: Mapping[str, object],
    scorecard: Mapping[str, object],
    manifest: GoldManifest,
    runs: Sequence[CohortRun],
    records: Sequence[FigureRecord],
    register: Sequence[DossierEntry],
    snapshot: Mapping[str, str],
) -> TraceabilityDossier:
    """O dossiê citável (seções de `CITABLE_SECTIONS`) e o interno, das fontes persistidas.

    `result_digest` é o da última `input_read` da referência (dono:
    `judged_copy.last_input_read_digest`, chamado pelo use case).

    Raises:
        ReportSourceMismatchError: scorecard fora da forma, sem tentativa `started` da
            referência, sem `blinding_statement` ou foto do gerador sem `code.src`.
        ValueError: ponteiro proibido numa seção citável (A17).
    """
    ref = judged_record.preregistration_ref
    started = _last_started(attempts, ref)
    plan = plan_chain.plan
    command = (
        "report-artifacts --data-root <data_root> --cohort <arquivo de cohort> "
        f"--preregistration {plan.name} --revision {plan.revision} "
        f"--preregistration-ref {ref}"
    )
    content: dict[str, list[DossierBlock]] = {
        "claim_pointers": _claim_blocks(scorecard),
        "declared_power": _power_blocks(scorecard),
        "identity": _identity_blocks(plan_chain, manifest, runs),
        "preregistration_chain": _chain_blocks(plan_chain),
        "pre_anchor_computation": _pre_anchor_blocks(register),
        "blinding_statement": _blinding_blocks(plan_chain),
        "judged_generation": _judged_blocks(plan_chain, judged_record, scorecard, manifest),
        "environment": _environment_blocks(started, register),
        "code_commits": _code_blocks(started, snapshot, command),
        "seeds": _seed_blocks(plan_chain, run_record),
        "figures": _figure_blocks(records),
        "reproduction": _reproduction_blocks(judged_record, result_digest, started, register),
        "deviations": _entries(register, DossierEntryKind.DEVIATION, DossierEntryKind.FINDING),
    }
    sections = [
        DossierSection(
            section_id=section_id,
            title=title,
            visibility=Visibility.CITABLE,
            blocks=tuple(content[section_id]),
        )
        for section_id, title in CITABLE_SECTIONS
    ]
    sections.append(
        DossierSection(
            section_id=INTERNAL_SECTION[0],
            title=INTERNAL_SECTION[1],
            visibility=Visibility.INTERNAL,
            blocks=tuple(_entries(register, DossierEntryKind.INTERNAL)),
        )
    )
    return TraceabilityDossier(sections=tuple(sections))
