"""Integração ponta-a-ponta do `TrainGbmQuantile` — adapters REAIS em `tmp_path`.

Task 06 da Stage 5.3 (A4/A5/A10 do concept §11): semeia um dataset TFT
sintético COMPLETO no layout físico da 3.5 (`processed/dataset_tft/<asset>/`,
sessões XNYS reais, TODAS as colunas de feature esperadas — C6 reprova seed
parcial) e roda o use case saído do `wire_dependencies` — o grafo REAL:
`ParquetMedallionStore` (read-only), `WalkForwardSplitter` sobre a janela ampla
fixa, `_LazyLightgbmQuantileTrainer` -> `LightgbmQuantileTrainer` (LightGBM de
verdade, CPU), `PersistPredictions` + `ParquetAnalyticsRepository` e
`CanonicalJsonHasher`. Este teste é a verificação end-to-end da Stage (não há
entrypoint HTTP/CLI no BC).

Prova:

- A4: predições LONG com `model_version='gbm_quantile'`, `split="test"`, grade
  completa por decisão x horizonte, `target_timestamp_utc` por indexação de
  sessão (4.3) e guardrail monotônico; `dim_run` com `seed` PREENCHIDA (I7);
- A5: duas execuções do MESMO comando contra stores isolados -> linhas
  persistidas idênticas e mesmos `best_iteration_by_horizon`;
- C7: reexecutar a MESMA invocação contra o MESMO store propaga
  `DuplicateKeyError` (fecha A8; espelho do C8 da 5.2);
- cauda sem janela completa -> `rows_skipped` > 0, nada fabricado;
- lazy wiring: importar `composition_root` NÃO importa `lightgbm`
  (subprocesso limpo — o proxy só carrega a lib no 1º treino).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantileCommand,
    TrainGbmQuantileResult,
    expected_feature_names,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.integration.features.modeling.conftest import seed_dataset, xnys_sessions

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from financial_forecasting.composition_root import ApplicationDependencies
    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )

# Geometria pequena sobre sessões XNYS REAIS (mesma técnica do e2e da 5.2):
# 120 sessões, 2 folds de test na cauda, gap = max_horizon + embargo = 3.
_ASSET = "TEST"
_FEATURE_SET = "fs_e2e_gbm"
_COHORT_ID = "cohort-e2e-53"
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_MAX_HORIZON = 2
_N_FOLDS = 2
_TEST_SIZE = 3
_VAL_SIZE = 5
_CALIB_SIZE = 5
_EMBARGO = 1
_SCHEMA_VERSION = 1
_SEED = 1234
_CEILING = 25
_MIN_DATA_IN_LEAF = 5
_FEATURE_NAMES = expected_feature_names()

_SILVER = "silver"
_FACTS = "fact_oos_predictions"
_DIM_RUN = "dim_run"


def _xnys_sessions() -> tuple[date, ...]:
    """120 sessões XNYS reais — helper compartilhado movido para o conftest."""
    return xnys_sessions(_N_SESSIONS)


def _command() -> TrainGbmQuantileCommand:
    return TrainGbmQuantileCommand(
        scope=ScopeSpec(
            asset_id=_ASSET,
            feature_set_name=_FEATURE_SET,
            max_horizon=_MAX_HORIZON,
            cohort_id=_COHORT_ID,
        ),
        params=GbmTrainingParams(
            seed=_SEED,
            num_boost_round_max=_CEILING,
            min_data_in_leaf=_MIN_DATA_IN_LEAF,
        ),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        n_folds=_N_FOLDS,
        test_size=_TEST_SIZE,
        val_size=_VAL_SIZE,
        calib_size=_CALIB_SIZE,
        embargo=_EMBARGO,
        schema_version=_SCHEMA_VERSION,
    )


def _wire_and_run(data_root: Path) -> tuple[ApplicationDependencies, TrainGbmQuantileResult]:
    seed_dataset(data_root, _xnys_sessions(), _FEATURE_NAMES, asset=_ASSET)
    deps = wire_dependencies(
        settings=Settings(
            _env_file=None,
            data_root=data_root,
            mlflow_tracking_uri=f"sqlite:///{data_root}/mlruns.db",
        )
    )
    return deps, deps.train_gbm_quantile(_command())


@dataclass(frozen=True)
class _PipelineRun:
    """Estado compartilhado da execução única do pipeline (fixture module-scoped)."""

    deps: ApplicationDependencies
    result: TrainGbmQuantileResult
    iso_timestamps: tuple[str, ...]

    def facts(self) -> Sequence[Row]:
        return self.deps.analytics_repository.read(layer=_SILVER, table=_FACTS)

    def dim_run(self) -> Sequence[Row]:
        return self.deps.analytics_repository.read(layer=_SILVER, table=_DIM_RUN)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> _PipelineRun:
    """Semeia o dataset, wireia o grafo real e roda o `TrainGbmQuantile` UMA vez."""
    data_root = tmp_path_factory.mktemp("e2e-train-gbm")
    deps, result = _wire_and_run(data_root)
    iso = tuple(
        datetime(day.year, day.month, day.day, tzinfo=UTC).isoformat() for day in _xnys_sessions()
    )
    return _PipelineRun(deps=deps, result=result, iso_timestamps=iso)


# -- A4: predições LONG alinhadas + dim_run com seed -------------------------------


@pytest.mark.integration
def test_e2e_facts_are_gbm_quantile_split_test_with_complete_grid(
    pipeline: _PipelineRun,
) -> None:
    """`model_version='gbm_quantile'`, `split="test"`, grade completa (A4)."""
    rows = pipeline.facts()

    assert rows, "expected persisted prediction rows"
    assert {str(r["model_version"]) for r in rows} == {"gbm_quantile"}
    assert all(str(r["split"]) == "test" for r in rows)
    grids: dict[tuple[str, int, int], set[float]] = {}
    for row in rows:
        key = (str(row["run_id"]), int(str(row["decision_idx"])), int(str(row["horizon"])))
        grids.setdefault(key, set()).add(float(str(row["quantile_level"])))
    assert grids
    assert all(levels == set(_LEVELS) for levels in grids.values())


@pytest.mark.integration
def test_e2e_alignment_target_timestamp_by_session_index(
    pipeline: _PipelineRun,
) -> None:
    """I1/I2: `target_timestamp_utc == dataset_timestamps[decision_idx + h]` (4.3)."""
    iso = pipeline.iso_timestamps
    for row in pipeline.facts():
        decision_idx = int(str(row["decision_idx"]))
        horizon = int(str(row["horizon"]))
        assert str(row["timestamp_utc"]) == iso[decision_idx]
        assert str(row["target_timestamp_utc"]) == iso[decision_idx + horizon]


@pytest.mark.integration
def test_e2e_guardrail_grid_is_monotone_per_decision_horizon(
    pipeline: _PipelineRun,
) -> None:
    """I3: `value_guardrail` monotônico não decrescente ao longo dos níveis."""
    by_key: dict[tuple[str, int, int], list[tuple[float, float]]] = {}
    for row in pipeline.facts():
        key = (str(row["run_id"]), int(str(row["decision_idx"])), int(str(row["horizon"])))
        by_key.setdefault(key, []).append(
            (float(str(row["quantile_level"])), float(str(row["value_guardrail"])))
        )

    for grid in by_key.values():
        values = [value for _, value in sorted(grid)]
        assert values == sorted(values)


@pytest.mark.integration
def test_e2e_dim_run_one_row_per_fold_with_filled_seed(pipeline: _PipelineRun) -> None:
    """I7: `dim_run` com 1 linha por fold, `seed` PREENCHIDA, cohort e fingerprint."""
    rows = pipeline.dim_run()

    assert len(rows) == _N_FOLDS
    assert {str(r["model_version"]) for r in rows} == {"gbm_quantile"}
    assert {str(r["fold"]) for r in rows} == {"0", "1"}
    assert all(int(str(r["seed"])) == _SEED for r in rows)
    assert all(str(r["parent_sweep_id"]) == _COHORT_ID for r in rows)
    assert all(str(r["split_fingerprint"]) for r in rows)
    assert {summary.run_id for summary in pipeline.result.runs} == {str(r["run_id"]) for r in rows}


@pytest.mark.integration
def test_e2e_best_iterations_within_ceiling_and_tail_skips_counted(
    pipeline: _PipelineRun,
) -> None:
    """m* em [1, teto] por (fold x horizonte); cauda pula e conta, nada fabricado."""
    for summary in pipeline.result.runs:
        assert set(summary.best_iteration_by_horizon) == set(_HORIZONS)
        assert all(1 <= m <= _CEILING for m in summary.best_iteration_by_horizon.values())
    last_fold = [s for s in pipeline.result.runs if s.fold_index == _N_FOLDS - 1]
    assert all(summary.rows_skipped > 0 for summary in last_fold)
    rows = pipeline.facts()
    max_idx = _N_SESSIONS - 1
    assert all(int(str(r["decision_idx"])) + int(str(r["horizon"])) <= max_idx for r in rows)
    assert len(rows) == sum(summary.rows_written for summary in pipeline.result.runs)


# -- A5: determinismo do fluxo completo (stores isolados) --------------------------


@pytest.mark.integration
def test_e2e_a5_two_isolated_runs_persist_identical_predictions(
    pipeline: _PipelineRun, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Mesmo comando contra store isolado -> mesmas linhas e mesmos m* (I4/A5)."""
    deps_b, result_b = _wire_and_run(tmp_path_factory.mktemp("e2e-train-gbm-b"))

    def _sorted_rows(rows: Sequence[Row]) -> list[tuple[object, ...]]:
        keys = (
            "run_id",
            "split",
            "horizon",
            "decision_idx",
            "quantile_level",
            "value_raw",
            "value_guardrail",
            "guardrail_applied",
            "timestamp_utc",
            "target_timestamp_utc",
            "model_version",
        )
        return sorted(tuple(row[key] for key in keys) for row in rows)

    facts_a = _sorted_rows(pipeline.facts())
    facts_b = _sorted_rows(deps_b.analytics_repository.read(layer=_SILVER, table=_FACTS))
    assert facts_a == facts_b
    assert [
        (s.run_id, s.fold_index, dict(s.best_iteration_by_horizon)) for s in pipeline.result.runs
    ] == [(s.run_id, s.fold_index, dict(s.best_iteration_by_horizon)) for s in result_b.runs]


# -- C7: rerun idêntico colide e propaga -------------------------------------------


@pytest.mark.integration
def test_e2e_c7_rerun_of_same_invocation_raises_duplicate_key(
    pipeline: _PipelineRun,
) -> None:
    """C7: mesma invocação, mesmo store -> `DuplicateKeyError` propaga (A8)."""
    with pytest.raises(DuplicateKeyError):
        pipeline.deps.train_gbm_quantile(_command())


# -- lazy wiring: importar o composition root não importa lightgbm ------------------


@pytest.mark.integration
def test_lazy_wiring_importing_composition_root_does_not_import_lightgbm() -> None:
    """O proxy lazy só carrega a lib no 1º treino (subprocesso limpo)."""
    probe = (
        "import sys; import financial_forecasting.composition_root; "
        "sys.exit(1 if 'lightgbm' in sys.modules else 0)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, (
        f"importar composition_root importou lightgbm (proxy lazy quebrado): {completed.stderr}"
    )
