"""Port-out `BaselineForecaster` — emissão da grade crua de quantis por baseline.

Protocol estrutural (concept 5.2 §4): dado `(spec, retornos, fronteira de
estimação, decisões, horizontes, grade de quantis)`, devolve os **valores crus**
da grade por decisão x horizonte. Os **dados** cruzam a fronteira como
primitivos/`collections.abc` — NUNCA DataFrame; o VO de domínio `BaselineSpec`
cruza o port (precedente `Candle`/`IndicatorCalculator`, 3.1). A implementação
real (`StatsforecastBaselineForecaster`, adapters/out) e o fake in-memory são
validados pela MESMA suite de contrato
(`tests/contract/features/modeling/test_baseline_forecaster_contract.py`,
parametrizada sobre `[fake, real]` — skill `pytest-with-fakes`).

Contrato semântico (concept §4/§5/§6; ADR 5.2.0002):

- **I4 — estimação congelada no train:** parâmetros estimados (mu-hat, phi-hat, sigma2_eps-hat do
  `ar1`; mu-hat do `historical_mean`) usam **só** `returns[: train_end_idx + 1]`;
  lambda/W nunca são re-estimados (vêm da `BaselineSpec`).
- **I3 — causalidade da emissão:** a grade crua na decisão `t` é função apenas
  de `returns[: t + 1]` — mutar/truncar a série depois de `t` não muda a
  emissão em `t` (concretiza o ADR 0.0.0018 no BC modeling).
- **C1 — janela insuficiente ergue:** `historical_quantiles` com menos de
  `window` retornos até a decisão, ou train trivialmente insuficiente para
  estimar o `ar1`, ergue `ValueError` (erguer, não fabricar).
- **C5 — não-finito ergue, nunca é emitido:** NaN/Inf em
  `returns[: max(decision_indices) + 1]` (a janela condicionante mais larga da
  chamada) ou em qualquer valor cru produzido → `ValueError`; um baseline
  determinístico jamais emite valor não-finito.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)

GridByHorizon = Mapping[int, tuple[float, ...]]
"""Por horizonte, os valores crus da grade alinhados 1:1 a `quantile_levels`."""


class BaselineForecaster(Protocol):
    """Contrato de emissão da grade crua de quantis de um baseline canônico."""

    def forecast(  # noqa: PLR0913 — parâmetros coesos do contrato de emissão
        self,
        *,
        spec: BaselineSpec,
        returns: Sequence[float],
        train_end_idx: int,
        decision_indices: Sequence[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> Mapping[int, GridByHorizon]:
        """Emite a grade crua por decisão x horizonte para uma spec de baseline.

        Args:
            spec: spec canônica do baseline (família + parâmetros pré-registrados).
            returns: `target_return` na grade densa de pregão do dataset.
            train_end_idx: último índice da partição train (fronteira de
                estimação — I4/D2).
            decision_indices: dias de decisão (bloco test), crescentes.
            horizons: horizontes de previsão em dias de pregão (>= 1).
            quantile_levels: grade densa comum do cohort (crescente, em (0, 1)).

        Returns:
            `decision_idx -> horizon -> grade crua` (tupla alinhada 1:1 a
            `quantile_levels`), com TODA decisão pedida presente.

        Raises:
            ValueError: janela/train insuficiente (C1), entrada ou emissão
                não-finita (C5), fit degenerado (C4 — adapter real) ou
                argumentos estruturalmente inválidos.
        """
        ...
