"""Serviço de domínio `ChristoffersenTest` — o único serviço de razão de verossimilhança.

stdlib-only (concept 6.3 §4, I2, I5, I6, I8, I13, C4, C6, C9; ADR `6_3_0001` itens
4, 7, 8 e Implementation notes; ADR `6_3_0004` item 2). Sobre uma `HitSequence`
(violação = `True`, lacuna = `None`):

- **trio puro** (convenção FC5, Christoffersen 1998 §3.1-§3.3): transições
  (n00, n01, n10, n11) só entre posições consecutivas **ambas observadas**
  (`count_transitions`, dono único no VO); LR_uc puro = `kupiec_pof(n01 + n11, Σn_ij,
  p)`; LR_ind pela verossimilhança de Markov de 1ª ordem (Christoffersen & Pelletier
  2004 §4.1 — `n11 = 0` é aplicável, 0·log 0 = 0); **LR_cc := LR_uc + LR_ind**,
  composto depois do piso (identidade exata, Christoffersen p. 847);
- **leitura Kupiec**: `kupiec_pof` sobre **todas** as posições observadas (o mesmo
  (x, n) da banda de Wilson) — no trio, a primeira violação observada fica fora do
  n_1 puro;
- **aplicabilidade é resultado** (ADR 6.3.0001 item 7): LR_ind/LR_cc só com status
  `APPLICABLE`, verificado na ordem NO_TRANSITIONS → BELOW_MIN_VIOLATIONS →
  DEGENERATE_TRANSITION_MATRIX (linha **ou** coluna vazia); `min_violations` é `int`
  obrigatório, sem default (valor pré-registrado da 6.5) e conta as violações de
  **todas** as posições observadas;
- toda LR passa pelo piso numérico I13 (`floor_lr_statistic`); p-valores assintóticos
  por `chi_square_sf` (df 1 para POF, LR_uc e LR_ind; df 2 para LR_cc);
- `horizon > 1` marca `independence_descriptive` (B-H7, doc §7.4), salvo na
  sub-série DGT, iid sob a nula de DGT.

Sensibilidades pré-registradas (Task 08): o LR_uc de 3 estados (Christoffersen 1998
§4.2, χ²(2); contagens reais das duas caudas unilaterais sobre todas as observadas -
ADR 6.3.0005 item 2) e o p-valor Monte Carlo com desempate de Dufour (2006, Eq. 2.30)
e referência de LR_ind/LR_cc condicionada ao mesmo evento de aplicabilidade do
observado (ADR 6.3.0006), só em h = 1 e fora de sub-série DGT.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from financial_forecasting.features.evaluation.domain.services.chi_square import (
    chi_square_sf,
    floor_lr_statistic,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
    validate_real_count,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import (
    kupiec_pof,
    xlogy,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
    validate_horizon,
    validate_positive_int,
)
from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
    belongs_to_dgt_partition,
    count_observed,
    count_transitions,
    count_violations,
    validate_hit_identity,
    validate_includes_degenerate,
    validate_kind_and_levels,
    validate_violation_elements,
)

_N_TRANSITIONS = 4
# Teto de tentativas do Monte Carlo: 100·N (ADR 6.3.0006 item 3).
MC_ATTEMPTS_CAP_FACTOR = 100
# Único mapa campo de p-valor -> (estatística, graus de liberdade da χ²): POF, LR_uc e
# LR_ind têm 1; LR_cc tem 2 (Christoffersen 1998 §3.3). Usado pelo `evaluate` e pelo
# `__post_init__` do relatório.
_P_VALUE_FIELDS: Final = (
    ("kupiec_pof_p_value", "kupiec_pof", 1),
    ("p_uc", "lr_uc", 1),
    ("p_ind", "lr_ind", 1),
    ("p_cc", "lr_cc", 2),
)


class IndependenceStatus(StrEnum):
    """Aplicabilidade de LR_ind/LR_cc — verificados NESTA ordem; vale o primeiro."""

    APPLICABLE = "applicable"
    NO_TRANSITIONS = "no_transitions"  # nenhum par consecutivo observado
    BELOW_MIN_VIOLATIONS = "below_min_violations"  # n_violations < min_violations
    # linha vazia (n00+n01 == 0 ou n10+n11 == 0) ou coluna vazia (n00+n10 == 0 ou n01+n11 == 0)
    DEGENERATE_TRANSITION_MATRIX = "degenerate_transition_matrix"


def independence_is_descriptive(*, horizon: int, dgt_step: int | None) -> bool:
    """LR_ind/LR_cc descritivos: multi-passo e fora de sub-série DGT (B-H7; regra única)."""
    return is_multi_step(horizon) and not belongs_to_dgt_partition(dgt_step)


def monte_carlo_defined_for(horizon: int) -> bool:
    """O p-valor Monte Carlo só existe em h = 1 (ADR 6.3.0006 item 7; regra única)."""
    return not is_multi_step(horizon)


def validate_min_violations(min_violations: int) -> None:
    """C4: `min_violations` é `int` (não `bool`) ≥ 0 — obrigatório, sem default."""
    if type(min_violations) is not int or min_violations < 0:
        raise ValueError(f"min_violations must be an int >= 0 (not bool), got {min_violations!r}")


def independence_status_for(
    transitions: tuple[int, int, int, int], *, n_violations: int, min_violations: int
) -> IndependenceStatus:
    """Status de LR_ind/LR_cc pela ordem de precedência (ADR 6.3.0001 item 7)."""
    n00, n01, n10, n11 = transitions
    if n00 + n01 + n10 + n11 == 0:
        return IndependenceStatus.NO_TRANSITIONS
    if n_violations < min_violations:
        return IndependenceStatus.BELOW_MIN_VIOLATIONS
    empty_row = n00 + n01 == 0 or n10 + n11 == 0
    empty_column = n00 + n10 == 0 or n01 + n11 == 0
    if empty_row or empty_column:
        return IndependenceStatus.DEGENERATE_TRANSITION_MATRIX
    return IndependenceStatus.APPLICABLE


@dataclass(frozen=True)
class ChristoffersenStatistics:
    """Saída do primitivo de sequência (trio puro + leitura Kupiec).

    Campos:
        n_observed: posições não-`None`.
        n_violations: violações entre as observadas.
        transitions: (n00, n01, n10, n11) sobre pares consecutivos observados.
        kupiec_pof: POF sobre as `n_observed` posições; `None` ⇔ `n_observed == 0`.
        lr_uc: LR_uc puro `kupiec_pof(n01 + n11, Σn_ij)`; `None` ⇔ Σn_ij == 0.
        lr_ind: `None` ⇔ status ≠ APPLICABLE.
        lr_cc: `lr_uc + lr_ind`, composto após o piso; `None` ⇔ status ≠ APPLICABLE.
        independence_status: o primeiro status que vale, na ordem de precedência.

    Raises:
        ValueError: estatísticas incoerentes (C9), um ramo por invariante.
    """

    n_observed: int
    n_violations: int
    transitions: tuple[int, int, int, int]
    kupiec_pof: float | None
    lr_uc: float | None
    lr_ind: float | None
    lr_cc: float | None
    independence_status: IndependenceStatus

    def __post_init__(self) -> None:
        """C9: contagens, desigualdades do ADR 6.3.0001 e presença das estatísticas."""
        self._check_counts()
        self._check_statistics_presence()
        for name, value in (
            ("kupiec_pof", self.kupiec_pof),
            ("lr_uc", self.lr_uc),
            ("lr_ind", self.lr_ind),
            ("lr_cc", self.lr_cc),
        ):
            if value is not None and not (is_finite_number(value) and value >= 0.0):
                raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
        if (
            self.lr_uc is not None
            and self.lr_ind is not None
            and self.lr_cc is not None
            and self.lr_cc != self.lr_uc + self.lr_ind
        ):
            raise ValueError(
                f"lr_cc must be lr_uc + lr_ind = {self.lr_uc + self.lr_ind!r}, got {self.lr_cc!r}"
            )

    @property
    def n_pairs(self) -> int:
        """Σn_ij — pares consecutivos observados."""
        return sum(self.transitions)

    def _check_counts(self) -> None:
        counts = (self.n_observed, self.n_violations, *self.transitions)
        if len(self.transitions) != _N_TRANSITIONS or any(
            type(value) is not int or value < 0 for value in counts
        ):
            raise ValueError(
                "n_observed, n_violations and the four transitions must be ints >= 0, got "
                f"n_observed={self.n_observed!r}, n_violations={self.n_violations!r}, "
                f"transitions={self.transitions!r}"
            )
        _, n01, n10, n11 = self.transitions
        n_pairs = self.n_pairs
        # As quatro desigualdades exatas do ADR 6.3.0001 (Implementation notes).
        if n_pairs > max(self.n_observed - 1, 0):
            raise ValueError(
                f"sum(transitions)={n_pairs} exceeds max(n_observed - 1, 0) for "
                f"n_observed={self.n_observed}"
            )
        if n01 + n11 > self.n_violations:
            raise ValueError(f"n01 + n11 = {n01 + n11} exceeds n_violations={self.n_violations}")
        if n10 + n11 > self.n_violations:
            raise ValueError(f"n10 + n11 = {n10 + n11} exceeds n_violations={self.n_violations}")
        if self.n_violations - (n01 + n11) > self.n_observed - n_pairs:
            raise ValueError(
                f"n_violations - (n01 + n11) = {self.n_violations - (n01 + n11)} exceeds "
                f"n_observed - sum(transitions) = {self.n_observed - n_pairs}"
            )

    def _check_statistics_presence(self) -> None:
        if (self.kupiec_pof is None) != (self.n_observed == 0):
            raise ValueError(
                f"kupiec_pof must be None exactly when n_observed == 0, got "
                f"kupiec_pof={self.kupiec_pof!r} with n_observed={self.n_observed}"
            )
        if (self.lr_uc is None) != (self.n_pairs == 0):
            raise ValueError(
                f"lr_uc must be None exactly when sum(transitions) == 0, got "
                f"lr_uc={self.lr_uc!r} with sum(transitions)={self.n_pairs}"
            )
        applicable = self.independence_status is IndependenceStatus.APPLICABLE
        for name, value in (("lr_ind", self.lr_ind), ("lr_cc", self.lr_cc)):
            if (value is not None) != applicable:
                raise ValueError(
                    f"{name} must be set exactly when independence_status is APPLICABLE, got "
                    f"{name}={value!r} with {self.independence_status.value}"
                )


def christoffersen_statistics(
    *, violations: Sequence[bool | None], violation_rate: float, min_violations: int
) -> ChristoffersenStatistics:
    """Trio puro + leitura Kupiec sobre uma sequência de violações com lacunas.

    Usado pelo serviço, pelo Monte Carlo e pelos testes de oráculo; valida os
    elementos (`bool` ou `None`, a mesma regra do VO), a taxa e `min_violations`.

    Raises:
        ValueError: elemento que não é `bool`/`None`, `violation_rate` fora de (0, 1)
            ou `min_violations` inválido (C4).
    """
    validate_rate(violation_rate, field="violation_rate")
    validate_min_violations(min_violations)
    validate_violation_elements(violations)
    n_observed = count_observed(violations)
    n_violations = count_violations(violations)
    transitions = count_transitions(violations)
    _, n01, _, n11 = transitions
    n_pairs = sum(transitions)
    pof = (
        kupiec_pof(violations=n_violations, observations=n_observed, violation_rate=violation_rate)
        if n_observed > 0
        else None
    )
    lr_uc = (
        kupiec_pof(violations=n01 + n11, observations=n_pairs, violation_rate=violation_rate)
        if n_pairs > 0
        else None
    )
    status = independence_status_for(
        transitions, n_violations=n_violations, min_violations=min_violations
    )
    lr_ind: float | None = None
    lr_cc: float | None = None
    if status is IndependenceStatus.APPLICABLE and lr_uc is not None:
        lr_ind = floor_lr_statistic(_raw_lr_ind(transitions))
        lr_cc = lr_uc + lr_ind
    return ChristoffersenStatistics(
        n_observed=n_observed,
        n_violations=n_violations,
        transitions=transitions,
        kupiec_pof=pof,
        lr_uc=lr_uc,
        lr_ind=lr_ind,
        lr_cc=lr_cc,
        independence_status=status,
    )


def _raw_lr_ind(transitions: tuple[int, int, int, int]) -> float:
    """-2·[l(π̂) - l(π̂01, π̂11)] (C&P 2004 §4.1), com `xlogy` — antes do piso."""
    n00, n01, n10, n11 = transitions
    n_pairs = n00 + n01 + n10 + n11
    pi = (n01 + n11) / n_pairs
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    null = xlogy(n00 + n10, 1.0 - pi) + xlogy(n01 + n11, pi)
    markov = xlogy(n00, 1.0 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1.0 - pi11) + xlogy(n11, pi11)
    return -2.0 * (null - markov)


@dataclass(frozen=True)
class ChristoffersenReport:
    """Relatório do trio + leitura Kupiec de uma `HitSequence`, com a identidade dela.

    Campos de identidade (copiados da sequência — D8): `horizon`, `kind`, `levels`,
    `violation_rate`, `tolerance`, `degeneracy_rate`, `includes_degenerate`,
    `dgt_offset`, `dgt_step`; `min_violations` usado; `statistics` do primitivo;
    p-valores assintóticos (`None` exatamente quando a estatística é `None`);
    `independence_descriptive` = `horizon > 1` fora de sub-série DGT (B-H7).

    Raises:
        ValueError: relatório incoerente (C9), um ramo por invariante.
    """

    horizon: int
    kind: HitKind
    levels: tuple[float, ...]
    violation_rate: float
    tolerance: float
    degeneracy_rate: float
    includes_degenerate: bool
    dgt_offset: int | None
    dgt_step: int | None
    min_violations: int
    statistics: ChristoffersenStatistics
    kupiec_pof_p_value: float | None
    p_uc: float | None
    p_ind: float | None
    p_cc: float | None
    independence_descriptive: bool

    def __post_init__(self) -> None:
        """C9: identidade copiada (regra do VO), status, p-valores e leitura descritiva."""
        validate_hit_identity(
            horizon=self.horizon,
            kind=self.kind,
            levels=self.levels,
            violation_rate=self.violation_rate,
            tolerance=self.tolerance,
            degeneracy_rate=self.degeneracy_rate,
            includes_degenerate=self.includes_degenerate,
            dgt_offset=self.dgt_offset,
            dgt_step=self.dgt_step,
            tolerance_field="ChristoffersenReport.tolerance",
        )
        validate_min_violations(self.min_violations)
        stats = self.statistics
        expected_status = independence_status_for(
            stats.transitions,
            n_violations=stats.n_violations,
            min_violations=self.min_violations,
        )
        if stats.independence_status is not expected_status:
            raise ValueError(
                f"independence_status must be {expected_status.value} for the transitions "
                f"and min_violations={self.min_violations}, got "
                f"{stats.independence_status.value}"
            )
        for field, statistic, df in _P_VALUE_FIELDS:
            _check_p_value(field, getattr(self, field), getattr(stats, statistic), df)
        expected_descriptive = independence_is_descriptive(
            horizon=self.horizon, dgt_step=self.dgt_step
        )
        if self.independence_descriptive != expected_descriptive:
            raise ValueError(
                "independence_descriptive must be (horizon > 1 and not a DGT sub-series) = "
                f"{expected_descriptive}, got {self.independence_descriptive!r}"
            )


def _check_p_value(name: str, p_value: float | None, statistic: float | None, df: int) -> None:
    if (p_value is None) != (statistic is None):
        raise ValueError(
            f"{name} must be None exactly when its statistic is None, got {name}={p_value!r} "
            f"with statistic={statistic!r}"
        )
    if p_value is None or statistic is None:
        return
    if not (is_finite_number(p_value) and 0.0 <= p_value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {p_value!r}")
    expected = chi_square_sf(statistic, df=df)
    if p_value != expected:
        raise ValueError(
            f"{name} must be chi_square_sf(statistic, df={df}) = {expected!r}, got {p_value!r}"
        )


class ChristoffersenTest:
    """Serviço único de LR sobre uma `HitSequence` (ADR 6.3.0001 item 4)."""

    @staticmethod
    def evaluate(sequence: HitSequence, *, min_violations: int) -> ChristoffersenReport:
        """Trio puro + leitura Kupiec, p-valores χ² e a identidade da sequência.

        Raises:
            ValueError: `min_violations` não-`int`, `bool` ou negativo (C4).
        """
        stats = christoffersen_statistics(
            violations=sequence.violations,
            violation_rate=sequence.violation_rate,
            min_violations=min_violations,
        )
        p_values = {
            field: _p_value(getattr(stats, statistic), df)
            for field, statistic, df in _P_VALUE_FIELDS
        }
        return ChristoffersenReport(
            horizon=sequence.horizon,
            kind=sequence.kind,
            levels=sequence.levels,
            violation_rate=sequence.violation_rate,
            tolerance=sequence.tolerance,
            degeneracy_rate=sequence.degeneracy_rate,
            includes_degenerate=sequence.includes_degenerate,
            dgt_offset=sequence.dgt_offset,
            dgt_step=sequence.dgt_step,
            min_violations=min_violations,
            statistics=stats,
            kupiec_pof_p_value=p_values["kupiec_pof_p_value"],
            p_uc=p_values["p_uc"],
            p_ind=p_values["p_ind"],
            p_cc=p_values["p_cc"],
            independence_descriptive=independence_is_descriptive(
                horizon=sequence.horizon, dgt_step=sequence.dgt_step
            ),
        )

    @staticmethod
    def monte_carlo_p_values(
        sequence: HitSequence, *, min_violations: int, draws: int, seed: int
    ) -> MonteCarloPValues:
        """p-valores MC de LR_uc, LR_ind e LR_cc sob Bernoulli(p) iid (ADR 6.3.0006).

        Ordem do RNG (contrato, item 5): um `random.Random(seed)`; U_0; por tentativa,
        um `random()` por posição **observada**, na ordem (violação ⇔ `< p`; lacunas
        preservadas), e depois o U_i do sorteio. Referência do LR_uc: os N primeiros
        sorteios; de LR_ind/LR_cc: os N primeiros sorteios APPLICABLE (mesmo
        `min_violations`), até o teto de 100·N tentativas (`MC_CAP_REACHED`).

        Raises:
            ValueError: sub-série DGT ou `horizon > 1` (C5, mensagens distintas);
                `min_violations`, `draws` ou `seed` inválidos ou `bool` (C4).
        """
        if sequence.is_dgt_subseries:
            raise ValueError(
                "Monte Carlo p-values are not defined on a DGT sub-series "
                f"(dgt_offset={sequence.dgt_offset}, dgt_step={sequence.dgt_step})"
            )
        if not monte_carlo_defined_for(sequence.horizon):
            raise ValueError(
                "Monte Carlo p-values require horizon == 1 (the (h-1)-dependence under H0 is "
                f"a nuisance parameter), got horizon={sequence.horizon}"
            )
        validate_min_violations(min_violations)
        _validate_draws_and_seed(draws, seed)
        return _monte_carlo(sequence, min_violations=min_violations, draws=draws, seed=seed)


def _p_value(statistic: float | None, df: int) -> float | None:
    return None if statistic is None else chi_square_sf(statistic, df=df)


def lr_uc_three_state(
    *, lower_count: float, upper_count: float, n: float, lower_rate: float, upper_rate: float
) -> float:
    """LR_uc de 3 estados (Christoffersen 1998 §4.2) - χ²(2) sob a nula.

    Estados: y ≤ q̂_{τ_l} (taxa `lower_rate`), y > q̂_{τ_u} (taxa `upper_rate`) e o
    meio. `-2·[l(taxas) - l(p̂)]` multinomial com `xlogy` (0·log 0 = 0) e o piso I13.
    Contagens reais (médias entre seeds) sobre todas as posições observadas (ADR
    6.3.0005 item 2); a validação é a do validador único dos kernels de contagem.

    Raises:
        ValueError: contagem/n fora do validador único, `lower_count + upper_count > n`,
            taxa fora de (0, 1) ou `lower_rate + upper_rate >= 1` (C3).
    """
    validate_real_count(lower_count, n, count_field="lower_count", n_field="n")
    validate_real_count(upper_count, n, count_field="upper_count", n_field="n")
    if lower_count + upper_count > n:
        raise ValueError(
            f"lower_count + upper_count must be <= n={n!r}, got {lower_count!r} + {upper_count!r}"
        )
    validate_rate(lower_rate, field="lower_rate")
    validate_rate(upper_rate, field="upper_rate")
    if lower_rate + upper_rate >= 1.0:
        raise ValueError(
            f"lower_rate + upper_rate must be < 1, got {lower_rate!r} + {upper_rate!r}"
        )
    # `lower_count + upper_count <= n` já vale (checado acima), logo o meio está em
    # [0, n]; com contagens reais a subtração pode sair -1.78e-15 quando a soma iguala n
    # em float — o meio é 0 aí.
    middle = max(0.0, n - lower_count - upper_count)
    null = (
        xlogy(lower_count, lower_rate)
        + xlogy(upper_count, upper_rate)
        + xlogy(middle, 1.0 - lower_rate - upper_rate)
    )
    fitted = (
        xlogy(lower_count, lower_count / n)
        + xlogy(upper_count, upper_count / n)
        + xlogy(middle, middle / n)
    )
    return floor_lr_statistic(-2.0 * (null - fitted))


class MonteCarloStatus(StrEnum):
    """Status de um p-valor Monte Carlo (ADR 6.3.0006 item 3)."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"  # estatística observada não aplicável
    MC_CAP_REACHED = "mc_cap_reached"  # < N sorteios aplicáveis em 100·N tentativas


