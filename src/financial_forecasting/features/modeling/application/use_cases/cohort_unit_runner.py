"""Máquina de unidades dos executores de cohort (Stage 5.5, extraída na Stage 7.3).

Extraída do `RunConfirmatoryCohort` sem mudar comportamento (concept 7.3 D7; ADR
7.3.0003 item 3). O executor confirmatório e o de ablação (`RunAblationCohort`)
importam daqui e nunca um do outro (guarda AST em
`tests/architecture/test_stage_7_3_regression_guards.py`). Cada executor define só a
lista de unidades e as pré-condições. Aqui fica o que eles compartilham:

- as exceções da corrida (I1, I4-I7) e o `CohortUnitOutcome`;
- `load_training_grid` (a leitura do grid único, com as coordenadas do dataset TFT
  importadas do produtor, `dataset_tft_contract`) e `check_cohort_declarations`
  (I4 + geometria);
- `recorded_run_problems`, a fonte única de "unidade completa";
- `writer_lock` (I12: lock de escritor único, liberado em `finally`),
  `check_environment` (I5) e `classify_and_run` (ADR 5.5.0003: ledger → reconferência;
  silver completo → `verified_completed`; parcial → erro; ausente → roda e marca
  depois do sucesso).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.feature_engineering.domain.services.dataset_tft_contract import (  # noqa: E501
    DATASET_TFT_LAYER,
    DATASET_TFT_TABLE,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    TrainingGrid,
    build_training_grid,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (  # noqa: E501
        CohortProgressLedger,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        RunSummary,
    )
    from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

_LOG = logging.getLogger(__name__)

RAN = "ran"
SKIPPED_COMPLETED = "skipped_completed"
VERIFIED_COMPLETED = "verified_completed"

ModelKey = tuple[str, int | None]
RecordedRuns = Mapping[ModelKey, Mapping[str, "RunSummary"]]


class CohortNotFrozenError(ApplicationError):
    """O spec não está congelado (I1): falta HP, proveniência, dado ou seeds."""


class DatasetMismatchError(ApplicationError):
    """A impressão digital do dado lido difere da declarada no spec (I4)."""


class CohortDeclarationMismatchError(ApplicationError):
    """Declarado ≠ observado: proveniência dos sweeps, feature set ou versão do pipeline (I4)."""


class EnvironmentMismatchError(ApplicationError):
    """Árvore suja ou ambiente/código diferente do gravado na primeira execução (I5)."""


class PartialCohortUnitError(ApplicationError):
    """Unidade fora do ledger com gravação parcial no silver (I7-d); remediação: nova revisão."""


class CompletedUnitCorruptedError(ApplicationError):
    """Unidade marcada no ledger cujas contagens não batem mais com o silver (I6)."""


class UnitOutputMismatchError(ApplicationError):
    """A unidade rodou, mas o silver não tem os runs esperados — não é marcada."""


@dataclass(frozen=True)
class CohortUnitOutcome:
    """DTO de saída — o que aconteceu com uma unidade."""

    unit_key: str
    status: str
    run_ids: tuple[str, ...]
    rows_written: int


@dataclass(frozen=True)
class UnitPlan:
    """Uma unidade da corrida: chave, o que ela grava e como executá-la."""

    key: str
    execute: Callable[[], Mapping[str, int]]
    model_keys: tuple[ModelKey, ...]


def _fold_index(fold: str) -> int | None:
    """Fold do índice como inteiro; vazio/ilegível (fold nulo no silver) → `None`."""
    try:
        return int(fold)
    except ValueError:
        return None


def recorded_run_problems(
    spec: CohortSpec,
    model_keys: Sequence[ModelKey],
    recorded: RecordedRuns,
) -> list[str]:
    """O que falta ou sobra nos runs gravados de `model_keys`; lista vazia = completo.

    Fonte ÚNICA de "unidade completa" — usada pela classificação da corrida
    (I7-c), pela conferência depois de executar uma unidade e pelo `verify`.
    Por modelo: um run por fold (`0..n_folds-1`, nem falta nem repete), fold
    legível, a contagem de linhas esperada do fold e todos os horizontes do
    spec; run órfão (registrado sem nenhum fato, I7-b) é ignorado. Entre
    modelos: no mesmo fold, os `target_timestamp` de cada horizonte são os
    mesmos.
    """
    geometry = spec.geometry
    n_levels = len(spec.quantile_levels)
    expected_rows = {
        fold: geometry.expected_prediction_rows(
            fold_index=fold, horizons=spec.horizons, n_levels=n_levels
        )
        for fold in range(geometry.n_folds)
    }
    problems: list[str] = []
    targets_by_fold: dict[int, set[tuple[tuple[int, frozenset[str]], ...]]] = {}
    for model_version, seed in model_keys:
        label = model_version if seed is None else f"{model_version} seed={seed}"
        folds: list[int] = []
        for run_id, (fold, rows, targets) in sorted(
            recorded.get((model_version, seed), {}).items()
        ):
            if rows == 0:
                continue  # órfão (registro sem fatos): não carrega predição, não conta
            index = _fold_index(fold)
            if index is None:
                problems.append(f"{label}: run {run_id} has an unreadable fold {fold!r}")
                continue
            folds.append(index)
            if rows != expected_rows.get(index):
                problems.append(
                    f"{label}: run {run_id} fold {index} has {rows} rows, "
                    f"expected {expected_rows.get(index)}"
                )
            if set(targets) != set(spec.horizons):
                problems.append(
                    f"{label}: run {run_id} has horizons {sorted(targets)}, "
                    f"expected {list(spec.horizons)}"
                )
            targets_by_fold.setdefault(index, set()).add(tuple(sorted(targets.items())))
        if sorted(folds) != list(range(geometry.n_folds)):
            problems.append(f"{label}: folds {sorted(folds)}, expected 0..{geometry.n_folds - 1}")
    problems.extend(
        f"fold {fold}: target_timestamp sets differ across models"
        for fold, variants in sorted(targets_by_fold.items())
        if len(variants) != 1
    )
    return problems


def load_training_grid(
    *, store: MedallionStore, asset_id: str, columns: Sequence[str]
) -> TrainingGrid:
    """O grid único do ativo, lido do dataset materializado (mesma leitura do treino)."""
    rows = store.read(layer=DATASET_TFT_LAYER, table=DATASET_TFT_TABLE, filters={"asset": asset_id})
    return build_training_grid(rows, columns=columns)


def check_cohort_declarations(  # noqa: PLR0913 — as declarações conferidas, uma por argumento
    spec: CohortSpec,
    *,
    store: MedallionStore,
    hasher: Hasher,
    modeling_columns: Sequence[str],
    observed_feature_set_hash: str,
    pipeline_version: str,
    supported_device: str,
    inherited_hyperparameters: bool = False,
) -> TrainingGrid:
    """I4 + geometria: o dado e o código de agora são os que o spec declara.

    Devolve o grid lido (o mesmo da corrida). Erros: `DatasetMismatchError`
    (impressão digital do dado), `CohortDeclarationMismatchError` (proveniência
    dos sweeps, `feature_set_hash`, device, `pipeline_version`) e o erro de
    geometria do domínio.

    `inherited_hyperparameters=True` (Stage 8.4, ADR 8.4.0001 item 6) dispensa SÓ a
    igualdade entre o dado dos sweeps e o declarado: a rodada de produção usa, por
    desenho, os hiperparâmetros do confirmatório sobre dado novo. A proveniência
    continua obrigatória e todas as outras conferências valem.
    """
    grid = load_training_grid(store=store, asset_id=spec.asset_id, columns=modeling_columns)
    observed = grid_fingerprint(grid, hasher=hasher, asset_id=spec.asset_id)
    if observed != spec.dataset_fingerprint:
        raise DatasetMismatchError(
            f"dataset fingerprint {observed[:12]} != declared "
            f"{str(spec.dataset_fingerprint)[:12]} — the materialized data changed"
        )
    provenance = spec.provenance
    if provenance is None:
        raise CohortDeclarationMismatchError("the cohort declares no sweep provenance")
    if not inherited_hyperparameters and provenance.dataset_fingerprint != spec.dataset_fingerprint:
        raise CohortDeclarationMismatchError(
            "sweeps ran on a different dataset than the one declared for the run"
        )
    if spec.feature_set_hash != observed_feature_set_hash:
        raise CohortDeclarationMismatchError(
            f"feature_set_hash {spec.feature_set_hash[:12]} != registry "
            f"{observed_feature_set_hash[:12]}"
        )
    if spec.device != supported_device:
        # O probe grava o device DECLARADO; sem esta igualdade, um spec com
        # "rocm" rodaria em CPU e carimbaria "rocm" no hash e no ledger.
        raise CohortDeclarationMismatchError(
            f"device {spec.device!r} declared, but the trainers run on {supported_device!r}"
        )
    if spec.pipeline_version != pipeline_version:
        raise CohortDeclarationMismatchError(
            f"pipeline_version {spec.pipeline_version!r} != code {pipeline_version!r}"
        )
    spec.geometry.fits(n_sessions=len(grid.timestamps), max_horizon=spec.max_horizon)
    return grid


@contextmanager
def writer_lock(ledger: CohortProgressLedger, *, break_stale: bool) -> Iterator[None]:
    """I12: lock de escritor único do `data_root`, liberado em `finally` (inclusive em erro)."""
    ledger.acquire_writer(break_stale=break_stale)
    try:
        yield
    finally:
        ledger.release_writer()


def check_environment(
    ledger: CohortProgressLedger, probe: RuntimeEnvironmentProbe, cohort_id: str, *, clock: Clock
) -> None:
    """I5: árvore limpa sempre; ambiente gravado na 1ª vez e igual nas seguintes."""
    snapshot = dict(probe.snapshot())
    if snapshot.get(DIRTY_KEY) == "true":
        raise EnvironmentMismatchError(
            "tracked uncommitted changes in src/, uv.lock or the cohort file — commit first"
        )
    recorded = ledger.environment(cohort_id)
    if recorded is None:
        ledger.record_environment(cohort_id, snapshot, started_at=clock.now().isoformat())
        return
    differing = sorted(
        key for key in set(recorded) | set(snapshot) if recorded.get(key) != snapshot.get(key)
    )
    if differing:
        raise EnvironmentMismatchError(
            f"environment differs from the first run on {differing} — resume refused"
        )


def classify_and_run(
    unit: UnitPlan,
    *,
    spec: CohortSpec,
    cohort_id: str,
    ledger: CohortProgressLedger,
    recorded: Callable[[], RecordedRuns],
) -> CohortUnitOutcome:
    """Classifica a unidade (ADR 5.5.0003), executa se for o caso, e loga início e desfecho.

    `spec` dá a geometria, os horizontes e a grade da contagem esperada; `recorded` lê o
    índice de runs do cohort (relido depois de executar a unidade).
    """
    started = time.monotonic()
    _LOG.info("unit %s: start", unit.key)
    outcome = _classify_and_run(
        unit, spec=spec, cohort_id=cohort_id, ledger=ledger, recorded=recorded
    )
    _LOG.info(
        "unit %s: %s (%d runs, %d rows written, %.1fs)",
        unit.key,
        outcome.status,
        len(outcome.run_ids),
        outcome.rows_written,
        time.monotonic() - started,
    )
    return outcome


def _classify_and_run(
    unit: UnitPlan,
    *,
    spec: CohortSpec,
    cohort_id: str,
    ledger: CohortProgressLedger,
    recorded: Callable[[], RecordedRuns],
) -> CohortUnitOutcome:
    by_model = recorded()
    runs = {
        run_id: summary
        for model_key in unit.model_keys
        for run_id, summary in by_model.get(model_key, {}).items()
    }
    completed = ledger.completed_units(cohort_id)
    if unit.key in completed:
        marked = completed[unit.key]
        for run_id, rows in marked.items():
            if run_id not in runs or runs[run_id][1] != rows:
                raise CompletedUnitCorruptedError(
                    f"unit {unit.key!r}: run {run_id} has "
                    f"{runs[run_id][1] if run_id in runs else 'no'} rows in silver, "
                    f"ledger says {rows}"
                )
        return CohortUnitOutcome(
            unit_key=unit.key,
            status=SKIPPED_COMPLETED,
            run_ids=tuple(sorted(marked)),
            rows_written=0,
        )

    if runs and any(summary[1] > 0 for summary in runs.values()):
        if not recorded_run_problems(spec, unit.model_keys, by_model):
            rows_by_run = {run_id: summary[1] for run_id, summary in runs.items()}
            ledger.mark_completed(cohort_id, unit.key, rows_by_run)
            return CohortUnitOutcome(
                unit_key=unit.key,
                status=VERIFIED_COMPLETED,
                run_ids=tuple(sorted(rows_by_run)),
                rows_written=0,
            )
        raise PartialCohortUnitError(
            f"unit {unit.key!r} of cohort {cohort_id} is partially persisted in silver "
            "— start a new cohort revision (revision += 1)"
        )

    rows_by_run = dict(unit.execute())
    # Só marca o que o silver confirma: um use case que devolvesse menos runs
    # ou linhas sem erguer erro ficaria `skipped_completed` para sempre.
    problems = recorded_run_problems(spec, unit.model_keys, recorded())
    if problems:
        raise UnitOutputMismatchError(
            f"unit {unit.key!r} ran but the silver does not hold the expected runs: "
            + "; ".join(problems)
        )
    ledger.mark_completed(cohort_id, unit.key, rows_by_run)
    return CohortUnitOutcome(
        unit_key=unit.key,
        status=RAN,
        run_ids=tuple(sorted(rows_by_run)),
        rows_written=sum(rows_by_run.values()),
    )
