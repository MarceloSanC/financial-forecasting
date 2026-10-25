"""`PresentationFigureSink` — satisfaz o port `ReportArtifactSink` para o texto do TCC (issue #250).

O destino das figuras no estilo de apresentação (`text/figuras/`): grava, direto em
`<output_dir>/`, `<id>.pdf` (os bytes do renderizador) e `<id>.json` (o registro, pelos
bytes de `document_bytes`, com o mesmo `generation_digest`, `preregistration_ref` e
`data_digest` do dossiê) de cada figura que o texto usa, e `omitted_figures.json` com o
motivo de cada figura omitida. O dossiê não é escrito aqui — ele mora em `docs/reports/`,
gravado pelo `FilesystemReportSink`.

Valida antes de tocar o disco (`check_artifacts`, dono único, sobre a entrada inteira) e
grava cada arquivo por um temporário trocado por `os.replace`; só toca os seus próprios
nomes (`<id>.pdf`/`<id>.json` do catálogo e o `omitted_figures.json`) — o PDF e o JSON de
figura omitida que sobrou de uma geração anterior saem; os demais arquivos do diretório
nunca. Nenhum caminho absoluto no conteúdo.
"""

from __future__ import annotations

import os
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


def _replace(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


class PresentationFigureSink:
    """Satisfaz `ReportArtifactSink` gravando só as figuras usadas pelo texto."""

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
        """Valida tudo e grava as figuras usadas, os registros e as omissões.

        Raises:
            ValueError: entrada inválida (`check_artifacts`), antes de qualquer escrita.
        """
        check_artifacts(figures, dossier)
        record = figures[0][2]
        omitted = {
            "generation_digest": record.generation_digest,
            "preregistration_ref": record.preregistration_ref,
            "omitted": self._omissions,
        }
        self._output.mkdir(parents=True, exist_ok=True)
        for figure_id, content, figure_record in figures:
            pdf = self._output / f"{figure_id}.pdf"
            json_path = self._output / f"{figure_id}.json"
            if figure_id in self._omissions:
                pdf.unlink(missing_ok=True)
                json_path.unlink(missing_ok=True)
                continue
            _replace(pdf, content)
            _replace(json_path, document_bytes(figure_record.as_mapping()))
        _replace(self._output / OMITTED_FILE, document_bytes(omitted))
