"""Fake do port `FigureRenderer` — "PDF" em memória feito da serialização da spec (8.3).

`render` devolve `b"%PDF-fake\\n" + spec.canonical_bytes()`: começa com a assinatura de
PDF que o `check_artifacts` exige, é determinístico e muda com qualquer valor do dado
plotado. `calls` conta as chamadas (os testes do use case afirmam 0 nas recusas — nada é
renderizado se a montagem falha) e `rendered` guarda os ids na ordem.
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureSpec,
)

FAKE_PDF_HEADER = b"%PDF-fake\n"


class InMemoryFigureRenderer:
    """Satisfaz `FigureRenderer` em memória."""

    def __init__(self) -> None:
        self.calls = 0
        self.rendered: list[str] = []

    def render(self, figure: FigureSpec) -> bytes:
        self.calls += 1
        self.rendered.append(figure.figure_id)
        return FAKE_PDF_HEADER + figure.canonical_bytes()

    def identity(self) -> Mapping[str, str]:
        return {"format": "pdf", "renderer": "in-memory"}
