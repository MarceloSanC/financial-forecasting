"""Mundo julgado sintético das figuras da 8.3 (Stage 8.3, Task 06).

Módulo privado (sem `test_`), stdlib + DTOs + domínio (gate de pureza do `evaluation`:
nenhum adapter, nenhum arquivo). `make_world()` devolve um `ReportWorld` mutável:

- o plano r3 sintético (`r3_payload` com seeds do candidato `[1, 2]`, níveis com dois
  pares simétricos e o `[conformal]` sobre esses pares);
- as linhas das 19 tabelas gold (as que as figuras não leem ficam vazias), montadas pela
  `GoldGeneration.from_stored` (dono único) em `inputs()`;
- o scorecard `Mapping` **coerente** com as linhas (as médias entre seeds do perfil
  calculadas das próprias linhas; o H1 com o `mean_observed` do filtro do gate).

**Fakes discriminantes:** todo valor sai de `value(...)` sobre **todos** os eixos da
chave (amostra, degenerados, banda, estimador, horizonte, seed, nível), então ler a linha
errada do mapa do D13 muda o valor desenhado.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
    GOLD_CALIBRATION_TABLE,
    GOLD_CONFORMAL_COVERAGE,
    GOLD_DM_RESULTS,
    GOLD_METRICS_BY_RUN,
    GOLD_SCHEMAS,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldTable,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    EMPIRICAL_COVERAGE_NOTE,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    ReportInputs,
    symmetric_pairs,
    tail_kind,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.unit.features.evaluation._preregistration_payload import r3_payload
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT

REFERENCE = "test_plan-r3-0123456789ab"
LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
CANDIDATE_SEEDS = (1, 2)
VARIANTS = ("nexcp_fixed_geometric_weights_v1", "split_cqr_asymmetric_unweighted_v1")
SAMPLES = ("common", "model_full")
BANDS = (0.95, 0.975)
ESTIMATORS = ("bartlett", "rectangular")
STARTED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

Row = dict[str, object]
Seed = int | None


def value(*parts: object) -> float:
    """Um valor em (0, 1) distinto por combinação de eixos (determinístico)."""
    digest = sha256(repr(parts).encode("utf-8")).hexdigest()
    return round(0.05 + 0.9 * int(digest[:8], 16) / 0xFFFFFFFF, 6)


def report_plan() -> Preregistration:
    """O r3 sintético com as seeds `[1, 2]` e dois pares simétricos."""
    payload = r3_payload()
    payload["quantile_levels"] = list(LEVELS)
    payload["seeds"] = {**payload["seeds"], "tft_quantile": list(CANDIDATE_SEEDS)}  # type: ignore[dict-item]
    conformal = dict(payload["conformal"])  # type: ignore[call-overload]
    conformal["pairs"] = [[0.1, 0.9], [0.25, 0.75]]
    payload["conformal"] = conformal
    return Preregistration.from_mapping(payload)


def seeds_of(plan: Preregistration, model: str) -> tuple[Seed, ...]:
    spec = plan.seeds[model]
    return (None,) if spec.seeds is None else tuple(spec.seeds)


@dataclass
class ReportWorld:
    """Plano, linhas gold e scorecard mutáveis antes de montar as `ReportInputs`."""

    plan: Preregistration
    rows: dict[str, list[Row]]
    scorecard: dict[str, object]
    silver_content: SilverContent = SAMPLE_SILVER_CONTENT
    reference: str = REFERENCE
    extra: dict[str, object] = field(default_factory=dict)

    def generation(self) -> GoldGeneration:
        command = refresh_command_from(self.plan, self.reference)
        tables = {
            name: list(GoldTable.sorted_by_key(name, GOLD_SCHEMAS[name].key, rows).rows)
            for name, rows in self.rows.items()
        }
        manifest = GoldManifest(
            status=RefreshStatus.COMPLETED,
            partition=command.partition,
            rows_by_table={name: len(rows) for name, rows in tables.items()},
            parameters=command.parameters,
            horizons=command.horizons,
            window_deficits=command.window_deficits,
            dataset_fingerprint=DatasetContentFingerprint(command.dataset_fingerprint),
            grid_trimmed_prefix=0,
            realized_sessions=40,
            realized_returns_fsum=0.125,
            realized_first_timestamp="2024-01-02T00:00:00+00:00",
            realized_last_timestamp="2024-12-31T00:00:00+00:00",
            n_runs=sum(len(seeds_of(self.plan, m)) for m in self.plan.models),
            build_order=tuple(name.removeprefix("gold_") for name in tables),
            started_at=STARTED_AT,
            finished_at=STARTED_AT,
            silver_content=self.silver_content,
        ).as_mapping()
        return GoldGeneration.from_stored(manifest, tables, partition=command.partition)

    def inputs(self) -> ReportInputs:
        return ReportInputs(
            plan=self.plan,
            preregistration_ref=self.reference,
            partition=refresh_command_from(self.plan, self.reference).partition,
            generation=self.generation(),
            scorecard=copy.deepcopy(self.scorecard),
        )

    def where(self, table: str, **match: object) -> list[Row]:
        """As linhas de `table` que casam `match` (por igualdade e tipo de `bool`)."""
        return [row for row in self.rows[table] if _matches(row, match)]

    def horizon(self, part: str, horizon: int) -> dict[str, object]:
        entries = self.scorecard[part]["horizons"]  # type: ignore[index]
        return next(e for e in entries if e["horizon"] == horizon)


def _matches(row: Row, match: Mapping[str, object]) -> bool:
    return all(
        row[k] == v and (type(row[k]) is bool) == (type(v) is bool) for k, v in match.items()
    )


def _row(schema: GoldTableSchema, base: Row, **values: object) -> Row:
    row: Row = {**base, **dict.fromkeys(schema.key), **dict.fromkeys(schema.read_columns)}
    if schema.name not in CONFIRMATORY_TABLES:
        row.pop("preregistration_ref", None)
    row.update(values)
    return row


# --------------------------------------------------------------------------------------
# Linhas gold
# --------------------------------------------------------------------------------------


def _metrics_rows(plan: Preregistration, base: Row) -> list[Row]:
    rows: list[Row] = []
    for h in plan.horizons:
        for model in plan.models:
            for seed in seeds_of(plan, model):
                for sample in SAMPLES:
                    series = {"model": model, "seed": seed, "horizon": h, "sample": sample}
                    for level in plan.quantile_levels:
                        rows.append(
                            _row(
                                GOLD_METRICS_BY_RUN,
                                base,
                                **series,
                                metric="pinball",
                                level_low=level,
                                level_high=None,
                                value=value("pinball", model, seed, h, sample, level),
                                n_points=200,
                            )
                        )
                    for low, high in symmetric_pairs(plan.quantile_levels):
                        for metric in ("picp", "mpiw"):
                            rows.append(
                                _row(
                                    GOLD_METRICS_BY_RUN,
                                    base,
                                    **series,
                                    metric=metric,
                                    level_low=low,
                                    level_high=high,
                                    value=value(metric, model, seed, h, sample, low),
                                    n_points=200,
                                )
                            )
    return rows


def observed(  # noqa: PLR0913 — os eixos de uma máscara
    model: str, seed: Seed, h: int, sample: str, includes: bool, band: float
) -> int:
    """`n_observed` de uma máscara (igual nas duas caudas e em todos os níveis)."""
    return 150 + int(100 * value("observed", model, seed, h, sample, includes, band))


def _calibration_rows(plan: Preregistration, base: Row) -> list[Row]:
    rows: list[Row] = []
    for h in plan.horizons:
        partitions: list[tuple[int | None, int | None]] = [(None, None)]
        if h > 1:
            partitions.append((0, h))
        for model in plan.models:
            for seed in seeds_of(plan, model):
                for sample in SAMPLES:
                    for level in plan.quantile_levels:
                        if level == 0.5:  # noqa: PLR2004 — a mediana não tem calibração
                            continue
                        for includes in (False, True):
                            for offset, step in partitions:
                                for band in BANDS:
                                    axes = (model, seed, h, sample, level, includes, offset, band)
                                    n_obs = observed(model, seed, h, sample, includes, band)
                                    if offset is not None:
                                        n_obs //= 2
                                    n_viol = int(n_obs * 0.3 * value("violations", *axes))
                                    rate = n_viol / n_obs
                                    width = 0.02 + 0.02 * value("width", *axes)
                                    rows.append(
                                        _row(
                                            GOLD_CALIBRATION_TABLE,
                                            base,
                                            model=model,
                                            seed=seed,
                                            horizon=h,
                                            sample=sample,
                                            kind=tail_kind(level),
                                            level_low=level,
                                            level_high=None,
                                            includes_degenerate=includes,
                                            dgt_offset=offset,
                                            dgt_step=step,
                                            band_level=band,
                                            n_observed=n_obs,
                                            n_violations=n_viol,
                                            degeneracy_rate=0.0,
                                            wilson_contains_nominal=True,
                                            p_ind=0.5,
                                            p_cc=0.5,
                                            independence_status="applicable",
                                            violation_rate=rate,
                                            wilson_estimate=round(rate + 0.001, 9),
                                            wilson_lower=round(rate - width, 9),
                                            wilson_upper=round(rate + width, 9),
                                        )
                                    )
    return rows


def _dm_rows(plan: Preregistration, base: Row) -> list[Row]:
    rows: list[Row] = []
    for h in plan.horizons:
        for estimator in ESTIMATORS:
            for comparator in plan.comparators:
                p_value = value("dm_p", h, estimator, comparator) / 10
                adjusted = min(1.0, round(p_value * 3, 9))
                rows.append(
                    _row(
                        GOLD_DM_RESULTS,
                        base,
                        horizon=h,
                        variance_estimator=estimator,
                        candidate=plan.candidate,
                        comparator=comparator,
                        n_points=200,
                        mean_differential=-value("dm_mean", h, estimator, comparator) / 100,
                        statistic=-2.0,
                        adjusted_p_value=adjusted,
                        rejected=adjusted < 0.05,  # noqa: PLR2004
                        fallback_applied=False,
                        alpha=plan.dm.alpha,
                        p_value=p_value,
                    )
                )
    return rows


def _conformal_rows(plan: Preregistration, base: Row, calibration: list[Row]) -> list[Row]:
    assert plan.conformal is not None
    native = {
        (r["seed"], r["horizon"], r["level_low"]): r["n_observed"]
        for r in calibration
        if r["model"] == plan.candidate
        and r["sample"] == "model_full"
        and r["includes_degenerate"] is False
        and r["dgt_offset"] is None
        and r["band_level"] == plan.h1_gate.profile_band_level
    }
    rows: list[Row] = []
    for h in plan.horizons:
        for variant in VARIANTS:
            for seed in (None, *seeds_of(plan, plan.candidate)):
                for low, high in plan.conformal.pairs:
                    levels = {"lower_level": low, "upper_level": high}
                    common: Row = {
                        "horizon": h,
                        "variant": variant,
                        "seed": seed,
                        "status": "ok",
                        "label": EMPIRICAL_COVERAGE_NOTE,
                    }
                    for kind, level in (("lower_tail", low), ("upper_tail", high)):
                        for band in BANDS:
                            axes = (h, variant, seed, kind, level, band)
                            coverage = value("conformal", h, variant, seed, kind, level)
                            rows.append(
                                _row(
                                    GOLD_CONFORMAL_COVERAGE,
                                    base,
                                    **common,
                                    **levels,
                                    kind=kind,
                                    band_level=band,
                                    nominal=level,
                                    n_evaluated=None if seed is None else native[(seed, h, level)],
                                    coverage=coverage,
                                    mean_of_seed_coverages=(
                                        value("seed_mean", *axes) if seed is None else None
                                    ),
                                    wilson_lower=round(coverage - 0.01 - band / 100, 9),
                                    wilson_upper=round(coverage + 0.01 + band / 100, 9),
                                )
                            )
                    rows.append(
                        _row(
                            GOLD_CONFORMAL_COVERAGE,
                            base,
                            **common,
                            **levels,
                            kind="pair",
                            band_level=None,
                            nominal=round(high - low, 9),
                            coverage=value("conformal_picp", h, variant, seed, low),
                            mpiw=value("conformal_mpiw", h, variant, seed, low),
                        )
                    )
    return rows


# --------------------------------------------------------------------------------------
# Scorecard coerente
# --------------------------------------------------------------------------------------


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items)


def _calibration_95(plan: Preregistration, rows: list[Row], h: int) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[Row]] = defaultdict(list)
    for row in rows:
        if row["horizon"] != h or row["band_level"] != plan.h1_gate.profile_band_level:
            continue
        key = tuple(
            row[c]
            for c in (
                "model",
                "sample",
                "kind",
                "level_low",
                "level_high",
                "includes_degenerate",
                "dgt_offset",
                "dgt_step",
            )
        )
        groups[key].append(row)
    return [
        {
            "model": key[0],
            "sample": key[1],
            "kind": key[2],
            "level_low": key[3],
            "level_high": key[4],
            "includes_degenerate": key[5],
            "dgt_offset": key[6],
            "dgt_step": key[7],
            "n_seeds": len(members),
            "mean_violations": _mean(float(m["n_violations"]) for m in members),  # type: ignore[arg-type]
            "mean_observed": _mean(float(m["n_observed"]) for m in members),  # type: ignore[arg-type]
        }
        for key, members in groups.items()
    ]


def _descriptors(rows: list[Row], h: int) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[float]] = defaultdict(list)
    for row in rows:
        if row["horizon"] == h:
            key = (row["model"], row["sample"], row["metric"], row["level_low"], row["level_high"])
            groups[key].append(float(row["value"]))  # type: ignore[arg-type]
    return [
        {
            "model": key[0],
            "sample": key[1],
            "metric": key[2],
            "level_low": key[3],
            "level_high": key[4],
            "mean": _mean(values),
            "minimum": min(values),
            "maximum": max(values),
            "n_seeds": len(values),
        }
        for key, values in groups.items()
    ]


def _band(count: float, n: float, band_level: float, level: float, h: int) -> dict[str, object]:
    estimate = count / n
    return {
        "horizon": h,
        "count": count,
        "n": n,
        "nominal": level if level < 0.5 else 1 - level,  # noqa: PLR2004
        "band_level": band_level,
        "applicable": True,
        "estimate": estimate,
        "lower": round(estimate - 0.03, 9),
        "upper": round(estimate + 0.04, 9),
        "contains_nominal": True,
        "serial_dependence_warning": h > 1,
    }


def _h1(plan: Preregistration, rows: list[Row], h: int, passed: bool) -> dict[str, object]:
    gate = plan.h1_gate
    bands: dict[str, dict[str, object]] = {}
    observed_95: float = 0.0
    for name, level in (("lower_band", gate.lower_level), ("upper_band", gate.upper_level)):

        def gate_rows(band: float, level: float = level) -> list[Row]:
            return [
                r
                for r in rows
                if r["model"] == plan.candidate
                and r["horizon"] == h
                and r["sample"] == "model_full"
                and r["level_low"] == level
                and r["includes_degenerate"] is False
                and r["dgt_offset"] is None
                and r["band_level"] == band
            ]

        at_gate = gate_rows(gate.gate_band_level)
        count = _mean(float(r["n_violations"]) for r in at_gate)  # type: ignore[arg-type]
        n = _mean(float(r["n_observed"]) for r in at_gate)  # type: ignore[arg-type]
        bands[name] = _band(count, n, gate.gate_band_level, level, h)
        observed_95 = _mean(float(r["n_observed"]) for r in gate_rows(gate.profile_band_level))  # type: ignore[arg-type]
    return {"horizon": h, "passed": passed, **bands, "mean_observed": observed_95}


def _dm_profile(rows: list[Row], h: int) -> list[dict[str, object]]:
    return [
        {
            "comparator": r["comparator"],
            "estimator": r["variance_estimator"],
            "n_points": r["n_points"],
            "mean_differential": r["mean_differential"],
            "statistic": r["statistic"],
            "adjusted_p_value": r["adjusted_p_value"],
            "rejected": r["rejected"],
            "fallback_applied": r["fallback_applied"],
            "effect_interval": None,
        }
        for r in rows
        if r["horizon"] == h
    ]


def _power(plan: Preregistration, h: int) -> list[dict[str, object]]:
    return [
        {
            "label": scenario.label,
            "role": scenario.role.value,
            "n": 200,
            "failure_probability": value("power", h, scenario.label),
            "assumes_independence": h == 1,
        }
        for scenario in plan.h1_gate.power_scenarios
    ]


def make_scorecard(
    plan: Preregistration, rows: Mapping[str, list[Row]], h1_passed: Mapping[int, bool]
) -> dict[str, object]:
    """O scorecard `as_mapping()` (só os campos que as figuras e o dossiê leem)."""
    calibration = rows[GOLD_CALIBRATION_TABLE.name]
    return {
        "preregistration_ref": REFERENCE,
        "verdict": {
            "horizons": [
                {"horizon": h, "h1": _h1(plan, calibration, h, h1_passed[h])} for h in plan.horizons
            ],
            "study_success_h1": any(h1_passed.values()),
        },
        "profile": {
            "horizons": [
                {
                    "horizon": h,
                    "power": _power(plan, h),
                    "calibration_95": _calibration_95(plan, calibration, h),
                    "descriptors": _descriptors(rows[GOLD_METRICS_BY_RUN.name], h),
                    "dm": _dm_profile(rows[GOLD_DM_RESULTS.name], h),
                }
                for h in plan.horizons
            ]
        },
    }


def make_world(h1_passed: Mapping[int, bool] | None = None) -> ReportWorld:
    """O mundo padrão: H1 passa em h+1 e reprova em h+7."""
    plan = report_plan()
    command = refresh_command_from(plan, REFERENCE)
    base: Row = {
        "asset": command.partition.asset,
        "parent_sweep_id": command.partition.parent_sweep_id,
        "preregistration_ref": REFERENCE,
    }
    rows: dict[str, list[Row]] = {name: [] for name in GOLD_SCHEMAS}
    rows[GOLD_METRICS_BY_RUN.name] = _metrics_rows(plan, base)
    rows[GOLD_CALIBRATION_TABLE.name] = _calibration_rows(plan, base)
    rows[GOLD_DM_RESULTS.name] = _dm_rows(plan, base)
    rows[GOLD_CONFORMAL_COVERAGE.name] = _conformal_rows(
        plan, base, rows[GOLD_CALIBRATION_TABLE.name]
    )
    passed = {1: True, 7: False} if h1_passed is None else dict(h1_passed)
    return ReportWorld(plan=plan, rows=rows, scorecard=make_scorecard(plan, rows, passed))
