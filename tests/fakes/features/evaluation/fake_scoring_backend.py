"""Fake do port `ScoringBackend` — delega às funções de série do domínio (ADR 6.1.0001).

Sem média própria: cada método chama a MESMA função de série que os serviços de
domínio usam na agregação (`mean_pinball`, `mean_crps_quantile`,
`mean_interval_score`), e a validação C7 vem junto (o validador único que elas
chamam). Assim o oráculo de biblioteca, comparado com o fake na suíte de contrato,
cobre o código de registro — e o `check_fake_parity.py` não acha bloco copiado entre
fake e adapter, porque o fake não tem lógica.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.services.crps_score import (
    mean_crps_quantile,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    mean_interval_score,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    mean_pinball,
)


class FakeScoringBackend:
    """Satisfaz `ScoringBackend` delegando às funções de série do domínio."""

    def mean_pinball(
        self, *, realized: Sequence[float], quantiles: Sequence[float], level: float
    ) -> float:
        return mean_pinball(realized=realized, quantiles=quantiles, level=level)

    def mean_crps_quantile(
        self,
        *,
        realized: Sequence[float],
        quantile_grid: Sequence[Sequence[float]],
        levels: Sequence[float],
    ) -> float:
        return mean_crps_quantile(realized=realized, quantile_grid=quantile_grid, levels=levels)

    def mean_interval_score(
        self,
        *,
        realized: Sequence[float],
        lower: Sequence[float],
        upper: Sequence[float],
        miscoverage: float,
    ) -> float:
        return mean_interval_score(
            realized=realized, lower=lower, upper=upper, miscoverage=miscoverage
        )
