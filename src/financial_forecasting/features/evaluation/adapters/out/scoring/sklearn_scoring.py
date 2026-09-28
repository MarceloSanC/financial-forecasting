"""Adapter `SklearnScoring` — satisfaz o port `ScoringBackend` via `sklearn` (ADR 6.1.0001).

Oráculo de biblioteca das três médias de scoring (ADR `6_1_0001` item 3). O sklearn
só tem a perda pinball nativa (`sklearn.metrics.mean_pinball_loss`, cujo `alpha` é o
**nível** τ); CRPS_Q e IS saem dela pelas identidades do doc de domínio:

- **CRPS_Q (doc §3.2):** média de CRPS_Q = 2 x média sobre k das pinball médias por
  nível — `2 * mean_k mean_pinball_loss(y, q_k, alpha=tau_k)`;
- **IS (doc §3.3; Bracher et al. 2021, App. A, Eq. (5)):**
  `IS_a = (2/a) * [rho_{a/2}(y - l) + rho_{1-a/2}(y - u)]`, logo a média é
  `(2/a) * [mean_pinball_loss(y, l, alpha=a/2) + mean_pinball_loss(y, u, alpha=1-a/2)]`.

Nenhuma fórmula nem média é copiada do domínio: a rota até o número é a da
biblioteca, e é isso que dá valor à comparação na suíte de contrato. A **entrada**,
porém, passa primeiro pelo validador único do domínio (C7): o sklearn não impõe o
contrato do port (aceita `alpha` em {0, 1}, não conhece `lower > upper`). O retorno
é convertido para `float` nativo (o port promete `float`, não `numpy.float64`).
"""

from __future__ import annotations

from collections.abc import Sequence

from sklearn.metrics import mean_pinball_loss

from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_crps_inputs,
    validate_interval_inputs,
    validate_pinball_inputs,
)


class SklearnScoring:
    """Satisfaz `ScoringBackend` com `sklearn.metrics.mean_pinball_loss` + identidades."""

    def mean_pinball(
        self, *, realized: Sequence[float], quantiles: Sequence[float], level: float
    ) -> float:
        validate_pinball_inputs(realized, quantiles, level)
        return float(mean_pinball_loss(list(realized), list(quantiles), alpha=level))

    def mean_crps_quantile(
        self,
        *,
        realized: Sequence[float],
        quantile_grid: Sequence[Sequence[float]],
        levels: Sequence[float],
    ) -> float:
        validate_crps_inputs(realized, quantile_grid, levels)
        observed = list(realized)
        per_level = [
            float(mean_pinball_loss(observed, [row[k] for row in quantile_grid], alpha=level))
            for k, level in enumerate(levels)
        ]
        return 2.0 * sum(per_level) / len(per_level)

    def mean_interval_score(
        self,
        *,
        realized: Sequence[float],
        lower: Sequence[float],
        upper: Sequence[float],
        miscoverage: float,
    ) -> float:
        validate_interval_inputs(realized, lower, upper, miscoverage)
        observed = list(realized)
        lower_term = mean_pinball_loss(observed, list(lower), alpha=miscoverage / 2.0)
        upper_term = mean_pinball_loss(observed, list(upper), alpha=1.0 - miscoverage / 2.0)
        return float((2.0 / miscoverage) * (lower_term + upper_term))
