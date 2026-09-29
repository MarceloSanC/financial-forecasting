"""Adapter `StatsmodelsHac` — satisfaz o port `InferenceBackend` via `statsmodels` (ADR 6.2.0003).

Oráculo de biblioteca do DM/HLN e do Holm (ADR `6_2_0003` item 3; concept 6.2 §4
Adapters, §8 Externas). A rota até cada número é a da biblioteca:

- **DM:** d = cand - comp; `OLS(d, 1).fit().get_robustcov_results(cov_type="HAC",
  kernel="uniform" | "bartlett", maxlags=h - 1, use_correction=False)` — a covariância
  HAC da média de d com pesos 1 (retangular, o "acf" do R) ou 1 - k/h (Bartlett) e
  divisor T, sem correção de graus de liberdade; var̂ = `cov_params()[0, 0]`. O
  `statsmodels` **não** ergue com variância negativa (o kernel uniforme não é PSD): o
  adapter checa o sinal ele mesmo — ≤ 0 com h > 1 refaz tudo com h = 1 e marca o
  fallback; ≤ 0 com h = 1 ergue a mensagem do `dm.test`. O fator HLN é aplicado **por
  fora** (o concept manda; quem o confere contra fonte independente é o R, Task 08) e o
  p-valor vem de `scipy.stats.t.cdf(S1*, T - 1)` — o cruzamento da `student_t_cdf` do
  domínio com o scipy acontece na suíte de contrato.
- **Holm:** `multipletests(p, method="holm")` com o método **explícito** (o default do
  `statsmodels` é `"hs"`, Holm-Šidák); ajustados = `[1]`, rejeição = `[0]` com o `alpha`
  pedido (o `statsmodels` compara por divisão; a paridade exata na fronteira só vale no
  conjunto de alphas da suíte — concept I6).

A **entrada** passa primeiro pelos validadores únicos do domínio (`validate_dm_request`,
`validate_p_values`, `validate_alpha`): a biblioteca não impõe o contrato do port
(aceitaria perda negativa, h ≥ T, p fora de [0, 1]). O retorno é o
`DieboldMarianoResult` do domínio e tuplas com `float`/`int`/`bool` **nativos** (o port
promete tipos nativos, não `numpy.float64`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats
from statsmodels.regression.linear_model import OLS
from statsmodels.stats.multitest import multipletests

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMarianoResult,
    DmVarianceEstimator,
    validate_dm_request,
)
from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
    validate_p_values,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    is_constant,
)

_KERNELS = {
    DmVarianceEstimator.RECTANGULAR: "uniform",
    DmVarianceEstimator.BARTLETT: "bartlett",
}


class StatsmodelsHac:
    """Satisfaz `InferenceBackend` com OLS + HAC e `multipletests` do `statsmodels`."""

    def diebold_mariano(
        self,
        *,
        candidate_losses: Sequence[float],
        comparator_losses: Sequence[float],
        horizon: int,
        variance_estimator: DmVarianceEstimator,
    ) -> DieboldMarianoResult:
        validate_dm_request(
            candidate_losses=candidate_losses,
            comparator_losses=comparator_losses,
            horizon=horizon,
            variance_estimator=variance_estimator,
        )
        d = np.asarray(candidate_losses, dtype=float) - np.asarray(comparator_losses, dtype=float)
        n_points = int(d.shape[0])
        horizon_used = horizon
        mean, variance = _hac_mean_and_variance(d, horizon, variance_estimator)
        if variance <= 0.0 and horizon > 1:
            horizon_used = 1
            mean, variance = _hac_mean_and_variance(d, horizon_used, variance_estimator)
        if variance <= 0.0:
            raise ValueError("Variance of DM statistic is zero")
        hln = math.sqrt(
            (n_points + 1 - 2 * horizon_used + horizon_used * (horizon_used - 1) / n_points)
            / n_points
        )
        statistic = hln * mean / math.sqrt(variance)
        return DieboldMarianoResult(
            horizon=horizon,
            horizon_used=horizon_used,
            fallback_applied=horizon_used != horizon,
            variance_estimator=variance_estimator,
            n_points=n_points,
            mean_differential=mean,
            long_run_variance=variance,
            statistic=statistic,
            degrees_of_freedom=n_points - 1,
            p_value=float(stats.t.cdf(statistic, n_points - 1)),
        )

    def holm_adjusted(self, *, p_values: Sequence[float]) -> tuple[float, ...]:
        validate_p_values(p_values)
        adjusted = multipletests(list(p_values), method="holm")[1]
        return tuple(float(value) for value in adjusted)

    def holm_rejected(self, *, p_values: Sequence[float], alpha: float) -> tuple[bool, ...]:
        validate_p_values(p_values)
        validate_alpha(alpha)
        rejected = multipletests(list(p_values), alpha=alpha, method="holm")[0]
        return tuple(bool(value) for value in rejected)


def _hac_mean_and_variance(
    d: np.ndarray, horizon: int, variance_estimator: DmVarianceEstimator
) -> tuple[float, float]:
    """(d̄, var̂(d̄)) pela OLS de d sobre a constante com covariância HAC (maxlags = h - 1).

    d constante tem variância **zero** por definição (o `acf` do R dá 0 exato). A OLS do
    `statsmodels` resolve por pseudo-inversa e deixa resíduos de ~1e-16 (var̂ ~1e-32 > 0);
    o adapter usa o predicado do dono (`_paired_inputs.is_constant`, o mesmo do primitivo
    do domínio) e devolve var̂ = 0, para o chamador aplicar o fallback/erro de C3 como o
    domínio e o R `dm.test`.
    """
    if is_constant(d.tolist()):
        return float(d[0]), 0.0
    fitted = OLS(d, np.ones_like(d)).fit()
    robust = fitted.get_robustcov_results(
        cov_type="HAC",
        kernel=_KERNELS[variance_estimator],
        maxlags=horizon - 1,
        use_correction=False,
    )
    return float(robust.params[0]), float(np.asarray(robust.cov_params())[0, 0])
