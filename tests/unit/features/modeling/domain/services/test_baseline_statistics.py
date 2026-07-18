"""Testes dos serviços de estatística de baseline (domínio puro) contra oráculos.

Oráculos com tolerância declarada (ADR 0.0.0021 — a duplicação É a verificação):

- `ewma_variance_path`: paridade com
  `pandas.Series(r**2).ewm(alpha=1-lambda, adjust=False).mean()` (oráculo SÓ no
  teste — o domínio segue stdlib-only), caso analítico curto conferido à mão e
  irrelevância numérica da semente para n > 500 (decai como lambda**n — D4).
- `ar1_step_forecast`: fixture fechada à mão (mu, phi, sigma2_eps, r_t, h
  conhecidos), paridade com a forma-soma sigma2_eps * soma phi**(2j)
  (Box-Jenkins (5.1.16)), variância crescente em h convergindo à incondicional
  sigma2_eps/(1-phi**2), e h=1 reduzindo a sigma_eps.

Cobre também todos os ramos de erro (`ValueError`) das duas funções.
"""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ar1_step_forecast,
    ewma_variance_path,
)

# Tolerâncias declaradas (ADR 0.0.0021).
_ORACLE_TOLERANCE = 1e-12
_CLOSED_FORM_TOLERANCE = 1e-15
_SEED_DECAY_TOLERANCE = 1e-12

_LAMBDA = 0.94


# --------------------------------------------------------------------------- #
# ewma_variance_path
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_ewma_analytic_short_case() -> None:
    """Caso curto à mão (lambda=0.9): semente r1² e duas iterações da recursão.

    s0 = 0.01² = 1e-4
    s1 = 0.9*1e-4 + 0.1*(-0.02)² = 1.3e-4
    s2 = 0.9*1.3e-4 + 0.1*0.03² = 2.07e-4
    """
    path = ewma_variance_path(returns=(0.01, -0.02, 0.03), decay_lambda=0.9)

    assert path[0] == pytest.approx(1.0e-4, abs=_CLOSED_FORM_TOLERANCE)
    assert path[1] == pytest.approx(1.3e-4, abs=_CLOSED_FORM_TOLERANCE)
    assert path[2] == pytest.approx(2.07e-4, abs=_CLOSED_FORM_TOLERANCE)


@pytest.mark.unit
def test_ewma_seed_is_first_squared_return() -> None:
    """Semente sigma2[0] = returns[0]**2 (concept D4; RMTD Eq. [5.3])."""
    path = ewma_variance_path(returns=(0.025,), decay_lambda=_LAMBDA)

    assert path == (0.025**2,)


@pytest.mark.unit
def test_ewma_parity_with_pandas_ewm_oracle() -> None:
    """Paridade com `pandas.ewm(alpha=1-lambda, adjust=False)` (oráculo; tol 1e-12).

    Série sintética determinística (RNG semeado); o oráculo pandas vive SÓ no
    teste — o domínio permanece stdlib-only (ADR 5.2.0001).
    """
    rng = np.random.default_rng(42)
    returns = tuple(rng.normal(0.0, 0.02, size=300).tolist())

    path = ewma_variance_path(returns=returns, decay_lambda=_LAMBDA)

    oracle = pd.Series([r**2 for r in returns]).ewm(alpha=1.0 - _LAMBDA, adjust=False).mean()
    for got, expected in zip(path, oracle.tolist(), strict=True):
        assert got == pytest.approx(expected, abs=_ORACLE_TOLERANCE)


@pytest.mark.unit
def test_ewma_seed_numerically_irrelevant_beyond_500_steps() -> None:
    """A influência da semente decai como lambda**n — irrelevante para n > 500 (D4).

    Duas séries idênticas exceto no primeiro retorno: no passo 600 a diferença
    entre os caminhos é < 1e-12 (lambda=0.94 => 0.94**599 ~ 8e-17).
    """
    rng = np.random.default_rng(7)
    tail = tuple(rng.normal(0.0, 0.02, size=600).tolist())
    series_a = (0.10, *tail)
    series_b = (-0.05, *tail)

    path_a = ewma_variance_path(returns=series_a, decay_lambda=_LAMBDA)
    path_b = ewma_variance_path(returns=series_b, decay_lambda=_LAMBDA)

    assert abs(path_a[-1] - path_b[-1]) < _SEED_DECAY_TOLERANCE


