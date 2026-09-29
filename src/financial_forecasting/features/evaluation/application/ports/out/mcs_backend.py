"""Port-out `McsBackend` — índices de bootstrap e b̂_sb para o MCS do domínio (ADR 6.2.0004).

Protocol estrutural de **dois métodos** (concept 6.2 §4; ADR `6_2_0004` itens 3 e 5). O
procedimento 'R' do Model Confidence Set roda no domínio (`ModelConfidenceSet.evaluate`)
sobre os índices que este port devolve; o adapter real `ArchMcs`
(`adapters/out/inference/arch_mcs.py`) é o **gerador de registro** dos índices
confirmatórios (`StationaryBootstrap`/`MovingBlockBootstrap` do `arch`, montados como o
`arch.MCS` monta os seus) e da estimativa b̂_sb de Politis-White. O `FakeMcsBackend` gera
índices com `random.Random(seed)` e devolve uma constante de `optimal_block_length` —
serve a testes de aplicação, não a estimativa. Só primitivos e VOs do domínio cruzam a
fronteira (gate `evaluation-no-inference-lib-leak`). Consumidor de produção: o use case da
Stage 6.4.

Contrato:

- `optimal_block_length(series=...)`: b̂_sb (esquema estacionário) **finito e ≥ 0**. A
  regra de bloco do domínio (`ModelConfidenceSet.block_length`, ADR `6_2_0005`) o
  converte em bloco **int** l = max(h, ⌈max b̂_sb⌉). Entrada validada por
  `validate_block_length_request` (mínimo de 11 pontos medido, valores finitos, série
  não constante) → `ValueError` (C9). O backend **real** pode erguer `ArithmeticError`
  quando a estimativa é numericamente indefinida para uma série que passa pelo
  validador (ex.: divisão por zero nas autocorrelações de séries inteiras com cauda
  demeaned nula) — nunca devolve o número espúrio (technical 6.2 §1; ADR `6_2_0004`).
- `bootstrap_indices(n_obs=..., block_size=..., reps=..., seed=..., scheme=...)`: um
  `BootstrapIndices` com reps x n_obs posições em [0, n_obs), o pedido ecoado e o
  `generator` preenchido. Entrada validada por `validate_bootstrap_request` →
  `ValueError` (C9).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
)


class McsBackend(Protocol):
    """b̂_sb e índices de bootstrap para o MCS; entrada inválida ergue `ValueError`."""

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        """b̂_sb de Politis-White (esquema estacionário), finito e ≥ 0."""
        ...

    def bootstrap_indices(
        self, *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
    ) -> BootstrapIndices:
        """reps x n_obs índices de reamostragem do esquema pedido."""
        ...
