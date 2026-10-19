"""Serviço de domínio `AttributionAssembly` — as séries d_t de H3 nos dois métodos (7.3).

Stdlib-only + o VO `QuantileForecast` do fornecedor (aresta de DADOS 7 declarada no
`bc-independence`, exceção do MÓDULO — ADR 7.3.0001 item 1, ADR 0.0.0053 item 3). Concept
7.3 §4, I10, I11, I17, I19; C9.

Duas etapas, porque o silver de atribuição é grande demais para caber inteiro (~8,7 M
linhas, I19):

1. **Redução por run** (`reduce_permuted_run`, `reduce_ablation_run`): o `RefreshGold` lê
   UM run, reduz as linhas a perdas por decisão e descarta os registros. Cada ponto
   (série, alvo) passa pelas regras públicas de alinhamento do `SeriesAssembly`
   (`duplicate_levels`, `index_violations`, `missing_levels`; uma definição só por
   regra, como na `ConformalAssembly` da 7.2), mais a grade igual à do comando e uma
   flag de guardrail por ponto. A perda de cada decisão é o pinball médio na grade
   (`PinballScore.per_point_losses`) sobre uma `CoverageSeries` construída com o
   `QuantileForecast` dos valores PERSISTIDOS (`value_guardrail`), nunca por `from_raw`.
   As decisões do run são as que têm todos os horizontes (H3-PAIR). Uma violação devolve
   `UndefinedRunReduction` com o motivo — nunca `AlignmentFinding`: H3 não está no
   caminho do veredito de H1/H2.
2. **Montagem** (`AttributionAssembly.assemble`): confere as reduções contra o cohort e o
   `[h3]` (todo run do candidato e da ablação reduzido, toda seed, k, família e
   configuração presentes — I11; semente e algoritmo da permutação — C9; `partition_hash`
   igual ao literal da r3 — I17) e agrega nas seeds (H3-SEEDS):
   - permutação: d_t = média nas seeds da média nas k de L^{perm f,k}_{s,t} - L^{id}_{s,t},
     com a identidade da PRÓPRIA tabela permutada (I7), nunca a de `fact_oos_predictions`;
   - LOCO: d_t = média nas seeds de L^{-f}_{s,t} - média nas seeds de L^{full}_{s,t}.
   Qualquer falha deixa o método `undefined` com o motivo; os dois métodos sobre decisões
   diferentes deixam os dois `undefined` (o bootstrap é conjunto).

`ValueError` só para erro de CHAMADA (redução sem linhas, linhas de dois runs).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import PinballScore
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    RuleViolation,
    duplicate_levels,
    extra_levels,
    guardrail_flag_mismatch,
    index_violations,
    missing_levels,
)
from financial_forecasting.features.evaluation.domain.value_objects.ablation_run_losses import (
    AblationRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentKind,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    LOCO,
    PERMUTATION,
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3Parameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_forecast_record import (  # noqa: E501
    IDENTITY_FAMILY,
    PermutedForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    PermutedRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)

_TEST: Final = "test"

Row = ForecastRecord | PermutedForecastRecord
SeriesLabel = tuple[str, int]  # (família, k); a identidade é ("none", 0)
Losses = Mapping[str, float]  # decisão → perda


@dataclass(frozen=True)
class UndefinedRunReduction:
    """Um run que não reduz: o motivo vem da regra violada (nunca `AlignmentFinding`)."""

    run_id: str
    reason: str


@dataclass(frozen=True)
class AttributionAssemblyResult:
    """As séries d_t de cada método, ou `None` e o motivo."""

    permutation: FamilyLossDifferentials | None
    permutation_reason: str | None
    ablation: FamilyLossDifferentials | None
    ablation_reason: str | None


class _Undefined(Exception):
    """Interrompe uma redução ou montagem com o motivo."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


# --- 1. redução por run -----------------------------------------------------------------


