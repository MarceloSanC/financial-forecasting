"""Fábrica pura de cohort sintético do gold (Stage 6.4, Tasks 04, 05, 06, 09 e 11).

`make_cohort(...)` devolve `records` (linhas longas do silver já juntadas ao
`dim_run`), `runs` e `realized` **coerentes** — sem nenhum achado do `SeriesAssembly` —
para que cada teste aplique uma violação só. Stdlib + domínio (gate de pureza).

Desenho do cohort padrão: modelos `gbm` (determinístico, seed `None`) e `tft` (seeds 1
e 2), folds `f0`/`f1` (fronteira no meio do intervalo de decisões), horizontes 1 e 2,
grade simétrica de 7 níveis, 40 sessões diárias, primeira decisão na sessão 5. O ponto
de decisão d do horizonte h tem alvo d + h; toda série termina na última sessão. Valores
pseudo-aleatórios determinísticos (`random.Random` semeado por string), para que nenhum
diferencial de perdas seja constante.

Um ponto especial (`Cohort.special`: `tft`, primeira seed, primeiro horizonte, primeira
decisão) tem `value_raw` cruzado, `value_guardrail` não-decrescente **diferente** de
`sorted(value_raw)` e `guardrail_applied = False` — o que `from_raw` nunca produziria.

Os mutadores devolvem um `Cohort` novo (imutável).

Stage 7.3 (Task 24): `with_permuted`, `with_ablation` e `with_vsn` acrescentam registros
sintéticos de atribuição pelos MESMOS runs e decisões de teste do candidato: linhas de
`fact_permuted_predictions` (identidade com valores próprios, diferentes do
`fact_oos_predictions`), runs e linhas LOCO da ablação (fold como inteiro em texto, o
formato do `dim_run`) e pesos da VSN.
"""

from __future__ import annotations

import dataclasses
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_forecast_record import (  # noqa: E501
    IDENTITY_FAMILY,
    PermutedForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_weight_record import (
    VsnWeightRecord,
)

GOLD_LEVELS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_OFFSETS = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)
DEFAULT_SEEDS: Mapping[str, tuple[int | None, ...]] = {"gbm": (None,), "tft": (1, 2)}
DEFAULT_HORIZONS = (1, 2)
FEATURE_SET = "fs-core"


def session(index: int) -> str:
    """Timestamp ISO UTC da sessão `index` (uma por dia)."""
    return (_EPOCH + timedelta(days=index)).isoformat()


def run_id(model: str, seed: int | None, fold: str) -> str:
    return f"{model}-s{seed}-{fold}"


@dataclass(frozen=True)
class Cohort:
    """Entradas do `SeriesAssembly.assemble`."""

    records: tuple[ForecastRecord, ...]
    runs: tuple[CohortRun, ...]
    realized: RealizedReturns
    special: Special | None = None
    # Stage 7.3: registros de atribuição (vazios até os mutadores `with_*`)
    permuted: tuple[PermutedForecastRecord, ...] = ()
    ablation_runs: tuple[CohortRun, ...] = ()
    ablation_records: tuple[ForecastRecord, ...] = ()
    vsn: tuple[VsnWeightRecord, ...] = ()


@dataclass(frozen=True)
class Special:
    """Coordenadas e valores do ponto com guardrail persistido fora do `from_raw`."""

    model: str
    seed: int | None
    horizon: int
    target_timestamp: str
    raw: tuple[float, ...]
    guardrail: tuple[float, ...]


def _values(rng: random.Random) -> tuple[float, ...]:
    center = rng.uniform(-0.02, 0.02)
    scale = rng.uniform(0.5, 1.5)
    return tuple(center + scale * offset for offset in _OFFSETS)


