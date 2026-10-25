"""`PresentationFigureSink` — as figuras do texto do TCC em arquivos (issue #250).

Grava, direto no diretório, `<id>.pdf` e `<id>.json` (bytes de `document_bytes`) das
figuras usadas e `omitted_figures.json` com o motivo das omitidas; não grava o dossiê;
valida antes de escrever; tira o que sobrou de figura omitida; não toca outros arquivos;
bytes iguais em duas escritas; falha no meio (staging ou troca) deixa a saída anterior
intacta (I9).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.reports.presentation_figure_sink import (  # noqa: E501
    OMITTED_FILE,
    STAGING_DIR,
    PresentationFigureSink,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_IDS,
)
from tests.contract.features.evaluation.test_report_artifact_sink_contract import (
    _dossier,
    _figures,
)

pytestmark = pytest.mark.integration

_OMITTED = {"dm_candidate_vs_comparators": "uma linha só"}


def _listing(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_writes_used_figures_records_and_omissions(tmp_path: Path) -> None:
    figures = _figures()
    PresentationFigureSink(tmp_path, _OMITTED).write(figures=figures, dossier=_dossier())
    used = [fid for fid in FIGURE_IDS if fid not in _OMITTED]
    expected = {f"{fid}.{ext}" for fid in used for ext in ("pdf", "json")} | {OMITTED_FILE}
    assert set(_listing(tmp_path)) == expected
    for figure_id, content, record in figures:
        if figure_id in _OMITTED:
            continue
        assert (tmp_path / f"{figure_id}.pdf").read_bytes() == content
        assert (tmp_path / f"{figure_id}.json").read_bytes() == document_bytes(record.as_mapping())
    omitted = json.loads((tmp_path / OMITTED_FILE).read_text(encoding="utf-8"))
    record = figures[0][2]
    assert omitted == {
        "generation_digest": record.generation_digest,
        "preregistration_ref": record.preregistration_ref,
        "omitted": _OMITTED,
    }


def test_rejects_invalid_input_before_writing(tmp_path: Path) -> None:
    figures = _figures()
    figures[2] = (figures[2][0], b"PNG", figures[2][2])
    with pytest.raises(ValueError, match="not a PDF"):
        PresentationFigureSink(tmp_path, _OMITTED).write(figures=figures, dossier=_dossier())
    with pytest.raises(ValueError, match="missing"):
        PresentationFigureSink(tmp_path, _OMITTED).write(
            figures=_figures()[:-1], dossier=_dossier()
        )
    assert _listing(tmp_path) == {}


def test_removes_stale_omitted_figure_and_keeps_other_files(tmp_path: Path) -> None:
    (tmp_path / "dm_candidate_vs_comparators.pdf").write_bytes(b"%PDF old")
    (tmp_path / "dm_candidate_vs_comparators.json").write_bytes(b"{}")
    (tmp_path / "diagrama.pdf").write_bytes(b"%PDF other")
    PresentationFigureSink(tmp_path, _OMITTED).write(figures=_figures(), dossier=_dossier())
    listing = _listing(tmp_path)
    assert "dm_candidate_vs_comparators.pdf" not in listing
    assert "dm_candidate_vs_comparators.json" not in listing
    assert (tmp_path / "diagrama.pdf").read_bytes() == b"%PDF other"
    assert not [name for name in listing if name.endswith(".tmp")]


def test_same_bytes_on_two_writes_and_replaces_previous(tmp_path: Path) -> None:
    sink = PresentationFigureSink(tmp_path, _OMITTED)
    sink.write(figures=_figures(b"old"), dossier=_dossier())
    sink.write(figures=_figures(), dossier=_dossier())
    first = _listing(tmp_path)
    sink.write(figures=_figures(), dossier=_dossier())
    assert _listing(tmp_path) == first
    assert (tmp_path / "reliability_diagram.pdf").read_bytes() == _figures()[0][1]


def test_creates_the_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "text" / "figuras"
    PresentationFigureSink(output, _OMITTED).write(figures=_figures(), dossier=_dossier())
    assert (output / OMITTED_FILE).is_file()


@pytest.mark.parametrize(
    ("omissions", "message"),
    [({"not_a_figure": "x"}, "not in FIGURE_CATALOG"), ({"vsn_weights": " "}, "reason")],
)
def test_rejects_unknown_omission_or_empty_reason(
    tmp_path: Path, omissions: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PresentationFigureSink(tmp_path, omissions)


@pytest.mark.parametrize("failing_call", [5, 25])
def test_swap_failure_restores_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_call: int
) -> None:
    # 19 trocas guardam a saída anterior (9 figuras x 2 + omissões) e 19 instalam a nova:
    # a 5ª falha guardando, a 25ª falha instalando (ramo da lista `installed`)
    (tmp_path / "diagrama.pdf").write_bytes(b"%PDF other")
    sink = PresentationFigureSink(tmp_path, _OMITTED)
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
        sink.write(figures=_figures(b" new"), dossier=_dossier())
    monkeypatch.setattr(os, "replace", real_replace)
    assert _listing(tmp_path) == before


def test_staging_write_failure_leaves_previous_output_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = PresentationFigureSink(tmp_path, _OMITTED)
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
        sink.write(figures=_figures(b" new"), dossier=_dossier())
    monkeypatch.setattr(Path, "write_bytes", real_write)
    assert _listing(tmp_path) == before
    assert not (tmp_path / STAGING_DIR).exists()
