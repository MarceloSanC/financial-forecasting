"""Fábrica de gold sintético coerente com um plano (Stage 6.5, technical §2 Task 08).

Módulo privado (sem `test_`), stdlib + DTOs + domínio (gate de pureza do `evaluation`:
nenhum adapter, nenhum arquivo). `make_stored(prereg, ...)` gera as linhas das cinco
tabelas gold **coerentes com o plano** — as chaves do `gold_schema`, o manifesto do
`refresh_command_from` — como um `StoredGold` mutável; cada teste aplica **uma**
violação pelos mutadores (`drop_rows`, `set_cell`, `add_seed`, `manifest`) e monta a
geração com `generation()` (pelo dono único `GoldGeneration.from_stored`).

Contagens por omissão: calibradas (25 violações em 250 pontos por cauda, degeneração
0); sub-séries DGT com `n // h`. O perfil (Task 09) e o use case (Task 10) reusam a
fábrica.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_DM_RESULTS,
    GOLD_MCS_RESULTS,
    GOLD_METRICS_BY_RUN,
    GOLD_QUALITY_CHECKS,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    block_length_rule,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.alignment_check import (  # noqa: E501
    ALIGNMENT_CHECK,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.degeneracy_check import (  # noqa: E501
    DEGENERACY_CHECK,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.statistical_preconditions_check import (  # noqa: E501
    STATISTICAL_PRECONDITIONS,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

REFERENCE = "test_plan-r0-0123456789ab"
T_POINTS = 250
MAX_BLOCK_ESTIMATE = 3.2
STARTED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
REQUIRED_CHECKS = (DEGENERACY_CHECK, ALIGNMENT_CHECK, STATISTICAL_PRECONDITIONS)

Row = dict[str, object]
# (modelo, seed, horizonte, amostra, kind) → (violações, pontos observados, degeneração)
Counts = Callable[[str, int | None, int, str, str], tuple[int, int, float]]


def calibrated(
    _model: str, _seed: int | None, _h: int, _sample: str, _kind: str
) -> tuple[int, int, float]:
    """25 violações em 250 pontos, sem degeneração (as duas caudas calibradas)."""
    return 25, 250, 0.0


def _seeds(prereg: Preregistration, model: str) -> list[int | None]:
    spec = prereg.seeds[model]
    return [None] if spec.seeds is None else list(spec.seeds)


@dataclass
class StoredGold:
    """Manifesto e linhas por tabela de uma geração, mutáveis antes de montar."""

    manifest: dict[str, object]
    rows: dict[str, list[Row]]
    partition: GoldPartition

    def drop_rows(self, table: str, where: Callable[[Row], bool]) -> int:
        """Remove as linhas de `table` que satisfazem `where`; devolve quantas."""
        before = len(self.rows[table])
        self.rows[table] = [row for row in self.rows[table] if not where(row)]
        return before - len(self.rows[table])

    def set_cell(self, table: str, where: Callable[[Row], bool], column: str, value: object) -> int:
        """Troca `column` nas linhas que satisfazem `where`; devolve quantas."""
        hits = [row for row in self.rows[table] if where(row)]
        for row in hits:
            row[column] = value
        return len(hits)

    def add_seed(self, model: str, seed: int, *, tables: Iterable[str] | None = None) -> None:
        """Copia as linhas da 1ª seed do modelo com `seed` (métricas e calibração)."""
        for table in tables or (GOLD_METRICS_BY_RUN.name, GOLD_CALIBRATION_TABLE.name):
            rows = [r for r in self.rows[table] if r["model"] == model]
            first = rows[0]["seed"]
            self.rows[table] += [{**r, "seed": seed} for r in rows if r["seed"] == first]

    def generation(self) -> GoldGeneration:
        """A geração montada pelo dono único (linhas ordenadas pela chave do schema)."""
        tables = {
            name: list(GoldTable.sorted_by_key(name, GOLD_SCHEMAS[name].key, rows).rows)
            for name, rows in self.rows.items()
        }
        manifest = copy.deepcopy(self.manifest)
        manifest["rows_by_table"] = {name: len(rows) for name, rows in tables.items()}
        return GoldGeneration.from_stored(manifest, tables, partition=self.partition)


def make_stored(  # noqa: PLR0913 — um eixo por parâmetro da geração sintética
    prereg: Preregistration,
    *,
    reference: str = REFERENCE,
    counts: Counts = calibrated,
    dm_rejected: Iterable[str] | None = None,
    mcs_included: Iterable[str] | None = None,
    checks: Iterable[tuple[str, str, str]] | None = None,
    status: RefreshStatus = RefreshStatus.COMPLETED,
    started_at: datetime = STARTED_AT,
    pinball: Callable[[str, int | None, int], float] | None = None,
) -> StoredGold:
    """Um gold `COMPLETED` coerente com `prereg` (ver docstring do módulo).

    `dm_rejected`: comparadores que Holm rejeita (omissão: os naive); `mcs_included`:
    modelos no MCS (omissão: todos); `checks`: (check, severidade, desfecho) de
    `gold_quality_checks` (omissão: os três exigidos com `pass`); `pinball`: P̄_G por
    (modelo, seed, horizonte) (omissão: 0,10 do candidato, 0,12 dos comparadores).
    """
    command = refresh_command_from(prereg, reference)
    partition = command.partition
    base: Row = {"asset": partition.asset, "parent_sweep_id": partition.parent_sweep_id}
    confirmatory: Row = {**base, "preregistration_ref": reference}
    rejected = set(prereg.comparator_tiers.naive if dm_rejected is None else dm_rejected)
    included = set(prereg.models if mcs_included is None else mcs_included)
    p_bar = pinball or (lambda model, _seed, _h: 0.10 if model == prereg.candidate else 0.12)
    parameters = command.parameters
    rows: dict[str, list[Row]] = {schema: [] for schema in GOLD_SCHEMAS}
    for check, severity, outcome in checks or [(c, "error", "pass") for c in REQUIRED_CHECKS]:
        rows[GOLD_QUALITY_CHECKS.name].append(
            {
                **base,
                "check": check,
                "kind": "summary",
                "horizon": None,
                "model": None,
                "seed": None,
                "severity": severity,
                "outcome": outcome,
                "occurrences": 1,
                "detail": "",
            }
        )
    if status is RefreshStatus.COMPLETED:
        _completed_rows(prereg, rows, confirmatory, counts, rejected, included, p_bar)
    else:
        rows = {GOLD_QUALITY_CHECKS.name: rows[GOLD_QUALITY_CHECKS.name]}
    manifest = GoldManifest(
        status=status,
        partition=partition,
        rows_by_table={name: len(r) for name, r in rows.items()},
        parameters=parameters,
        horizons=command.horizons,
        window_deficits=command.window_deficits,
        dataset_fingerprint=DatasetContentFingerprint(command.dataset_fingerprint),
        grid_trimmed_prefix=0,
        realized_sessions=T_POINTS,
        realized_returns_fsum=0.125,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-12-31T00:00:00+00:00",
        n_runs=sum(len(_seeds(prereg, m)) for m in prereg.models),
        build_order=tuple(name.removeprefix("gold_") for name in rows),
        started_at=started_at,
        finished_at=started_at,
    ).as_mapping()
    return StoredGold(manifest=manifest, rows=rows, partition=partition)


def _completed_rows(  # noqa: PLR0913 — os eixos do make_stored, repassados
    prereg: Preregistration,
    rows: dict[str, list[Row]],
    confirmatory: Row,
    counts: Counts,
    rejected: set[str],
    included: set[str],
    p_bar: Callable[[str, int | None, int], float],
) -> None:
    command = refresh_command_from(prereg, str(confirmatory["preregistration_ref"]))
    parameters = command.parameters
    for h in prereg.horizons:
        for model in prereg.models:
            for seed in _seeds(prereg, model):
                for sample in ("model_full", "common"):
                    _series_rows(prereg, rows, confirmatory, counts, p_bar, model, seed, h, sample)
        for estimator in parameters.dm_variance_estimators:
            for comparator in prereg.comparators:
                hit = comparator in rejected
                rows[GOLD_DM_RESULTS.name].append(
                    {
                        **confirmatory,
                        "horizon": h,
                        "variance_estimator": estimator.value,
                        "candidate": prereg.candidate,
                        "comparator": comparator,
                        "n_points": T_POINTS,
                        "mean_differential": -0.01 if hit else 0.002,
                        "statistic": -3.0 if hit else 0.5,
                        "adjusted_p_value": 0.001 if hit else 0.6,
                        "rejected": hit,
                        "fallback_applied": False,
                        "alpha": parameters.dm_alpha,
                    }
                )
        for scheme in parameters.mcs_schemes:
            for model in prereg.models:
                rows[GOLD_MCS_RESULTS.name].append(
                    {
                        **confirmatory,
                        "horizon": h,
                        "scheme": scheme.value,
                        "model": model,
                        "included": model in included,
                        "statistic": prereg.rules.mcs_statistic,
                        "block_size": block_length_rule(horizon=h, max_estimate=MAX_BLOCK_ESTIMATE),
                        "max_block_estimate": MAX_BLOCK_ESTIMATE,
                        "alpha": parameters.mcs_alpha,
                        "reps": parameters.mcs_reps,
                        "seed": parameters.mcs_seed,
                    }
                )


def _series_rows(  # noqa: PLR0913 — uma série (modelo, seed, horizonte, amostra)
    prereg: Preregistration,
    rows: dict[str, list[Row]],
    confirmatory: Row,
    counts: Counts,
    p_bar: Callable[[str, int | None, int], float],
    model: str,
    seed: int | None,
    h: int,
    sample: str,
) -> None:
    gate = prereg.h1_gate
    band_levels = sorted({gate.gate_band_level, gate.profile_band_level})
    series = {**confirmatory, "model": model, "seed": seed, "horizon": h, "sample": sample}
    rows[GOLD_METRICS_BY_RUN.name].append(
        {
            **series,
            "metric": "pinball_grid_mean",
            "level_low": None,
            "level_high": None,
            "value": p_bar(model, seed, h),
            "n_points": T_POINTS,
        }
    )
    for level in prereg.quantile_levels:
        rows[GOLD_METRICS_BY_RUN.name].append(
            {
                **series,
                "metric": "pinball",
                "level_low": level,
                "level_high": None,
                "value": p_bar(model, seed, h),
                "n_points": T_POINTS,
            }
        )
    partitions: list[tuple[int | None, int | None, int]] = [(None, None, 1)]
    if h > 1:
        partitions += [(k, h, h) for k in range(h)]
    for kind, level in (("lower_tail", gate.lower_level), ("upper_tail", gate.upper_level)):
        violations, observed, degeneracy = counts(model, seed, h, sample, kind)
        for includes in (False, True):
            for offset, step, divisor in partitions:
                for band in band_levels:
                    rows[GOLD_CALIBRATION_TABLE.name].append(
                        {
                            **series,
                            "kind": kind,
                            "level_low": level,
                            "level_high": None,
                            "includes_degenerate": includes,
                            "dgt_offset": offset,
                            "dgt_step": step,
                            "band_level": band,
                            "n_observed": observed // divisor,
                            "n_violations": violations // divisor,
                            "degeneracy_rate": degeneracy,
                            "wilson_contains_nominal": True,
                            "p_ind": 0.5,
                            "p_cc": 0.5,
                            "independence_status": "applicable",
                        }
                    )


def make_generation(prereg: Preregistration, **kwargs: object) -> GoldGeneration:
    """`make_stored(prereg, **kwargs).generation()`."""
    return make_stored(prereg, **kwargs).generation()  # type: ignore[arg-type]