def mc_p_value(
    *,
    observed: float,
    simulated: Sequence[float],
    uniforms: Sequence[float],
    observed_uniform: float,
) -> float:
    """p-valor Monte Carlo com desempate aleatorizado de Dufour (2006, Eq. 2.30-2.31).

    G̃_N = 1 - (1/N)·Σ1(S_i ≤ S_0) + (1/N)·Σ1(S_i = S_0)·1(U_i ≥ U_0) e
    p̃ = (N·G̃_N + 1)/(N + 1); "≤" e "=" são comparações **exatas** de float (todas as
    estatísticas saem do mesmo primitivo, na mesma ordem de operações). Calculado em
    inteiros: N·G̃_N = N - #(S_i ≤ S_0) + #(S_i = S_0 e U_i ≥ U_0).

    Raises:
        ValueError: `simulated` e `uniforms` de tamanhos diferentes ou vazios.
    """
    draws = len(simulated)
    if draws < 1 or len(uniforms) != draws:
        raise ValueError(
            f"simulated and uniforms must have the same length >= 1, got {draws} and "
            f"{len(uniforms)}"
        )
    at_or_below = sum(1 for value in simulated if value <= observed)
    ties_kept = sum(
        1
        for value, uniform in zip(simulated, uniforms, strict=True)
        if value == observed and uniform >= observed_uniform
    )
    return (draws - at_or_below + ties_kept + 1) / (draws + 1)


