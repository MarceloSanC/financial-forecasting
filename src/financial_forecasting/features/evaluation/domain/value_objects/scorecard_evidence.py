"""VOs de evidência do scorecard confirmatório, por horizonte (Stage 6.5).

Value objects de domínio **frozen, stdlib-only** (concept 6.5 §4 "Evidência por
horizonte", D6, D8, I8, I11; ADRs `6_5_0006` itens 1-7, `6_5_0008` item 2). São
o que o mapeador da application monta a partir das linhas do gold e o que o
`H1Gate`, o `ConfirmatoryScorecard` e o perfil consomem — nada aqui é
recomputado do gold (I8): só médias entre seeds de colunas persistidas.

- `SeedTailCounts` — as contagens de uma seed numa cauda (`seed = None` nos
  modelos sem seed);
- `TailEvidence` — uma cauda (nível τ) com as contagens por seed; a estimativa da
  banda é a **razão de médias** c̄/n̄ (a entrada dos kernels de contagem, ADR
  6.3.0005); a média das taxas por seed vai só ao perfil (ADR 6.5.0006 item 2);
- `DgtTailEvidence` / `CalibrationEvidence` — as duas caudas de uma amostra, com
  as sub-séries DGT (offsets 0..h-1, passo h) quando h > 1;
- `ComparatorCalibration`, `DmEvidence`, `McsEvidence`, `HorizonEvidence`;
- `SeedSpread.of(values)` — dono da agregação entre seeds dos descritores do
  perfil (média, mínimo, máximo).

n nunca é S·T (I11): cada `SeedTailCounts.n_observed` é o n de **um** conjunto
alinhado; as médias são entre seeds.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
    validate_horizon,
    validate_positive_int,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)

GATE_SAMPLE: Final = "model_full"
"""Amostra do gate H1 (ADR 6.5.0006 item 1)."""

COMMON_SAMPLE: Final = "common"
"""Amostra comum da comparação (doc §6.7; ADR 6.4.0007)."""


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _check_text(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty str, got {value!r}")


def _check_count(value: object, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be an int >= 0, got {value!r}")


def _check_tuple_of(value: object, kind: type, *, field: str, allow_empty: bool) -> None:
    if not isinstance(value, tuple) or (not value and not allow_empty):
        raise ValueError(
            f"{field} must be a {'' if allow_empty else 'non-empty '}tuple, got {value!r}"
        )
    for item in value:
        if not isinstance(item, kind):
            raise ValueError(f"{field} must hold {kind.__name__}, got {item!r}")


@dataclass(frozen=True)
class SeedTailCounts:
    """Contagens de uma seed numa cauda: violações, pontos observados e degeneração.

    Raises:
        ValueError: `seed` não-`int`/`bool`/negativa (ou não `None`); contagens não
            inteiras ≥ 0; `n_violations > n_observed`; degeneração fora de [0, 1].
    """

    seed: int | None
    n_violations: int
    n_observed: int
    degeneracy_rate: float

    def __post_init__(self) -> None:
        """Forma de cada campo e `n_violations ≤ n_observed`."""
        if self.seed is not None:
            _check_count(self.seed, field="seed")
        _check_count(self.n_violations, field="n_violations")
        _check_count(self.n_observed, field="n_observed")
        if self.n_violations > self.n_observed:
            raise ValueError(
                f"n_violations must be <= n_observed, got {self.n_violations} > {self.n_observed}"
            )
        rate = self.degeneracy_rate
        if not is_finite_number(rate) or not 0.0 <= rate <= 1.0:
            raise ValueError(f"degeneracy_rate must be a finite number in [0, 1], got {rate!r}")


@dataclass(frozen=True)
class TailEvidence:
    """Uma cauda (nível τ) com as contagens de cada seed (seeds distintas).

    Raises:
        ValueError: nível fora de (0, 1); `seeds` vazio, com outro tipo ou seed repetida.
    """

    level: float
    seeds: tuple[SeedTailCounts, ...]

    def __post_init__(self) -> None:
        """Nível pelo dono; seeds não vazias e distintas."""
        validate_rate(self.level, field="level")
        _check_tuple_of(self.seeds, SeedTailCounts, field="seeds", allow_empty=False)
        ids = [counts.seed for counts in self.seeds]
        if len(set(ids)) != len(ids):
            raise ValueError(f"seeds must be distinct, got {ids}")

    @property
    def seed_ids(self) -> tuple[int | None, ...]:
        """As seeds, na ordem."""
        return tuple(counts.seed for counts in self.seeds)

    @property
    def mean_violations(self) -> float:
        """c̄: média das violações entre seeds."""
        return _mean([counts.n_violations for counts in self.seeds])

    @property
    def mean_observed(self) -> float:
        """n̄: média dos pontos não-degenerados entre seeds (nunca S·T)."""
        return _mean([counts.n_observed for counts in self.seeds])

    @property
    def mean_degeneracy(self) -> float:
        """Média da taxa de degeneração entre seeds."""
        return _mean([counts.degeneracy_rate for counts in self.seeds])

    @property
    def mean_of_seed_rates(self) -> float | None:
        """Média das taxas ĉ_s = c_s/n_s (só perfil); `None` se nenhuma seed tem n > 0."""
        rates = [c.n_violations / c.n_observed for c in self.seeds if c.n_observed > 0]
        return _mean(rates) if rates else None


def _check_same_seeds(first: TailEvidence, second: TailEvidence, *, field: str) -> None:
    if first.seed_ids != second.seed_ids:
        raise ValueError(
            f"{field}: the two tails must have the same seeds, got {list(first.seed_ids)} and "
            f"{list(second.seed_ids)}"
        )


def _check_same_series(lower: TailEvidence, upper: TailEvidence, *, field: str) -> None:
    """As duas caudas de uma série: mesmas seeds e, por seed, o mesmo n e a mesma degeneração.

    `n_observed` e `degeneracy_rate` são da **série** (pontos não-degenerados e fração
    degenerada do conjunto alinhado), não da cauda — iguais nas duas caudas por
    construção da 6.4 (`HitSequence`); divergir é evidência incoerente.
    """
    _check_same_seeds(lower, upper, field=field)
    for low, up in zip(lower.seeds, upper.seeds, strict=True):
        if (low.n_observed, low.degeneracy_rate) != (up.n_observed, up.degeneracy_rate):
            raise ValueError(
                f"{field}: seed {low.seed} must have the same n_observed and degeneracy_rate "
                f"in the two tails, got ({low.n_observed}, {low.degeneracy_rate!r}) and "
                f"({up.n_observed}, {up.degeneracy_rate!r})"
            )


@dataclass(frozen=True)
class DgtTailEvidence:
    """As duas caudas de uma sub-série DGT (offset k, passo h)."""

    offset: int
    step: int
    lower: TailEvidence
    upper: TailEvidence

    def __post_init__(self) -> None:
        """Passo ≥ 2, offset em [0, passo) e as mesmas seeds nas duas caudas."""
        validate_positive_int(self.step, field="step")
        if not is_multi_step(self.step):
            raise ValueError(f"step must be >= 2 (a DGT sub-series), got {self.step}")
        _check_count(self.offset, field="offset")
        if self.offset >= self.step:
            raise ValueError(f"offset must be < step={self.step}, got {self.offset}")
        _check_same_series(self.lower, self.upper, field=f"dgt offset {self.offset}")


@dataclass(frozen=True)
class CalibrationEvidence:
    """As duas caudas de uma amostra e as sub-séries DGT (vazias ou completas).

    Raises:
        ValueError: amostra vazia; caudas com seeds diferentes; DGT com passo
            diferente entre sub-séries, offsets fora de 0..passo-1 ou seeds diferentes
            das da série inteira.
    """

    sample: str
    lower: TailEvidence
    upper: TailEvidence
    dgt: tuple[DgtTailEvidence, ...]

    def __post_init__(self) -> None:
        """Seeds iguais nas caudas e em cada sub-série; DGT completo quando presente."""
        _check_text(self.sample, field="sample")
        _check_same_series(self.lower, self.upper, field=f"sample {self.sample}")
        _check_tuple_of(self.dgt, DgtTailEvidence, field="dgt", allow_empty=True)
        if not self.dgt:
            return
        steps = {sub.step for sub in self.dgt}
        if len(steps) != 1:
            raise ValueError(f"dgt sub-series must share one step, got {sorted(steps)}")
        (step,) = steps
        offsets = [sub.offset for sub in self.dgt]
        if offsets != list(range(step)):
            raise ValueError(f"dgt offsets must be 0..{step - 1} in order, got {offsets}")
        for sub in self.dgt:
            _check_same_seeds(self.lower, sub.lower, field=f"dgt offset {sub.offset}")

    @property
    def mean_degeneracy(self) -> float:
        """Degeneração média da amostra (a taxa é da série: igual nas duas caudas)."""
        return self.lower.mean_degeneracy


@dataclass(frozen=True)
class ComparatorCalibration:
    """Calibração de um comparador no par do gate (perfil de H1, doc §6.4)."""

    model: str
    lower: TailEvidence
    upper: TailEvidence

    def __post_init__(self) -> None:
        """Nome não vazio e as mesmas seeds nas duas caudas."""
        _check_text(self.model, field="model")
        _check_same_series(self.lower, self.upper, field=f"comparator {self.model}")


@dataclass(frozen=True)
class DmEvidence:
    """Uma linha do DM candidato x comparador (colunas persistidas; ADR 6.5.0006 item 6)."""

    comparator: str
    estimator: DmVarianceEstimator
    n_points: int
    mean_differential: float
    statistic: float
    adjusted_p_value: float
    rejected: bool
    fallback_applied: bool

    def __post_init__(self) -> None:
        """Forma: nome, enum, T ≥ 1, números finitos, p em [0, 1], flags `bool`."""
        _check_text(self.comparator, field="comparator")
        if not isinstance(self.estimator, DmVarianceEstimator):
            raise ValueError(f"estimator must be a DmVarianceEstimator, got {self.estimator!r}")
        validate_positive_int(self.n_points, field="n_points")
        for name in ("mean_differential", "statistic"):
            if not is_finite_number(getattr(self, name)):
                raise ValueError(f"{name} must be a finite number, got {getattr(self, name)!r}")
        p_value = self.adjusted_p_value
        if not is_finite_number(p_value) or not 0.0 <= p_value <= 1.0:
            raise ValueError(f"adjusted_p_value must be in [0, 1], got {p_value!r}")
        for name in ("rejected", "fallback_applied"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a bool, got {getattr(self, name)!r}")


@dataclass(frozen=True)
class McsEvidence:
    """Pertença de um modelo ao MCS de um esquema (ADR 6.5.0006 item 6)."""

    scheme: BootstrapScheme
    model: str
    included: bool

    def __post_init__(self) -> None:
        """Esquema do enum, nome não vazio, `included` `bool`."""
        if not isinstance(self.scheme, BootstrapScheme):
            raise ValueError(f"scheme must be a BootstrapScheme, got {self.scheme!r}")
        _check_text(self.model, field="model")
        if not isinstance(self.included, bool):
            raise ValueError(f"included must be a bool, got {self.included!r}")


@dataclass(frozen=True, kw_only=True)
class HorizonEvidence:
    """Tudo o que o veredito e o perfil de um horizonte leem do gold.

    Campos:
        horizon: o horizonte (≥ 1).
        common_points: T da amostra comum (o `n_points` do DM do horizonte).
        gate: caudas do candidato em `model_full` (com DGT completo se h > 1).
        common: caudas do candidato na amostra comum (sensibilidade do gate).
        comparators_calibration: calibração de cada comparador (perfil).
        mean_pinball: P̄_G por modelo na amostra comum (informação, ADR 6.5.0007 item 4).
        dm: linhas do DM (todos os estimadores).
        mcs: pertença ao MCS (todos os esquemas).

    Raises:
        ValueError: evidência incoerente — amostras trocadas, DGT que não é o do
            horizonte, DM com T ≠ `common_points`, par (comparador, estimador) ou
            (esquema, modelo) repetido, P̄_G não finito.
    """

    horizon: int
    common_points: int
    gate: CalibrationEvidence
    common: CalibrationEvidence
    comparators_calibration: tuple[ComparatorCalibration, ...]
    mean_pinball: Mapping[str, float]
    dm: tuple[DmEvidence, ...]
    mcs: tuple[McsEvidence, ...]

    def __post_init__(self) -> None:
        """Coerência entre as partes (ver Raises)."""
        validate_horizon(self.horizon, field="horizon")
        validate_positive_int(self.common_points, field="common_points")
        self._check_samples()
        _check_tuple_of(
            self.comparators_calibration,
            ComparatorCalibration,
            field="comparators_calibration",
            allow_empty=True,
        )
        models = [entry.model for entry in self.comparators_calibration]
        if len(set(models)) != len(models):
            raise ValueError(f"comparators_calibration repeats a model: {models}")
        if not isinstance(self.mean_pinball, Mapping):
            raise ValueError(f"mean_pinball must be a Mapping, got {self.mean_pinball!r}")
        for model, value in self.mean_pinball.items():
            if not is_finite_number(value) or value < 0.0:
                raise ValueError(f"mean_pinball[{model!r}] must be a finite number >= 0")
        object.__setattr__(self, "mean_pinball", MappingProxyType(dict(self.mean_pinball)))
        self._check_dm()
        self._check_mcs()

    def _check_samples(self) -> None:
        for name, expected in (("gate", GATE_SAMPLE), ("common", COMMON_SAMPLE)):
            evidence = getattr(self, name)
            if not isinstance(evidence, CalibrationEvidence):
                raise ValueError(f"{name} must be a CalibrationEvidence, got {evidence!r}")
            if evidence.sample != expected:
                raise ValueError(f"{name}.sample must be {expected!r}, got {evidence.sample!r}")
        if is_multi_step(self.horizon):
            if len(self.gate.dgt) != self.horizon:
                raise ValueError(
                    f"gate.dgt must hold the {self.horizon} sub-series of horizon {self.horizon} "
                    f"(offsets 0..{self.horizon - 1}), got {len(self.gate.dgt)}"
                )
        elif self.gate.dgt:
            raise ValueError("horizon 1 has no DGT sub-series, gate.dgt must be empty")
        if self.common.dgt and self.common.dgt[0].step != self.horizon:
            raise ValueError(f"common.dgt step must be the horizon {self.horizon}")

    def _check_dm(self) -> None:
        _check_tuple_of(self.dm, DmEvidence, field="dm", allow_empty=True)
        pairs = [(row.comparator, row.estimator) for row in self.dm]
        if len(set(pairs)) != len(pairs):
            raise ValueError(f"dm repeats a (comparator, estimator) pair: {pairs}")
        points = sorted({row.n_points for row in self.dm})
        if points and points != [self.common_points]:
            raise ValueError(
                f"dm n_points must equal common_points={self.common_points}, got {points}"
            )

    def _check_mcs(self) -> None:
        _check_tuple_of(self.mcs, McsEvidence, field="mcs", allow_empty=True)
        pairs = [(row.scheme, row.model) for row in self.mcs]
        if len(set(pairs)) != len(pairs):
            raise ValueError(f"mcs repeats a (scheme, model) pair: {pairs}")


@dataclass(frozen=True)
class SeedSpread:
    """Média, mínimo e máximo entre seeds de um descritor (perfil; ADR 6.5.0008 item 2)."""

    mean: float
    minimum: float
    maximum: float
    n_seeds: int

    def __post_init__(self) -> None:
        """`minimum ≤ mean ≤ maximum`, todos finitos; `n_seeds ≥ 1`."""
        validate_positive_int(self.n_seeds, field="n_seeds")
        values = (self.minimum, self.mean, self.maximum)
        if not all(is_finite_number(value) for value in values):
            raise ValueError(f"a SeedSpread needs finite numbers, got {values}")
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError(f"a SeedSpread needs minimum <= mean <= maximum, got {values}")

    @classmethod
    def of(cls, values: Sequence[float]) -> SeedSpread:
        """A agregação entre seeds — dono único da regra `mean_...` dos descritores.

        Raises:
            ValueError: sequência vazia ou valor não finito.
        """
        if len(values) == 0:
            raise ValueError("a SeedSpread needs at least one value")
        for value in values:
            if not is_finite_number(value):
                raise ValueError(f"a SeedSpread needs finite numbers, got {value!r}")
        mean = _mean(values)
        # a média em float pode sair 1 ULP fora de [min, max] com valores iguais
        return cls(
            mean=min(max(mean, min(values)), max(values)),
            minimum=min(values),
            maximum=max(values),
            n_seeds=len(values),
        )
