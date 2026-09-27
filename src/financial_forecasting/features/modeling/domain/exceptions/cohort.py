"""Exceções de domínio do grid de treino e do cohort confirmatório (Stage 5.5).

Erros de REGRA do domínio — o dado ou a geometria violam uma pré-condição que o
treino exige —, não falha de backend (`backend.py`) nem erro de orquestração
(os erros de aplicação do cohort vivem no use case `RunConfirmatoryCohort`).

- **`InteriorMissingValuesError`** — valor ausente (None/NaN/inf) DEPOIS do
  prefixo de aquecimento: o grid não corta buracos no meio da série nem os
  preenche em silêncio (ADR 5.5.0004). Carrega a contagem por coluna para a
  decisão ser tomada com a medição.
- **`NoUsableRowsError`** — nenhuma linha tem todas as colunas finitas.
- **`GeometryDoesNotFitError`** — a geometria do cohort não cabe no grid útil
  (o fold 0 ficaria sem treino).
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.shared.domain.exceptions.base import DomainError


class InteriorMissingValuesError(DomainError):
    """Valores ausentes depois do prefixo de aquecimento; contagem por coluna."""

    def __init__(self, counts: Mapping[str, int], *, first_usable: int) -> None:
        self.counts = dict(counts)
        self.first_usable = first_usable
        detail = ", ".join(f"{name}={count}" for name, count in sorted(self.counts.items()))
        super().__init__(
            f"missing values after the warm-up prefix (first usable row {first_usable}): "
            f"{detail} — interior gaps are not trimmed nor imputed (ADR 5.5.0004)"
        )


class NoUsableRowsError(DomainError):
    """Nenhuma linha tem todas as colunas pedidas finitas."""


class GeometryDoesNotFitError(DomainError):
    """A geometria do cohort não cabe no grid útil de treino."""
