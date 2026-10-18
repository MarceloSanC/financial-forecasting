"""Serviço de domínio `ConformalCoverage` — cobertura conformal na série nativa (ADR 7.2.0004).

stdlib-only (concept 7.2 §4, I8, I9; C6). Nenhuma regra re-derivada:

- máscara: `DegeneracyGate.evaluate(series.native, tolerance=…)`, a da série nativa
  embutida, então `n_evaluated` é o do `CoverageMetrics` da mesma série;
- ĉ por cauda: `is_at_or_below(y, L)` e `is_at_or_below(y, U)` (empate conta);
- PICP: `is_inside_closed(y, L, U)` (bordas dentro); intervalo cruzado (L > U) não
  cobre, entra no MPIW com a largura U - L como está e conta como cruzado;
- nominal do par: `pair_nominal`; banda: `WilsonBand.evaluate` por cauda e nível de
  banda, com nominal τ_lo (cauda inferior) e τ_hi (cauda superior);
- MPIW infinito quando algum limite mantido é infinito (sinalizado);
- aninhamento: fração das linhas mantidas cujos limites não seguem
  L(τ_1) ≤ … ≤ L(τ_m) ≤ U(τ_m) ≤ … ≤ U(τ_1).

Série nativa 100 % degenerada ⇒ relatório "não aplicável" (C6), não erro. Todo
relatório carrega `EMPIRICAL_COVERAGE_LABEL` (I9), validado na construção.

`seed_mean` agrega as seeds completas de um (horizonte, variante): c̄, n̄, a estimativa
c̄/n̄ (a base da banda, ADR 6.5.0006 item 2) e, ao lado, a média das coberturas por seed
com o dp amostral (o literal do doc §4.9 e do ADR 0.0.0008 item 9). PICP, MPIW,
cruzamento e aninhamento também saem "pelas duas médias" (concept 7.2 §4): a contada
(c̄/n̄; MPIW ponderado por n) e a média simples por seed com o dp.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
    DegeneracyReport,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBand,
    WilsonBandReport,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import is_int
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    is_at_or_below,
    is_inside_closed,
    pair_nominal,
)

EMPIRICAL_COVERAGE_LABEL: Final = "cobertura empírica (não garantida)"
_MIN_SEEDS_FOR_SD = 2


def _check_label(label: str, owner: str) -> None:
    if label != EMPIRICAL_COVERAGE_LABEL:
        raise ValueError(f"a {owner} must carry EMPIRICAL_COVERAGE_LABEL, got {label!r}")


@dataclass(frozen=True)
class ConformalTailCoverage:
    """ĉ de uma cauda conformal e a banda de Wilson em cada nível de banda."""

    level: float  # τ da cauda (o nominal da banda)
    count_at_or_below: int
    coverage: float
    bands: tuple[WilsonBandReport, ...]  # um por nível de banda


@dataclass(frozen=True)
class ConformalPairCoverage:
    """PICP, MPIW, cruzamento e as duas caudas de um par conformal."""

    lower_level: float
    upper_level: float
    nominal: float
    picp: float
    mpiw: float
    mpiw_infinite: bool
    crossed_rate: float
    lower_tail: ConformalTailCoverage
    upper_tail: ConformalTailCoverage
    covered_count: int  # linhas com L ≤ y ≤ U (base da média c̄/n̄ entre seeds)
    crossed_count: int  # linhas com L > U


@dataclass(frozen=True)
class ConformalCoverageReport:
    """Cobertura conformal de uma (seed, horizonte, variante) sobre a série nativa."""

    seed: int
    horizon: int
    variant: str
    n_points: int
    n_evaluated: int
    applicable: bool
    degeneracy: DegeneracyReport  # o da série nativa embutida
    per_pair: tuple[ConformalPairCoverage, ...]
    nesting_violation_rate: float | None
    nesting_violation_count: int | None = None
    label: str = EMPIRICAL_COVERAGE_LABEL

    def __post_init__(self) -> None:
        _check_label(self.label, "ConformalCoverageReport")
        expected = self.n_points - self.degeneracy.n_degenerate
        if self.degeneracy.n_points != self.n_points or self.n_evaluated != expected:
            raise ValueError(
                f"n_evaluated={self.n_evaluated} must be n_points - n_degenerate = {expected}"
            )
        if self.applicable != (self.n_evaluated > 0):
            raise ValueError(
                f"applicable must be (n_evaluated > 0), got {self.applicable!r} with "
                f"n_evaluated={self.n_evaluated}"
            )
        if not self.applicable and (self.per_pair or self.nesting_violation_rate is not None):
            raise ValueError("a non-applicable report has no per_pair and no nesting rate")
        if self.applicable:
            self._check_counts()

    def _check_counts(self) -> None:
        """Contagens presentes, em [0, n] e coerentes com as taxas (aninhamento, par)."""
        n = self.n_evaluated
        count = self.nesting_violation_count
        if count is None or not 0 <= count <= n or self.nesting_violation_rate != count / n:
            raise ValueError(
                f"nesting_violation_count={count!r} and nesting_violation_rate="
                f"{self.nesting_violation_rate!r} must agree over n_evaluated={n}"
            )
        for pair in self.per_pair:
            for name, value, rate in (
                ("covered_count", pair.covered_count, pair.picp),
                ("crossed_count", pair.crossed_count, pair.crossed_rate),
            ):
                if not 0 <= value <= n or rate != value / n:
                    raise ValueError(
                        f"pair ({pair.lower_level}, {pair.upper_level}): {name}={value} and its "
                        f"rate {rate} must agree over n_evaluated={n}"
                    )


@dataclass(frozen=True)
class ConformalSeedMeanTail:
    """Média entre seeds de uma cauda: c̄, c̄/n̄ (com banda) e a média das coberturas."""

    level: float
    mean_count: float  # c̄
    coverage: float  # c̄ / n̄ (estimativa da banda)
    mean_of_seed_coverages: float
    sd_of_seed_coverages: float | None  # dp amostral; None com uma seed
    bands: tuple[WilsonBandReport, ...]  # Wilson em (c̄, n̄), nominal τ


@dataclass(frozen=True)
class ConformalSeedMeanPair:
    """Média entre seeds de um par: PICP pelas duas médias, MPIW, cruzamento e caudas."""

    lower_level: float
    upper_level: float
    nominal: float
    picp: float  # c̄_dentro / n̄
    mean_of_seed_picps: float
    sd_of_seed_picps: float | None
    mpiw: float  # Σ n_s·MPIW_s / Σ n_s (infinito se alguma seed for infinita)
    mpiw_infinite: bool
    mean_of_seed_mpiws: float  # média simples dos MPIW por seed (infinita se alguma for)
    sd_of_seed_mpiws: float | None  # None com uma seed ou com MPIW infinito
    crossed_rate: float  # c̄_cruzado / n̄
    mean_of_seed_crossed_rates: float
    sd_of_seed_crossed_rates: float | None
    lower_tail: ConformalSeedMeanTail
    upper_tail: ConformalSeedMeanTail


@dataclass(frozen=True)
class ConformalSeedMeanCoverage:
    """Média entre as seeds completas de um (horizonte, variante)."""

    horizon: int
    variant: str
    applicable: bool  # False ⇔ zero seeds usadas (status undefined)
    seeds_used: tuple[int, ...]
    seeds_excluded: tuple[int, ...]  # expected_seeds - seeds_used
    n_mean: float | None  # n̄ = média dos n_evaluated das seeds usadas
    per_pair: tuple[ConformalSeedMeanPair, ...]
    nesting_violation_rate: float | None  # c̄_violação / n̄
    mean_of_seed_nesting_rates: float | None = None
    sd_of_seed_nesting_rates: float | None = None
    label: str = EMPIRICAL_COVERAGE_LABEL

    def __post_init__(self) -> None:
        _check_label(self.label, "ConformalSeedMeanCoverage")
        if self.applicable != bool(self.seeds_used):
            raise ValueError("applicable must be (seeds_used is not empty)")
        if not self.applicable and (self.per_pair or self.n_mean is not None):
            raise ValueError("a non-applicable seed mean has no per_pair and no n_mean")


def _tail(
    *, level: float, count: int, n: int, horizon: int, band_levels: tuple[float, ...]
) -> ConformalTailCoverage:
    return ConformalTailCoverage(
        level=level,
        count_at_or_below=count,
        coverage=count / n,
        bands=tuple(
            WilsonBand.evaluate(
                horizon=horizon, count=count, n=n, nominal=level, band_level=band_level
            )
            for band_level in band_levels
        ),
    )


def _pair_coverage(
    series: ConformalCoverageSeries,
    limits: ConformalPairLimits,
    kept: list[int],
    band_levels: tuple[float, ...],
) -> ConformalPairCoverage:
    realized = series.native.realized
    n = len(kept)
    horizon = series.native.horizon
    below_lower = sum(1 for i in kept if is_at_or_below(realized[i], limits.lower[i]))
    below_upper = sum(1 for i in kept if is_at_or_below(realized[i], limits.upper[i]))
    covered = sum(
        1 for i in kept if is_inside_closed(realized[i], limits.lower[i], limits.upper[i])
    )
    crossed = sum(1 for i in kept if limits.lower[i] > limits.upper[i])
    infinite = any(math.isinf(limits.lower[i]) or math.isinf(limits.upper[i]) for i in kept)
    mpiw = math.inf if infinite else math.fsum(limits.upper[i] - limits.lower[i] for i in kept) / n
    return ConformalPairCoverage(
        lower_level=limits.lower_level,
        upper_level=limits.upper_level,
        nominal=pair_nominal(limits.lower_level),
        picp=covered / n,
        mpiw=mpiw,
        mpiw_infinite=infinite,
        crossed_rate=crossed / n,
        lower_tail=_tail(
            level=limits.lower_level,
            count=below_lower,
            n=n,
            horizon=horizon,
            band_levels=band_levels,
        ),
        upper_tail=_tail(
            level=limits.upper_level,
            count=below_upper,
            n=n,
            horizon=horizon,
            band_levels=band_levels,
        ),
        covered_count=covered,
        crossed_count=crossed,
    )


def _nests(chain: list[float]) -> bool:
    return all(a <= b for a, b in pairwise(chain))


def _nesting_violations(series: ConformalCoverageSeries, kept: list[int]) -> int:
    ordered = sorted(series.pairs, key=lambda limits: limits.lower_level)  # τ_1 o mais externo
    violations = 0
    for i in kept:
        chain = [limits.lower[i] for limits in ordered] + [
            limits.upper[i] for limits in reversed(ordered)
        ]
        if not _nests(chain):
            violations += 1
    return violations


def _mean_sd(values: list[float]) -> tuple[float, float | None]:
    mean = math.fsum(values) / len(values)
    return mean, statistics.stdev(values) if len(values) >= _MIN_SEEDS_FOR_SD else None


class ConformalCoverage:
    """Cobertura conformal sobre a série nativa embutida e a média entre seeds."""

    @staticmethod
    def evaluate(
        series: ConformalCoverageSeries, *, tolerance: float, band_levels: tuple[float, ...]
    ) -> ConformalCoverageReport:
        """ĉ por cauda, PICP/MPIW/cruzamento por par e aninhamento, nas linhas mantidas.

        Raises:
            ValueError: tolerância inválida (do `DegeneracyGate`) ou nível de banda
                inválido (do `WilsonBand`).
        """
        degeneracy = DegeneracyGate.evaluate(series.native, tolerance=tolerance)
        kept = [i for i, degenerate in enumerate(degeneracy.degenerate) if not degenerate]
        if not kept:  # C6: 100 % degenerada
            return ConformalCoverageReport(
                seed=series.seed,
                horizon=series.native.horizon,
                variant=series.variant,
                n_points=series.native.n_points,
                n_evaluated=0,
                applicable=False,
                degeneracy=degeneracy,
                per_pair=(),
                nesting_violation_rate=None,
            )
        violations = _nesting_violations(series, kept)
        return ConformalCoverageReport(
            seed=series.seed,
            horizon=series.native.horizon,
            variant=series.variant,
            n_points=series.native.n_points,
            n_evaluated=len(kept),
            degeneracy=degeneracy,
            applicable=True,
            per_pair=tuple(
                _pair_coverage(series, limits, kept, band_levels) for limits in series.pairs
            ),
            nesting_violation_rate=violations / len(kept),
            nesting_violation_count=violations,
        )

    @staticmethod
    def seed_mean(
        reports: Sequence[ConformalCoverageReport],
        *,
        horizon: int,
        variant: str,
        expected_seeds: tuple[int, ...],
        band_levels: tuple[float, ...],
    ) -> ConformalSeedMeanCoverage:
        """Média entre as seeds completas; sem relatório aplicável ⇒ `applicable=False`.

        `reports` são os das seeds completas daquele (horizonte, variante): mesmo
        horizonte e variante, seeds de `expected_seeds`, sem repetição. Relatório não
        aplicável (série 100 % degenerada) não entra nas médias e a seed fica excluída.

        Raises:
            ValueError: horizonte ou variante diferente, seed fora de `expected_seeds`,
                seed repetida, ou pares diferentes entre os relatórios.
        """
        if not all(is_int(seed) for seed in expected_seeds) or len(set(expected_seeds)) != len(
            expected_seeds
        ):
            raise ValueError(f"expected_seeds must be distinct ints, got {expected_seeds!r}")
        seen: set[int] = set()
        for report in reports:
            if report.horizon != horizon or report.variant != variant:
                raise ValueError(
                    f"report of (horizon {report.horizon}, variant {report.variant!r}) in the "
                    f"mean of (horizon {horizon}, variant {variant!r})"
                )
            if report.seed not in expected_seeds:
                raise ValueError(f"seed {report.seed} is not in expected_seeds {expected_seeds}")
            if report.seed in seen:
                raise ValueError(f"seed {report.seed} is repeated")
            seen.add(report.seed)
        used = sorted((r for r in reports if r.applicable), key=lambda r: r.seed)
        seeds_used = tuple(r.seed for r in used)
        excluded = tuple(sorted(set(expected_seeds) - set(seeds_used)))
        if not used:
            return ConformalSeedMeanCoverage(
                horizon=horizon,
                variant=variant,
                applicable=False,
                seeds_used=(),
                seeds_excluded=excluded,
                n_mean=None,
                per_pair=(),
                nesting_violation_rate=None,
            )
        pairs = [(p.lower_level, p.upper_level) for p in used[0].per_pair]
        for report in used[1:]:
            if [(p.lower_level, p.upper_level) for p in report.per_pair] != pairs:
                raise ValueError("reports of the seed mean must hold the same pairs")
        n_mean = math.fsum(r.n_evaluated for r in used) / len(used)
        # o relatório aplicável valida a contagem (presente e coerente com a taxa)
        nesting_mean = math.fsum(r.nesting_violation_count or 0 for r in used) / len(used) / n_mean
        mean_nesting, sd_nesting = _mean_sd([r.nesting_violation_rate or 0.0 for r in used])
        return ConformalSeedMeanCoverage(
            horizon=horizon,
            variant=variant,
            applicable=True,
            seeds_used=seeds_used,
            seeds_excluded=excluded,
            n_mean=n_mean,
            per_pair=tuple(
                _mean_pair(used, k, n_mean, horizon, band_levels) for k in range(len(pairs))
            ),
            nesting_violation_rate=nesting_mean,
            mean_of_seed_nesting_rates=mean_nesting,
            sd_of_seed_nesting_rates=sd_nesting,
        )


def _mean_tail(
    tails: list[ConformalTailCoverage],
    n_mean: float,
    horizon: int,
    band_levels: tuple[float, ...],
) -> ConformalSeedMeanTail:
    mean_count = math.fsum(t.count_at_or_below for t in tails) / len(tails)
    mean_cov, sd_cov = _mean_sd([t.coverage for t in tails])
    level = tails[0].level
    return ConformalSeedMeanTail(
        level=level,
        mean_count=mean_count,
        coverage=mean_count / n_mean,
        mean_of_seed_coverages=mean_cov,
        sd_of_seed_coverages=sd_cov,
        bands=tuple(
            WilsonBand.evaluate(
                horizon=horizon, count=mean_count, n=n_mean, nominal=level, band_level=b
            )
            for b in band_levels
        ),
    )


def _mean_pair(
    used: list[ConformalCoverageReport],
    k: int,
    n_mean: float,
    horizon: int,
    band_levels: tuple[float, ...],
) -> ConformalSeedMeanPair:
    pairs = [r.per_pair[k] for r in used]
    first = pairs[0]
    mean_picp, sd_picp = _mean_sd([p.picp for p in pairs])
    mean_crossed, sd_crossed = _mean_sd([p.crossed_rate for p in pairs])
    infinite = any(p.mpiw_infinite for p in pairs)
    mean_mpiw, sd_mpiw = (math.inf, None) if infinite else _mean_sd([p.mpiw for p in pairs])
    total_n = math.fsum(r.n_evaluated for r in used)
    mpiw = (
        math.inf
        if infinite
        else math.fsum(p.mpiw * r.n_evaluated for p, r in zip(pairs, used, strict=True)) / total_n
    )
    return ConformalSeedMeanPair(
        lower_level=first.lower_level,
        upper_level=first.upper_level,
        nominal=first.nominal,
        picp=math.fsum(p.covered_count for p in pairs) / len(pairs) / n_mean,
        mean_of_seed_picps=mean_picp,
        sd_of_seed_picps=sd_picp,
        mpiw=mpiw,
        mpiw_infinite=infinite,
        mean_of_seed_mpiws=mean_mpiw,
        sd_of_seed_mpiws=sd_mpiw,
        crossed_rate=math.fsum(p.crossed_count for p in pairs) / len(pairs) / n_mean,
        mean_of_seed_crossed_rates=mean_crossed,
        sd_of_seed_crossed_rates=sd_crossed,
        lower_tail=_mean_tail([p.lower_tail for p in pairs], n_mean, horizon, band_levels),
        upper_tail=_mean_tail([p.upper_tail for p in pairs], n_mean, horizon, band_levels),
    )
