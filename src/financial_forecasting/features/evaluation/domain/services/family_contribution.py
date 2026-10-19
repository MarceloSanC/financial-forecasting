"""Serviço de domínio `FamilyContribution` — participação por família e intervalo de Δ_f (7.3).

Stdlib-only (concept 7.3 §4, I13-I15; ADR 7.3.0005 H3-CI, H3-LEVEL, H3-NEG, H3-READ; ADR
7.3.0001 item 1). Sobre as séries d_t de UM método (`FamilyLossDifferentials`):

- importância I_f(h) = média em t de d_{f,t}(h), com o sinal (sem corte);
- participação s_f(h) = I_f(h) / Σ_g I_g(h) e Δ_f = s_f(7) - s_f(1);
- método `undefined` se Σ_g I_g(h) <= 0 no ponto, em h = 1 ou h = 7 (H3-NEG);
- réplicas: os MESMOS índices de bootstrap (uma `BootstrapIndices`) para os dois
  horizontes e as quatro famílias. Uma réplica com Σ* <= 0 em h = 1 ou h = 7 fica nas B
  e entra como +inf no cálculo de q_{1-a/2} e como -inf no de q_{a/2} — os dois limites
  alargam (I14); a contagem por horizonte vai ao relatório;
- intervalo básico [2Δ̂ - q_{1-a/2}, 2Δ̂ - q_{a/2}] com quantis tipo 7
  (`linear_quantile`), a = 1 - nível (o nível de Bonferroni do `[h3]`, 0,9875) — igual ao
  `arch.conf_int(method="basic")` sobre os mesmos índices sem réplica indefinida (I13);
- leitura (H3-READ): lado = sinal de Δ̂; a família exclui 0 quando o intervalo exclui 0
  estritamente desse lado; excluir 0 do lado oposto, com Δ̂ = 0, ou ter um limite
  exatamente 0 deixa a família `undefined`; heterogêneo ⇔ alguma família `ok` exclui 0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)

OK: Final = "ok"
UNDEFINED: Final = "undefined"
_H1, _H7 = 1, 7


def linear_quantile(values: Sequence[float], probability: float) -> float:
    """Quantil tipo 7 (interpolação linear, o default do numpy) sem NaN com infinitos.

    Entre um infinito e outro valor o resultado é o infinito (nunca `inf - inf`).

    Raises:
        ValueError: série vazia, valor NaN ou probabilidade fora de [0, 1].
    """
    if not values:
        raise ValueError("linear_quantile needs at least one value")
    if not 0 <= probability <= 1:
        raise ValueError(f"probability must be in [0, 1], got {probability!r}")
    ordered = sorted(float(value) for value in values)
    if any(math.isnan(value) for value in ordered):
        raise ValueError("linear_quantile does not accept NaN")
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    fraction = position - low
    if fraction == 0 or low + 1 >= len(ordered):
        return ordered[low]
    below, above = ordered[low], ordered[low + 1]
    if below == -math.inf:
        return -math.inf
    if above == math.inf:
        return math.inf
    return below + fraction * (above - below)


@dataclass(frozen=True)
class FamilyShare:
    """Participações, Δ_f, o intervalo e a leitura de uma família (limites podem ser ±inf)."""

    family: str
    share_h1: float | None
    share_h7: float | None
    delta: float | None
    lower: float | None
    upper: float | None
    side: int | None  # -1 | 0 | +1 = sinal de Δ̂_f
    excludes_zero: bool | None
    status: str
    reason: str | None


@dataclass(frozen=True)
class FamilyContributionReport:
    """O relatório de um método: importâncias, participações, nível e a heterogeneidade."""

    method: str
    importance: Mapping[tuple[str, int], float]
    shares: tuple[FamilyShare, ...]
    level: float
    nonpositive_replicas: Mapping[int, int]
    status: str
    reason: str | None
    heterogeneous: bool | None


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _shares(
    importance: Mapping[tuple[str, int], float], families: Sequence[str]
) -> dict[str, float] | None:
    """Δ_f por família, ou `None` se Σ_g I_g(h) <= 0 em algum horizonte."""
    totals = {h: math.fsum(importance[(f, h)] for f in families) for h in (_H1, _H7)}
    if any(total <= 0 for total in totals.values()):
        return None
    return {
        f: importance[(f, _H7)] / totals[_H7] - importance[(f, _H1)] / totals[_H1] for f in families
    }


def _side(delta: float) -> int:
    return (delta > 0) - (delta < 0)


def _read(  # noqa: PLR0913 — os campos de uma família já calculados
    family: str, share_h1: float, share_h7: float, delta: float, lower: float, upper: float
) -> FamilyShare:
    """H3-READ: lado, exclusão de 0 e os casos `undefined` de uma família."""
    side = _side(delta)
    reason: str | None = None
    excludes: bool | None = False
    if any(math.isnan(value) for value in (delta, lower, upper)):
        # defesa (C7-1): um NaN nunca vira "ok" no gold
        reason = "the interval has a NaN bound"
    elif lower == 0 or upper == 0:
        reason = "a bound of the interval is exactly 0"
    elif lower > 0 or upper < 0:
        if (side > 0 and lower > 0) or (side < 0 and upper < 0):
            excludes = True
        else:
            reason = "the interval excludes 0 on the side opposite to delta"
    if reason is not None:
        excludes = None
    return FamilyShare(
        family=family,
        share_h1=share_h1,
        share_h7=share_h7,
        delta=delta,
        lower=lower,
        upper=upper,
        side=side,
        excludes_zero=excludes,
        status=OK if reason is None else UNDEFINED,
        reason=reason,
    )


class FamilyContribution:
    """Participação por família e intervalo básico de Bonferroni (ver docstring do módulo)."""

    @staticmethod
    def evaluate(
        differentials: FamilyLossDifferentials, *, bootstrap: BootstrapIndices, level: float
    ) -> FamilyContributionReport:
        """O relatório de um método sobre os índices de bootstrap compartilhados.

        Raises:
            ValueError: índices com `n_obs` diferente do número de decisões, ou nível fora
                de (0, 1) — erro de chamada.
        """
        if not 0 < level < 1:
            raise ValueError(f"level must be in (0, 1), got {level!r}")
        n = len(differentials.decision_timestamps)
        if bootstrap.n_obs != n:
            raise ValueError(f"bootstrap has n_obs {bootstrap.n_obs} for {n} decisions")
        families = differentials.families
        series = differentials.differentials
        importance = {key: _mean(values) for key, values in series.items()}
        point = _shares(importance, families)
        nonpositive = {_H1: 0, _H7: 0}
        if point is None:
            reason = "the point total of importances is <= 0 at h=1 or h=7 (H3-NEG)"
            return FamilyContributionReport(
                method=differentials.method,
                importance=importance,
                shares=tuple(
                    FamilyShare(f, None, None, None, None, None, None, None, UNDEFINED, reason)
                    for f in families
                ),
                level=level,
                nonpositive_replicas=nonpositive,
                status=UNDEFINED,
                reason=reason,
                heterogeneous=None,
            )
        replicas: list[dict[str, float] | None] = []
        for row in bootstrap.indices:
            resampled = {
                key: math.fsum(values[i] for i in row) / n for key, values in series.items()
            }
            for h in (_H1, _H7):
                if math.fsum(resampled[(f, h)] for f in families) <= 0:
                    nonpositive[h] += 1
            replicas.append(_shares(resampled, families))
        a = 1 - level
        totals = {h: math.fsum(importance[(g, h)] for g in families) for h in (_H1, _H7)}
        shares = []
        for f in families:
            delta = point[f]
            high = linear_quantile([math.inf if r is None else r[f] for r in replicas], 1 - a / 2)
            low = linear_quantile([-math.inf if r is None else r[f] for r in replicas], a / 2)
            shares.append(
                _read(
                    f,
                    importance[(f, _H1)] / totals[_H1],
                    importance[(f, _H7)] / totals[_H7],
                    delta,
                    2 * delta - high,
                    2 * delta - low,
                )
            )
        return FamilyContributionReport(
            method=differentials.method,
            importance=importance,
            shares=tuple(shares),
            level=level,
            nonpositive_replicas=nonpositive,
            status=OK,
            reason=None,
            heterogeneous=any(s.status == OK and s.excludes_zero for s in shares),
        )
