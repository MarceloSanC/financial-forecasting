"""Fake do port `McsBackend` — índices por `random.Random` e b̂_sb constante (ADR 6.2.0004).

A geração é do fake (o domínio não tem RNG); a **validação** é a do domínio
(`validate_bootstrap_request`, `validate_block_length_request`), então fake e adapter
recusam as mesmas entradas (C9). O leiaute dos índices é o dos esquemas do `arch`:

- estacionário: início uniforme e, a cada passo, novo início com probabilidade
  1/`block_size`, senão `(anterior + 1) % n_obs` (volta ao início da série);
- moving-block: blocos de `block_size` posições consecutivas com início uniforme em
  [0, `n_obs - block_size`], concatenados e truncados em `n_obs`.

`optimal_block_length` devolve a constante fixada na construção (default 1,0): o fake
serve a testes de aplicação, não a estimativa.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
    validate_block_length_request,
    validate_bootstrap_request,
)

_GENERATOR = "stdlib random.Random"


class FakeMcsBackend:
    """Satisfaz `McsBackend` com `random.Random(seed)` e um b̂_sb constante."""

    def __init__(self, block_length: float = 1.0) -> None:
        self._block_length = block_length

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        validate_block_length_request(series)
        return self._block_length

    def bootstrap_indices(
        self, *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
    ) -> BootstrapIndices:
        validate_bootstrap_request(
            n_obs=n_obs, block_size=block_size, reps=reps, seed=seed, scheme=scheme
        )
        rng = random.Random(seed)
        draw = _stationary_row if scheme is BootstrapScheme.STATIONARY else _moving_block_row
        return BootstrapIndices(
            scheme=scheme,
            block_size=block_size,
            seed=seed,
            n_obs=n_obs,
            generator=_GENERATOR,
            indices=tuple(draw(rng, n_obs, block_size) for _ in range(reps)),
        )


def _stationary_row(rng: random.Random, n_obs: int, block_size: int) -> tuple[int, ...]:
    position = rng.randrange(n_obs)
    row = [position]
    for _ in range(n_obs - 1):
        position = (
            rng.randrange(n_obs) if rng.random() < 1.0 / block_size else (position + 1) % n_obs
        )
        row.append(position)
    return tuple(row)


def _moving_block_row(rng: random.Random, n_obs: int, block_size: int) -> tuple[int, ...]:
    row: list[int] = []
    while len(row) < n_obs:
        start = rng.randint(0, n_obs - block_size)
        row.extend(range(start, start + block_size))
    return tuple(row[:n_obs])
