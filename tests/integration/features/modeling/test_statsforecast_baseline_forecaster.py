"""Integration test do `StatsforecastBaselineForecaster` — oráculo AR(1) + C4 + I7.

Cobre o que a suite de contrato (fake+real) NÃO cobre — o que é específico do
adapter real (Task 07; A3/A8):

- **Oráculo de recuperação AR(1) (A3; concept §8):** série sintética com
  **μ ≠ 0 material** (μ = 0.05) e φ = 0.6 alto o bastante para distinguir a
  média μ do intercepto c = μ(1-φ) = 0.02 dentro da tolerância declarada —
  pega exatamente o bug de wiring μ vs intercepto da parametrização do R.
- **Fixture fechada de delegação:** com fit forjado no seam, a emissão do
  adapter é EXATAMENTE `ar1_step_forecast` + `gaussian_grid` do domínio
  (ADR 5.2.0001 — toda emissão por fórmula de domínio); com o fit real, a
  emissão reproduz as mesmas fórmulas aplicadas aos parâmetros de `_fit_ar1`.
- **C4 via seam:** fit forjado com |φ̂| ≥ 1, sigma2_eps ≤ 0 ou NaN → ergue.
- **I7 — dispatch exaustivo:** toda família canônica emite; spec forjada com
  família desconhecida (via `object.__setattr__`, contornando o C3 do VO)
  ergue.

numpy é permitido AQUI e no adapter (nunca em domain/application — gate
`modeling-no-statsforecast-leak`, Task 08). Tolerâncias declaradas por teste
(ADR 0.0.0021).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.adapters.out.statsforecast import (
    statsforecast_baseline_forecaster as adapter_module,
)
from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
    StatsforecastBaselineForecaster,
    _fit_ar1,
)
from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ar1_step_forecast,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    gaussian_grid,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BASELINE_FAMILIES,
    BaselineSpec,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.integration

# -- série sintética do oráculo (RNG semeado — determinística) -------------------

_MU = 0.05  # μ ≠ 0 MATERIAL: c = μ(1-φ) = 0.02 fica a 0.03 de μ — >> tolerância
_PHI = 0.6
_SIGMA_EPS = 0.01
_N_ORACLE = 2000
_INTERCEPT = _MU * (1.0 - _PHI)  # 0.02 — o que um wrapper bugado devolveria como "mu"

# Tolerâncias declaradas (ADR 0.0.0021). Justificativa: com n = 2000,
# se(μ̂) ≈ (sigma_eps/√(1-φ²))/√n · √((1+φ)/(1-φ)) ≈ 6e-4 e se(φ̂) ≈ √((1-φ²)/n) ≈ 0.018;
# as tolerâncias abaixo são folgadas (≥ 5sigma) sem jamais admitir o intercepto
# c = 0.02 como μ (|μ - c| = 0.03 = 3x a tolerância de μ).
_TOL_MU = 0.01
_TOL_PHI = 0.09
_REL_TOL_SIGMA2 = 0.15


def _synthetic_ar1(
    n: int, *, mu: float = _MU, phi: float = _PHI, sigma_eps: float = _SIGMA_EPS
) -> tuple[float, ...]:
    """Série AR(1) determinística: r_t = μ + φ(r_{t-1} - μ) + ε_t, ε ~ N(0, sigma_eps²)."""
    rng = random.Random(7)
    values = [mu + rng.gauss(0.0, sigma_eps)]
    for _ in range(n - 1):
        values.append(mu + phi * (values[-1] - mu) + rng.gauss(0.0, sigma_eps))
    return tuple(values)


# -- oráculo de recuperação (A3): μ ≠ 0 material, μ vs intercepto ---------------


def test_fit_ar1_recovers_synthetic_parameters_within_declared_tolerance() -> None:
    """`_fit_ar1` recupera (μ, φ, sigma²_ε) da série sintética nas tolerâncias declaradas."""
    series = _synthetic_ar1(_N_ORACLE)

    mu_hat, phi_hat, sigma2_hat = _fit_ar1(series)

    assert mu_hat == pytest.approx(_MU, abs=_TOL_MU)
    assert phi_hat == pytest.approx(_PHI, abs=_TOL_PHI)
    assert sigma2_hat == pytest.approx(_SIGMA_EPS**2, rel=_REL_TOL_SIGMA2)


def test_fit_ar1_returns_the_mean_not_the_intercept() -> None:
    """O bug de wiring μ vs intercepto: μ̂ deve casar μ = 0.05 e REJEITAR c = 0.02.

    A parametrização do R (`include_mean=True`) rotula a média de "intercept";
    um wrapper que a tratasse como intercepto c = μ(1-φ) (ou a convertesse na
    direção errada) devolveria ≈ 0.02 — a 3 tolerâncias de distância de μ.
    """
    series = _synthetic_ar1(_N_ORACLE)

    mu_hat, _phi_hat, _sigma2_hat = _fit_ar1(series)

    assert abs(mu_hat - _MU) < _TOL_MU
    assert abs(mu_hat - _INTERCEPT) > 2 * _TOL_MU


# -- fixture fechada: a emissão do adapter É a fórmula de domínio ---------------

_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
_HORIZONS = (1, 3)
_N_SHORT = 60
_TRAIN_END_IDX = 39
_DECISIONS = (48, 52)

# Fit forjado da fixture fechada — valores exatos, sem estimação.
_FORGED_FIT = (0.002, 0.5, 1e-4)


def _forged_fit(_returns: Sequence[float]) -> tuple[float, float, float]:
    return _FORGED_FIT


def _expected_ar1_emission(
    params: tuple[float, float, float], returns: tuple[float, ...]
) -> dict[int, dict[int, tuple[float, ...]]]:
    """Oráculo de domínio: `ar1_step_forecast` + `gaussian_grid` por decisão x h."""
    mu, phi, sigma2_eps = params
    expected: dict[int, dict[int, tuple[float, ...]]] = {}
    for decision in _DECISIONS:
        expected[decision] = {}
        for horizon in _HORIZONS:
            mean, std = ar1_step_forecast(
                mu=mu,
                phi=phi,
                sigma2_eps=sigma2_eps,
                last_return=returns[decision],
                horizon=horizon,
            )
            expected[decision][horizon] = gaussian_grid(mean=mean, std=std, levels=_LEVELS)
    return expected


def test_ar1_emission_is_exactly_the_domain_formula_with_forged_fit() -> None:
    """Fixture fechada: com fit forjado, adapter == `ar1_step_forecast`+`gaussian_grid`."""
    returns = _synthetic_ar1(_N_SHORT)
    adapter = StatsforecastBaselineForecaster(fit_ar1=_forged_fit)

    result = adapter.forecast(
        spec=BaselineSpec(family="ar1"),
        returns=returns,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=_DECISIONS,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    expected = _expected_ar1_emission(_FORGED_FIT, returns)
    assert {d: dict(g) for d, g in result.items()} == expected  # igualdade EXATA


def test_ar1_emission_with_real_fit_matches_domain_formula_on_fitted_params() -> None:
    """Com o fit statsforecast real, a emissão reproduz as fórmulas de domínio
    aplicadas aos parâmetros devolvidos por `_fit_ar1` sobre o train congelado."""
    returns = _synthetic_ar1(_N_SHORT)
    fitted = _fit_ar1(returns[: _TRAIN_END_IDX + 1])

    result = StatsforecastBaselineForecaster().forecast(
        spec=BaselineSpec(family="ar1"),
        returns=returns,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=_DECISIONS,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    expected = _expected_ar1_emission(fitted, returns)
    assert {d: dict(g) for d, g in result.items()} == expected


# -- C4 via seam: fit degenerado ergue ------------------------------------------


@pytest.mark.parametrize(
    "forged",
    [
        pytest.param((0.0, 1.2, 1e-4), id="phi-explosive-1.2"),
        pytest.param((0.0, -1.0, 1e-4), id="phi-unit-root--1.0"),
        pytest.param((0.0, 0.5, 0.0), id="sigma2-zero"),
        pytest.param((0.0, 0.5, -1e-6), id="sigma2-negative"),
        pytest.param((math.nan, 0.5, 1e-4), id="mu-nan"),
        pytest.param((0.0, math.nan, 1e-4), id="phi-nan"),
    ],
)
def test_c4_degenerate_forged_fit_raises(forged: tuple[float, float, float]) -> None:
    """C4: fit forjado degenerado (|φ̂| ≥ 1, sigma2_eps ≤ 0, não-finito) ergue no adapter."""
    returns = _synthetic_ar1(_N_SHORT)
    adapter = StatsforecastBaselineForecaster(fit_ar1=lambda _r: forged)

    with pytest.raises(ValueError, match=r"C4"):
        adapter.forecast(
            spec=BaselineSpec(family="ar1"),
            returns=returns,
            train_end_idx=_TRAIN_END_IDX,
            decision_indices=_DECISIONS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )


def test_c4_seam_is_monkeypatchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """O seam default é o módulo-level `_fit_ar1` — monkeypatch no módulo vale
    para instâncias construídas DEPOIS do patch (C4 sem tocar a lib)."""
    monkeypatch.setattr(adapter_module, "_fit_ar1", lambda _r: (0.0, 1.5, 1e-4))

    with pytest.raises(ValueError, match=r"\|phi\| >= 1"):
        adapter_module.StatsforecastBaselineForecaster().forecast(
            spec=BaselineSpec(family="ar1"),
            returns=_synthetic_ar1(_N_SHORT),
            train_end_idx=_TRAIN_END_IDX,
            decision_indices=_DECISIONS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )


# -- I7: dispatch exaustivo ------------------------------------------------------

_SPECS = {
    spec.family: spec
    for spec in BaselineSpec.canonical_five(historical_quantiles_window=20)
}


@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_dispatch_every_canonical_family_emits(family: str) -> None:
    """I7: toda família canônica emite grade completa por decisão x horizonte."""
    result = StatsforecastBaselineForecaster().forecast(
        spec=_SPECS[family],
        returns=_synthetic_ar1(_N_SHORT),
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=_DECISIONS,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    assert set(result) == set(_DECISIONS)
    for grids in result.values():
        assert set(grids) == set(_HORIZONS)
        for grid in grids.values():
            assert len(grid) == len(_LEVELS)
            assert all(math.isfinite(v) for v in grid)


def test_dispatch_unknown_family_raises() -> None:
    """I7: spec forjada com família desconhecida (contornando o C3 do VO) ergue."""
    forged_spec = BaselineSpec(family="zero_return")
    object.__setattr__(forged_spec, "family", "arma_11")  # contorna o __post_init__

    with pytest.raises(ValueError, match=r"unknown baseline family 'arma_11'"):
        StatsforecastBaselineForecaster().forecast(
            spec=forged_spec,
            returns=_synthetic_ar1(_N_SHORT),
            train_end_idx=_TRAIN_END_IDX,
            decision_indices=_DECISIONS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )
