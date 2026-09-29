"""Fake do port `InferenceBackend` — só delega aos primitivos do domínio (ADR 6.2.0003).

Sem fórmula própria: cada método chama o MESMO primitivo que os serviços de domínio usam
(`diebold_mariano`, `holm_adjust`, `holm_reject`), e a validação C3/C4 vem junto (os
validadores únicos que eles chamam). Assim o oráculo de biblioteca, comparado com o fake
na suíte de contrato, cobre o código de registro — e o `check_fake_parity.py` não acha
bloco copiado entre fake e adapter, porque o fake não tem lógica.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMarianoResult,
    DmVarianceEstimator,
    diebold_mariano,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    holm_adjust,
    holm_reject,
)


class FakeInferenceBackend:
    """Satisfaz `InferenceBackend` delegando aos primitivos do domínio."""

    def diebold_mariano(
        self,
        *,
        candidate_losses: Sequence[float],
        comparator_losses: Sequence[float],
        horizon: int,
        variance_estimator: DmVarianceEstimator,
    ) -> DieboldMarianoResult:
        return diebold_mariano(
            candidate_losses=candidate_losses,
            comparator_losses=comparator_losses,
            horizon=horizon,
            variance_estimator=variance_estimator,
        )

    def holm_adjusted(self, *, p_values: Sequence[float]) -> tuple[float, ...]:
        return holm_adjust(p_values)

    def holm_rejected(self, *, p_values: Sequence[float], alpha: float) -> tuple[bool, ...]:
        return holm_reject(p_values, alpha=alpha)
