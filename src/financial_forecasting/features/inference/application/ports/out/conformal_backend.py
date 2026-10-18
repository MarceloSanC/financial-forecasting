"""Port-out `ConformalBackend` — oráculo do split-CQR sem pesos sobre primitivos (ADR 7.2.0002).

Protocol estrutural (concept 7.2 §4 "Inference — application"; ADR 7.2.0002 itens 4
e 6). O split-CQR assimétrico é implementado UMA vez, stdlib-only, no domain do
`inference` (`ConformalCalibrator`, a implementação de **registro**). Este port
existe só para que uma biblioteca validada (`mapie`) atue como **oráculo** da
variante sem pesos: o adapter `MapieCqrBackend` (`adapters/out/mapie/`) e o
`FakeConformalBackend` passam pela mesma suíte de contrato
(`tests/contract/features/inference/test_conformal_backend_contract.py`).

**Nenhum use case chama este port** (I1; ADR 6.4.0008, sem verificação cruzada em
runtime): só o adapter e a suíte de contrato o importam, o que uma guarda AST em
`tests/architecture/test_stage_7_2_regression_guards.py` confere. Só primitivos e
`collections.abc` cruzam a fronteira (gate `inference-no-mapie-leak`).

Convenções: `calib_lower`/`calib_upper` são q̂_lo e q̂_hi do calib (vetor rearranjado),
`calib_realized` o y de cada ponto, alinhados; `tail_alpha` é a miscobertura de
CADA cauda, alpha_lo = tau_lo = 1 - tau_hi (par simétrico). Devolve as correções
(Q_lo, Q_hi) da variante sem pesos, nessa ordem.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ConformalBackend(Protocol):
    """Oráculo da variante sem pesos do split-CQR; nunca chamado por use case (I1)."""

    def split_cqr_corrections(
        self,
        *,
        calib_lower: Sequence[float],
        calib_upper: Sequence[float],
        calib_realized: Sequence[float],
        tail_alpha: float,
    ) -> tuple[float, float]:
        """(Q_lo, Q_hi): as correções conformais das caudas inferior e superior."""
        ...