@dataclass(frozen=True)
class MonteCarloPValues:
    """p-valores Monte Carlo de LR_uc, LR_ind e LR_cc, autodescritivos (ADR 6.3.0006).

    Campos: identidade da sequência (`horizon`, `kind`, `levels`, `tolerance`,
    `includes_degenerate`); `min_violations` (define o evento A de aplicabilidade);
    `draws` (N), `seed`, `attempts` (sorteios consumidos; 0 sem LR_uc observado);
    `p_uc`/`uc_status`; `p_ind`, `p_cc`/`ind_status`.

    Raises:
        ValueError: resultado incoerente (C9), um ramo por invariante.
    """

    horizon: int
    kind: HitKind
    levels: tuple[float, ...]
    tolerance: float
    includes_degenerate: bool
    min_violations: int
    draws: int
    seed: int
    attempts: int
    p_uc: float | None
    uc_status: MonteCarloStatus
    p_ind: float | None
    p_cc: float | None
    ind_status: MonteCarloStatus

    def __post_init__(self) -> None:
        """C9: parâmetros, status, presença dos p-valores e contagem de tentativas."""
        validate_horizon(self.horizon, field="horizon")
        if not monte_carlo_defined_for(self.horizon):
            raise ValueError(
                f"Monte Carlo p-values exist only for horizon == 1, got {self.horizon}"
            )
        validate_kind_and_levels(self.kind, self.levels)
        validate_tolerance(self.tolerance, field="MonteCarloPValues.tolerance")
        validate_includes_degenerate(self.includes_degenerate)
        validate_min_violations(self.min_violations)
        _validate_draws_and_seed(self.draws, self.seed)
        for name, p_value in (("p_uc", self.p_uc), ("p_ind", self.p_ind), ("p_cc", self.p_cc)):
            if p_value is not None and not (is_finite_number(p_value) and 0.0 <= p_value <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {p_value!r}")
        if self.uc_status is MonteCarloStatus.MC_CAP_REACHED:
            raise ValueError("uc_status is never MC_CAP_REACHED (every draw has LR_uc)")
        uc_applicable = self.uc_status is MonteCarloStatus.APPLICABLE
        if (self.p_uc is not None) != uc_applicable:
            raise ValueError(
                f"p_uc must be set exactly when uc_status is APPLICABLE, got p_uc={self.p_uc!r} "
                f"with {self.uc_status.value}"
            )
        ind_applicable = self.ind_status is MonteCarloStatus.APPLICABLE
        for name, p_value in (("p_ind", self.p_ind), ("p_cc", self.p_cc)):
            if (p_value is not None) != ind_applicable:
                raise ValueError(
                    f"{name} must be set exactly when ind_status is APPLICABLE, got "
                    f"{name}={p_value!r} with {self.ind_status.value}"
                )
        self._check_attempts(uc_applicable=uc_applicable)

    def _check_attempts(self, *, uc_applicable: bool) -> None:
        cap = MC_ATTEMPTS_CAP_FACTOR * self.draws
        if type(self.attempts) is not int:
            raise ValueError(f"attempts must be an int, got {self.attempts!r}")
        if not uc_applicable:
            if self.attempts != 0 or self.ind_status is not MonteCarloStatus.NOT_APPLICABLE:
                raise ValueError(
                    "without an observed LR_uc nothing is drawn: attempts must be 0 and "
                    f"ind_status not_applicable, got attempts={self.attempts}, "
                    f"ind_status={self.ind_status.value}"
                )
            return
        if not self.draws <= self.attempts <= cap:
            raise ValueError(
                f"attempts must be in [draws, 100*draws] = [{self.draws}, {cap}], "
                f"got {self.attempts}"
            )
        if self.ind_status is MonteCarloStatus.NOT_APPLICABLE and self.attempts != self.draws:
            raise ValueError(
                "with ind_status not_applicable there is no redraw: attempts must equal "
                f"draws={self.draws}, got {self.attempts}"
            )
        if self.ind_status is MonteCarloStatus.MC_CAP_REACHED and self.attempts != cap:
            raise ValueError(
                f"mc_cap_reached means the cap was used: attempts must be {cap}, "
                f"got {self.attempts}"
            )


def _validate_draws_and_seed(draws: int, seed: int) -> None:
    validate_positive_int(draws, field="draws")
    if type(seed) is not int:
        raise ValueError(f"seed must be an int (not bool), got {seed!r}")


def _monte_carlo(
    sequence: HitSequence, *, min_violations: int, draws: int, seed: int
) -> MonteCarloPValues:
    """Laço do ADR 6.3.0006 itens 2-5 (parâmetros já validados)."""
    rate = sequence.violation_rate
    observed = christoffersen_statistics(
        violations=sequence.violations, violation_rate=rate, min_violations=min_violations
    )
    if observed.lr_uc is None:
        return _mc_result(
            sequence,
            min_violations=min_violations,
            draws=draws,
            seed=seed,
            attempts=0,
            p_uc=None,
            p_ind_cc=(None, None),
            ind_status=MonteCarloStatus.NOT_APPLICABLE,
        )
    ind_observed = observed.independence_status is IndependenceStatus.APPLICABLE
    rng = random.Random(seed)  # simulação reprodutível (não criptográfica)
    observed_uniform = rng.random()
    uc_values: list[float] = []
    uc_uniforms: list[float] = []
    ind_values: list[float] = []
    cc_values: list[float] = []
    ind_uniforms: list[float] = []
    cap = MC_ATTEMPTS_CAP_FACTOR * draws
    attempts = 0
    while attempts < cap and (len(uc_values) < draws or (ind_observed and len(ind_values) < draws)):
        drawn = tuple(
            None if value is None else rng.random() < rate for value in sequence.violations
        )
        uniform = rng.random()
        attempts += 1
        stats = christoffersen_statistics(
            violations=drawn, violation_rate=rate, min_violations=min_violations
        )
        if len(uc_values) < draws and stats.lr_uc is not None:
            uc_values.append(stats.lr_uc)
            uc_uniforms.append(uniform)
        if (
            ind_observed
            and len(ind_values) < draws
            and stats.lr_ind is not None
            and stats.lr_cc is not None
        ):
            ind_values.append(stats.lr_ind)
            cc_values.append(stats.lr_cc)
            ind_uniforms.append(uniform)
    p_uc = mc_p_value(
        observed=observed.lr_uc,
        simulated=uc_values,
        uniforms=uc_uniforms,
        observed_uniform=observed_uniform,
    )
    ind_status = MonteCarloStatus.NOT_APPLICABLE
    p_ind_cc: tuple[float | None, float | None] = (None, None)
    if ind_observed and observed.lr_ind is not None and observed.lr_cc is not None:
        if len(ind_values) == draws:
            ind_status = MonteCarloStatus.APPLICABLE
            p_ind_cc = (
                mc_p_value(
                    observed=observed.lr_ind,
                    simulated=ind_values,
                    uniforms=ind_uniforms,
                    observed_uniform=observed_uniform,
                ),
                mc_p_value(
                    observed=observed.lr_cc,
                    simulated=cc_values,
                    uniforms=ind_uniforms,
                    observed_uniform=observed_uniform,
                ),
            )
        else:
            ind_status = MonteCarloStatus.MC_CAP_REACHED
    return _mc_result(
        sequence,
        min_violations=min_violations,
        draws=draws,
        seed=seed,
        attempts=attempts,
        p_uc=p_uc,
        p_ind_cc=p_ind_cc,
        ind_status=ind_status,
    )


def _mc_result(  # noqa: PLR0913 - a sequência + os campos do resultado (keyword-only)
    sequence: HitSequence,
    *,
    min_violations: int,
    draws: int,
    seed: int,
    attempts: int,
    p_uc: float | None,
    p_ind_cc: tuple[float | None, float | None],
    ind_status: MonteCarloStatus,
) -> MonteCarloPValues:
    return MonteCarloPValues(
        horizon=sequence.horizon,
        kind=sequence.kind,
        levels=sequence.levels,
        tolerance=sequence.tolerance,
        includes_degenerate=sequence.includes_degenerate,
        min_violations=min_violations,
        draws=draws,
        seed=seed,
        attempts=attempts,
        p_uc=p_uc,
        uc_status=MonteCarloStatus.NOT_APPLICABLE if p_uc is None else MonteCarloStatus.APPLICABLE,
        p_ind=p_ind_cc[0],
        p_cc=p_ind_cc[1],
        ind_status=ind_status,
    )