@pytest.mark.unit
def test_ewma_path_aligns_one_to_one_with_returns() -> None:
    """O caminho tem exatamente um sigma2 por retorno (O(n), alinhado 1:1)."""
    returns = (0.01, 0.02, -0.01, 0.0, 0.03)

    path = ewma_variance_path(returns=returns, decay_lambda=_LAMBDA)

    assert len(path) == len(returns)


@pytest.mark.unit
def test_ewma_empty_returns_raises() -> None:
    """Série vazia ergue (não há semente possível)."""
    with pytest.raises(ValueError, match="non-empty"):
        ewma_variance_path(returns=(), decay_lambda=_LAMBDA)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ewma_non_finite_return_raises(bad: float) -> None:
    """NaN/Inf na série ergue (C5)."""
    with pytest.raises(ValueError, match="finite"):
        ewma_variance_path(returns=(0.01, bad), decay_lambda=_LAMBDA)


@pytest.mark.unit
@pytest.mark.parametrize("bad_lambda", [0.0, 1.0, -0.5, 1.5])
def test_ewma_decay_lambda_out_of_open_interval_raises(bad_lambda: float) -> None:
    """lambda fora de (0, 1) ergue."""
    with pytest.raises(ValueError, match="decay_lambda"):
        ewma_variance_path(returns=(0.01, 0.02), decay_lambda=bad_lambda)


# --------------------------------------------------------------------------- #
# ar1_step_forecast
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_ar1_closed_fixture_h1() -> None:
    """Fixture fechada à mão, h=1: média mu + phi*(r_t - mu); desvio sigma_eps.

    mu=0.05, phi=0.6, sigma2_eps=0.0004, r_t=0.11:
    média = 0.05 + 0.6*(0.11-0.05) = 0.086; desvio = sqrt(0.0004) = 0.02.
    """
    mean, std = ar1_step_forecast(mu=0.05, phi=0.6, sigma2_eps=0.0004, last_return=0.11, horizon=1)

    assert mean == pytest.approx(0.086, abs=_CLOSED_FORM_TOLERANCE)
    assert std == pytest.approx(0.02, abs=_CLOSED_FORM_TOLERANCE)


@pytest.mark.unit
def test_ar1_closed_fixture_h2() -> None:
    """Fixture fechada à mão, h=2 (Hamilton §4.2 / Box-Jenkins (5.1.16)).

    média = 0.05 + 0.6²*(0.11-0.05) = 0.0716;
    var = 0.0004*(1 + 0.6²) = 0.000544 => desvio = sqrt(0.000544).
    """
    mean, std = ar1_step_forecast(mu=0.05, phi=0.6, sigma2_eps=0.0004, last_return=0.11, horizon=2)

    assert mean == pytest.approx(0.0716, abs=_CLOSED_FORM_TOLERANCE)
    assert std == pytest.approx(math.sqrt(0.000544), abs=_CLOSED_FORM_TOLERANCE)


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [1, 2, 3, 7, 20])
def test_ar1_variance_matches_psi_weight_sum_form(horizon: int) -> None:
    """Forma fechada = forma-soma sigma2_eps * soma_{j=0}^{h-1} phi**(2j) (5.1.16)."""
    mu, phi, sigma2_eps, r_t = 0.001, -0.4, 0.0004, -0.02

    _, std = ar1_step_forecast(
        mu=mu, phi=phi, sigma2_eps=sigma2_eps, last_return=r_t, horizon=horizon
    )

    sum_form = sigma2_eps * sum(phi ** (2 * j) for j in range(horizon))
    assert std == pytest.approx(math.sqrt(sum_form), abs=_CLOSED_FORM_TOLERANCE)


