"""Adapter `ArchMcs` — satisfaz o port `McsBackend` via `arch` (ADR 6.2.0004).

**Gerador de registro** dos índices de bootstrap confirmatórios e da estimativa b̂_sb
(ADR `6_2_0004` itens 2 e 5; concept 6.2 §4 Adapters, §8 Externas):

- `bootstrap_indices`: `StationaryBootstrap` ou `MovingBlockBootstrap` sobre
  `np.arange(n_obs)` com `seed` int — **exatamente** como o `arch.MCS` monta o seu
  bootstrap —, e cada réplica de `bs.bootstrap(reps)` vira uma linha de índices (a
  posição reamostrada `data[0][0]`). O `generator` registra a versão do `arch` e a classe
  (`"arch <versão> <Classe> / numpy default_rng"`): reproduzir um MCS confirmatório depende
  das versões pinadas de `arch`/`numpy`.
- `optimal_block_length`: coluna `"stationary"` de
  `arch.bootstrap.optimal_block_length` (Politis & White 2004; Patton, Politis & White
  2009). A chamada roda sob `np.errstate(divide="raise", invalid="raise")`: divisão por
  zero nas autocorrelações (ex.: série inteira com cauda demeaned nula — medido no
  technical 6.2 §1 e §7) ou resultado não-finito/negativo viram `ArithmeticError` — o
  adapter se recusa a devolver o número espúrio (decisão de detalhe do §1).

A **entrada** passa primeiro pelos validadores únicos do domínio
(`validate_bootstrap_request`, `validate_block_length_request`) — os mesmos do fake (C9). O
retorno é o `BootstrapIndices` do domínio com `int` nativos e o b̂_sb como `float` nativo.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import arch
import numpy as np
from arch.bootstrap import MovingBlockBootstrap, StationaryBootstrap, optimal_block_length

from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
    validate_block_length_request,
    validate_bootstrap_request,
)

_CLASSES = {
    BootstrapScheme.STATIONARY: StationaryBootstrap,
    BootstrapScheme.MOVING_BLOCK: MovingBlockBootstrap,
}


class ArchMcs:
    """Satisfaz `McsBackend` com os bootstraps e o `optimal_block_length` do `arch`."""

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        validate_block_length_request(series)
        try:
            with np.errstate(divide="raise", invalid="raise"):
                table = optimal_block_length(np.asarray(series, dtype=float))
                estimate = float(table["stationary"].iloc[0])
        except FloatingPointError as error:
            raise ArithmeticError(
                f"optimal_block_length is numerically undefined for this series ({error})"
            ) from error
        if not math.isfinite(estimate) or estimate < 0.0:
            raise ArithmeticError(f"optimal_block_length returned {estimate}")
        return estimate

    def bootstrap_indices(
        self, *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
    ) -> BootstrapIndices:
        validate_bootstrap_request(
            n_obs=n_obs, block_size=block_size, reps=reps, seed=seed, scheme=scheme
        )
        cls = _CLASSES[scheme]
        bootstrap = cls(block_size, np.arange(n_obs), seed=seed)
        rows = tuple(
            tuple(int(index) for index in data[0][0]) for data in bootstrap.bootstrap(reps)
        )
        return BootstrapIndices(
            scheme=scheme,
            block_size=block_size,
            seed=seed,
            n_obs=n_obs,
            generator=f"arch {arch.__version__} {cls.__name__} / numpy default_rng",
            indices=rows,
        )
