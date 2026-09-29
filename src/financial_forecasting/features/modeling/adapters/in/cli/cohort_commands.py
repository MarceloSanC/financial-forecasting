"""Comandos do cohort confirmatório: `sweep`, `freeze`, `run` e `verify` (Stage 5.5).

ATENÇÃO — `in` é keyword do Python: este módulo é carregado por
`importlib.import_module` (o `cli.py` da raiz e os testes) — LAYOUT §8.

Tudo o que os comandos usam chega por `CohortCommandDeps`, montado pelo `cli.py`
a partir do composition root (regra 3 do `check_layout`: `adapters/in` não
importa `adapters/out`). O arquivo do cohort é lido e reescrito por
`cohort_file`.

- `sweep` — exige `n_trials` (do arquivo ou `--n-trials`); adquire o lock do
  `data_root`; roda os dois sweeps na geometria EXPLORATÓRIA
  (`geometry.exploratory()`) sob o scope id do rascunho e grava cada resultado
  pelo ledger. Um sweep já gravado sob o mesmo scope id não roda de novo.
- `freeze` — adquire o lock; lê do ledger os resultados GRAVADOS pelo `sweep`
  (nunca retreina nem relê um estudo) e reescreve o arquivo com os
  hiperparâmetros, a proveniência e a impressão digital do grid atual, que tem
  de ser a mesma sobre a qual os dois sweeps rodaram (I4).
- `run` — chama o use case, que é o dono único do lock no `run`.
- `verify` — confere, só pelo índice de runs do silver, que cada modelo tem
  um run por fold com a contagem esperada e que todos os runs de um fold têm os
  mesmos `target_timestamp` por horizonte. Não importa nada de `evaluation`:
  verificar a corrida não pode olhar métrica nenhuma (cegamento até a 6.5).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, TextIO

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortNotFrozenError,
    DatasetMismatchError,
    RunConfirmatoryCohortCommand,
    cohort_model_keys,
    load_training_grid,
    recorded_run_problems,
)
from financial_forecasting.features.modeling.application.use_cases.run_gbm_sweep import (
    RunGbmSweepCommand,
)
from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
    RunTftSweepCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.domain.exceptions.base import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (  # noqa: E501
        CohortProgressLedger,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        CohortRunIndex,
    )
    from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (  # noqa: E501
        RunConfirmatoryCohortResult,
    )
    from financial_forecasting.features.modeling.application.use_cases.run_gbm_sweep import (
        RunGbmSweepResult,
    )
    from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
        RunTftSweepResult,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

_TFT = "tft"
_GBM = "gbm"
# `verify` com divergência; erro de execução do CLI sai com 2 (`cli.py`).
EXIT_MISMATCH = 1


class CohortCommandError(ApplicationError):
    """Pré-condição de um comando do cohort não atendida (mensagem acionável)."""


@dataclass(frozen=True)
class CohortCommandDeps:
    """O que os comandos recebem do composition root (via `cli.py`)."""

    store: MedallionStore
    hasher: Hasher
    ledger: CohortProgressLedger
    run_index: CohortRunIndex
    run_tft_sweep: Callable[[RunTftSweepCommand], RunTftSweepResult]
    run_gbm_sweep: Callable[[RunGbmSweepCommand], RunGbmSweepResult]
    confirmatory_cohort_for: Callable[
        [Path, str], Callable[[RunConfirmatoryCohortCommand], RunConfirmatoryCohortResult]
    ]
    modeling_columns: Sequence[str]
    load_spec: Callable[[Path], CohortSpec]
    parse_spec: Callable[[str], CohortSpec]
    dump_spec: Callable[[CohortSpec], str]


# -- sweep -----------------------------------------------------------------------------


def sweep(
    deps: CohortCommandDeps,
    cohort_path: Path,
    *,
    out: TextIO,
    n_trials: int | None = None,
    break_stale_lock: bool = False,
) -> int:
    """Roda os dois sweeps exploratórios e grava os resultados pelo ledger."""
    spec = _with_n_trials(deps.load_spec(cohort_path), n_trials)
    scope_id = _scope_id(deps.hasher, spec)
    plan = spec.sweep
    budget = plan.n_trials
    assert budget is not None  # _with_n_trials garante
    geometry = spec.geometry.exploratory()
    scope = ScopeSpec(
        asset_id=spec.asset_id,
        feature_set_name=spec.feature_set_name,
        max_horizon=spec.max_horizon,
        cohort_id=scope_id,
    )
    deps.ledger.acquire_writer(break_stale=break_stale_lock)
    try:
        done = deps.ledger.sweep_results(scope_id)
        if _TFT in done:
            out.write(f"tft sweep already recorded under {scope_id} — skipped\n")
        else:
            tft = deps.run_tft_sweep(
                RunTftSweepCommand(
                    base_params=plan.tft_base_params,
                    space=plan.tft_space,
                    scope=scope,
                    n_trials=budget,
                    seed=plan.sampler_seed,
                    horizons=spec.horizons,
                    quantile_levels=spec.quantile_levels,
                    n_folds=geometry.n_folds,
                    test_size=geometry.test_size,
                    val_size=geometry.val_size,
                    calib_size=geometry.calib_size,
                    embargo=geometry.embargo,
                )
            )
            deps.ledger.record_sweep_result(scope_id, _TFT, _sweep_record(tft, budget))
            out.write(f"tft sweep recorded under {scope_id} (study {tft.study_id})\n")
        if _GBM in done:
            out.write(f"gbm sweep already recorded under {scope_id} — skipped\n")
        else:
            gbm = deps.run_gbm_sweep(
                RunGbmSweepCommand(
                    base_params=plan.gbm_base_params,
                    space=plan.gbm_space,
                    scope=scope,
                    n_trials=budget,
                    seed=plan.sampler_seed,
                    horizons=spec.horizons,
                    quantile_levels=spec.quantile_levels,
                    n_folds=geometry.n_folds,
                    test_size=geometry.test_size,
                    val_size=geometry.val_size,
                    calib_size=geometry.calib_size,
                    embargo=geometry.embargo,
                )
            )
            deps.ledger.record_sweep_result(scope_id, _GBM, _sweep_record(gbm, budget))
            out.write(f"gbm sweep recorded under {scope_id} (study {gbm.study_id})\n")
    finally:
        deps.ledger.release_writer()
    return 0


def _with_n_trials(spec: CohortSpec, n_trials: int | None) -> CohortSpec:
    """`--n-trials` sobrepõe o arquivo; entra no rascunho, logo no scope id."""
    if n_trials is not None:
        return replace(spec, sweep=replace(spec.sweep, n_trials=n_trials))
    if spec.sweep.n_trials is None:
        raise CohortCommandError(
            "sweep.n_trials is not set in the cohort file — decide it or pass --n-trials"
        )
    return spec


def _scope_id(hasher: Hasher, spec: CohortSpec) -> str:
    draft_hash = CohortHash.compute(hasher=hasher, payload=spec.draft_payload())
    return spec.exploratory_scope_id(draft_hash)


def _sweep_record(
    result: RunTftSweepResult | RunGbmSweepResult, n_trials: int
) -> dict[str, object]:
    best = next(t for t in result.trials if t.trial_number == result.best_trial_number)
    return {
        "study_id": result.study_id,
        "best_trial_number": result.best_trial_number,
        "best_objective": best.objective_value,
        "best_params": asdict(result.best_params),
        "dataset_fingerprint": result.dataset_fingerprint,
        "n_trials": n_trials,
    }


# -- freeze ----------------------------------------------------------------------------


def freeze(
    deps: CohortCommandDeps,
    cohort_path: Path,
    *,
    out: TextIO,
    break_stale_lock: bool = False,
) -> int:
    """Reescreve o arquivo com HPs, proveniência e impressão digital (congelamento)."""
    spec = deps.load_spec(cohort_path)
    if spec.is_frozen():
        raise CohortCommandError(
            f"cohort {spec.name!r} r{spec.revision} is already frozen — "
            "a change needs a new revision"
        )
    if spec.sweep.n_trials is None:
        raise CohortCommandError("sweep.n_trials is not set — sweep with it before freezing")
    if not spec.seeds:
        raise CohortCommandError("seeds are empty — decide the TFT seeds before freezing")
    scope_id = _scope_id(deps.hasher, spec)
    deps.ledger.acquire_writer(break_stale=break_stale_lock)
    try:
        results = deps.ledger.sweep_results(scope_id)
        missing = [model for model in (_TFT, _GBM) if model not in results]
        if missing:
            raise CohortCommandError(
                f"no recorded sweep result for {missing} under {scope_id} — run sweep first"
            )
        tft, gbm = results[_TFT], results[_GBM]
        swept_on = {str(tft["dataset_fingerprint"]), str(gbm["dataset_fingerprint"])}
        if len(swept_on) != 1:
            raise DatasetMismatchError("the TFT and GBM sweeps ran on different datasets")
        (swept_fingerprint,) = swept_on
        grid = load_training_grid(
            store=deps.store, asset_id=spec.asset_id, columns=deps.modeling_columns
        )
        current = grid_fingerprint(grid, hasher=deps.hasher, asset_id=spec.asset_id)
        if current != swept_fingerprint:
            raise DatasetMismatchError(
                f"current dataset fingerprint {current[:12]} != the sweeps' "
                f"{swept_fingerprint[:12]} — the materialized data changed after the sweeps"
            )
        spec.geometry.fits(n_sessions=len(grid.timestamps), max_horizon=spec.max_horizon)
        frozen = replace(
            spec,
            # `best_params` volta do JSON como dict[str, object]; os tipos são
            # conferidos pela ida e volta do arquivo logo abaixo (F3 do Checkpoint C).
            tft_params=TftTrainingParams(**_params(tft)),  # type: ignore[arg-type]
            gbm_params=GbmTrainingParams(**_params(gbm)),  # type: ignore[arg-type]
            provenance=SweepProvenance(
                tft_study_id=str(tft["study_id"]),
                tft_best_trial=int(str(tft["best_trial_number"])),
                tft_best_objective=float(str(tft["best_objective"])),
                gbm_study_id=str(gbm["study_id"]),
                gbm_best_trial=int(str(gbm["best_trial_number"])),
                gbm_best_objective=float(str(gbm["best_objective"])),
                dataset_fingerprint=swept_fingerprint,
            ),
            dataset_fingerprint=current,
        )
        text = deps.dump_spec(frozen)
        # O hash publicado tem de ser o que o `run` vai recalcular do ARQUIVO: a
        # ida e volta tem de fechar antes de gravar (valor de tipo errado vindo de
        # `best_params`, ou escrita que o `parse` recusa, param aqui).
        reread = deps.parse_spec(text)
        if reread != frozen:
            raise CohortCommandError(
                "the frozen cohort does not survive a write/read round trip — not written"
            )
        _write_atomically(cohort_path, text)
    finally:
        deps.ledger.release_writer()
    cohort_hash = CohortHash.compute(hasher=deps.hasher, payload=reread.hash_payload())
    out.write(f"frozen {frozen.cohort_id(cohort_hash)}\nhash {cohort_hash.value}\n")
    return 0


def _params(record: Mapping[str, object]) -> dict[str, object]:
    params = record["best_params"]
    if not isinstance(params, dict):
        raise CohortCommandError(f"recorded best_params is not a table: {params!r}")
    return dict(params)


def _write_atomically(path: Path, text: str) -> None:
    temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


# -- run -------------------------------------------------------------------------------


def run(
    deps: CohortCommandDeps,
    cohort_path: Path,
    *,
    out: TextIO,
    break_stale_lock: bool = False,
) -> int:
    """Corre o cohort congelado; o lock é do use case (o comando não o adquire)."""
    spec = deps.load_spec(cohort_path)
    use_case = deps.confirmatory_cohort_for(cohort_path, spec.device)
    result = use_case(RunConfirmatoryCohortCommand(spec=spec, break_stale_lock=break_stale_lock))
    out.write(f"cohort {result.cohort_id}\n")
    for outcome in result.outcomes:
        out.write(f"  {outcome.unit_key}: {outcome.status} ({len(outcome.run_ids)} runs)\n")
    return 0


# -- verify ----------------------------------------------------------------------------


def verify(deps: CohortCommandDeps, cohort_path: Path, *, out: TextIO) -> int:
    """Confere a corrida pelo silver e pelo ledger; exit 0 só se tudo bate.

    A regra de "unidade completa" é a da corrida (`recorded_run_problems`); aqui
    ela vale para todos os modelos juntos (alvos iguais entre modelos por fold).
    Soma-se: nenhum run de modelo não declarado sob o cohort, e o ledger com
    todas as unidades, com as mesmas contagens do silver (A8).
    """
    spec = deps.load_spec(cohort_path)
    if not spec.is_frozen():
        raise CohortNotFrozenError(f"cohort {spec.name!r} r{spec.revision} is not frozen")
    cohort_hash = CohortHash.compute(hasher=deps.hasher, payload=spec.hash_payload())
    cohort_id = spec.cohort_id(cohort_hash)
    recorded = deps.run_index.recorded_runs(
        asset_id=spec.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
    )
    units = cohort_model_keys(spec)
    model_keys = [key for keys in units.values() for key in keys]
    problems = recorded_run_problems(spec, model_keys, recorded)
    unexpected = sorted(set(recorded) - set(model_keys), key=str)
    if unexpected:
        problems.append(f"runs of undeclared models under the cohort: {unexpected}")
    completed = deps.ledger.completed_units(cohort_id)
    for unit_key, keys in units.items():
        silver = {
            run_id: rows for key in keys for run_id, (_, rows, _) in recorded.get(key, {}).items()
        }
        if unit_key not in completed:
            problems.append(f"ledger: unit {unit_key!r} is not marked completed")
        elif dict(completed[unit_key]) != silver:
            problems.append(f"ledger: unit {unit_key!r} counts differ from the silver")
    geometry = spec.geometry
    per_model = sum(
        geometry.expected_prediction_rows(
            fold_index=fold, horizons=spec.horizons, n_levels=len(spec.quantile_levels)
        )
        for fold in range(geometry.n_folds)
    )
    observed_total = sum(
        rows for key in model_keys for _, rows, _ in recorded.get(key, {}).values()
    )
    out.write(
        f"cohort {cohort_id}: {len(model_keys)} models x {geometry.n_folds} folds; "
        f"rows expected {per_model * len(model_keys)}, observed {observed_total}\n"
    )
    for problem in problems:
        out.write(f"MISMATCH {problem}\n")
    if problems:
        return EXIT_MISMATCH
    out.write("OK\n")
    return 0
