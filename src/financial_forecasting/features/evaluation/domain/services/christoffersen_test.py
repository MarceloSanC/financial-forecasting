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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.services.chi_square import (
    chi_square_sf,
    floor_lr_statistic,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import (
    kupiec_pof,
    xlogy,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
    count_transitions,
)

_DF_ONE = 1
_N_TRANSITIONS = 4
_DF_TWO = 2


class IndependenceStatus(StrEnum):
    """Aplicabilidade de LR_ind/LR_cc — verificados NESTA ordem; vale o primeiro."""

    APPLICABLE = "applicable"
    NO_TRANSITIONS = "no_transitions"  # nenhum par consecutivo observado
    BELOW_MIN_VIOLATIONS = "below_min_violations"  # n_violations < min_violations
    # linha vazia (n00+n01 == 0 ou n10+n11 == 0) ou coluna vazia (n00+n10 == 0 ou n01+n11 == 0)
    DEGENERATE_TRANSITION_MATRIX = "degenerate_transition_matrix"


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
    for index, value in enumerate(violations):
        if value is not None and type(value) is not bool:
            raise ValueError(f"violations[{index}] must be a bool or None, got {value!r}")
    n_observed = sum(1 for value in violations if value is not None)
    n_violations = sum(1 for value in violations if value is True)
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
        """C9: horizonte, status, p-valores e leitura descritiva coerentes."""
        validate_horizon(self.horizon, field="horizon")
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
        for name, p_value, statistic, df in (
            ("kupiec_pof_p_value", self.kupiec_pof_p_value, stats.kupiec_pof, _DF_ONE),
            ("p_uc", self.p_uc, stats.lr_uc, _DF_ONE),
            ("p_ind", self.p_ind, stats.lr_ind, _DF_ONE),
            ("p_cc", self.p_cc, stats.lr_cc, _DF_TWO),
        ):
            _check_p_value(name, p_value, statistic, df)
        expected_descriptive = self.horizon > 1 and self.dgt_offset is None
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
            kupiec_pof_p_value=_p_value(stats.kupiec_pof, _DF_ONE),
            p_uc=_p_value(stats.lr_uc, _DF_ONE),
            p_ind=_p_value(stats.lr_ind, _DF_ONE),
            p_cc=_p_value(stats.lr_cc, _DF_TWO),
            independence_descriptive=sequence.horizon > 1 and not sequence.is_dgt_subseries,
        )


def _p_value(statistic: float | None, df: int) -> float | None:
    return None if statistic is None else chi_square_sf(statistic, df=df)