def _point_violation(
    rows: Sequence[Row],
    *,
    target: str,
    horizon: int,
    levels: tuple[float, ...],
    realized: RealizedReturns,
) -> RuleViolation | None:
    """As regras públicas do `SeriesAssembly` num ponto (uma definição por regra, C6-4)."""
    by_level: dict[float, list[Row]] = defaultdict(list)
    for row in rows:
        by_level[row.quantile_level].append(row)
    duplicate = duplicate_levels(by_level, target_timestamp=target)  # type: ignore[arg-type]
    if duplicate is not None:
        return duplicate
    indexes = index_violations(
        target_timestamp=target,
        decisions={(row.decision_timestamp, row.decision_idx) for row in rows},
        horizon=horizon,
        realized=realized,
    )
    if indexes:
        return indexes[0]
    for violation in (
        missing_levels(present=by_level, expected=levels, target_timestamp=target),
        extra_levels(present=by_level, expected=levels, where=f"target {target!r}"),
        guardrail_flag_mismatch((row.guardrail_applied for row in rows), target_timestamp=target),
    ):
        if violation is not None:
            return violation
    return None


def _series_losses(
    points: Mapping[str, Sequence[Row]],
    *,
    horizon: int,
    levels: tuple[float, ...],
    realized: RealizedReturns,
) -> dict[str, float]:
    """Perda média na grade de cada decisão de uma série (alvo → linhas dos níveis)."""
    targets = sorted(points)
    for target in targets:
        violation = _point_violation(
            points[target], target=target, horizon=horizon, levels=levels, realized=realized
        )
        if violation is not None:
            raise _Undefined(f"{violation.kind.value}: {violation.detail}")
    forecasts = []
    decisions = []
    for target in targets:
        by_level = {row.quantile_level: row for row in points[target]}
        rows = [by_level[level] for level in levels]
        # I6 da 6.4: o VO do fornecedor com os valores PERSISTIDOS — nunca `from_raw`
        forecasts.append(
            QuantileForecast(
                levels=levels,
                raw_values=tuple(row.value_raw for row in rows),
                guardrail_values=tuple(row.value_guardrail for row in rows),
                guardrail_applied=rows[0].guardrail_applied,
            )
        )
        decisions.append(rows[0].decision_timestamp)
    series = CoverageSeries(
        horizon=horizon,
        levels=levels,
        target_timestamps=tuple(targets),
        forecasts=tuple(forecasts),
        realized=tuple(realized.realized_at(target) for target in targets),
    )
    losses = PinballScore.per_point_losses(series)
    if len(set(decisions)) != len(decisions):
        raise _Undefined(f"h={horizon}: two targets for one decision")
    return dict(zip(decisions, losses, strict=True))


def _common_decisions(by_horizon: Mapping[int, Losses], *, run_id: str) -> tuple[str, ...]:
    """As decisões com todos os horizontes (H3-PAIR), em ordem."""
    common = set.intersection(*(set(losses) for losses in by_horizon.values()))
    if not common:
        raise _Undefined(f"run {run_id}: no decision has every horizon {sorted(by_horizon)}")
    return tuple(sorted(common))


