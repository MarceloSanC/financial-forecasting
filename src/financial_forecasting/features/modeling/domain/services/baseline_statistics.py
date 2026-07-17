"""Serviços de domínio: estatística dos baselines (recursão EWMA, AR(1) h-step).

Domínio puro (stdlib-only — ADR 5.2.0001). Duas funções puras que materializam
as fórmulas pré-registradas do doc de domínio `quantile-model-training.md` §3:

- `ewma_variance_path` (§3.6): recursão RiskMetrics sobre o quadrado dos
  retornos — RMTD Eq. [5.3], ``sigma2[t] = lambda*sigma2[t-1] +
  (1-lambda)*returns[t]**2`` — com semente ``sigma2[0] = returns[0]**2``
  (concept D4; a semente decai como lambda**n e é numericamente irrelevante nas
  janelas reais). ``sigma2[t]`` é a variância prevista para ``t+1`` dado
  ``returns[: t+1]``. O(n) por caminho.
- `ar1_step_forecast` (§3.5): formas fechadas h-step do AR(1) —
  média ``mu + phi**h * (last_return - mu)`` (Hamilton 1994 §4.2) e desvio
  ``sqrt(sigma2_eps * (1 - phi**(2h)) / (1 - phi**2))`` (Box-Jenkins 2015
  Eq. (5.1.16); igual a ``sigma2_eps * soma_{j=0}^{h-1} phi**(2j)``), que
  cresce com h até a incondicional ``sigma2_eps / (1 - phi**2)``.

Validações defensivas erguem `ValueError` (superfície de C4/C5 no domínio:
parâmetros degenerados ou entradas não-finitas nunca produzem emissão).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def ewma_variance_path(*, returns: Sequence[float], decay_lambda: float) -> tuple[float, ...]:
    """Caminho da variância EWMA (RMTD Eq. [5.3]) sobre a série de retornos.

    ``sigma2[t]`` é a variância prevista para ``t+1`` condicionada em
    ``returns[: t+1]``; semente ``sigma2[0] = returns[0]**2`` (concept D4).

    Args:
        returns: série de retornos (não-vazia, todos finitos), ordem temporal.
        decay_lambda: fator de decaimento lambda em (0, 1) (canônico 0.94).

    Returns:
        Tupla ``sigma2`` alinhada 1:1 a `returns`.

    Raises:
        ValueError: `returns` vazio ou com valor não-finito; `decay_lambda`
            fora de (0, 1).
    """
    if not returns:
        raise ValueError("ewma_variance_path returns must be non-empty")
    if any(not math.isfinite(r) for r in returns):
        raise ValueError("ewma_variance_path returns must all be finite")
    if not 0.0 < decay_lambda < 1.0:
        raise ValueError(f"ewma_variance_path decay_lambda must be in (0, 1); got {decay_lambda}")

    path: list[float] = [float(returns[0]) ** 2]
    for r in returns[1:]:
        path.append(decay_lambda * path[-1] + (1.0 - decay_lambda) * float(r) ** 2)
    return tuple(path)


def ar1_step_forecast(
    *,
    mu: float,
    phi: float,
    sigma2_eps: float,
    last_return: float,
    horizon: int,
) -> tuple[float, float]:
    """Média e desvio h-step fechados do AR(1) (Hamilton §4.2; Box-Jenkins (5.1.16)).

    Média condicional ``mu + phi**h * (last_return - mu)``; variância do erro
    ``sigma2_eps * (1 - phi**(2h)) / (1 - phi**2)`` — crescente em h, convergindo
    para a incondicional ``sigma2_eps / (1 - phi**2)``; em h=1 reduz a
    ``sigma2_eps``.

    Args:
        mu: média incondicional estimada (finita).
        phi: coeficiente autorregressivo, |phi| < 1 (estacionariedade — C4).
        sigma2_eps: variância do ruído (> 0 e finita — C4).
        last_return: retorno condicionante r_t da decisão (finito).
        horizon: passos à frente (>= 1).

    Returns:
        Par ``(média, desvio)`` da previsão h-step.

    Raises:
        ValueError: |phi| >= 1, `sigma2_eps` não-positivo/não-finito,
            `mu`/`last_return` não-finitos ou `horizon < 1`.
    """
    if not math.isfinite(mu):
        raise ValueError(f"ar1_step_forecast mu must be finite; got {mu}")
    if not math.isfinite(phi) or abs(phi) >= 1.0:
        raise ValueError(f"ar1_step_forecast phi must satisfy |phi| < 1 (stationarity); got {phi}")
    if not math.isfinite(sigma2_eps) or sigma2_eps <= 0.0:
        raise ValueError(f"ar1_step_forecast sigma2_eps must be finite and > 0; got {sigma2_eps}")
    if not math.isfinite(last_return):
        raise ValueError(f"ar1_step_forecast last_return must be finite; got {last_return}")
    if horizon < 1:
        raise ValueError(f"ar1_step_forecast horizon must be >= 1; got {horizon}")

    mean = mu + phi**horizon * (last_return - mu)
    variance = sigma2_eps * (1.0 - phi ** (2 * horizon)) / (1.0 - phi**2)
    return mean, math.sqrt(variance)
