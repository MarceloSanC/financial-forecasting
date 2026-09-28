"""Port-out `ScoringBackend` — as três médias de scoring sobre primitivos (ADR 6.1.0001).

Protocol estrutural (concept 6.1 §4; ADR `6_1_0001` itens 2 e 4). As fórmulas de
pinball, CRPS_Q e interval score são implementadas UMA vez, stdlib-only, no domínio
(`evaluation/domain/services/`) — a implementação de **registro**. Este port existe
para que bibliotecas validadas (`sklearn`, `scoringrules`) atuem como **oráculos**
dessas médias: os adapters `SklearnScoring` e `ScoringrulesBackend`
(`adapters/out/scoring/`) e o `FakeScoringBackend` (que delega às funções de série
do domínio) passam pela MESMA suíte de contrato
(`tests/contract/features/evaluation/test_scoring_backend_contract.py`). Só
primitivos e `collections.abc` cruzam a fronteira — nada de `numpy` (gate
`evaluation-no-scoring-lib-leak`).

Convenções dos parâmetros (doc de domínio §3.1-§3.3):

- `realized`: o valor realizado y_t, um por ponto.
- `level`: o **nível** τ do quantil em (0, 1) — em `sklearn.metrics.mean_pinball_loss`
  é o argumento `alpha`; aqui o nome é `level` para não colidir com a miscobertura.
- `quantiles`: q̂_τ(t), um por ponto, alinhado a `realized`.
- `quantile_grid` / `levels`: uma grade por ponto, alinhada aos `levels` (em (0, 1)).
- `lower` / `upper`: extremos do intervalo central, `lower <= upper` em todo ponto.
- `miscoverage`: a miscobertura alpha do intervalo central, em (0, 1) — **nunca** `alpha`
  (ambíguo com o `alpha` = nível do sklearn).

Escalas: pinball em rho_τ (sem fator 2); CRPS_Q = (2/K)·Σ_k rho_{τ_k} médio sobre os
pontos; IS_alpha de Gneiting & Raftery (2007) Eq. (43), não escalado. Todas as três
devolvem a **média** sobre os pontos, como `float` nativo.

Contrato de entrada (C7): `level`/`miscoverage` fora de (0, 1), sequências de
tamanhos diferentes, sequência vazia, grade vazia ou desalinhada e `lower > upper`
erguem `ValueError` — o mesmo validador único do domínio
(`scoring_input_validation`) é chamado por todas as implementações.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ScoringBackend(Protocol):
    """Três médias de scoring sobre primitivos; entrada inválida ergue `ValueError`."""

    def mean_pinball(
        self, *, realized: Sequence[float], quantiles: Sequence[float], level: float
    ) -> float:
        """Média de rho_τ(y - q̂_τ) sobre os pontos (τ = `level`)."""
        ...

    def mean_crps_quantile(
        self,
        *,
        realized: Sequence[float],
        quantile_grid: Sequence[Sequence[float]],
        levels: Sequence[float],
    ) -> float:
        """Média de CRPS_Q = (2/K)·Σ_k rho_{τ_k}(y - q̂_{τ_k}) sobre os pontos."""
        ...

    def mean_interval_score(
        self,
        *,
        realized: Sequence[float],
        lower: Sequence[float],
        upper: Sequence[float],
        miscoverage: float,
    ) -> float:
        """Média de IS_alpha(l, u; y) sobre os pontos (alpha = `miscoverage`)."""
        ...
