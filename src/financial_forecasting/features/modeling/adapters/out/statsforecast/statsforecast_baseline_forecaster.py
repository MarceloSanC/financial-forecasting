"""Adapter real do port `BaselineForecaster` — `statsforecast` SÓ no fit do AR(1).

Desde a issue #66 este arquivo contém **apenas** a conversa com a biblioteca. A
política de emissão inteira (dispatch pelas 5 famílias, janela condicionante,
flat-em-h, guards C1/C5, I7 e a ordem validar → estimar → emitir) vive no
serviço de domínio `domain/services/baseline_emission.py`, para onde tanto este
adapter quanto o fake in-memory delegam. Antes disso as duas implementações
carregavam ~114 linhas idênticas, e o contract test parametrizado
`[fake, real]` rodava duas cópias da MESMA regra — incapaz, por construção, de
detectar a divergência que existe para detectar.

O que sobrou aqui é a conversa que o núcleo realmente tem com o mundo externo:
"estime os parâmetros do AR(1)".

`statsforecast` é usado EXCLUSIVAMENTE nessa estimação
(`ARIMA(order=(1, 0, 0), include_mean=True)` — port do `arima` do R), atrás do
**seam injetável** `_fit_ar1(returns) -> (mu, phi, sigma2_eps)`:

- **Atenção μ vs intercepto:** com `include_mean=True`, o coeficiente que o R
  rotula `intercept` É a média incondicional μ (NÃO o intercepto c = μ(1-φ));
  o wrapper o expõe explicitamente como `mu` — o oráculo de recuperação em
  série sintética com μ ≠ 0 material (teste de integração) existe para pegar
  exatamente esse bug de wiring (concept §8).
- **C4 — fit degenerado ergue:** |φ̂| ≥ 1, sigma2_eps ≤ 0 ou coeficiente não-finito
  → `ValueError` no adapter (fail-fast; AR(1) não estacionário em retornos
  diários é dado ruim, não caso a acomodar). O seam torna o ramo testável com
  fit forjado (injeção via construtor ou monkeypatch).
- **C1 e variância zero no train** ficam junto do fit porque são condições de
  ADMISSIBILIDADE da estimação, não da emissão: sem elas, a lib devolveria
  sigma2_eps ~ 1e-38 numa série constante e a emissão fabricaria uma escala
  gaussiana degenerada.

Protocolo de informação (ADR 5.2.0002 — I3/I4/D2/D4) e fronteira de erro são
hoje garantidos pelo serviço de domínio, o que é justamente o que torna a
paridade com o fake (`tests/fakes/features/modeling/in_memory_baseline_forecaster.py`)
uma propriedade estrutural em vez de uma coincidência mantida à mão. Ambos
respondem à MESMA suite de contrato
(`tests/contract/features/modeling/test_baseline_forecaster_contract.py`).
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import numpy as np
from statsforecast.models import ARIMA

from financial_forecasting.features.modeling.domain.services.baseline_emission import (
    emit_baseline_grids,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
        BaselineSpec,
    )

_MIN_AR1_TRAIN = 3
"""Mínimo de observações no train para estimar o AR(1) (C1 — paridade com o fake)."""


def _fit_ar1(returns: Sequence[float]) -> tuple[float, float, float]:
    """Estima (mu, phi, sigma2_eps) do AR(1) via `statsforecast` (ADR 5.2.0001).

    `ARIMA(order=(1, 0, 0), include_mean=True)` é o port do `arima` do R:
    `model_["coef"]["intercept"]` É a média incondicional μ (parametrização
    centrada — NUNCA converter por c/(1-φ)); `model_["coef"]["ar1"]` é φ̂;
    `model_["sigma2"]` é sigma2_eps.

    Args:
        returns: partição train (`returns[: train_end_idx + 1]`), finita.

    Returns:
        Tripla `(mu, phi, sigma2_eps)` como `float` Python (fronteira tipada).
    """
    model = ARIMA(order=(1, 0, 0), include_mean=True)
    model.fit(np.asarray(returns, dtype=np.float64))
    # `model_` é o dict do port do R (sem stubs — Any p/ o mypy); a fronteira do
    # wrapper é convertida explicitamente para `float` Python (technical §1).
    fitted = model.model_
    coef = fitted["coef"]
    return float(coef["intercept"]), float(coef["ar1"]), float(fitted["sigma2"])


class StatsforecastBaselineForecaster:
    """Implementação real do contrato `BaselineForecaster`.

    Casca fina sobre `emit_baseline_grids` (domínio): o adapter contribui
    apenas com o estimador do AR(1). O fit fica atrás do seam `fit_ar1`
    (default: `_fit_ar1`, statsforecast) — injetável no construtor para os
    testes exercitarem C4 com fit forjado sem tocar a lib.
    """

    def __init__(
        self,
        *,
        fit_ar1: Callable[[Sequence[float]], tuple[float, float, float]] | None = None,
    ) -> None:
        """Inicializa o adapter com o seam de estimação do AR(1) (C4 testável)."""
        self._fit_ar1 = _fit_ar1 if fit_ar1 is None else fit_ar1

    def forecast(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        spec: BaselineSpec,
        returns: Sequence[float],
        train_end_idx: int,
        decision_indices: Sequence[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> Mapping[int, GridByHorizon]:
        """Emite a grade crua por decisão x horizonte (ver docstring do port)."""
        return emit_baseline_grids(
            self._fitted_ar1_params,
            spec=spec,
            returns=returns,
            train_end_idx=train_end_idx,
            decision_indices=decision_indices,
            horizons=horizons,
            quantile_levels=quantile_levels,
        )

    # -- estimação (I4: congelada no train; C4: fit degenerado ergue) ----------

    def _fitted_ar1_params(self, train: Sequence[float]) -> tuple[float, float, float]:
        """Fit único por chamada sobre o train congelado, validado contra C4."""
        if len(train) < _MIN_AR1_TRAIN:
            raise ValueError(
                f"ar1 needs at least {_MIN_AR1_TRAIN} train observations; got {len(train)} (C1)"
            )
        # Train de variância zero ergue ANTES do fit (paridade observável exata com
        # o fake — Checkpoint C MAJOR-1): sem este guard, o fit da lib numa série
        # constante devolve sigma2_eps ~ 1e-38 > 0 (passa o C4 `<= 0`) e a emissão
        # fabricaria uma escala gaussiana degenerada — erguer, não fabricar.
        mean = fmean(train)
        variance = sum((r - mean) ** 2 for r in train) / len(train)
        if variance <= 0.0:
            raise ValueError(
                "ar1 train series has zero variance (constant returns) — "
                "cannot estimate AR(1) moments"
            )
        mu, phi, sigma2_eps = self._fit_ar1(train)
        if not (math.isfinite(mu) and math.isfinite(phi) and math.isfinite(sigma2_eps)):
            raise ValueError(
                "ar1 fit produced non-finite parameters "
                f"(mu={mu}, phi={phi}, sigma2_eps={sigma2_eps}) — degenerate fit (C4)"
            )
        if abs(phi) >= 1.0:
            raise ValueError(
                f"ar1 fit produced |phi| >= 1 (phi={phi}) — non-stationary fit on daily "
                "returns is a data bug, not a case to accommodate (C4)"
            )
        if sigma2_eps <= 0.0:
            raise ValueError(
                f"ar1 fit produced sigma2_eps <= 0 (sigma2_eps={sigma2_eps}) — "
                "degenerate fit (C4)"
            )
        return mu, phi, sigma2_eps
