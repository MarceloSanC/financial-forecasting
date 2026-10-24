"""Fake do port `ReportArtifactSink` — guarda a única escrita em memória (8.3).

Valida pela mesma regra do real (`check_artifacts`, dono único em
`dtos/report_artifacts.py` — sem cópia aqui, `check_fake_parity`) antes de guardar.
`writes` conta as chamadas aceitas; `figures` e `dossier` são os da última. `fail_with`
injeta uma falha de escrita (o tudo ou nada do use case): a chamada ergue a exceção e
nada é guardado.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureRecord,
    TraceabilityDossier,
    check_artifacts,
)


class InMemoryReportArtifactSink:
    """Satisfaz `ReportArtifactSink` em memória."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with
        self.writes = 0
        self.figures: tuple[tuple[str, bytes, FigureRecord], ...] = ()
        self.dossier: TraceabilityDossier | None = None

    def write(
        self,
        *,
        figures: Sequence[tuple[str, bytes, FigureRecord]],
        dossier: TraceabilityDossier,
    ) -> None:
        check_artifacts(figures, dossier)
        if self.fail_with is not None:
            raise self.fail_with
        self.writes += 1
        self.figures = tuple(figures)
        self.dossier = dossier

    @property
    def records(self) -> dict[str, FigureRecord]:
        """Os registros da última escrita, por id."""
        return {figure_id: record for figure_id, _, record in self.figures}
