"""Integração: MCS 'R' do domínio sobre índices do `ArchMcs` x `arch.MCS` (A8; ADR 6.2.0004).

Importa `arch`/`numpy` diretamente (integração). Para cada esquema x seed x bloco, o
domínio (`ModelConfidenceSet.evaluate` sobre `ArchMcs().bootstrap_indices(...)`) e o
`arch.MCS(method="R")` com o **mesmo** T, k, seed, reps, bloco e esquema devem dar a
**mesma ordem de eliminação** e p-valores MCS **idênticos** (`==`: são múltiplos de
1/reps). Perdas sem empate (T = 250, k = 4, colunas de escalas distintas, seed declarada).
**Não** compara `included`: o `arch` usa p̂ > alpha e o domínio p̂ ≥ alpha (Thm. 3) — a
fronteira é teste analítico do unit.

Mais a guarda do adapter: série que passa pelo validador mas deixa a estimativa de Politis-
White numericamente indefinida (divisão por zero) → `ArithmeticError`, nunca o número
espúrio (o `arch` 8.0.0 devolveria 8,0 com 12 avisos).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from arch.bootstrap import MCS

from financial_forecasting.features.evaluation.adapters.out.inference.arch_mcs import ArchMcs
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    ModelConfidenceSet,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_N_POINTS = 250
_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)
_MODELS = ("m0", "m1", "m2", "m3")
_DATA_SEED = 62_114
_SCALES = (1.0, 1.05, 1.1, 1.3)
_ALPHA = 0.10
_REPS = 1000
_ARCH_BOOTSTRAP = {
    BootstrapScheme.STATIONARY: "stationary",
    BootstrapScheme.MOVING_BLOCK: "moving block",
}


def _losses() -> np.ndarray:
    """T x k perdas contínuas (sem empate), escalas distintas por coluna."""
    rng = np.random.default_rng(_DATA_SEED)
    return rng.standard_normal((_N_POINTS, len(_MODELS))) ** 2 * np.asarray(_SCALES)


def _series(losses: np.ndarray) -> PairedLossSeries:
    return PairedLossSeries(
        horizon=1,
        models=_MODELS,
        target_timestamps=tuple(
            (_EPOCH + timedelta(days=offset)).isoformat() for offset in range(_N_POINTS)
        ),
        losses=tuple(tuple(float(v) for v in losses[:, j]) for j in range(len(_MODELS))),
    )


_CASES = [
    pytest.param(scheme, seed, block, id=f"{scheme.value}-seed{seed}-block{block}")
    for scheme in BootstrapScheme
    for seed in (1, 7)
    for block in (3, 10)
]


@pytest.mark.integration
@pytest.mark.parametrize(("scheme", "seed", "block"), _CASES)
def test_mcs_matches_arch(scheme: BootstrapScheme, seed: int, block: int) -> None:
    losses = _losses()
    indices = ArchMcs().bootstrap_indices(
        n_obs=_N_POINTS, block_size=block, reps=_REPS, seed=seed, scheme=scheme
    )
    report = ModelConfidenceSet.evaluate(_series(losses), bootstrap=indices, alpha=_ALPHA)
    oracle = MCS(
        losses,
        size=_ALPHA,
        reps=_REPS,
        block_size=block,
        method="R",
        bootstrap=_ARCH_BOOTSTRAP[scheme],
        seed=seed,
    )
    oracle.compute()
    expected = [
        (_MODELS[int(index)], float(p_value)) for index, p_value in oracle.pvalues["Pvalue"].items()
    ]
    actual = [(entry.model, entry.mcs_p_value) for entry in report.eliminations]
    assert actual == expected


@pytest.mark.integration
def test_arch_block_length_arithmetic_error() -> None:
    """[1, -1, 0, ..., 0] (22 pontos) passa pelo validador; o arch divide por zero."""
    with pytest.raises(ArithmeticError, match="numerically undefined"):
        ArchMcs().optimal_block_length(series=[1.0, -1.0] + [0.0] * 20)
