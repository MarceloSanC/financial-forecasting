"""`FilesystemReportSink` — satisfaz o port `ReportArtifactSink` em arquivos (Stage 8.3).

Grava em `<output_dir>/` (concept 8.3 §4, I8, I9; technical 8.3 §1 "Sink"):

- `figures/<id>.pdf` (os bytes do renderizador) e `figures/<id>.json` (o registro, pelos
  bytes de `document_bytes` — `sort_keys`, `indent=2`, LF final);
- `final_traceability_dossier.md` e `final_traceability_dossier_internal.md`, pelo
  `dossier_markdown.render` (dono único do Markdown).

Tudo ou nada: valida antes de tocar o disco (`check_artifacts`, dono único); escreve num
staging `.report-artifacts-staging/` (removido antes, se sobrou); troca no fim — o atual
vai para `.report-artifacts-previous/`, o staging entra no lugar por `os.replace`; sucesso
remove o anterior, falha em qualquer passo restaura o anterior e remove o staging (saída
anterior intacta). Só toca `figures/` e os dois `.md`; os demais arquivos do diretório
(relatórios da 8.2, registro curado) nunca. Nenhum caminho absoluto no conteúdo.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureRecord,
    TraceabilityDossier,
    Visibility,
    check_artifacts,
)
from financial_forecasting.features.evaluation.application.use_cases.dossier_markdown import (
    CITABLE_FILE,
    INTERNAL_FILE,
    render,
)

FIGURES_DIR: Final = "figures"
STAGING_DIR: Final = ".report-artifacts-staging"
PREVIOUS_DIR: Final = ".report-artifacts-previous"
_MARKDOWN: Final = ((CITABLE_FILE, Visibility.CITABLE), (INTERNAL_FILE, Visibility.INTERNAL))
_MANAGED: Final = (FIGURES_DIR, CITABLE_FILE, INTERNAL_FILE)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


class FilesystemReportSink:
    """Satisfaz `ReportArtifactSink` gravando em `output_dir` com troca no fim."""

    def __init__(self, output_dir: Path) -> None:
        self._output = output_dir

    def write(
        self,
        *,
        figures: Sequence[tuple[str, bytes, FigureRecord]],
        dossier: TraceabilityDossier,
    ) -> None:
        """Valida, grava no staging e troca de uma vez (I9).

        Raises:
            ValueError: entrada inválida (`check_artifacts`), antes de qualquer escrita.
            OSError: falha de escrita ou de troca — a saída anterior é restaurada.
        """
        check_artifacts(figures, dossier)
        markdown = {name: render(dossier, visibility) for name, visibility in _MARKDOWN}
        staging = self._output / STAGING_DIR
        try:
            _remove(staging)
            (staging / FIGURES_DIR).mkdir(parents=True)
            for figure_id, content, record in figures:
                (staging / FIGURES_DIR / f"{figure_id}.pdf").write_bytes(content)
                (staging / FIGURES_DIR / f"{figure_id}.json").write_bytes(
                    document_bytes(record.as_mapping())
                )
            for name, text in markdown.items():
                (staging / name).write_bytes(text.encode("utf-8"))
            self._swap(staging)
        finally:
            _remove(staging)

    def _swap(self, staging: Path) -> None:
        previous = self._output / PREVIOUS_DIR
        _remove(previous)
        previous.mkdir()
        saved: list[str] = []
        installed: list[str] = []
        try:
            for name in _MANAGED:
                if (self._output / name).exists():
                    os.replace(self._output / name, previous / name)
                    saved.append(name)
            for name in _MANAGED:
                os.replace(staging / name, self._output / name)
                installed.append(name)
        except BaseException:
            for name in installed:
                _remove(self._output / name)
            for name in saved:
                _remove(self._output / name)
                os.replace(previous / name, self._output / name)
            _remove(previous)
            raise
        _remove(previous)
