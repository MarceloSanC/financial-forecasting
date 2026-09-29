"""Serviço de domínio `ModelConfidenceSet` — MCS de HLN (2011), estatística 'R', e a regra de bloco.

Implementação **de registro**, stdlib-only (concept 6.2 §4, I8-I10, C6-C8; ADR
`6_2_0004` itens 1 e 4; ADR `6_2_0005`; doc §6.5). O procedimento roda sobre os índices
de reamostragem de um `BootstrapIndices` (gerador de registro: o adapter `ArchMcs`), com
os mesmos passos do `arch.MCS(method="R")`:

- d̄_ij = L̄_i - L̄_j, L̄_i = Σ_t L_i,t / T (`math.fsum`);
- em cada réplica b, L̄*_i,b = Σ L_i,idx / T sobre a linha b; d*_ij,b = L̄*_i,b - L̄*_j,b;
- var̂_ij = Σ_b (d*_ij,b - d̄_ij)² / B, estimada **uma vez** (bootstrap recentrado);
- t_ij = d̄_ij/√var̂_ij e t*_ij,b = (d*_ij,b - d̄_ij)/√var̂_ij;
- por passo, sobre os incluídos: T_R = max t_ij e p do passo = #{b : T_R < max t*_ij,b}/B
  (convenção do `arch`, para os números baterem); elimina o **modelo-linha** do máximo
  (empate exato → um só modelo, o primeiro modelo-linha na ordem de `series.models`);
- p-valor MCS = máximo acumulado dos p de passo na ordem de eliminação (Def. 4), o
  sobrevivente com 1,0; **pertença ⇔ p̂ ≥ alpha** (Thm. 3; o `arch` usa ">" — por isso a
  pertença na fronteira é teste analítico, não de paridade).

Pré-condições (`ValueError`, nesta ordem): alpha em (0, 1); `bootstrap.reps ≥
MIN_MCS_REPS`; `bootstrap.n_obs == T`; nenhum par com diferencial constante (a
pré-condição var(L_i - L_j) > 0 é do MCS, não do VO — ADR `6_2_0001`); nenhum var̂_ij ≤ 0.

`block_length`: l = max(h, ⌈max b̂_sb⌉), uma estimativa finita ≥ 0 por par de
`series.model_pairs()` (ADR `6_2_0005`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import accumulate
from typing import Final

from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_horizon,
    check_points,
    is_constant,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
    check_generator,
    validate_bootstrap_request,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

MIN_MCS_REPS: Final = 1000

_STATISTIC = "R"
_MIN_ELIMINATIONS = 2


def validate_mcs_reps(reps: int) -> None:
    """Validador único do mínimo de réplicas do MCS (`reps >= MIN_MCS_REPS`).

    Consumido pelo `McsReport`, pelo `ModelConfidenceSet.evaluate` e pelos
    `RefreshParameters` da 6.4 (ADR 6.4.0006 item 2). O tipo (int não-bool) é do
    `validate_bootstrap_parameters`; aqui só o piso confirmatório.

    Raises:
        ValueError: `reps` abaixo de `MIN_MCS_REPS`.
    """
    if reps < MIN_MCS_REPS:
        raise ValueError(
            f"reps must be >= {MIN_MCS_REPS} (the MCS needs reps >= {MIN_MCS_REPS}), "
            f"got {reps!r}"
        )


@dataclass(frozen=True)
class McsElimination:
    """Um passo do MCS: o modelo eliminado (ou o sobrevivente), p do passo e p MCS."""

    model: str
    step_p_value: float
    mcs_p_value: float


@dataclass(frozen=True)
class McsReport:
    """MCS de um horizonte, estatística 'R'.

    Campos:
        horizon, n_points: horizonte e T da série.
        alpha: nível em (0, 1).
        statistic: sempre "R".
        scheme, block_size, reps, seed, generator: copiados do `BootstrapIndices`.
        eliminations: k entradas na ordem de eliminação; a última é o sobrevivente.
        included: {m : mcs_p_value ≥ alpha}, na ordem de `series.models`.

    Raises:
        ValueError: relatório incoerente (I9; C8), na construção. "Nomes = `series.models`"
            e "proveniência = a dos índices" são garantias de construção do `evaluate`.
    """

    horizon: int
    n_points: int
    alpha: float
    statistic: str
    scheme: BootstrapScheme
    block_size: int
    reps: int
    seed: int
    generator: str
    eliminations: tuple[McsElimination, ...]
    included: tuple[str, ...]

    def __post_init__(self) -> None:
        """I9: estatística, amostra, bootstrap, máximo acumulado e pertença."""
        if self.statistic != _STATISTIC:
            raise ValueError(f"statistic must be {_STATISTIC!r}, got {self.statistic!r}")
        validate_alpha(self.alpha)
        check_horizon(self.horizon)
        check_points(self.n_points, self.horizon)
        validate_bootstrap_request(
            n_obs=self.n_points,
            block_size=self.block_size,
            reps=self.reps,
            seed=self.seed,
            scheme=self.scheme,
        )
        validate_mcs_reps(self.reps)
        check_generator(self.generator)
        self._check_eliminations()
        self._check_included()

    def _check_eliminations(self) -> None:
        eliminations = self.eliminations
        if not isinstance(eliminations, tuple) or len(eliminations) < _MIN_ELIMINATIONS:
            raise ValueError(
                f"eliminations must be a tuple of k >= {_MIN_ELIMINATIONS} entries, "
                f"got {eliminations!r}"
            )
        names = [entry.model for entry in eliminations]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError(f"elimination names must be non-empty str, got {names}")
        if len(set(names)) != len(names):
            raise ValueError(f"elimination names must be unique, got {names}")
        steps = [entry.step_p_value for entry in eliminations]
        if any(not is_finite_number(step) or not 0.0 <= step <= 1.0 for step in steps):
            raise ValueError(f"step p-values must be in [0, 1], got {steps}")
        cumulative = list(accumulate(steps, max))
        if [entry.mcs_p_value for entry in eliminations] != cumulative:
            raise ValueError(
                "mcs_p_value must be the cumulative max of step_p_value in elimination "
                f"order, got {[entry.mcs_p_value for entry in eliminations]} for {steps}"
            )
        if steps[-1] != 1.0:
            raise ValueError(f"the last (surviving) model must have p = 1.0, got {steps[-1]}")

    def _check_included(self) -> None:
        if not isinstance(self.included, tuple) or len(set(self.included)) != len(self.included):
            raise ValueError(f"included must be a tuple without repeats, got {self.included!r}")
        expected = {e.model for e in self.eliminations if e.mcs_p_value >= self.alpha}
        if set(self.included) != expected:
            raise ValueError(
                f"included must be {{m : mcs_p_value >= alpha}} = {sorted(expected)}, "
                f"got {self.included}"
            )


class ModelConfidenceSet:
    """MCS 'R' e regra de bloco sobre uma `PairedLossSeries` (um horizonte)."""

    @staticmethod
    def block_length(
        series: PairedLossSeries, *, block_estimates: Mapping[tuple[str, str], float]
    ) -> int:
        """l = max(h, ⌈max b̂_sb⌉) — uma estimativa por par de `series.model_pairs()`.

        Raises:
            ValueError: par faltando, par desconhecido (inclusive invertido), estimativa
                negativa, não-finita, não-número ou `bool` (C7).
        """
        pairs = series.model_pairs()
        unknown = [pair for pair in block_estimates if pair not in pairs]
        if unknown:
            raise ValueError(f"unknown model pairs in block_estimates: {unknown}")
        missing = [pair for pair in pairs if pair not in block_estimates]
        if missing:
            raise ValueError(f"block_estimates misses the model pairs {missing}")
        for pair, estimate in block_estimates.items():
            if not is_finite_number(estimate) or estimate < 0.0:
                raise ValueError(
                    f"block estimate of {pair} must be a finite number >= 0, got {estimate!r}"
                )
        return max(series.horizon, math.ceil(max(block_estimates.values())))

    @staticmethod
    def evaluate(
        series: PairedLossSeries, *, bootstrap: BootstrapIndices, alpha: float
    ) -> McsReport:
        """MCS 'R' ao nível alpha sobre os índices de `bootstrap`.

        Raises:
            ValueError: pré-condições de C6 (ver docstring do módulo).
        """
        validate_alpha(alpha)
        validate_mcs_reps(bootstrap.reps)
        if bootstrap.n_obs != series.n_points:
            raise ValueError(
                f"bootstrap n_obs ({bootstrap.n_obs}) must equal T ({series.n_points})"
            )
        for first, second in series.model_pairs():
            if is_constant(series.differential(first, second)):
                raise ValueError(
                    f"models {first!r} and {second!r} have a constant loss differential "
                    "(the MCS needs var(L_i - L_j) > 0)"
                )
        statistics = _studentized_differences(series, bootstrap)
        eliminations = _eliminate(series.models, statistics, bootstrap.reps)
        return McsReport(
            horizon=series.horizon,
            n_points=series.n_points,
            alpha=alpha,
            statistic=_STATISTIC,
            scheme=bootstrap.scheme,
            block_size=bootstrap.block_size,
            reps=bootstrap.reps,
            seed=bootstrap.seed,
            generator=bootstrap.generator,
            eliminations=eliminations,
            included=tuple(
                model
                for model in series.models
                if next(e.mcs_p_value for e in eliminations if e.model == model) >= alpha
            ),
        )


@dataclass(frozen=True)
class _Studentized:
    """t_ij e t*_ij,b para todo par ordenado (i, j), i ≠ j (índices de modelo)."""

    observed: dict[tuple[int, int], float]
    simulated: dict[tuple[int, int], list[float]]


def _studentized_differences(series: PairedLossSeries, bootstrap: BootstrapIndices) -> _Studentized:
    n_points = series.n_points
    columns = [series.losses_of(model) for model in series.models]
    means = [math.fsum(column) / n_points for column in columns]
    boot_means = [
        [math.fsum(map(column.__getitem__, row)) / n_points for row in bootstrap.indices]
        for column in columns
    ]
    observed: dict[tuple[int, int], float] = {}
    simulated: dict[tuple[int, int], list[float]] = {}
    size = len(columns)
    for i in range(size):
        for j in range(i + 1, size):
            mean_diff = means[i] - means[j]
            centred = [
                star_i - star_j - mean_diff
                for star_i, star_j in zip(boot_means[i], boot_means[j], strict=True)
            ]
            variance = math.fsum(value * value for value in centred) / bootstrap.reps
            if variance <= 0.0:
                raise ValueError(
                    f"bootstrap variance of d({series.models[i]!r}, {series.models[j]!r}) "
                    "is zero (e.g. every replication reproduces the sample)"
                )
            scale = math.sqrt(variance)
            observed[i, j] = mean_diff / scale
            observed[j, i] = -observed[i, j]
            simulated[i, j] = [value / scale for value in centred]
            simulated[j, i] = [-value for value in simulated[i, j]]
    return _Studentized(observed=observed, simulated=simulated)


def _eliminate(
    models: Sequence[str], statistics: _Studentized, reps: int
) -> tuple[McsElimination, ...]:
    included = list(range(len(models)))
    steps: list[tuple[int, float]] = []
    while len(included) > 1:
        pairs = [(i, j) for i in included for j in included if i != j]
        # max estrito na ordem (linha, coluna): num empate exato fica o 1º modelo-linha
        worst = pairs[0]
        for pair in pairs[1:]:
            if statistics.observed[pair] > statistics.observed[worst]:
                worst = pair
        test_stat = statistics.observed[worst]
        # T*_R,b = max dos t*_ij,b dos incluídos, réplica a réplica
        simulated_max = map(max, zip(*(statistics.simulated[pair] for pair in pairs), strict=True))
        exceed = sum(1 for value in simulated_max if test_stat < value)
        steps.append((worst[0], exceed / reps))
        included.remove(worst[0])
    steps.append((included[0], 1.0))
    cumulative = accumulate((p_value for _, p_value in steps), max)
    return tuple(
        McsElimination(model=models[index], step_p_value=p_value, mcs_p_value=mcs_p)
        for (index, p_value), mcs_p in zip(steps, cumulative, strict=True)
    )