@pytest.mark.unit
def test_ar1_variance_increases_in_h_and_converges_to_unconditional() -> None:
    """Variância crescente em h, convergindo a sigma2_eps/(1-phi²).

    Estritamente crescente enquanto o incremento phi**(2h) é representável em
    float (h <= 15 para phi=0.6); não-decrescente em toda a faixa; no limite
    (h=40) igual à incondicional dentro da tolerância declarada.
    """
    mu, phi, sigma2_eps = 0.0, 0.6, 0.0004

    stds = [
        ar1_step_forecast(mu=mu, phi=phi, sigma2_eps=sigma2_eps, last_return=0.01, horizon=h)[1]
        for h in range(1, 41)
    ]

    assert all(b > a for a, b in pairwise(stds[:15]))
    assert all(b >= a for a, b in pairwise(stds))
    unconditional_std = math.sqrt(sigma2_eps / (1.0 - phi**2))
    assert stds[-1] == pytest.approx(unconditional_std, abs=_ORACLE_TOLERANCE)


@pytest.mark.unit
def test_ar1_mean_converges_to_mu_in_h() -> None:
    """A média h-step converge para mu (phi**h -> 0)."""
    mean, _ = ar1_step_forecast(mu=0.05, phi=0.6, sigma2_eps=0.0004, last_return=0.11, horizon=60)

    assert mean == pytest.approx(0.05, abs=_ORACLE_TOLERANCE)


@pytest.mark.unit
def test_ar1_phi_zero_is_flat_at_mu_with_sigma_eps() -> None:
    """phi=0 degenera para ruído branco: média mu e desvio sigma_eps para todo h."""
    for horizon in (1, 5, 10):
        mean, std = ar1_step_forecast(
            mu=0.002, phi=0.0, sigma2_eps=0.0004, last_return=0.05, horizon=horizon
        )
        assert mean == pytest.approx(0.002, abs=_CLOSED_FORM_TOLERANCE)
        assert std == pytest.approx(0.02, abs=_CLOSED_FORM_TOLERANCE)


@pytest.mark.unit
@pytest.mark.parametrize("bad_phi", [1.0, -1.0, 1.2, -1.5, math.nan, math.inf])
def test_ar1_non_stationary_phi_raises(bad_phi: float) -> None:
    """|phi| >= 1 (ou não-finito) ergue — superfície de C4 no domínio."""
    with pytest.raises(ValueError, match="phi"):
        ar1_step_forecast(mu=0.0, phi=bad_phi, sigma2_eps=0.0004, last_return=0.01, horizon=1)


@pytest.mark.unit
@pytest.mark.parametrize("bad_sigma2", [0.0, -0.0004, math.nan, math.inf])
def test_ar1_non_positive_or_non_finite_sigma2_raises(bad_sigma2: float) -> None:
    """sigma2_eps <= 0 ou não-finito ergue (C4)."""
    with pytest.raises(ValueError, match="sigma2_eps"):
        ar1_step_forecast(mu=0.0, phi=0.5, sigma2_eps=bad_sigma2, last_return=0.01, horizon=1)


@pytest.mark.unit
@pytest.mark.parametrize("bad_mu", [math.nan, math.inf, -math.inf])
def test_ar1_non_finite_mu_raises(bad_mu: float) -> None:
    """mu não-finito ergue."""
    with pytest.raises(ValueError, match="mu"):
        ar1_step_forecast(mu=bad_mu, phi=0.5, sigma2_eps=0.0004, last_return=0.01, horizon=1)


@pytest.mark.unit
@pytest.mark.parametrize("bad_return", [math.nan, math.inf, -math.inf])
def test_ar1_non_finite_last_return_raises(bad_return: float) -> None:
    """last_return não-finito ergue (C5)."""
    with pytest.raises(ValueError, match="last_return"):
        ar1_step_forecast(mu=0.0, phi=0.5, sigma2_eps=0.0004, last_return=bad_return, horizon=1)


@pytest.mark.unit
@pytest.mark.parametrize("bad_horizon", [0, -1, -7])
def test_ar1_non_positive_horizon_raises(bad_horizon: int) -> None:
    """horizon < 1 ergue."""
    with pytest.raises(ValueError, match="horizon"):
        ar1_step_forecast(mu=0.0, phi=0.5, sigma2_eps=0.0004, last_return=0.01, horizon=bad_horizon)