def make_cohort(  # noqa: PLR0913 — um parâmetro por eixo do cohort (keyword-only)
    *,
    seeds: Mapping[str, tuple[int | None, ...]] = DEFAULT_SEEDS,
    folds: tuple[str, ...] = ("f0", "f1"),
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    levels: tuple[float, ...] = GOLD_LEVELS,
    n_sessions: int = 40,
    first_decision: int = 5,
    prefixes: Mapping[str, int] | None = None,
) -> Cohort:
    """Cohort coerente (sem achado) com os eixos pedidos.

    `prefixes[model]` atrasa a primeira decisão do modelo em N sessões (déficit de
    janela); o chamador passa o `window_deficits` correspondente.
    """
    prefixes = prefixes or {}
    span = n_sessions - first_decision
    boundaries = [first_decision + span * (k + 1) // len(folds) for k in range(len(folds))]

    def fold_of(decision: int) -> str:
        return next(fold for fold, bound in zip(folds, boundaries, strict=True) if decision < bound)

    runs = tuple(
        CohortRun(
            run_id=run_id(model, seed, fold),
            model=model,
            seed=seed,
            fold=fold,
            feature_set_name=FEATURE_SET,
            config_signature=f"sig-{model}",
        )
        for model in sorted(seeds)
        for seed in seeds[model]
        for fold in folds
    )
    records: list[ForecastRecord] = []
    for model in sorted(seeds):
        for seed in seeds[model]:
            for horizon in horizons:
                rng = random.Random(f"{model}|{seed}|{horizon}")
                start = first_decision + prefixes.get(model, 0)
                for decision in range(start, n_sessions - horizon):
                    raw = _values(rng)
                    for level, value in zip(levels, raw, strict=False):
                        records.append(
                            ForecastRecord(
                                run_id=run_id(model, seed, fold_of(decision)),
                                model=model,
                                seed=seed,
                                fold=fold_of(decision),
                                horizon=horizon,
                                decision_idx=decision,
                                decision_timestamp=session(decision),
                                target_timestamp=session(decision + horizon),
                                split="test",
                                quantile_level=level,
                                value_raw=value,
                                value_guardrail=value,
                                guardrail_applied=False,
                            )
                        )
    rng = random.Random("realized")
    realized = RealizedReturns(
        timestamps=tuple(session(i) for i in range(n_sessions)),
        returns=tuple(rng.uniform(-0.03, 0.03) for _ in range(n_sessions)),
    )
    cohort = Cohort(records=tuple(records), runs=runs, realized=realized)
    special = special_point(cohort)
    return with_special(cohort, special) if special is not None else cohort


def special_point(cohort: Cohort) -> Special | None:
    """O ponto especial: `tft`, primeira seed, primeiro horizonte, primeira decisão."""
    rows = [r for r in cohort.records if r.model == "tft"]
    if not rows:
        return None
    seed = min((r.seed for r in rows), key=lambda s: -1 if s is None else s)
    horizon = min(r.horizon for r in rows)
    target = min(r.target_timestamp for r in rows if r.seed == seed and r.horizon == horizon)
    point = sorted(
        (r for r in rows if (r.seed, r.horizon, r.target_timestamp) == (seed, horizon, target)),
        key=lambda r: r.quantile_level,
    )
    raw = tuple(reversed([r.value_raw for r in point]))  # cruzado
    guardrail = (*sorted(raw)[:-1], sorted(raw)[-1] + 0.005)  # não-decrescente ≠ sorted(raw)
    return Special("tft", seed, horizon, target, raw, guardrail)


def with_special(cohort: Cohort, special: Special) -> Cohort:
    levels = sorted({r.quantile_level for r in cohort.records})

    def change(record: ForecastRecord) -> ForecastRecord:
        position = levels.index(record.quantile_level)
        return dataclasses.replace(
            record,
            value_raw=special.raw[position],
            value_guardrail=special.guardrail[position],
            guardrail_applied=False,
        )

    changed = replace_records(
        cohort,
        at_point(special.model, special.seed, special.horizon, special.target_timestamp),
        change,
    )
    return dataclasses.replace(changed, special=special)


# --- mutadores -------------------------------------------------------------------------

Predicate = Callable[[ForecastRecord], bool]


def at_point(model: str, seed: int | None, horizon: int, target_timestamp: str) -> Predicate:
    """Seleciona todas as linhas (níveis) de um ponto."""
    return lambda r: (
        (r.model, r.seed, r.horizon, r.target_timestamp)
        == (
            model,
            seed,
            horizon,
            target_timestamp,
        )
    )


def of_series(model: str, seed: int | None, horizon: int) -> Predicate:
    """Seleciona todas as linhas de uma série (modelo, seed, h)."""
    return lambda r: (r.model, r.seed, r.horizon) == (model, seed, horizon)


def targets_of(cohort: Cohort, model: str, seed: int | None, horizon: int) -> list[str]:
    """Alvos da série, em ordem."""
    return sorted(
        {r.target_timestamp for r in cohort.records if of_series(model, seed, horizon)(r)}
    )


def drop_records(cohort: Cohort, predicate: Predicate) -> Cohort:
    return dataclasses.replace(cohort, records=tuple(r for r in cohort.records if not predicate(r)))


def replace_records(
    cohort: Cohort, predicate: Predicate, change: Callable[[ForecastRecord], ForecastRecord]
) -> Cohort:
    return dataclasses.replace(
        cohort, records=tuple(change(r) if predicate(r) else r for r in cohort.records)
    )


def add_records(cohort: Cohort, *extra: ForecastRecord) -> Cohort:
    return dataclasses.replace(cohort, records=cohort.records + extra)


def replace_runs(
    cohort: Cohort, predicate: Callable[[CohortRun], bool], change: Callable[[CohortRun], CohortRun]
) -> Cohort:
    return dataclasses.replace(
        cohort, runs=tuple(change(r) if predicate(r) else r for r in cohort.runs)
    )


def with_calib(
    cohort: Cohort, *, model: str, calib_decisions: Mapping[str, tuple[int, ...]]
) -> Cohort:
    """Acrescenta registros `split = "calib"` pelos mesmos runs (Stage 7.2, Task 14).

    `calib_decisions[fold]` são os índices de decisão do calib de cada run daquele fold,
    em todo horizonte e seed do `model`; alvo = decisão + h. Os valores vêm de um
    `random.Random` semeado por (modelo, seed, fold, h), com `value_guardrail` igual a
    `value_raw` (grade já monótona).
    """
    levels = sorted({r.quantile_level for r in cohort.records})
    horizons = sorted({r.horizon for r in cohort.records if r.model == model})
    extra: list[ForecastRecord] = []
    for run in cohort.runs:
        if run.model != model or run.fold not in calib_decisions:
            continue
        for horizon in horizons:
            rng = random.Random(f"calib|{model}|{run.seed}|{run.fold}|{horizon}")
            for decision in calib_decisions[run.fold]:
                raw = _values(rng)
                for level, value in zip(levels, raw, strict=False):
                    extra.append(
                        ForecastRecord(
                            run_id=run.run_id,
                            model=model,
                            seed=run.seed,
                            fold=run.fold,
                            horizon=horizon,
                            decision_idx=decision,
                            decision_timestamp=session(decision),
                            target_timestamp=session(decision + horizon),
                            split="calib",
                            quantile_level=level,
                            value_raw=value,
                            value_guardrail=value,
                            guardrail_applied=False,
                        )
                    )
    return add_records(cohort, *extra)


# --- Stage 7.3, Task 24: registros de atribuição ------------------------------------------

PERMUTATION_ALGORITHM = "fisher_yates_random_random_v1"
PERMUTATION_SEED = 130
PARTITION_HASH = "a1" * 32  # o `SYNTHETIC_PARTITION_HASH` do helper `_h3_parameters`
ABLATION_FEATURE_SET = "fs_all_ablation"


def fold_index_of(cohort: Cohort, fold: str | None) -> int:
    """Posição do fold do candidato (os folds sintéticos são `f0`, `f1`, ...)."""
    folds = sorted({run.fold for run in cohort.runs if run.fold is not None})
    return folds.index(str(fold))


def points_of_run(cohort: Cohort, run: CohortRun) -> list[ForecastRecord]:
    """Uma linha por (h, decisão) do teste do run (só pelas coordenadas do ponto)."""
    seen: dict[tuple[int, int], ForecastRecord] = {}
    for record in cohort.records:
        if record.run_id == run.run_id and record.split == "test":
            seen.setdefault((record.horizon, record.decision_idx), record)
    return [seen[key] for key in sorted(seen)]


def with_permuted(  # noqa: PLR0913 — um parâmetro por coluna de proveniência
    cohort: Cohort,
    *,
    model: str = "tft",
    k_p: int = 2,
    families: tuple[str, ...] = H3_FAMILIES,
    partition_hash: str = PARTITION_HASH,
    permutation_seed: int = PERMUTATION_SEED,
    permutation_algorithm: str = PERMUTATION_ALGORITHM,
) -> Cohort:
    """Linhas de `fact_permuted_predictions` para cada run do `model`: identidade e (f, k).

    Os valores vêm de um `random.Random` semeado por (run, família, k, h, decisão), com
    `value_guardrail = value_raw` (grade monótona): a identidade NÃO repete o
    `fact_oos_predictions` do mesmo ponto.
    """
    levels = sorted({r.quantile_level for r in cohort.records})
    labels = [(IDENTITY_FAMILY, 0), *((f, k) for f in families for k in range(1, k_p + 1))]
    extra: list[PermutedForecastRecord] = []
    for run in cohort.runs:
        if run.model != model or run.seed is None:
            continue
        for point in points_of_run(cohort, run):
            for family, k in labels:
                rng = random.Random(
                    f"perm|{run.run_id}|{family}|{k}|{point.horizon}|{point.decision_idx}"
                )
                for level, value in zip(levels, _values(rng), strict=False):
                    extra.append(
                        PermutedForecastRecord(
                            run_id=run.run_id,
                            model=model,
                            seed=run.seed,
                            fold_index=fold_index_of(cohort, run.fold),
                            permuted_family=family,
                            permutation_index=k,
                            permutation_seed=permutation_seed,
                            permutation_algorithm=permutation_algorithm,
                            partition_hash=partition_hash,
                            horizon=point.horizon,
                            decision_idx=point.decision_idx,
                            decision_timestamp=point.decision_timestamp,
                            target_timestamp=point.target_timestamp,
                            quantile_level=level,
                            value_raw=value,
                            value_guardrail=value,
                            guardrail_applied=False,
                        )
                    )
    return dataclasses.replace(cohort, permuted=cohort.permuted + tuple(extra))


def ablation_models(families: tuple[str, ...] = H3_FAMILIES) -> tuple[str, ...]:
    """A configuração de referência e as quatro LOCO, na ordem das famílias."""
    return (LOCO_REFERENCE_MODEL, *(loco_model_of(family) for family in families))


def with_ablation(cohort: Cohort, *, model: str = "tft", seeds: tuple[int, ...] = (1, 2)) -> Cohort:
    """Runs e linhas de teste LOCO nas MESMAS decisões do candidato, por fold e seed.

    O fold do run é o inteiro em texto (`"0"`, `"1"`), o formato do `dim_run`.
    """
    levels = sorted({r.quantile_level for r in cohort.records})
    reference = next(run for run in cohort.runs if run.model == model)
    by_fold = {
        str(run.fold): points_of_run(cohort, run)
        for run in cohort.runs
        if run.model == model and run.seed == reference.seed
    }
    runs: list[CohortRun] = []
    records: list[ForecastRecord] = []
    for configuration in ablation_models():
        for seed in seeds:
            for fold in sorted(by_fold):
                index = fold_index_of(cohort, fold)
                ablation = CohortRun(
                    run_id=f"{configuration}-s{seed}-{index}",
                    model=configuration,
                    seed=seed,
                    fold=str(index),
                    feature_set_name=ABLATION_FEATURE_SET,
                    config_signature=f"sig-{configuration}",
                )
                runs.append(ablation)
                for point in by_fold[fold]:
                    rng = random.Random(
                        f"loco|{configuration}|{seed}|{point.horizon}|{point.decision_idx}"
                    )
                    for level, value in zip(levels, _values(rng), strict=False):
                        records.append(
                            dataclasses.replace(
                                point,
                                run_id=ablation.run_id,
                                model=configuration,
                                seed=seed,
                                fold=ablation.fold,
                                quantile_level=level,
                                value_raw=value,
                                value_guardrail=value,
                                guardrail_applied=False,
                            )
                        )
    return dataclasses.replace(
        cohort,
        ablation_runs=cohort.ablation_runs + tuple(runs),
        ablation_records=cohort.ablation_records + tuple(records),
    )


def with_vsn(cohort: Cohort, *, variables: Mapping[str, str], model: str = "tft") -> Cohort:
    """Pesos da VSN (variável → família) em cada decisão de teste de cada run do `model`."""
    extra: list[VsnWeightRecord] = []
    for run in cohort.runs:
        if run.model != model or run.seed is None:
            continue
        decisions = sorted(
            {(p.decision_idx, p.decision_timestamp) for p in points_of_run(cohort, run)}
        )
        for decision_idx, timestamp in decisions:
            rng = random.Random(f"vsn|{run.run_id}|{decision_idx}")
            raw = [rng.uniform(0.1, 1.0) for _ in variables]
            total = sum(raw)
            for (variable, family), weight in zip(sorted(variables.items()), raw, strict=True):
                extra.append(
                    VsnWeightRecord(
                        run_id=run.run_id,
                        model=model,
                        seed=run.seed,
                        fold_index=fold_index_of(cohort, run.fold),
                        decision_idx=decision_idx,
                        decision_timestamp=timestamp,
                        variable=variable,
                        family=family,
                        weight=weight / total,
                    )
                )
    return dataclasses.replace(cohort, vsn=cohort.vsn + tuple(extra))
