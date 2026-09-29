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

import random
from datetime import UTC, datetime, timedelta

import arch
import numpy as np
import pytest
from arch.bootstrap import MCS, MovingBlockBootstrap, StationaryBootstrap
from arch.bootstrap import optimal_block_length as arch_optimal_block_length

from financial_forecasting.features.evaluation.adapters.out.inference import arch_mcs
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


def _ar1_series() -> list[float]:
    """A mesma AR(1) da suíte de contrato: Random(622026), phi = 0,6, 250 pontos."""
    rng = random.Random(62_2026)
    series = [rng.gauss(0.0, 1.0)]
    for _ in range(249):
        series.append(0.6 * series[-1] + rng.gauss(0.0, 1.0))
    return series


@pytest.mark.integration
def test_arch_block_length_uses_stationary_column_sbcol() -> None:
    """O adapter lê a coluna "stationary" (b̂_sb), não a "circular" (b̂_cb)."""
    series = _ar1_series()
    table = arch_optimal_block_length(np.asarray(series))
    stationary = float(table["stationary"].iloc[0])
    circular = float(table["circular"].iloc[0])
    assert stationary != circular
    assert ArchMcs().optimal_block_length(series=series) == stationary


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scheme", "cls"),
    [
        (BootstrapScheme.STATIONARY, StationaryBootstrap),
        (BootstrapScheme.MOVING_BLOCK, MovingBlockBootstrap),
    ],
)
def test_arch_generator_records_version_and_class_genver(
    scheme: BootstrapScheme, cls: type
) -> None:
    indices = ArchMcs().bootstrap_indices(n_obs=20, block_size=3, reps=2, seed=1, scheme=scheme)
    assert indices.generator == f"arch {arch.__version__} {cls.__name__} / numpy default_rng"


@pytest.mark.integration
@pytest.mark.parametrize("value", [float("nan"), -1.0, float("inf")])
def test_arch_block_length_nonfinite_guard_nfguard(
    monkeypatch: pytest.MonkeyPatch, value: float
) -> None:
    """Resultado não-finito ou negativo do arch vira ArithmeticError, nunca o número."""
    frame = arch_optimal_block_length(np.asarray(_ar1_series()))
    frame.loc[:, "stationary"] = value
    monkeypatch.setattr(arch_mcs, "optimal_block_length", lambda _series: frame)
    with pytest.raises(ArithmeticError, match="returned"):
        ArchMcs().optimal_block_length(series=_ar1_series())
