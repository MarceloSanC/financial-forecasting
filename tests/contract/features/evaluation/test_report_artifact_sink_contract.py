"""Contrato do port `ReportArtifactSink` — fake e real (Stage 8.3, Task 12; A11, A13, I8, I9).

Pernas `[fake, real]`: `InMemoryReportArtifactSink` e `FilesystemReportSink` (em
`tmp_path`). A fixture devolve o sink e um leitor do que a perna escreveu. As duas guardam
as dez figuras, os registros pelos bytes de `document_bytes` e o dossiê, e recusam entrada
inválida antes de escrever. Só no real: o layout de arquivos, o Markdown igual ao
`dossier_markdown.render`, a troca que substitui a saída anterior inteira, a restauração
quando a troca falha no meio, os demais arquivos intocados e bytes iguais em duas escritas.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.reports.filesystem_report_sink import (
    FilesystemReportSink,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CITABLE_SECTIONS,
    FIGURE_CATALOG,
    FIGURE_IDS,
    INTERNAL_SECTION,
    DossierBlock,
    DossierSection,
    FigureRecord,
    SourceKind,
    SourceRef,
    TraceabilityDossier,
    Visibility,
)
from financial_forecasting.features.evaluation.application.ports.out.report_artifact_sink import (
    ReportArtifactSink,
)
from financial_forecasting.features.evaluation.application.use_cases.dossier_markdown import (
    CITABLE_FILE,
    INTERNAL_FILE,
    render,
)
from financial_forecasting.features.evaluation.application.use_cases.report_dossier import (
    REGENERATE_HEADING,
)
from tests.fakes.features.evaluation.in_memory_report_artifact_sink import (
    InMemoryReportArtifactSink,
)

Figures = list[tuple[str, bytes, FigureRecord]]


def _record(figure_id: str) -> FigureRecord:
    return FigureRecord(
        figure_id=figure_id,
        data_digest=hashlib.sha256(figure_id.encode()).hexdigest(),
        generation_digest="96" * 32,
        preregistration_ref="test_plan-r3-0123456789ab",
        revision=3,
        partition=GoldPartition(asset="AAPL", parent_sweep_id="test_cohort-r0"),
        sources=(
            SourceRef(
                kind=SourceKind.GOLD_TABLE, name="gold_metrics_by_run", filter={}, fields=("value",)
            ),
        ),
        silver_units={},
        excluded_degenerate={},
        omissions=FIGURE_CATALOG[figure_id].omissions,
        code={"code.src": "a" * 64, "code.uv_lock": "b" * 64},
        renderer={"format": "pdf"},
    )


def _figures(tag: bytes = b"") -> Figures:
    return [(fid, b"%PDF-1.4 " + fid.encode() + tag, _record(fid)) for fid in FIGURE_IDS]


def _dossier(text: str = "valor") -> TraceabilityDossier:
    sections = []
    for section_id, title in CITABLE_SECTIONS:
        blocks = [DossierBlock(heading="bloco", rows=(("campo", text),), pointer=None)]
        if section_id == "code_commits":
            blocks.append(
                DossierBlock(
                    heading=REGENERATE_HEADING,
                    rows=(
                        ("regra", "regenerar em qualquer commit"),
                        ("comando", "report-artifacts"),
                    ),
                )
            )
        sections.append(
            DossierSection(
                section_id=section_id,
                title=title,
                visibility=Visibility.CITABLE,
                blocks=tuple(blocks),
            )
        )
    sections.append(
        DossierSection(
            section_id=INTERNAL_SECTION[0],
            title=INTERNAL_SECTION[1],
            visibility=Visibility.INTERNAL,
            blocks=(DossierBlock(heading="interno", rows=(("campo", text),)),),
        )
    )
    return TraceabilityDossier(sections=tuple(sections))


@dataclass
class _Leg:
    sink: ReportArtifactSink
    written: Callable[[], dict[str, bytes]]
    """Registro `<id>.json` e os dois Markdown, pelo nome, como a perna os guardou."""


def _fake_leg() -> _Leg:
    sink = InMemoryReportArtifactSink()

    def written() -> dict[str, bytes]:
        if sink.dossier is None:
            return {}
        out = {
            f"{fid}.json": document_bytes(record.as_mapping()) for fid, _, record in sink.figures
        }
        out.update({f"{fid}.pdf": content for fid, content, _ in sink.figures})
        out[CITABLE_FILE] = render(sink.dossier, Visibility.CITABLE).encode()
        out[INTERNAL_FILE] = render(sink.dossier, Visibility.INTERNAL).encode()
        return out

    return _Leg(sink=sink, written=written)


def _real_leg(root: Path) -> _Leg:
    def written() -> dict[str, bytes]:
        out = (
            {p.name: p.read_bytes() for p in (root / "figures").glob("*")}
            if (root / "figures").is_dir()
            else {}
        )
        for name in (CITABLE_FILE, INTERNAL_FILE):
            if (root / name).is_file():
                out[name] = (root / name).read_bytes()
        return out

    return _Leg(sink=FilesystemReportSink(root), written=written)


@pytest.fixture(params=["fake", "real"])
def leg(request: pytest.FixtureRequest, tmp_path: Path) -> _Leg:
    return _fake_leg() if request.param == "fake" else _real_leg(tmp_path)


@pytest.mark.contract
def test_writes_every_figure_record_and_both_dossiers(leg: _Leg) -> None:
    leg.sink.write(figures=_figures(), dossier=_dossier())
    written = leg.written()
    for figure_id in FIGURE_IDS:
        assert written[f"{figure_id}.pdf"].startswith(b"%PDF")
        assert f"{figure_id}.json" in written
    assert written[CITABLE_FILE].startswith(b"# ")
    assert written[INTERNAL_FILE].startswith(b"# Interno")


@pytest.mark.contract
def test_record_bytes_are_document_bytes(leg: _Leg) -> None:
    figures = _figures()
    leg.sink.write(figures=figures, dossier=_dossier())
    for figure_id, _, record in figures:
        assert leg.written()[f"{figure_id}.json"] == document_bytes(record.as_mapping())


@pytest.mark.contract
def test_rejects_duplicate_or_unknown_id_before_writing(leg: _Leg) -> None:
    figures = _figures()
    with pytest.raises(ValueError, match="repeat"):
        leg.sink.write(figures=[*figures, figures[0]], dossier=_dossier())
    with pytest.raises(ValueError, match="missing"):
        leg.sink.write(figures=figures[:-1], dossier=_dossier())
    assert leg.written() == {}


@pytest.mark.contract
def test_rejects_non_pdf_bytes_before_writing(leg: _Leg) -> None:
    figures = _figures()
    figures[2] = (figures[2][0], b"PNG", figures[2][2])
    with pytest.raises(ValueError, match="not a PDF"):
        leg.sink.write(figures=figures, dossier=_dossier())
    assert leg.written() == {}


# ------------------------------------------------------------------------------ só real


def _listing(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.contract
def test_layout_figures_pdf_json_and_two_markdown(tmp_path: Path) -> None:
    FilesystemReportSink(tmp_path).write(figures=_figures(), dossier=_dossier())
    expected = {f"figures/{fid}.{ext}" for fid in FIGURE_IDS for ext in ("pdf", "json")}
    assert set(_listing(tmp_path)) == expected | {CITABLE_FILE, INTERNAL_FILE}


@pytest.mark.contract
def test_markdown_equals_dossier_markdown_render(tmp_path: Path) -> None:
    dossier = _dossier("acentuação — ok")
    FilesystemReportSink(tmp_path).write(figures=_figures(), dossier=dossier)
    assert (tmp_path / CITABLE_FILE).read_bytes() == render(dossier, Visibility.CITABLE).encode()
    assert (tmp_path / INTERNAL_FILE).read_bytes() == render(dossier, Visibility.INTERNAL).encode()
    assert b"\r" not in (tmp_path / CITABLE_FILE).read_bytes()


@pytest.mark.contract
def test_rewrite_replaces_previous_figures_entirely(tmp_path: Path) -> None:
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "old_figure.pdf").write_bytes(b"%PDF old")
    FilesystemReportSink(tmp_path).write(figures=_figures(), dossier=_dossier())
    assert not (tmp_path / "figures" / "old_figure.pdf").exists()
    assert not (tmp_path / ".report-artifacts-previous").exists()
    assert not (tmp_path / ".report-artifacts-staging").exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    "failing_call",
    [2, 5],
    ids=["while-saving-the-previous", "after-a-partial-install"],
)
def test_failure_midway_restores_previous_and_removes_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_call: int
) -> None:
    # CC3-3: as trocas são 3 para guardar a saída anterior e 3 para instalar a nova; a 5ª
    # falha depois de `figures/` já instalado (ramo da lista `installed`).
    sink = FilesystemReportSink(tmp_path)
    sink.write(figures=_figures(), dossier=_dossier())
    before = _listing(tmp_path)
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == failing_call:
            raise OSError("disk full")
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(OSError, match="disk full"):
        sink.write(figures=_figures(b" new"), dossier=_dossier("novo"))
    monkeypatch.setattr(os, "replace", real_replace)
    assert _listing(tmp_path) == before


@pytest.mark.contract
def test_staging_write_failure_leaves_previous_output_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = FilesystemReportSink(tmp_path)
    sink.write(figures=_figures(), dossier=_dossier())
    before = _listing(tmp_path)
    real_write = Path.write_bytes
    calls = {"n": 0}

    def flaky(self: Path, data: bytes) -> int:
        calls["n"] += 1
        if calls["n"] == 5:  # noqa: PLR2004 — no meio das figuras do staging
            raise OSError("disk full")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky)
    with pytest.raises(OSError, match="disk full"):
        sink.write(figures=_figures(b" new"), dossier=_dossier("novo"))
    monkeypatch.setattr(Path, "write_bytes", real_write)
    assert _listing(tmp_path) == before
    assert not (tmp_path / ".report-artifacts-staging").exists()


@pytest.mark.contract
def test_other_files_in_output_untouched(tmp_path: Path) -> None:
    (tmp_path / "reproduction_audit.md").write_bytes(b"# 8.2\n")
    (tmp_path / "dossier_register.toml").write_bytes(b"[[entry]]\n")
    FilesystemReportSink(tmp_path).write(figures=_figures(), dossier=_dossier())
    assert (tmp_path / "reproduction_audit.md").read_bytes() == b"# 8.2\n"
    assert (tmp_path / "dossier_register.toml").read_bytes() == b"[[entry]]\n"


@pytest.mark.contract
def test_two_writes_same_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    FilesystemReportSink(first).write(figures=_figures(), dossier=_dossier())
    FilesystemReportSink(second).write(figures=_figures(), dossier=_dossier())
    assert _listing(first) == _listing(second)
    FilesystemReportSink(first).write(figures=_figures(), dossier=_dossier())
    assert _listing(first) == _listing(second)
    assert all(not value.startswith("/") for value in _listing(first))
