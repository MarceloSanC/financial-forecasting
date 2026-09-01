"""Fake in-memory do port `BaselineForecaster` — NÃO um mock.

Desde a issue #66 a docstring e a implementação finalmente coincidem: fake e
adapter real divergem **apenas na estimação** do AR(1) porque só isso mora
aqui. Toda a política de emissão (as 5 famílias, a janela condicionante, o
flat-em-h, os guards C1/C5, o I7 e a ordem validar → estimar → emitir) é o
serviço de domínio `baseline_emission`, para onde as duas pernas delegam.
Antes, ~114 linhas eram idênticas entre este arquivo e o adapter, e o contract
test parametrizado `[fake, real]` rodava duas cópias da mesma regra.

O *shortcut* legítimo deste dublê (na acepção de Meszaros) é singular e
localizado: `_ar1_train_moments` estima (mu-hat, phi-hat, sigma2_eps-hat) com
momentos stdlib do train congelado, no lugar do fit `statsforecast` do adapter.
Ambos respondem à MESMA suite de contrato
(`tests/contract/features/modeling/test_baseline_forecaster_contract.py`).
"""

from __future__ import annotations

from statistics import fmean
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.domain.services.baseline_emission import (
    emit_baseline_grids,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
        BaselineSpec,
    )

_MIN_AR1_TRAIN = 3
"""Mínimo de observações no train para estimar momentos do AR(1) (C1)."""


class FakeBaselineForecaster:
    """Implementação in-memory determinística do contrato `BaselineForecaster`."""

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
            _ar1_train_moments,
            spec=spec,
            returns=returns,
            train_end_idx=train_end_idx,
            decision_indices=decision_indices,
            horizons=horizons,
            quantile_levels=quantile_levels,
        )


def _ar1_train_moments(train: Sequence[float]) -> tuple[float, float, float]:
    """Momentos do train para o AR(1): (mu-hat, phi-hat, sigma2_eps-hat) — estimação stdlib (I4/D2).

    phi-hat = autocorrelação lag-1 amostral; sigma2_eps-hat = (1-phi-hat²)·var. Train trivialmente
    insuficiente (< 3 pontos) ou de variância zero ergue `ValueError` (C1 e a
    postura "erguer, não fabricar" — um AR(1) sobre série constante é
    degenerado, não caso a acomodar).
    """
    n = len(train)
    if n < _MIN_AR1_TRAIN:
        raise ValueError(f"ar1 needs at least {_MIN_AR1_TRAIN} train observations; got {n} (C1)")
    mu = fmean(train)
    variance = sum((r - mu) ** 2 for r in train) / n
    if variance <= 0.0:
        raise ValueError(
            "ar1 train series has zero variance (constant returns) — "
            "cannot estimate AR(1) moments"
        )
    autocov1 = sum((train[t] - mu) * (train[t - 1] - mu) for t in range(1, n)) / n
    phi = autocov1 / variance
    sigma2_eps = (1.0 - phi**2) * variance
    # |phi-hat| < 1 e sigma2_eps-hat > 0 são re-validados por `ar1_step_forecast` (superfície C4).
    return mu, phi, sigma2_eps
