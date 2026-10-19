"""Comandos do cohort de ablação: `ablation-pilot`, `-run`, `-verify` e `-freeze` (Stage 7.3).

ATENÇÃO — `in` é keyword do Python: este módulo é carregado por
`importlib.import_module` (o `cli.py` da raiz e os testes) — LAYOUT §8.

Tudo o que os comandos usam chega por `AblationCommandDeps`, montado pelo `cli.py` a
partir do composition root (regra 3 do `check_layout`: `adapters/in` não importa
`adapters/out`). O `CohortCommandDeps` da 5.5 fica intocado (technical 7.3 §1).

- `ablation-pilot` — mede o custo de uma unidade (`MeasureAblationCost`) e imprime o
  teto e a estimativa por número de seeds; não grava nada.
- `ablation-run` — corre o cohort congelado; o use case recusa o rascunho (C3).
- `ablation-verify` — confere a corrida só pelo índice de runs do silver e pelo
  ledger, como o `verify` da 5.5; não olha métrica nenhuma (cegamento, I9).
- `ablation-freeze --seeds 1,2,…` — grava `seeds` e o `torch_build` OBSERVADO (a chave
  `torch` do probe) no arquivo, por troca atômica (`os.replace`); recusa um spec já
  congelado.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
    recorded_run_problems,
)
from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (
    MeasureAblationCostCommand,
)
from financial_forecasting.features.modeling.application.use_cases.run_ablation_cohort import (
    RunAblationCohortCommand,
    ablation_model_keys,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
        AblationCohortSpec,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (  # noqa: E501
        CohortProgressLedger,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        CohortRunIndex,
    )
    from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (  # noqa: E501
        AblationCostReport,
    )
    from financial_forecasting.features.modeling.application.use_cases.run_ablation_cohort import (
        RunAblationCohortResult,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

# `ablation-verify` com divergência; erro de execução do CLI sai com 2 (`cli.py`).
EXIT_MISMATCH = 1
_TORCH_KEY = "torch"
_HOUR = 3600.0


class AblationCommandError(ApplicationError):
    """Pré-condição de um comando do cohort de ablação não atendida."""


@dataclass(frozen=True)
class AblationCommandDeps:
    """O que os comandos de ablação recebem do composition root (via `cli.py`)."""

    hasher: Hasher
    ledger: CohortProgressLedger
    run_index: CohortRunIndex
    load_spec: Callable[[Path], tuple[AblationCohortSpec, CohortSpec]]
    dump_spec: Callable[[AblationCohortSpec], str]
    ablation_cohort_for: Callable[
        [Path], Callable[[RunAblationCohortCommand], RunAblationCohortResult]
    ]
    measure_ablation_cost_for: Callable[
        [Path], Callable[[MeasureAblationCostCommand], AblationCostReport]
    ]
    runtime_probe_for: Callable[[Path, str], RuntimeEnvironmentProbe]
    # Devices que o composition root sabe montar (`_SUPPORTED_DEVICES`): o `freeze`
    # recusa um device fora deles antes de abrir o probe e de escrever (C3-6).
    supported_devices: frozenset[str]


def _cohort_id(hasher: Hasher, spec: AblationCohortSpec) -> tuple[str, str]:
    cohort_hash = CohortHash.compute(hasher=hasher, payload=spec.hash_payload())
    return spec.cohort_id(cohort_hash), cohort_hash.value


# -- pilot ------------------------------------------------------------------------------


def pilot(deps: AblationCommandDeps, path: Path, *, out: TextIO) -> int:
    """Mede a unidade piloto e imprime o relatório; artefato num diretório temporário."""
    spec, base = deps.load_spec(path)
    measure = deps.measure_ablation_cost_for(path)
    with tempfile.TemporaryDirectory(prefix="ablation-pilot-") as pilot_dir:
        report = measure(MeasureAblationCostCommand(spec=spec, base=base, pilot_dir=pilot_dir))
    out.write(
        f"pilot {report.configuration} seed {report.seed} fold {report.fold_index}: "
        f"wall {report.wall_seconds:.1f}s, epochs {report.epochs_run} "
        f"(best {report.best_epoch}, max {report.max_epochs}), "
        f"{report.seconds_per_epoch:.2f}s/epoch; device {report.device}, "
        f"torch {report.torch_build}\n"
    )
    out.write(f"{report.label}\n")
    for seeds in sorted(report.ceiling_seconds):
        out.write(
            f"S={seeds}: ceiling {report.ceiling_seconds[seeds] / _HOUR:.1f} h, "
            f"estimate {report.estimate_seconds[seeds] / _HOUR:.1f} h\n"
        )
    return 0


# -- run --------------------------------------------------------------------------------


def run(
    deps: AblationCommandDeps, path: Path, *, out: TextIO, break_stale_lock: bool = False
) -> int:
    """Corre o cohort de ablação congelado (retomável); o use case recusa o rascunho."""
    spec, base = deps.load_spec(path)
    result = deps.ablation_cohort_for(path)(
        RunAblationCohortCommand(spec=spec, base=base, break_stale_lock=break_stale_lock)
    )
    for outcome in result.outcomes:
        out.write(
            f"unit {outcome.unit_key}: {outcome.status} "
            f"({len(outcome.run_ids)} runs, {outcome.rows_written} rows written)\n"
        )
    out.write(f"ablation {result.cohort_id}: cohort_hash {result.cohort_hash}\n")
    return 0


# -- verify -----------------------------------------------------------------------------


def verify(deps: AblationCommandDeps, path: Path, *, out: TextIO) -> int:
    """Confere a corrida pelo silver e pelo ledger; exit 0 só se tudo bate."""
    spec, base = deps.load_spec(path)
    if not spec.is_frozen():
        raise CohortNotFrozenError(f"ablation cohort {spec.name!r} r{spec.revision} is not frozen")
    cohort_id, _ = _cohort_id(deps.hasher, spec)
    recorded = deps.run_index.recorded_runs(
        asset_id=base.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
    )
    units = ablation_model_keys(spec)
    model_keys = [key for keys in units.values() for key in keys]
    problems = recorded_run_problems(base, model_keys, recorded)
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
    geometry = base.geometry
    per_run_total = sum(
        geometry.expected_prediction_rows(
            fold_index=fold, horizons=base.horizons, n_levels=len(base.quantile_levels)
        )
        for fold in range(geometry.n_folds)
    )
    observed = sum(rows for key in model_keys for _, rows, _ in recorded.get(key, {}).values())
    n_configurations = len(spec.configurations)
    n_seeds = len(spec.seeds)
    out.write(
        f"ablation {cohort_id}: {n_configurations} configurations x {geometry.n_folds} folds x "
        f"{n_seeds} seeds = {n_configurations * geometry.n_folds * n_seeds} runs; "
        f"rows expected {per_run_total * len(model_keys)}, observed {observed}\n"
    )
    for problem in problems:
        out.write(f"MISMATCH {problem}\n")
    if problems:
        return EXIT_MISMATCH
    out.write("OK\n")
    return 0


# -- freeze -----------------------------------------------------------------------------


def freeze(deps: AblationCommandDeps, path: Path, *, out: TextIO, seeds: Sequence[int]) -> int:
    """Congela o spec com as seeds dadas e o `torch_build` observado (troca atômica)."""
    spec, _ = deps.load_spec(path)
    if spec.is_frozen():
        raise AblationCommandError(
            f"ablation cohort {spec.name!r} r{spec.revision} is already frozen — "
            "a new revision is needed to change it"
        )
    if spec.device not in deps.supported_devices:
        raise AblationCommandError(
            f"device {spec.device!r} is not supported; expected one of "
            f"{sorted(deps.supported_devices)} — nothing was frozen"
        )
    torch_build = deps.runtime_probe_for(path, spec.device).snapshot().get(_TORCH_KEY)
    if not torch_build:
        raise AblationCommandError("the runtime probe reported no torch version")
    frozen = spec.with_freeze(seeds=seeds, torch_build=torch_build)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(deps.dump_spec(frozen), encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    cohort_id, cohort_hash = _cohort_id(deps.hasher, frozen)
    out.write(
        f"frozen {cohort_id}: cohort_hash {cohort_hash}; seeds {len(frozen.seeds)}; "
        f"torch_build {torch_build}\n"
    )
    return 0
