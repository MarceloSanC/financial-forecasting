"""DTOs do dado plotado, do registro por figura e do dossiê (Stage 8.3, Task 02).

Cobre A11 (forma do registro e `data_digest` pelo dono único), A16 (omissões fechadas no
tipo, comparadas com a lista literal do D13), A17 (1ª barreira na construção e os padrões
da 2ª) e a base do A1/A5/A12 (catálogo, rótulos, seções citáveis fechadas).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CITABLE_82_ANCHORS,
    CITABLE_SECTIONS,
    FIGURE_CATALOG,
    FIGURE_IDS,
    INTERNAL_SECTION,
    DossierBlock,
    DossierEntry,
    DossierEntryKind,
    DossierSection,
    ElementLabel,
    FigureRecord,
    FigureSpec,
    GenerateReportArtifactsCommand,
    PanelScope,
    PanelSpec,
    ReportArtifactsResult,
    SeriesKind,
    SeriesSpec,
    SilverContentMismatchError,
    SourceKind,
    SourceRef,
    StatusLabel,
    TraceabilityDossier,
    Visibility,
    canonical_json_bytes,
    check_artifacts,
    fan_chart_seed_note,
    find_forbidden,
)

_SHA = "a" * 64
_SHA_B = "b" * 64
_CITABLE_82_ANCHOR_COUNT = 4  # E2 item 7, env-equal, [measurement] E2 e E3
_CITABLE_SECTION_COUNT = 13  # as 14 linhas da tabela do doc §7 menos a interna

# A16: a coluna "Omissões declaradas" do D13 (concept 8.3 §7), literal, sem a marcação
# Markdown (negrito e crase); "nenhuma (…)" é a tupla vazia.
_D13_OMISSIONS: dict[str, tuple[str, ...]] = {
    "reliability_diagram": (
        "τ = 0,5 (sem linha de calibração)",
        "banda de Wilson do candidato nos níveis fora do gate e da média entre seeds "
        "(o gold só a tem por seed; a dispersão por seed é desenhada no lugar)",
    ),
    "quantile_score_plot": (),
    "sharpness_diagram": (),
    "picp_mpiw_plot": (),
    "dm_candidate_vs_comparators": (),
    "oos_fan_chart": (),
    "loss_differential_acf": ("faixa de confiança da ACF (±1,96/√n não persistida)",),
    "h3_family_importance": ("intervalo bootstrap de I_f(h) e de s_f(h) (o gold só tem o de Δ_f)",),
    "vsn_weights": (),
    "native_vs_conformal": (
        "referência de dispersão Beta agregada (o gold só tem beta_mean/beta_sd por "
        "fold × seed × cauda; agregar ou tirar quantis seria cálculo novo)",  # noqa: RUF001
        "banda de Wilson do nativo na média entre seeds (só por seed no gold; os pontos "
        "por seed ficam como dispersão)",
    ),
}

# I11 / technical §1: as frases obrigatórias por figura (sete figuras têm frase).
_REQUIRED_NOTES: dict[str, str] = {
    "reliability_diagram": "banda binomial anti-conservadora em h+7 e sob agrupamento",
    "sharpness_diagram": "sharpness só tem sentido sujeito à calibração",
    "picp_mpiw_plot": (
        "o gráfico não ordena modelos — mais estreito só é melhor com cobertura igual"
    ),
    "oos_fan_chart": "seed 1, ilustrativa; as métricas usam a média entre seeds",
    "h3_family_importance": (
        "linguagem estritamente descritiva: a família f responde por uma parcela maior "
        'da perda evitada em h+7 do que em h+1; nunca "f causa"'
    ),
    "vsn_weights": "horizonte-invariante",
    "native_vs_conformal": "cobertura empírica (não garantida)",
}


def _label(status: StatusLabel = StatusLabel.DESCRIPTIVE, note: str | None = None) -> ElementLabel:
    return ElementLabel(status=status, note=note)


def _series(series_id: str = "s", **overrides: object) -> SeriesSpec:
    fields: dict[str, object] = {
        "series_id": series_id,
        "kind": SeriesKind.POINTS,
        "name": "candidato",
        "label": _label(),
        "x": (0.1, 0.9),
        "y": (0.11, 0.88),
    }
    fields.update(overrides)
    return SeriesSpec(**fields)  # type: ignore[arg-type]


def _panel(panel_id: str = "h1", **overrides: object) -> PanelSpec:
    fields: dict[str, object] = {
        "panel_id": panel_id,
        "scope": PanelScope.HORIZON,
        "horizon": 1,
        "title": "h+1",
        "x_label": "τ",
        "y_label": "ĉ(τ)",
        "series": (_series(),),
        "label": _label(),
    }
    fields.update(overrides)
    return PanelSpec(**fields)  # type: ignore[arg-type]


def _spec(figure_id: str, **overrides: object) -> FigureSpec:
    entry = FIGURE_CATALOG[figure_id]
    panel_label = _label(note=entry.panel_note)
    fields: dict[str, object] = {
        "figure_id": figure_id,
        "title": entry.title,
        "panels": (_panel(label=panel_label),),
        "notes": (_REQUIRED_NOTES[figure_id],) if figure_id in _REQUIRED_NOTES else (),
        "omissions": entry.omissions,
    }
    fields.update(overrides)
    return FigureSpec(**fields)  # type: ignore[arg-type]


def _record(figure_id: str = "quantile_score_plot", **overrides: object) -> FigureRecord:
    fields: dict[str, object] = {
        "figure_id": figure_id,
        "data_digest": _SHA,
        "generation_digest": _SHA_B,
        "preregistration_ref": "aapl_confirmatory-r3-00fd83d9cd39",
        "revision": 3,
        "partition": GoldPartition(asset="AAPL", parent_sweep_id="aapl_confirmatory-r0"),
        "sources": (
            SourceRef(
                kind=SourceKind.GOLD_TABLE,
                name="gold_metrics_by_run",
                filter={"sample": "common", "metric": "pinball", "level_low": 0.1},
                fields=("value",),
            ),
        ),
        "silver_units": {},
        "excluded_degenerate": {},
        "omissions": FIGURE_CATALOG[figure_id].omissions,
        "omitted_models": (),
        "code": {"code.src": _SHA, "code.uv_lock": _SHA_B},
        "renderer": {"format": "pdf", "renderer": "in-memory"},
    }
    fields.update(overrides)
    return FigureRecord(**fields)  # type: ignore[arg-type]


def _dossier() -> TraceabilityDossier:
    block = DossierBlock(heading="bloco", rows=(("campo", "valor"),), pointer=None)
    sections = tuple(
        DossierSection(section_id=sid, title=title, visibility=Visibility.CITABLE, blocks=(block,))
        for sid, title in CITABLE_SECTIONS
    )
    internal = DossierSection(
        section_id=INTERNAL_SECTION[0],
        title=INTERNAL_SECTION[1],
        visibility=Visibility.INTERNAL,
        blocks=(block,),
    )
    return TraceabilityDossier(sections=(*sections, internal))


def _artifacts() -> list[tuple[str, bytes, FigureRecord]]:
    return [(fid, b"%PDF-1.4 x", _record(fid)) for fid in FIGURE_IDS]


# ---------------------------------------------------------------------------- catálogo


@pytest.mark.unit
def test_catalog_has_the_ten_ids_in_doc_order() -> None:
    assert FIGURE_IDS == (
        "reliability_diagram",
        "quantile_score_plot",
        "sharpness_diagram",
        "picp_mpiw_plot",
        "dm_candidate_vs_comparators",
        "oos_fan_chart",
        "loss_differential_acf",
        "h3_family_importance",
        "vsn_weights",
        "native_vs_conformal",
    )


@pytest.mark.unit
def test_catalog_omissions_equal_concept_d13_literal() -> None:
    assert {fid: entry.omissions for fid, entry in FIGURE_CATALOG.items()} == _D13_OMISSIONS


@pytest.mark.unit
def test_spec_rejects_omission_outside_catalog() -> None:
    with pytest.raises(ValueError, match="omissions"):
        _spec("quantile_score_plot", omissions=("algo não declarado",))
    with pytest.raises(ValueError, match="omissions"):
        _spec("reliability_diagram", omissions=_D13_OMISSIONS["reliability_diagram"][:1])


@pytest.mark.unit
@pytest.mark.parametrize("figure_id", sorted(_REQUIRED_NOTES))
def test_spec_rejects_missing_required_note(figure_id: str) -> None:
    assert _spec(figure_id).figure_id == figure_id
    with pytest.raises(ValueError, match="required notes"):
        _spec(figure_id, notes=("outra legenda",))


@pytest.mark.unit
def test_fan_chart_note_needs_an_integer_seed() -> None:
    assert fan_chart_seed_note(7) == "seed 7, ilustrativa; as métricas usam a média entre seeds"
    assert _spec("oos_fan_chart", notes=(fan_chart_seed_note(7),)).notes
    with pytest.raises(ValueError, match="required notes"):
        _spec("oos_fan_chart", notes=(FIGURE_CATALOG["oos_fan_chart"].required_notes[0],))


@pytest.mark.unit
def test_conformal_requires_the_note_on_every_panel() -> None:
    label = _label(note="cobertura empírica (não garantida)")
    two = (_panel("h1", label=label), _panel("h7", horizon=7, label=_label()))
    with pytest.raises(ValueError, match=r"panels \['h7'\]"):
        _spec("native_vs_conformal", panels=two)


@pytest.mark.unit
def test_spec_rejects_unknown_id_and_repeated_panel() -> None:
    with pytest.raises(ValueError, match="FIGURE_CATALOG"):
        FigureSpec(figure_id="exploratory", title="t", panels=(_panel(),), notes=(), omissions=())
    with pytest.raises(ValueError, match="repeats a panel_id"):
        _spec("quantile_score_plot", panels=(_panel(), _panel()))


# ------------------------------------------------------------------------- dado plotado


@pytest.mark.unit
def test_series_without_label_does_not_construct() -> None:
    with pytest.raises(ValueError, match="ElementLabel"):
        _series(label=None)
    with pytest.raises(ValueError, match="ElementLabel"):
        _series(label="descritivo")


@pytest.mark.unit
def test_status_label_has_no_exploratory() -> None:
    assert {label.value for label in StatusLabel} == {
        "confirmatório",
        "descritivo (perfil)",
        "descritivo",
        "descritivo (perfil) — H2 não aplicável",
    }
    with pytest.raises(ValueError):
        StatusLabel("exploratório")


@pytest.mark.unit
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "0.1"])
def test_non_finite_values_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="finite"):
        _series(y=(0.1, bad))
    with pytest.raises(ValueError, match="finite"):
        _series(low=(bad, 0.2), high=(0.3, 0.4))
    if not isinstance(bad, str):
        with pytest.raises(ValueError, match="finite"):
            _series(x=(0.1, bad))


@pytest.mark.unit
def test_none_is_a_valid_gap() -> None:
    assert _series(y=(None, 0.2)).y == (None, 0.2)


@pytest.mark.unit
def test_low_high_lengths_must_match_x() -> None:
    with pytest.raises(ValueError, match="length of x"):
        _series(low=(0.1,), high=(0.2, 0.3))
    with pytest.raises(ValueError, match="length of x"):
        _series(y=(0.1,))
    with pytest.raises(ValueError, match="length of x"):
        _series(text=("a",))


@pytest.mark.unit
def test_boxes_need_quartiles_and_whiskers_and_only_boxes_have_whiskers() -> None:
    box = _series(
        kind=SeriesKind.BOXES,
        x=("par 0,1-0,9",),
        y=(0.02,),
        low=(0.01,),
        high=(0.03,),
        whisker_low=(0.0,),
        whisker_high=(0.05,),
    )
    assert box.as_mapping()["whisker_high"] == [0.05]
    with pytest.raises(ValueError, match="boxes need"):
        replace(box, whisker_low=None)
    with pytest.raises(ValueError, match="only in boxes"):
        _series(whisker_low=(0.0, 0.0))


@pytest.mark.unit
def test_horizon_panel_requires_horizon_and_invariant_forbids_it() -> None:
    with pytest.raises(ValueError, match="horizon"):
        _panel(horizon=None)
    with pytest.raises(ValueError, match="horizon"):
        _panel(horizon=0)
    with pytest.raises(ValueError, match="has no horizon"):
        _panel(scope=PanelScope.HORIZON_INVARIANT, horizon=1)
    with pytest.raises(ValueError, match="has no horizon"):
        _panel(scope=PanelScope.HORIZON_COMPARISON, horizon=7)
    assert _panel(scope=PanelScope.HORIZON_INVARIANT, horizon=None).horizon is None


@pytest.mark.unit
def test_panel_rejects_empty_or_repeated_series() -> None:
    with pytest.raises(ValueError, match="at least one series"):
        _panel(series=())
    with pytest.raises(ValueError, match="repeats a series_id"):
        _panel(series=(_series("a"), _series("a")))


@pytest.mark.unit
def test_canonical_bytes_are_order_independent_and_exact() -> None:
    forward = {"a": 1, "b": {"x": 0.1, "y": [1.5, None]}}
    backward = {"b": {"y": [1.5, None], "x": 0.1}, "a": 1}
    assert canonical_json_bytes(forward) == canonical_json_bytes(backward)
    with pytest.raises(ValueError):
        canonical_json_bytes({"a": math.nan})

    spec = _spec("quantile_score_plot")
    bumped = _spec(
        "quantile_score_plot",
        panels=(_panel(series=(_series(y=(math.nextafter(0.11, 1.0), 0.88)),)),),
    )
    assert spec.canonical_bytes() == _spec("quantile_score_plot").canonical_bytes()
    assert spec.canonical_bytes() != bumped.canonical_bytes()
    assert spec.data_digest != bumped.data_digest
    assert spec.data_digest == hashlib.sha256(spec.canonical_bytes()).hexdigest()
    assert json.loads(spec.canonical_bytes())["figure_id"] == "quantile_score_plot"


# ---------------------------------------------------------------------------- registro


@pytest.mark.unit
def test_record_as_mapping_fields_and_no_commit_or_time() -> None:
    record = _record()
    mapping = record.as_mapping()
    assert set(mapping) == {
        "figure_id",
        "data_digest",
        "generation_digest",
        "preregistration_ref",
        "revision",
        "partition",
        "sources",
        "silver_units",
        "excluded_degenerate",
        "omissions",
        "omitted_models",
        "code",
        "renderer",
    }
    assert mapping["partition"] == {"asset": "AAPL", "parent_sweep_id": "aapl_confirmatory-r0"}
    assert mapping["sources"] == [
        {
            "kind": "gold_table",
            "name": "gold_metrics_by_run",
            "filter": {"level_low": 0.1, "metric": "pinball", "sample": "common"},
            "fields": ["value"],
        }
    ]
    assert mapping["code"] == {"code.src": _SHA, "code.uv_lock": _SHA_B}
    json.dumps(mapping, allow_nan=False)

    for key in ("commit", "head_commit", "time", "generated_at", "at"):
        with pytest.raises(ValueError, match="I8"):
            _record(renderer={"format": "pdf", key: "x"})
    for key in ("commit", "started_at"):
        with pytest.raises(ValueError, match="I8"):
            _record(
                sources=(
                    SourceRef(kind=SourceKind.DOCUMENT, name="s", filter={key: 1}, fields=("f",)),
                )
            )
    for absolute in ("/app/data/x", "C:/Users/x", "C:\\Users\\x"):
        with pytest.raises(ValueError, match="absolute path"):
            _record(renderer={"format": absolute})
    with pytest.raises(ValueError, match="code must hold exactly"):
        _record(code={"code.src": _SHA})
    with pytest.raises(ValueError, match="omissions differ"):
        _record("reliability_diagram", omissions=())


@pytest.mark.unit
def test_record_silver_units_and_degenerate_counts() -> None:
    record = _record(
        "sharpness_diagram",
        silver_units={"fact_oos_predictions|r1|2024": _SHA, "dim_run|c": _SHA_B},
        excluded_degenerate={"tft_quantile|1|h1|0.1-0.9": 2},
    )
    assert list(record.silver_units) == ["dim_run|c", "fact_oos_predictions|r1|2024"]
    assert record.as_mapping()["excluded_degenerate"] == {"tft_quantile|1|h1|0.1-0.9": 2}
    with pytest.raises(ValueError, match="sha256"):
        _record(silver_units={"dim_run|c": "x"})
    with pytest.raises(ValueError, match="excluded_degenerate"):
        _record(excluded_degenerate={"k": -1})


@pytest.mark.unit
def test_record_carries_omitted_models_and_refuses_repeats() -> None:
    record = _record("sharpness_diagram", omitted_models=("baseline_historical_mean",))
    assert record.as_mapping()["omitted_models"] == ["baseline_historical_mean"]
    with pytest.raises(ValueError, match="omitted_models"):
        _record("sharpness_diagram", omitted_models=("m", "m"))
    with pytest.raises(ValueError, match="omitted_models"):
        _record("sharpness_diagram", omitted_models=["m"])


@pytest.mark.unit
def test_source_ref_validation() -> None:
    with pytest.raises(ValueError, match="finite"):
        SourceRef(kind=SourceKind.GOLD_TABLE, name="t", filter={"v": math.nan}, fields=("f",))
    with pytest.raises(ValueError, match="scalar"):
        SourceRef(kind=SourceKind.GOLD_TABLE, name="t", filter={"v": [1]}, fields=("f",))
    with pytest.raises(ValueError, match="unique"):
        SourceRef(kind=SourceKind.GOLD_TABLE, name="t", filter={}, fields=("f", "f"))
    with pytest.raises(ValueError, match="SourceKind"):
        SourceRef(kind="gold_table", name="t", filter={}, fields=("f",))  # type: ignore[arg-type]


# --------------------------------------------------------------- registro curado (A17)


@pytest.mark.unit
def test_dossier_entry_kinds_closed_and_finding_requires_open() -> None:
    assert {kind.value for kind in DossierEntryKind} == {
        "deviation",
        "finding",
        "pre_anchor",
        "environment",
        "reproduction",
        "internal",
    }
    pointer = "docs/stages/8.1-confirmatory-run/technical.md#x"
    finding = DossierEntry(
        kind=DossierEntryKind.FINDING, title="t", summary="s", pointer=pointer, status="open"
    )
    assert finding.visibility is Visibility.CITABLE
    with pytest.raises(ValueError, match="needs status"):
        DossierEntry(kind=DossierEntryKind.FINDING, title="t", summary="s", pointer=pointer)
    with pytest.raises(ValueError, match="needs status"):
        replace(finding, status="resolved")
    with pytest.raises(ValueError, match="only in finding"):
        DossierEntry(
            kind=DossierEntryKind.DEVIATION, title="t", summary="s", pointer=pointer, status="open"
        )
    with pytest.raises(ValueError, match="DossierEntryKind"):
        DossierEntry(kind="deviation", title="t", summary="s", pointer=pointer)  # type: ignore[arg-type]
    for bad in ("", "/abs/x.md", "docs\\x.md", "../x.md", "docs/x y.md", "#only-anchor"):
        with pytest.raises(ValueError):
            DossierEntry(kind=DossierEntryKind.DEVIATION, title="t", summary="s", pointer=bad)


@pytest.mark.unit
@pytest.mark.parametrize(
    "pointer",
    [
        "docs/stages/8.2-equivalence-audit/technical.md#2026-10-24--finding-auditoria",
        "DOCS/Stages/8.2-equivalence-audit/concept.md",
        "docs/stages/8.2_equivalence_audit/technical.md",
        "docs/reports/equivalence_audit.md",
        "docs/reports/Equivalence-Audit.md#4",
        "docs/reports/prior_evidence_registry.toml",
        "docs/reports/prior-evidence-registry.toml",
        "docs/adr/8_2_0003-prior-evidence.md",
        "docs/adr/8-2-0004-b3.md",
        "tests/equivalence/prior_evidence.py",
        "Tests/Equivalence/test_x.py",
        # CC1-1: ponteiros não normalizados não contornam o prefixo (recusa na forma)
        "./docs/stages/8.2-equivalence-audit/concept.md",
        "docs//stages/8.2-equivalence-audit/concept.md",
        "docs/./reports/equivalence_audit.md",
    ],
)
def test_non_internal_entry_with_forbidden_pointer_rejected(pointer: str) -> None:
    for kind in DossierEntryKind:
        if kind is DossierEntryKind.INTERNAL:
            continue
        status = "open" if kind is DossierEntryKind.FINDING else None
        with pytest.raises(ValueError, match=r"A17|repo-relative"):
            DossierEntry(kind=kind, title="t", summary="s", pointer=pointer, status=status)


@pytest.mark.unit
@pytest.mark.parametrize("anchor", sorted(CITABLE_82_ANCHORS))
def test_citable_82_anchors_allowed(anchor: str) -> None:
    assert len(CITABLE_82_ANCHORS) == _CITABLE_82_ANCHOR_COUNT
    for kind in (DossierEntryKind.DEVIATION, DossierEntryKind.REPRODUCTION):
        entry = DossierEntry(kind=kind, title="t", summary="s", pointer=anchor)
        assert entry.visibility is Visibility.CITABLE
    upper = anchor.upper().replace("_", "-")
    assert (
        DossierEntry(kind=DossierEntryKind.DEVIATION, title="t", summary="s", pointer=upper).pointer
        == upper
    )


@pytest.mark.unit
def test_internal_entry_may_point_anywhere() -> None:
    for pointer in (
        "docs/reports/equivalence_audit.md",
        "tests/equivalence/prior_evidence.py",
        "docs/adr/8_2_0004-x.md",
        "docs/stages/8.2-equivalence-audit/technical.md#e4",
    ):
        entry = DossierEntry(
            kind=DossierEntryKind.INTERNAL, title="t", summary="s", pointer=pointer
        )
        assert entry.visibility is Visibility.INTERNAL


# ------------------------------------------------------------------------------ dossiê


@pytest.mark.unit
def test_dossier_sections_closed() -> None:
    # A12: uma seção por linha da tabela do doc §7 menos a última (13), na ordem do D8.
    assert [sid for sid, _ in CITABLE_SECTIONS] == [
        "claim_pointers",
        "declared_power",
        "identity",
        "preregistration_chain",
        "pre_anchor_computation",
        "blinding_statement",
        "judged_generation",
        "environment",
        "code_commits",
        "seeds",
        "figures",
        "reproduction",
        "deviations",
    ]
    dossier = _dossier()
    assert len(dossier.sections_of(Visibility.CITABLE)) == _CITABLE_SECTION_COUNT
    assert [s.section_id for s in dossier.sections_of(Visibility.INTERNAL)] == ["internal"]
    sections = dossier.sections
    with pytest.raises(ValueError, match="exactly CITABLE_SECTIONS"):
        TraceabilityDossier(sections=sections[1:])
    with pytest.raises(ValueError, match="exactly CITABLE_SECTIONS"):
        TraceabilityDossier(sections=(sections[1], sections[0], *sections[2:]))
    with pytest.raises(ValueError, match="exactly CITABLE_SECTIONS"):
        TraceabilityDossier(sections=sections[:-1])
    with pytest.raises(ValueError, match="exactly CITABLE_SECTIONS"):
        TraceabilityDossier(
            sections=(replace(sections[0], visibility=Visibility.INTERNAL), *sections[1:])
        )


@pytest.mark.unit
def test_dossier_block_validation() -> None:
    with pytest.raises(ValueError, match="pair"):
        DossierBlock(heading="h", rows=(("a",),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="repo-relative"):
        DossierBlock(heading="h", rows=(), pointer="/abs.md")
    assert DossierBlock(heading="h", rows=(("a", ""),)).rows == (("a", ""),)


# --------------------------------------------------------------------- comando/resultado


@pytest.mark.unit
def test_command_and_result_validation() -> None:
    entry = DossierEntry(
        kind=DossierEntryKind.DEVIATION, title="t", summary="s", pointer="docs/x.md"
    )
    command = GenerateReportArtifactsCommand(
        name="aapl_confirmatory",
        revision=3,
        preregistration_ref="aapl_confirmatory-r3-00fd83d9cd39",
        cohort_seeds=(1, 2),
        register=(entry,),
    )
    assert command.cohort_seeds == (1, 2)
    for overrides in (
        {"name": ""},
        {"revision": -1},
        {"revision": True},
        {"preregistration_ref": ""},
        {"cohort_seeds": ()},
        {"cohort_seeds": (1, 1)},
        {"cohort_seeds": [1, 2]},
        {"cohort_seeds": (True,)},
        {"register": ("x",)},
    ):
        with pytest.raises(ValueError):
            replace(command, **overrides)  # type: ignore[arg-type]

    figures = tuple((fid, _SHA) for fid in FIGURE_IDS)
    result = ReportArtifactsResult(
        preregistration_ref="ref", generation_digest=_SHA, figures=figures, register_entries=1
    )
    assert result.figures == figures
    for overrides in (
        {"generation_digest": "x"},
        {"figures": figures[::-1]},
        {"figures": figures[:-1]},
        {"figures": ((figures[0][0], "x"), *figures[1:])},
        {"register_entries": -1},
    ):
        with pytest.raises(ValueError):
            replace(result, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_silver_mismatch_error_has_sorted_keys_only() -> None:
    error = SilverContentMismatchError(["realized|AAPL", "dim_run|c"])
    assert error.keys == ("dim_run|c", "realized|AAPL")
    assert str(error) == (
        "silver content differs from the judged copy at units ['dim_run|c', 'realized|AAPL']"
    )


# ------------------------------------------------------------- validação da escrita


@pytest.mark.unit
def test_check_artifacts_accepts_ten_catalog_ids_with_pdf_bytes_and_matching_records() -> None:
    check_artifacts(_artifacts(), _dossier())
    check_artifacts(list(reversed(_artifacts())), _dossier())


@pytest.mark.unit
def test_check_artifacts_rejects_duplicate_id() -> None:
    figures = _artifacts()
    with pytest.raises(ValueError, match="repeat"):
        check_artifacts([*figures, figures[0]], _dossier())


@pytest.mark.unit
def test_check_artifacts_rejects_missing_or_unknown_id() -> None:
    figures = _artifacts()
    with pytest.raises(ValueError, match="missing"):
        check_artifacts(figures[:-1], _dossier())
    unknown = ("exploratory", b"%PDF", figures[0][2])
    with pytest.raises(ValueError, match="unknown"):
        check_artifacts([*figures[:-1], unknown], _dossier())


@pytest.mark.unit
def test_check_artifacts_rejects_non_pdf_bytes() -> None:
    figures = _artifacts()
    figures[3] = (figures[3][0], b"PNG", figures[3][2])
    with pytest.raises(ValueError, match="not a PDF"):
        check_artifacts(figures, _dossier())


@pytest.mark.unit
def test_check_artifacts_rejects_record_of_other_id() -> None:
    figures = _artifacts()
    figures[0] = (figures[0][0], figures[0][1], figures[1][2])
    with pytest.raises(ValueError, match="record of another"):
        check_artifacts(figures, _dossier())
    with pytest.raises(ValueError, match="TraceabilityDossier"):
        check_artifacts(_artifacts(), "dossier")  # type: ignore[arg-type]


# ------------------------------------------------------------- 2ª barreira do A17


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "ver docs/reports/equivalence_audit.md",
        "ver docs/reports/EQUIVALENCE-AUDIT.md#2",
        "o equivalence_audit lista",
        "o prior_evidence e o Prior-Evidence",
        "andaime em tests/equivalence/",
        "ADR 8.2.0003",
        "ADR 8_2_0004",
        "docs/adr/8-2-0003-x.md",
        "PRIOR_CANDIDATE_LABELS",
        "prior-candidate-labels",
        "a Evidência Anterior",
        "do projeto   anterior",
        "reproduction_audit.md#5-limite",
        "reproduction-audit.md §5",
        "a §5 do `reproduction_audit.md`",
    ],
)
def test_forbidden_patterns_match_each_a17_term(text: str) -> None:
    assert find_forbidden(text), text


@pytest.mark.unit
def test_forbidden_patterns_spare_citable_82_anchors() -> None:
    for anchor in CITABLE_82_ANCHORS:
        assert find_forbidden(f"Fonte: [{anchor}](../../{anchor})") == ()
    assert find_forbidden("docs/stages/8.2_equivalence_audit/technical.md") == ()
    assert find_forbidden("reproduction_audit.md#1-claim … #4-comparação; ADR 8.2.0002") == ()


@pytest.mark.unit
def test_find_forbidden_returns_matches_in_text() -> None:
    text = "ver equivalence_audit.md e a evidência anterior"
    assert find_forbidden(text) == (
        "equivalence_audit.md",
        "equivalence_audit",
        "equivalence_audit",
        "evidência anterior",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "pointer",
    [
        "./docs/x.md",
        "docs//x.md",
        "docs/./x.md",
        "docs/stages/../reports/x.md",
    ],
)
def test_pointer_must_be_normalized(pointer: str) -> None:
    with pytest.raises(ValueError, match="repo-relative"):
        DossierEntry(kind=DossierEntryKind.INTERNAL, title="t", summary="s", pointer=pointer)
    assert DossierEntry(
        kind=DossierEntryKind.INTERNAL, title="t", summary="s", pointer="tests/equivalence/"
    ).pointer.endswith("/")


@pytest.mark.unit
def test_second_barrier_spares_the_82_directory_only_with_the_slash() -> None:
    assert find_forbidden("docs/stages/8.2-equivalence-audit/technical.md") == ()
    assert find_forbidden("a Stage 8.2-equivalence-audit inteira") == ("equivalence-audit",)
