"""Port-out `InferenceBackend` — DM/HLN e Holm sobre primitivos (ADR 6.2.0003 item 3).

Protocol estrutural (concept 6.2 §4; ADR `6_2_0003`). DM/HLN e Holm são implementados
UMA vez, stdlib-only, no domínio (`diebold_mariano.py`, `holm_correction.py`) — a
implementação de **registro**. Este port existe para que uma biblioteca validada
(`statsmodels`: OLS com covariância HAC e `multipletests`) atue como **oráculo** dessas
contas: o adapter `StatsmodelsHac` (`adapters/out/inference/`) e o
`FakeInferenceBackend` (que só delega aos primitivos do domínio) passam pela MESMA suíte
de contrato (`tests/contract/features/evaluation/test_inference_backend_contract.py`).
Só primitivos, `collections.abc` e os tipos do domínio cruzam a fronteira — nada de
`numpy`/`statsmodels` (gate `evaluation-no-inference-lib-leak`).

Convenções (doc de domínio §6.1, §6.3, §6.4; convenções #14/#14b):

- d_t = L_cand,t - L_comp,t; o teste é **unilateral**, H1: E[d] < 0 (o candidato tem
  perda esperada menor); p = P(t_{T-1} ≤ S1*), S1* com a correção HLN;
- variância de longo prazo retangular (o "acf" do R — registro) ou Bartlett; var̂ ≤ 0
  com h > 1 recalcula tudo com h = 1 (`fallback_applied`);
- Holm (1979): p-valores ajustados na ordem de entrada; rejeição de registro p̃ ≤ alpha.

Contrato de entrada — o mesmo validador único do domínio em toda implementação:

- C3 (`validate_dm_request`): tamanhos iguais; T ≥ 2 e T > h; perdas finitas e ≥ 0;
  `horizon` int não-bool ≥ 1; `variance_estimator` membro de `DmVarianceEstimator`;
  variância nula com h = 1 (inclusive depois do fallback) → `ValueError`;
- C4 (`validate_p_values`, `validate_alpha`): lista não-vazia de p-valores finitos em
  [0, 1]; alpha finito em (0, 1) → senão `ValueError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMarianoResult,
    DmVarianceEstimator,
)


class InferenceBackend(Protocol):
    """DM/HLN unilateral e Holm sobre primitivos; entrada inválida ergue `ValueError`."""

    def diebold_mariano(
        self,
        *,
        candidate_losses: Sequence[float],
        comparator_losses: Sequence[float],
        horizon: int,
        variance_estimator: DmVarianceEstimator,
    ) -> DieboldMarianoResult:
        """DM/HLN do candidato contra o comparador (H1: E[L_cand - L_comp] < 0)."""
        ...

    def holm_adjusted(self, *, p_values: Sequence[float]) -> tuple[float, ...]:
        """p-valores ajustados de Holm, na ordem de entrada."""
        ...

    def holm_rejected(self, *, p_values: Sequence[float], alpha: float) -> tuple[bool, ...]:
        """Rejeição de Holm ao nível alpha, na ordem de entrada."""
        ...
