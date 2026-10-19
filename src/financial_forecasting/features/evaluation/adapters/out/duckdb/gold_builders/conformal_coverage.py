"""`ConformalCoverageGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_conformal_coverage`).

Mapeamento puro dos relatórios de cobertura conformal (ADR 7.2.0003 item 7; technical
7.2 §1, "Colunas das tabelas gold"). Por (seed, horizonte, variante), o mesmo conjunto
de linhas em qualquer status, então as chaves nunca colidem:

- por par do plano, `lower_tail` e `upper_tail` uma por nível de banda (ĉ, nominal τ,
  Wilson), `pair` (PICP em `coverage`, nominal do par, MPIW, cruzamento) e uma `nesting`
  (níveis e banda nulos);
- `status ∈ {ok, undefined, not_applicable}`: `undefined` com o motivo (alguma unidade
  não-`ok` naquela seed, horizonte e variante), `not_applicable` com `n_evaluated = 0`
  (série nativa 100 % degenerada, C6); fora de `ok`, medidas, Wilson e `label` nulos;
- linha de média entre seeds com `seed` nulo: `coverage` = c̄/n̄ (a base da banda) e, ao
  lado, `mean_of_seed_coverages` e o dp; o mesmo para PICP, MPIW, cruzamento e
  aninhamento ("pelas duas médias", concept 7.2 §4); n̄ em `n_mean` e c̄ em `mean_count`
  (DOUBLE; `n_evaluated` e `count` ficam inteiros, só nas linhas por seed — C4-9);
  `n_seeds_used` e `seeds_excluded`
  (texto `"1,2"` ordenado, `""` sem exclusão); com zero seeds completas, o conjunto de
  linhas com `status = undefined`; com uma seed, os dp são nulos;
- MPIW infinito vai como `null` com `mpiw_infinite = true` (o `GoldTable` recusa não
  finito); `label` = `EMPIRICAL_COVERAGE_LABEL` em toda linha `ok` (I9).

Sem bloco `[conformal]` → zero linhas.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_COVERAGE,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
    ConformalCoverageReport,
    ConformalSeedMeanCoverage,
    ConformalSeedMeanTail,
    ConformalTailCoverage,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBandReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    pair_nominal,
)

Row = dict[str, object]
OK = "ok"
UNDEFINED = "undefined"
NOT_APPLICABLE = "not_applicable"
NO_COMPLETE_SEED = "no complete seed for this horizon and variant"


def _finite(value: float | None) -> float | None:
    return None if value is None or math.isinf(value) else value


def _empty_row(base: Row) -> Row:
    return {
        **base,
        **dict.fromkeys(GOLD_CONFORMAL_COVERAGE.key),
        **dict.fromkeys(GOLD_CONFORMAL_COVERAGE.read_columns),
    }


def _wilson(band: WilsonBandReport) -> Row:
    return {
        "band_level": band.band_level,
        "wilson_lower": band.lower,
        "wilson_upper": band.upper,
        "wilson_contains_nominal": band.contains_nominal,
        "serial_dependence_warning": band.serial_dependence_warning,
    }


class _Scaffold:
    """As linhas fixas de uma (seed, h, variante) para um status não-`ok`."""

    def __init__(self, inputs: GoldInputs) -> None:
        parameters = inputs.parameters.conformal_parameters
        self.pairs = parameters.pairs if parameters is not None else ()
        self.band_levels = inputs.parameters.band_levels
        self.base = partition_columns(inputs, confirmatory=True)

    def rows(self, common: Row) -> Iterator[Row]:
        """Por par: caudas por banda e o par; mais uma de aninhamento."""
        for low, high in self.pairs:
            levels = {"lower_level": low, "upper_level": high}
            for kind in ("lower_tail", "upper_tail"):
                for band_level in self.band_levels:
                    yield {
                        **_empty_row(self.base),
                        **common,
                        **levels,
                        "kind": kind,
                        "band_level": band_level,
                    }
            yield {**_empty_row(self.base), **common, **levels, "kind": "pair"}
        yield {**_empty_row(self.base), **common, "kind": "nesting"}


def _ok_common(report: ConformalCoverageReport) -> Row:
    return {
        "horizon": report.horizon,
        "variant": report.variant,
        "seed": report.seed,
        "status": OK,
        "label": EMPIRICAL_COVERAGE_LABEL,
        "n_points": report.n_points,
        "n_evaluated": report.n_evaluated,
    }


def _tail_rows(base: Row, common: Row, kind: str, tail: ConformalTailCoverage) -> list[Row]:
    return [
        {
            **_empty_row(base),
            **common,
            "kind": kind,
            "nominal": tail.level,
            "count": tail.count_at_or_below,
            "coverage": tail.coverage,
            **_wilson(band),
        }
        for band in tail.bands
    ]


def _report_rows(base: Row, report: ConformalCoverageReport) -> list[Row]:
    common = _ok_common(report)
    rows: list[Row] = []
    for pair in report.per_pair:
        levels = {"lower_level": pair.lower_level, "upper_level": pair.upper_level}
        rows += _tail_rows(base, {**common, **levels}, "lower_tail", pair.lower_tail)
        rows += _tail_rows(base, {**common, **levels}, "upper_tail", pair.upper_tail)
        rows.append(
            {
                **_empty_row(base),
                **common,
                **levels,
                "kind": "pair",
                "nominal": pair.nominal,
                "count": pair.covered_count,
                "coverage": pair.picp,
                "mpiw": _finite(pair.mpiw),
                "mpiw_infinite": pair.mpiw_infinite,
                "crossed_rate": pair.crossed_rate,
            }
        )
    rows.append(
        {
            **_empty_row(base),
            **common,
            "kind": "nesting",
            "count": report.nesting_violation_count,
            "nesting_violation_rate": report.nesting_violation_rate,
        }
    )
    return rows


def _mean_tail_rows(base: Row, common: Row, kind: str, tail: ConformalSeedMeanTail) -> list[Row]:
    return [
        {
            **_empty_row(base),
            **common,
            "kind": kind,
            "nominal": tail.level,
            "mean_count": tail.mean_count,
            "coverage": tail.coverage,
            "mean_of_seed_coverages": tail.mean_of_seed_coverages,
            "sd_of_seed_coverages": tail.sd_of_seed_coverages,
            **_wilson(band),
        }
        for band in tail.bands
    ]


def _excluded(mean: ConformalSeedMeanCoverage) -> str:
    return ",".join(str(seed) for seed in sorted(mean.seeds_excluded))


def _mean_rows(base: Row, scaffold: _Scaffold, mean: ConformalSeedMeanCoverage) -> list[Row]:
    seeds = {
        "horizon": mean.horizon,
        "variant": mean.variant,
        "seed": None,
        "n_seeds_used": len(mean.seeds_used),
        "seeds_excluded": _excluded(mean),
    }
    if not mean.applicable:
        return list(scaffold.rows({**seeds, "status": UNDEFINED, "reason": NO_COMPLETE_SEED}))
    common = {**seeds, "status": OK, "label": EMPIRICAL_COVERAGE_LABEL, "n_mean": mean.n_mean}
    rows: list[Row] = []
    for pair in mean.per_pair:
        levels = {"lower_level": pair.lower_level, "upper_level": pair.upper_level}
        rows += _mean_tail_rows(base, {**common, **levels}, "lower_tail", pair.lower_tail)
        rows += _mean_tail_rows(base, {**common, **levels}, "upper_tail", pair.upper_tail)
        rows.append(
            {
                **_empty_row(base),
                **common,
                **levels,
                "kind": "pair",
                "nominal": pair_nominal(pair.lower_level),
                "coverage": pair.picp,
                "mean_of_seed_coverages": pair.mean_of_seed_picps,
                "sd_of_seed_coverages": pair.sd_of_seed_picps,
                "mpiw": _finite(pair.mpiw),
                "mpiw_infinite": pair.mpiw_infinite,
                "mean_of_seed_mpiws": _finite(pair.mean_of_seed_mpiws),
                "sd_of_seed_mpiws": pair.sd_of_seed_mpiws,
                "crossed_rate": pair.crossed_rate,
                "mean_of_seed_crossed_rates": pair.mean_of_seed_crossed_rates,
                "sd_of_seed_crossed_rates": pair.sd_of_seed_crossed_rates,
            }
        )
    rows.append(
        {
            **_empty_row(base),
            **common,
            "kind": "nesting",
            "nesting_violation_rate": mean.nesting_violation_rate,
            "mean_of_seed_nesting_rates": mean.mean_of_seed_nesting_rates,
            "sd_of_seed_nesting_rates": mean.sd_of_seed_nesting_rates,
        }
    )
    return rows


class ConformalCoverageGoldBuilder:
    """Cobertura conformal por seed e a média entre seeds, com o rótulo empírico."""

    name = "conformal_coverage"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """As linhas fixas de cada (seed, h, variante) e de cada média entre seeds."""
        reports = inputs.conformal_reports
        scaffold = _Scaffold(inputs)
        base = scaffold.base
        rows: list[Row] = []
        for report in reports.coverage:
            if report.applicable:
                rows += _report_rows(base, report)
            else:
                rows += scaffold.rows(
                    {
                        "horizon": report.horizon,
                        "variant": report.variant,
                        "seed": report.seed,
                        "status": NOT_APPLICABLE,
                        "n_points": report.n_points,
                        "n_evaluated": 0,
                    }
                )
        for missing in reports.undefined_coverage:
            rows += scaffold.rows(
                {
                    "horizon": missing.horizon,
                    "variant": missing.variant,
                    "seed": missing.seed,
                    "status": UNDEFINED,
                    "reason": missing.reason,
                    "n_points": missing.n_points,
                }
            )
        for mean in reports.seed_means:
            rows += _mean_rows(base, scaffold, mean)
        return GoldTable.sorted_by_key(
            GOLD_CONFORMAL_COVERAGE.name, GOLD_CONFORMAL_COVERAGE.key, rows
        )
