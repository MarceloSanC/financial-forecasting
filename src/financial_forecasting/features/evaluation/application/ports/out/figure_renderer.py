"""Port-out `FigureRenderer` — desenha o dado plotado como PDF determinístico (Stage 8.3).

Port do **consumidor** (concept 8.3 §4; ADR `8_3_0003`): o `GenerateReportArtifacts`
monta cada `FigureSpec` por funções puras e só então pede os bytes. O port não conhece
biblioteca de desenho — recebe o dado plotado e devolve bytes; o adapter só desenha o que
a spec traz, nunca recalcula.

Real: `MatplotlibFigureRenderer` (`features/evaluation/adapters/out/plots/`; matplotlib
confinado ali pelo contrato `evaluation-no-matplotlib-leak`). Fake:
`InMemoryFigureRenderer` (`tests/fakes/features/evaluation/`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureSpec,
)


class FigureRenderer(Protocol):
    """Renderiza uma `FigureSpec` como PDF de uma página."""

    def render(self, figure: FigureSpec) -> bytes:
        """Os bytes do PDF (começam com `%PDF`).

        Determinístico: a mesma `FigureSpec`, no mesmo ambiente, dá os mesmos bytes em
        qualquer chamada e processo (sem data de criação nem estado global — I8).
        """
        ...

    def identity(self) -> Mapping[str, str]:
        """A identidade do renderizador para o registro da figura.

        Ex.: `{"format": "pdf", "matplotlib": "3.11.0", "freetype": "2.6.1"}`. Nada de
        instante, host ou caminho.
        """
        ...
