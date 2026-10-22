"""Fake in-memory do port `ServingGoldReader` do `inference` (Stage 7.4).

Devolve o `ServingGold` carregado para a partição (`asset`, `cohort_id`). Partição não
carregada é partição sem geração publicada: o fake devolve `ServingGold.unpublished` com
o motivo e os rótulos que o real (`ReadServingGold`) usa, porque o invariante do port é
que gold ausente é estado, não erro (auditoria de testes TA-5; a forma é provada contra o
real pelo cenário "outro cohort" da suíte de contrato). `error` simula a geração que não
se sustenta (o real ergue `ApplicationError`). `calls` registra cada leitura, para os
testes afirmarem a partição pedida.
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.inference.application.dtos.serving_gold import (
    ServingGold,
)


class InMemoryServingGoldReader:
    """Satisfaz `ServingGoldReader` com um mapa partição → `ServingGold`."""

    def __init__(
        self,
        golds: Mapping[tuple[str, str], ServingGold],
        *,
        error: Exception | None = None,
    ) -> None:
        self._golds = dict(golds)
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def read(self, *, asset: str, cohort_id: str) -> ServingGold:
        self.calls.append((asset, cohort_id))
        if self._error is not None:
            raise self._error
        gold = self._golds.get((asset, cohort_id))
        if gold is None:
            return ServingGold.unpublished(
                reason=f"gold não publicado para o cohort {cohort_id}",
                conformal_label=EMPIRICAL_COVERAGE_LABEL,
                h3_label=H3_LABEL,
                vsn_label=VSN_LABEL,
            )
        return gold