def _labelled_losses(
    records: Sequence[PermutedForecastRecord],
    *,
    levels: tuple[float, ...],
    realized: RealizedReturns,
) -> dict[SeriesLabel, dict[int, dict[str, float]]]:
    """(família, k) → h → decisão → perda; toda série com as decisões da identidade."""
    run_id = records[0].run_id
    grouped: dict[SeriesLabel, dict[int, dict[str, list[Row]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for record in records:
        label = (record.permuted_family, record.permutation_index)
        grouped[label][record.horizon][record.target_timestamp].append(record)
    identity_label = (IDENTITY_FAMILY, 0)
    if identity_label not in grouped:
        raise _Undefined(f"run {run_id}: no identity rows (none, 0)")
    losses: dict[SeriesLabel, dict[int, dict[str, float]]] = {}
    for label in sorted(grouped):
        losses[label] = {}
        for horizon in sorted(grouped[label]):
            try:
                losses[label][horizon] = _series_losses(
                    grouped[label][horizon], horizon=horizon, levels=levels, realized=realized
                )
            except _Undefined as exc:
                raise _Undefined(
                    f"run {run_id} {label[0]} k={label[1]} h={horizon}: {exc.reason}"
                ) from None
    identity = losses[identity_label]
    for label, by_horizon in losses.items():
        for horizon, series in by_horizon.items():
            if horizon not in identity or set(series) != set(identity[horizon]):
                raise _Undefined(
                    f"run {run_id} {label[0]} k={label[1]} h={horizon}: decisions differ from "
                    "the identity"
                )
    return losses


def reduce_permuted_run(
    records: Sequence[PermutedForecastRecord],
    *,
    realized: RealizedReturns,
    levels: tuple[float, ...],
) -> PermutedRunLosses | UndefinedRunReduction:
    """As perdas por decisão de UM run do candidato: identidade e cada (família, k).

    Raises:
        ValueError: nenhuma linha, ou linhas de mais de um run (erro de chamada).
    """
    if not records:
        raise ValueError("reduce_permuted_run needs the records of one run")
    run_ids = {record.run_id for record in records}
    if len(run_ids) != 1:
        raise ValueError(f"reduce_permuted_run takes one run, got {sorted(run_ids)}")
    first = records[0]
    try:
        provenance = {
            (r.seed, r.fold_index, r.permutation_seed, r.permutation_algorithm, r.partition_hash)
            for r in records
        }
        if len(provenance) != 1:
            raise _Undefined(
                f"run {first.run_id}: mixed seed, fold or permutation provenance "
                f"{sorted(provenance)}"
            )
        losses = _labelled_losses(records, levels=levels, realized=realized)
        identity_label = (IDENTITY_FAMILY, 0)
        identity = losses[identity_label]
        decisions = _common_decisions(identity, run_id=first.run_id)
        return PermutedRunLosses(
            run_id=first.run_id,
            seed=first.seed,
            fold_index=first.fold_index,
            permutation_seed=first.permutation_seed,
            permutation_algorithm=first.permutation_algorithm,
            partition_hash=first.partition_hash,
            decision_timestamps=decisions,
            identity={h: tuple(identity[h][t] for t in decisions) for h in identity},
            permuted={
                (label[0], label[1], h): tuple(series[t] for t in decisions)
                for label, by_horizon in losses.items()
                if label != identity_label
                for h, series in by_horizon.items()
            },
        )
    except _Undefined as exc:
        return UndefinedRunReduction(run_id=first.run_id, reason=exc.reason)


def reduce_ablation_run(
    records: Sequence[ForecastRecord],
    *,
    run: CohortRun,
    realized: RealizedReturns,
    levels: tuple[float, ...],
) -> AblationRunLosses | UndefinedRunReduction:
    """As perdas por decisão de UM run da ablação (só `split = "test"`).

    Raises:
        ValueError: linha de outro run (erro de chamada).
    """
    foreign = sorted({record.run_id for record in records} - {run.run_id})
    if foreign:
        raise ValueError(f"reduce_ablation_run takes the records of {run.run_id}, got {foreign}")
    try:
        if run.seed is None:
            raise _Undefined(f"run {run.run_id}: no seed")
        try:
            fold_index = int(str(run.fold))
        except ValueError:
            raise _Undefined(f"run {run.run_id}: fold {run.fold!r} is not an int") from None
        test = [record for record in records if record.split == _TEST]
        if not test:
            raise _Undefined(f"run {run.run_id}: no test rows")
        models = sorted({record.model for record in test} - {run.model})
        if models:
            raise _Undefined(
                f"run {run.run_id}: {AlignmentKind.MODEL_VERSION_MISMATCH.value}: rows of "
                f"{models} for model {run.model!r}"
            )
        grouped: dict[int, dict[str, list[Row]]] = defaultdict(lambda: defaultdict(list))
        for record in test:
            grouped[record.horizon][record.target_timestamp].append(record)
        by_horizon: dict[int, dict[str, float]] = {}
        for horizon in sorted(grouped):
            try:
                by_horizon[horizon] = _series_losses(
                    grouped[horizon], horizon=horizon, levels=levels, realized=realized
                )
            except _Undefined as exc:
                raise _Undefined(f"run {run.run_id} h={horizon}: {exc.reason}") from None
        decisions = _common_decisions(by_horizon, run_id=run.run_id)
        return AblationRunLosses(
            run_id=run.run_id,
            model_version=run.model,
            seed=run.seed,
            fold_index=fold_index,
            decision_timestamps=decisions,
            losses={h: tuple(by_horizon[h][t] for t in decisions) for h in by_horizon},
        )
    except _Undefined as exc:
        return UndefinedRunReduction(run_id=run.run_id, reason=exc.reason)


# --- 2. montagem ------------------------------------------------------------------------


Reduction = PermutedRunLosses | AblationRunLosses | UndefinedRunReduction


def _first_undefined(reductions: Sequence[Reduction]) -> str | None:
    undefined = sorted(
        (r for r in reductions if isinstance(r, UndefinedRunReduction)), key=lambda r: r.run_id
    )
    return undefined[0].reason if undefined else None


def _by_run(reductions: Sequence[Reduction], runs: Sequence[CohortRun]) -> dict[str, Reduction]:
    """Uma redução por run esperado; falta ou sobra é `undefined` (I11)."""
    by_run: dict[str, Reduction] = {}
    for reduction in reductions:
        run_id = reduction.run_id
        if run_id in by_run:
            raise _Undefined(f"run {run_id} reduced twice")
        by_run[run_id] = reduction
    expected = {run.run_id for run in runs}
    missing = sorted(expected - set(by_run))
    if missing:
        raise _Undefined(f"run {missing[0]} has no attribution reduction")
    extra = sorted(set(by_run) - expected)
    if extra:
        raise _Undefined(f"reduction of run {extra[0]} is not a run of the cohort")
    return by_run


def _concatenate(
    parts: Sequence[tuple[int, tuple[str, ...], Mapping[object, tuple[float, ...]]]], *, what: str
) -> tuple[tuple[str, ...], dict[object, tuple[float, ...]]]:
    """Os folds de uma seed, em ordem de fold; decisões disjuntas e crescentes."""
    ordered = sorted(parts, key=lambda part: part[0])
    folds = [part[0] for part in ordered]
    if len(set(folds)) != len(folds):
        raise _Undefined(f"{what}: fold repeated {folds}")
    timestamps: tuple[str, ...] = tuple(t for part in ordered for t in part[1])
    if any(b <= a for a, b in pairwise(timestamps)):
        raise _Undefined(f"{what}: decisions of the folds overlap or are out of order")
    keys = set(ordered[0][2])
    if any(set(part[2]) != keys for part in ordered):
        raise _Undefined(f"{what}: folds with different series")
    series = {key: tuple(v for part in ordered for v in part[2][key]) for key in keys}
    return timestamps, series


def _same_decisions(by_unit: Mapping[object, tuple[str, ...]], *, what: str) -> tuple[str, ...]:
    decision_sets = set(by_unit.values())
    if len(decision_sets) != 1:
        raise _Undefined(f"{what}: decision sets differ between seeds or configurations")
    return next(iter(decision_sets))


def _check_permuted(
    run: CohortRun,
    reduction: PermutedRunLosses,
    *,
    parameters: H3Parameters,
    horizons: tuple[int, ...],
) -> None:
    """A proveniência (C9, I17), a seed do `dim_run` e todo (família, k, h) do `[h3]` (I11)."""
    if reduction.permutation_seed != parameters.permutation_seed:
        raise _Undefined(
            f"run {run.run_id}: permutation_seed {reduction.permutation_seed} != "
            f"{parameters.permutation_seed} of [h3] (C9)"
        )
    if reduction.permutation_algorithm != parameters.permutation_algorithm:
        raise _Undefined(
            f"run {run.run_id}: permutation_algorithm {reduction.permutation_algorithm!r} "
            f"!= {parameters.permutation_algorithm!r} of [h3] (C9)"
        )
    if reduction.partition_hash != parameters.partition_hash:
        raise _Undefined(
            f"run {run.run_id}: partition_hash {reduction.partition_hash[:12]} != "
            f"{parameters.partition_hash[:12]} of [h3.partition] (I17)"
        )
    if reduction.seed != run.seed:
        raise _Undefined(f"run {run.run_id}: seed {reduction.seed} != dim_run {run.seed}")
    if tuple(reduction.identity) != horizons:
        raise _Undefined(
            f"run {run.run_id}: identity horizons {list(reduction.identity)} != "
            f"{list(horizons)}"
        )
    expected = {
        (f, k, h)
        for f in parameters.families
        for k in range(1, parameters.k_p + 1)
        for h in horizons
    }
    missing = sorted(expected - set(reduction.permuted))
    if missing:
        raise _Undefined(f"run {run.run_id}: misses (family, k, h) {list(missing[0])} (I11)")
    extra = sorted(set(reduction.permuted) - expected)
    if extra:
        raise _Undefined(f"run {run.run_id}: (family, k, h) {list(extra[0])} outside [h3]")


def _permutation(  # noqa: PLR0913 — as reduções e o que a conferência precisa
    *,
    candidate_runs: Sequence[CohortRun],
    permuted: Sequence[PermutedRunLosses | UndefinedRunReduction],
    parameters: H3Parameters,
    candidate: str,
    candidate_seeds: tuple[int, ...],
    horizons: tuple[int, ...],
) -> FamilyLossDifferentials:
    reason = _first_undefined(permuted)
    if reason is not None:
        raise _Undefined(reason)
    runs = [run for run in candidate_runs if run.model == candidate]
    by_run = _by_run(permuted, runs)
    families, k_p = parameters.families, parameters.k_p
    parts: dict[int, list[tuple[int, tuple[str, ...], Mapping[object, tuple[float, ...]]]]] = (
        defaultdict(list)
    )
    for run in sorted(runs, key=lambda r: r.run_id):
        reduction = by_run[run.run_id]
        if not isinstance(reduction, PermutedRunLosses):  # pragma: no cover — `_first_undefined`
            raise _Undefined(f"run {run.run_id}: not reduced")
        _check_permuted(run, reduction, parameters=parameters, horizons=horizons)
        series: dict[object, tuple[float, ...]] = {
            ("none", 0, h): reduction.identity[h] for h in horizons
        }
        for key, value in reduction.permuted.items():
            series[key] = value
        parts[reduction.seed].append((reduction.fold_index, reduction.decision_timestamps, series))
    missing_seeds = sorted(set(candidate_seeds) - set(parts))
    if missing_seeds:
        raise _Undefined(f"seed {missing_seeds[0]} of the candidate has no attribution run (I11)")
    extra_seeds = sorted(set(parts) - set(candidate_seeds))
    if extra_seeds:
        raise _Undefined(f"seed {extra_seeds[0]} is not a seed of the candidate")
    per_seed = {
        seed: _concatenate(parts[seed], what=f"permutation seed {seed}") for seed in candidate_seeds
    }
    decisions = _same_decisions({s: per_seed[s][0] for s in candidate_seeds}, what="permutation")
    n = len(decisions)
    # (f, h, s, t) → média nas k de L^{perm f,k} - L^{id}; e (f, h, k, s, t) para o perfil por k
    gap: dict[tuple[str, int, int, int], tuple[float, ...]] = {}
    for seed in candidate_seeds:
        series_of = per_seed[seed][1]
        for f in families:
            for h in horizons:
                identity = series_of[("none", 0, h)]
                for k in range(1, k_p + 1):
                    perm = series_of[(f, k, h)]
                    gap[(f, h, k, seed)] = tuple(perm[t] - identity[t] for t in range(n))
    differentials = {
        (f, h): tuple(
            _mean(
                [_mean([gap[(f, h, k, s)][t] for k in range(1, k_p + 1)]) for s in candidate_seeds]
            )
            for t in range(n)
        )
        for f in families
        for h in horizons
    }
    seed_importances = {
        (f, h, s): _mean(
            [_mean([gap[(f, h, k, s)][t] for k in range(1, k_p + 1)]) for t in range(n)]
        )
        for f in families
        for h in horizons
        for s in candidate_seeds
    }
    permutation_importances = {
        (f, h, k): _mean([_mean([gap[(f, h, k, s)][t] for s in candidate_seeds]) for t in range(n)])
        for f in families
        for h in horizons
        for k in range(1, k_p + 1)
    }
    return FamilyLossDifferentials(
        method=PERMUTATION,
        families=families,
        horizons=horizons,
        decision_timestamps=decisions,
        differentials=differentials,
        seed_importances=seed_importances,
        permutation_importances=permutation_importances,
    )


def _as_series(losses: Mapping[int, tuple[float, ...]]) -> dict[object, tuple[float, ...]]:
    series: dict[object, tuple[float, ...]] = {}
    for horizon, values in losses.items():
        series[horizon] = values
    return series


def _loco(
    *,
    ablation_runs: Sequence[CohortRun],
    ablation_losses: Sequence[AblationRunLosses | UndefinedRunReduction],
    parameters: H3Parameters,
    horizons: tuple[int, ...],
) -> FamilyLossDifferentials:
    reason = _first_undefined(ablation_losses)
    if reason is not None:
        raise _Undefined(reason)
    reference = parameters.ablation_reference_model
    models = {f: parameters.ablation_models[f] for f in parameters.families}
    configurations = (reference, *models.values())
    runs = [run for run in ablation_runs if run.model in configurations]
    by_run = _by_run(ablation_losses, runs)
    seeds = parameters.ablation_seeds
    parts: dict[
        tuple[str, int], list[tuple[int, tuple[str, ...], Mapping[object, tuple[float, ...]]]]
    ] = defaultdict(list)
    for run in sorted(runs, key=lambda r: r.run_id):
        reduction = by_run[run.run_id]
        if not isinstance(reduction, AblationRunLosses):  # pragma: no cover — `_first_undefined`
            raise _Undefined(f"run {run.run_id}: not reduced")
        if reduction.model_version != run.model or reduction.seed != run.seed:
            raise _Undefined(f"run {run.run_id}: reduction identity differs from the dim_run")
        if tuple(reduction.losses) != horizons:
            raise _Undefined(
                f"run {run.run_id}: horizons {list(reduction.losses)} != {list(horizons)}"
            )
        parts[(run.model, reduction.seed)].append(
            (reduction.fold_index, reduction.decision_timestamps, _as_series(reduction.losses))
        )
    for model in configurations:
        for seed in seeds:
            if (model, seed) not in parts:
                raise _Undefined(
                    f"configuration {model} seed {seed} of the ablation has no run (I11)"
                )
    extra = sorted(key for key in parts if key[1] not in seeds)
    if extra:
        raise _Undefined(f"ablation run of {extra[0][0]} seed {extra[0][1]} is not a declared seed")
    units = {
        key: _concatenate(parts[key], what=f"ablation {key[0]} seed {key[1]}")
        for key in sorted(parts)
    }
    decisions = _same_decisions({key: unit[0] for key, unit in units.items()}, what="loco")
    n = len(decisions)

    def seed_mean(model: str, h: int, t: int) -> float:
        return _mean([units[(model, s)][1][h][t] for s in seeds])

    differentials = {
        (f, h): tuple(seed_mean(models[f], h, t) - seed_mean(reference, h, t) for t in range(n))
        for f in parameters.families
        for h in horizons
    }
    seed_importances = {
        (f, h, s): _mean(
            [units[(models[f], s)][1][h][t] - units[(reference, s)][1][h][t] for t in range(n)]
        )
        for f in parameters.families
        for h in horizons
        for s in seeds
    }
    return FamilyLossDifferentials(
        method=LOCO,
        families=parameters.families,
        horizons=horizons,
        decision_timestamps=decisions,
        differentials=differentials,
        seed_importances=seed_importances,
        permutation_importances={},
    )


class AttributionAssembly:
    """Monta as séries d_t de H3 nos dois métodos (ver docstring do módulo)."""

    @staticmethod
    def assemble(  # noqa: PLR0913 — as reduções e as declarações do plano
        *,
        candidate_runs: Sequence[CohortRun],
        permuted: Sequence[PermutedRunLosses | UndefinedRunReduction],
        ablation_runs: Sequence[CohortRun],
        ablation_losses: Sequence[AblationRunLosses | UndefinedRunReduction],
        parameters: H3Parameters,
        candidate: str,
        candidate_seeds: tuple[int, ...],
        horizons: tuple[int, ...],
    ) -> AttributionAssemblyResult:
        """As séries de cada método, ou `None` com o motivo (nunca exceção de dado)."""
        permutation: FamilyLossDifferentials | None = None
        permutation_reason: str | None = None
        ablation: FamilyLossDifferentials | None = None
        ablation_reason: str | None = None
        try:
            permutation = _permutation(
                candidate_runs=candidate_runs,
                permuted=permuted,
                parameters=parameters,
                candidate=candidate,
                candidate_seeds=candidate_seeds,
                horizons=horizons,
            )
        except _Undefined as exc:
            permutation_reason = exc.reason
        try:
            ablation = _loco(
                ablation_runs=ablation_runs,
                ablation_losses=ablation_losses,
                parameters=parameters,
                horizons=horizons,
            )
        except _Undefined as exc:
            ablation_reason = exc.reason
        if (
            permutation is not None
            and ablation is not None
            and permutation.decision_timestamps != ablation.decision_timestamps
        ):
            reason = (
                "the permutation and loco decision sets differ "
                f"({len(permutation.decision_timestamps)} vs "
                f"{len(ablation.decision_timestamps)}); the joint bootstrap needs one set"
            )
            permutation, ablation = None, None
            permutation_reason, ablation_reason = reason, reason
        return AttributionAssemblyResult(
            permutation=permutation,
            permutation_reason=permutation_reason,
            ablation=ablation,
            ablation_reason=ablation_reason,
        )
