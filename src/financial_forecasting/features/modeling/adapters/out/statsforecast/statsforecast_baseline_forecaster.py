"""Adapter real do port `BaselineForecaster` — `statsforecast` SÓ no fit do AR(1).

Implementa o contrato semântico do port (concept 5.2 §4/§5/§6) com **dispatch
exaustivo** pelas 5 famílias canônicas, delegando TODA a emissão aos serviços de
domínio puros (`quantile_grid_emission`/`baseline_statistics` — ADR 5.2.0001):
a fórmula pré-registrada é o contrato; a lib é meio, nunca autoridade.

`statsforecast` é usado EXCLUSIVAMENTE na estimação dos parâmetros do AR(1)
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

Protocolo de informação (ADR 5.2.0002 — I3/I4/D2/D4), espelhando o fake de
referência (`tests/fakes/features/modeling/in_memory_baseline_forecaster.py`):
estimação congelada em `returns[: train_end_idx + 1]`; estado condicionante
(r_t, recursão EWMA, janela rolante) causal até cada decisão. Fronteira de
erro idêntica: C1 (train/janela insuficiente), C5 (não-finito na janela
condicionante nunca emite) e variância condicionante zero do `ewma_vol` erguem
`ValueError`. Ambos respondem à MESMA suite de contrato
(`tests/contract/features/modeling/test_baseline_forecaster_contract.py`).
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import numpy as np
from statsforecast.models import ARIMA

from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ar1_step_forecast,
    ewma_variance_path,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    degenerate_grid,
    gaussian_grid,
    sample_quantiles_type7,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BASELINE_FAMILIES,
    BaselineSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
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
    """Implementação real do contrato `BaselineForecaster` (dispatch exaustivo).

    O fit do AR(1) fica atrás do seam `fit_ar1` (default: `_fit_ar1`,
    statsforecast) — injetável no construtor para os testes exercitarem C4 com
    fit forjado sem tocar a lib.
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
        series = tuple(float(r) for r in returns)
        self._validate_structure(series, train_end_idx, decision_indices, horizons)

        ar1_params = (
            self._fitted_ar1_params(series[: train_end_idx + 1])
            if spec.family == "ar1"
            else None
        )

        result: dict[int, GridByHorizon] = {}
        for decision_idx in decision_indices:
            result[decision_idx] = self._emit_decision(
                spec=spec,
                returns=series,
                train_end_idx=train_end_idx,
                decision_idx=decision_idx,
                horizons=horizons,
                quantile_levels=quantile_levels,
                ar1_params=ar1_params,
            )
        return result

    # -- estimação (I4: congelada no train; C4: fit degenerado ergue) ----------

    def _fitted_ar1_params(self, train: tuple[float, ...]) -> tuple[float, float, float]:
        """Fit único por chamada sobre o train congelado, validado contra C4."""
        if len(train) < _MIN_AR1_TRAIN:
            raise ValueError(
                f"ar1 needs at least {_MIN_AR1_TRAIN} train observations; got {len(train)} (C1)"
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

    # -- validação estrutural + C5 (entrada) — paridade com o fake -------------

    @staticmethod
    def _validate_structure(
        returns: tuple[float, ...],
        train_end_idx: int,
        decision_indices: Sequence[int],
        horizons: Sequence[int],
    ) -> None:
        """Valida índices/horizontes e a finitude da janela condicionante (C5)."""
        if not returns:
            raise ValueError("returns must be non-empty")
        if not 0 <= train_end_idx < len(returns):
            raise ValueError(
                f"train_end_idx must be in [0, {len(returns) - 1}]; got {train_end_idx}"
            )
        if not decision_indices:
            raise ValueError("decision_indices must be non-empty")
        previous: int | None = None
        for idx in decision_indices:
            if not 0 <= idx < len(returns):
                raise ValueError(f"decision index {idx} out of range [0, {len(returns) - 1}]")
            if idx <= train_end_idx:
                raise ValueError(
                    f"decision index {idx} must be after train_end_idx={train_end_idx}"
                )
            if previous is not None and idx <= previous:
                raise ValueError("decision_indices must be strictly increasing")
            previous = idx
        if not horizons or any(h < 1 for h in horizons):
            raise ValueError(f"horizons must be non-empty and >= 1; got {tuple(horizons)}")
        # C5 (entrada): a janela condicionante mais larga da chamada é
        # returns[: max(decisions)+1]; não-finito ali é bug de dado, nunca emite.
        widest = max(decision_indices)
        if any(not math.isfinite(r) for r in returns[: widest + 1]):
            raise ValueError(
                "non-finite value in the conditioning window "
                f"returns[: {widest + 1}] — a deterministic baseline never emits (C5)"
            )

    # -- emissão por decisão (TODA por fórmula de domínio — ADR 5.2.0001) ------

    @staticmethod
    def _emit_decision(  # noqa: PLR0913 — parâmetros coesos de uma decisão
        *,
        spec: BaselineSpec,
        returns: tuple[float, ...],
        train_end_idx: int,
        decision_idx: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        ar1_params: tuple[float, float, float] | None,
    ) -> GridByHorizon:
        """Despacha a família e monta `horizon -> grade crua` para uma decisão."""
        train = returns[: train_end_idx + 1]

        if spec.family == "zero_return":
            grid = degenerate_grid(value=0.0, levels=quantile_levels)
            return {h: grid for h in horizons}

        if spec.family == "historical_mean":
            grid = degenerate_grid(value=fmean(train), levels=quantile_levels)
            return {h: grid for h in horizons}

        if spec.family == "ar1":
            assert ar1_params is not None  # fit único garantido em forecast()
            mu, phi, sigma2_eps = ar1_params
            last_return = returns[decision_idx]
            emission: dict[int, tuple[float, ...]] = {}
            for horizon in horizons:
                mean, std = ar1_step_forecast(
                    mu=mu,
                    phi=phi,
                    sigma2_eps=sigma2_eps,
                    last_return=last_return,
                    horizon=horizon,
                )
                emission[horizon] = gaussian_grid(mean=mean, std=std, levels=quantile_levels)
            return emission

        if spec.family == "ewma_vol":
            assert spec.decay_lambda is not None  # garantido pelo VO (C3)
            sigma2 = ewma_variance_path(
                returns=returns[: decision_idx + 1], decay_lambda=spec.decay_lambda
            )[-1]
            if sigma2 <= 0.0:
                # Borda Checkpoint C (paridade com o fake): série toda-zero até a
                # decisão => sigma2-hat = 0; gaussian_grid exige std > 0 — erguer,
                # não fabricar.
                raise ValueError(
                    "ewma_vol conditioning window produced zero variance at decision "
                    f"{decision_idx} (all-zero returns up to t) — refusing to emit a "
                    "degenerate Gaussian scale"
                )
            grid = gaussian_grid(mean=0.0, std=math.sqrt(sigma2), levels=quantile_levels)
            return {h: grid for h in horizons}  # flat em h — RMTD [5.18]

        if spec.family == "historical_quantiles":
            assert spec.window is not None  # garantido pelo VO (C3)
            if decision_idx + 1 < spec.window:
                raise ValueError(
                    f"historical_quantiles needs {spec.window} returns up to the decision; "
                    f"decision {decision_idx} has only {decision_idx + 1} (C1)"
                )
            window_values = returns[decision_idx - spec.window + 1 : decision_idx + 1]
            grid = sample_quantiles_type7(values=window_values, levels=quantile_levels)
            return {h: grid for h in horizons}  # flat em h (incondicional)

        # I7 — dispatch exaustivo: família fora do canônico ergue (o VO já barra na
        # construção; este ramo blinda contra spec forjada/nova família sem adapter).
        raise ValueError(
            f"unknown baseline family {spec.family!r}; expected one of {BASELINE_FAMILIES} (I7)"
        )
