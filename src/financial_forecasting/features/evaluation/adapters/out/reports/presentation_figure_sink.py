"""`PresentationFigureSink` — satisfaz o port `ReportArtifactSink` para o texto do TCC (issue #250).

O destino **só de figuras** do port (a variante que a docstring do port admite): as
figuras no estilo de apresentação em `text/figuras/`. Grava, direto em `<output_dir>/`,
`<id>.pdf` (os bytes do renderizador) e `<id>.json` (o registro, pelos bytes de
`document_bytes`, com o mesmo `generation_digest`, `preregistration_ref` e `data_digest` do
dossiê) de cada figura que o texto usa, e `omitted_figures.json` com o motivo de cada
figura do catálogo que o texto não usa. O dossiê é validado e não é escrito — ele mora em
`docs/reports/`, gravado pelo `FilesystemReportSink`.

Tudo ou nada (I9), como o `FilesystemReportSink`: valida antes de tocar o disco
(`check_artifacts`, dono único, sobre a entrada inteira); escreve num staging
`.presentation-staging/` (removido antes, se sobrou); troca no fim — os nomes geridos que
existem vão para `.presentation-previous/`, os do staging entram no lugar por `os.replace`;
sucesso remove o anterior, falha em qualquer passo restaura o anterior e remove o staging.
Os nomes geridos são `<id>.pdf`/`<id>.json` de TODO o catálogo e o `omitted_figures.json`
— o PDF e o JSON de figura omitida que sobrou de uma geração anterior saem; os demais
arquivos do diretório nunca são tocados. Nenhum caminho absoluto no conteúdo.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_IDS,
    FigureRecord,
    TraceabilityDossier,
    check_artifacts,
)

OMITTED_FILE: Final = "omitted_figures.json"
STAGING_DIR: Final = ".presentation-staging"
PREVIOUS_DIR: Final = ".presentation-previous"
_MANAGED: Final = (
    *(f"{figure_id}.{ext}" for figure_id in FIGURE_IDS for ext in ("pdf", "json")),
    OMITTED_FILE,
)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


class PresentationFigureSink:
    """Satisfaz `ReportArtifactSink` gravando só as figuras usadas pelo texto, de uma vez."""

    def __init__(self, output_dir: Path, omissions: Mapping[str, str]) -> None:
        """`omissions`: figura do catálogo → motivo de o texto não a usar.

        Raises:
            ValueError: omissão fora do catálogo ou com motivo vazio.
        """
        unknown = sorted(set(omissions) - set(FIGURE_IDS))
        if unknown:
            raise ValueError(f"omitted figures not in FIGURE_CATALOG: {unknown}")
        if any(not reason.strip() for reason in omissions.values()):
            raise ValueError("every omitted figure needs a reason")
        self._output = output_dir
        self._omissions = dict(omissions)

    def write(
        self,
        *,
        figures: Sequence[tuple[str, bytes, FigureRecord]],
        dossier: TraceabilityDossier,
    ) -> None:
        """Valida tudo, grava no staging e troca de uma vez (I9).

        Raises:
            ValueError: entrada inválida (`check_artifacts`), antes de qualquer escrita.
            OSError: falha de escrita ou de troca — a saída anterior é restaurada.
        """
        check_artifacts(figures, dossier)
        record = figures[0][2]
        omitted = {
            "generation_digest": record.generation_digest,
            "preregistration_ref": record.preregistration_ref,
            "omitted": self._omissions,
        }
        self._output.mkdir(parents=True, exist_ok=True)
        staging = self._output / STAGING_DIR
        try:
            _remove(staging)
            staging.mkdir()
            for figure_id, content, figure_record in figures:
                if figure_id in self._omissions:
                    continue
                (staging / f"{figure_id}.pdf").write_bytes(content)
                (staging / f"{figure_id}.json").write_bytes(
                    document_bytes(figure_record.as_mapping())
                )
            (staging / OMITTED_FILE).write_bytes(document_bytes(omitted))
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
                if (staging / name).exists():
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
