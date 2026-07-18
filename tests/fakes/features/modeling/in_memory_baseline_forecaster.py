"""Fake in-memory do port `BaselineForecaster` — NÃO um mock.

`FakeBaselineForecaster` implementa as 5 famílias canônicas REUSANDO os serviços
de domínio das Tasks 02/03 (`quantile_grid_emission`/`baseline_statistics`) — a
emissão É o contrato (ADR 5.2.0001), então fake e adapter real divergem apenas na
**estimação** do AR(1) (aqui: momentos stdlib do train; no real: fit
`statsforecast`). Ambos respondem à MESMA suite de contrato
(`tests/contract/features/modeling/test_baseline_forecaster_contract.py`).

Protocolo de informação (ADR 5.2.0002 — I3/I4/D2/D4):

- **Estimação congelada no train:** mu-hat = média de `returns[: train_end_idx+1]`;
  para `ar1`, momentos do train (phi-hat = autocorrelação lag-1, sigma2_eps-hat = (1-phi-hat²)·var).
- **Estado condicionante causal até cada decisão:** r_t = `returns[t]` (`ar1`),
  recursão EWMA desde a origem até t (`ewma_vol`, semente sigma2[0] = returns[0]**2 — D4),
  janela rolante terminando EM t (`historical_quantiles` — ADR 5.2.0003).

Fronteira de erro (concept §6): train/janela insuficiente ergue `ValueError`
(C1); entrada não-finita na janela condicionante ergue (C5 — nunca emite);
variância condicionante **zero** (série toda-zero até a decisão) também ergue —
`gaussian_grid` exige `std > 0` e a postura é "erguer, não fabricar" (decisão
local da Stage 5.2, Checkpoint C do bloco 1: a borda emerge aqui no fake, com
mensagem própria, antes de chegar ao serviço de emissão).
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

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
        series = tuple(float(r) for r in returns)
        self._validate_structure(series, train_end_idx, decision_indices, horizons)

        result: dict[int, GridByHorizon] = {}
        for decision_idx in decision_indices:
            result[decision_idx] = self._emit_decision(
                spec=spec,
                returns=series,
                train_end_idx=train_end_idx,
                decision_idx=decision_idx,
                horizons=horizons,
                quantile_levels=quantile_levels,
            )
        return result

    # -- validação estrutural + C5 (entrada) ----------------------------------

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

    # -- emissão por decisão ---------------------------------------------------

    def _emit_decision(  # noqa: PLR0913 — parâmetros coesos de uma decisão
        self,
        *,
        spec: BaselineSpec,
        returns: tuple[float, ...],
        train_end_idx: int,
        decision_idx: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
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
            mu, phi, sigma2_eps = _ar1_train_moments(train)
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
                # Borda Checkpoint C: série toda-zero até a decisão => sigma2-hat = 0;
                # gaussian_grid exige std > 0 — erguer, não fabricar.
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

        # I7 — dispatch exaustivo com ramo EXPLÍCITO (Checkpoint C MINOR-2): família
        # fora do canônico ergue o MESMO ValueError do adapter real — nunca um
        # assert (que evapora sob `python -O` e viraria TypeError downstream).
        raise ValueError(
            f"unknown baseline family {spec.family!r}; expected one of {BASELINE_FAMILIES} (I7)"
        )


def _ar1_train_moments(train: tuple[float, ...]) -> tuple[float, float, float]:
    """Momentos do train para o AR(1): (mu-hat, phi-hat, sigma2_eps-hat) — estimação stdlib (I4/D2).

    phi-hat = autocorrelação lag-1 amostral; sigma2_eps-hat = (1-phi-hat²)·var. Train trivialmente
    insuficiente (< 3 pontos) ou de variância zero ergue `ValueError` (C1 e a
    postura "erguer, não fabricar" — um AR(1) sobre série constante é
    degenerado, não caso a acomodar).
    """
    n = len(train)
    if n < _MIN_AR1_TRAIN:
        raise ValueError(
            f"ar1 needs at least {_MIN_AR1_TRAIN} train observations; got {n} (C1)"
        )
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
