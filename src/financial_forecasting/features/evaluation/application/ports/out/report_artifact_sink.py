"""Port-out `ReportArtifactSink` — o destino das figuras, dos registros e do dossiê (Stage 8.3).

Port do **consumidor** (concept 8.3 §4, I9; ADRs `8_3_0002` e `8_3_0004`): o
`GenerateReportArtifacts` só escreve depois de montar tudo, e numa **única** chamada com
todos os artefatos — tudo ou nada. A validação antes de qualquer escrita é a de
`check_artifacts` (dono único, `dtos/report_artifacts.py`), chamada pelo fake e pelo real.

Real: `FilesystemReportSink` (`features/evaluation/adapters/out/reports/`): grava
`figures/<id>.pdf`, `figures/<id>.json` e os dois Markdown do dossiê num staging trocado
no fim; falha no meio restaura a saída anterior. Fake: `InMemoryReportArtifactSink`
(`tests/fakes/features/evaluation/`).

Destino só de figuras (issue #250): um sink pode gravar só as figuras e os registros —
validando a entrada inteira, dossiê inclusive, e com o mesmo tudo ou nada — e deixar o
dossiê com o destino canônico. Real: `PresentationFigureSink` (mesmo pacote; as figuras do
texto do TCC em `text/figuras/`, e as que o texto não usa declaradas, com o motivo, em
`omitted_figures.json`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureRecord,
    TraceabilityDossier,
)


class ReportArtifactSink(Protocol):
    """Escreve as dez figuras com os seus registros e o dossiê, de uma vez."""

    def write(
        self,
        *,
        figures: Sequence[tuple[str, bytes, FigureRecord]],
        dossier: TraceabilityDossier,
    ) -> None:
        """Escreve tudo ou nada (I9).

        `figures` são `(id, bytes do PDF, registro)`, um por figura do catálogo. Entrada
        inválida (`check_artifacts`) ergue `ValueError` antes de qualquer escrita; falha
        no meio deixa a saída anterior intacta. Um destino só de figuras (ver o docstring
        do módulo) não grava o dossiê e pode deixar de fora figuras declaradas omitidas.
        """
        ...
