"""E2E — `TrainTft` de ponta a ponta pelo grafo REAL (Task 14).

Sem dublês: `wire_dependencies` monta o `PfTftTrainer` de verdade (via proxy
lazy), o `ParquetMedallionStore` sobre um `tmp_path` e o `MlflowTracker` real
apontando para um SQLite isolado. Prova:

- **A16:** o fluxo completo roda, o artefato existe em disco e o run está no
  MLflow com params, tags e o artefato registrado — é o item "runs logados no
  MLflow" do DoD, fechado com o adapter real e não só com o fake;
- **A7:** linhas em `fact_oos_predictions` com `model_version='tft_quantile'`,
  guardrail aplicado e `dim_run` com `seed` preenchida;
- **A13:** paridade de base amostral com o GBM (5.3) — para cada horizonte, o
  conjunto de `target_timestamp` persistido pelo candidato é IGUAL ao do
  comparador. É o que a inferência pareada do Step 6 pressupõe;
- **A9:** duas execuções contra stores isolados produzem as mesmas predições;
- **C7:** reexecução idêntica contra o MESMO store propaga `DuplicateKeyError`;
- **wiring:** os dois campos novos existem e importar o composition root NÃO
  importa `torch` nem `optuna`.

O treino é real, então a fixture do pipeline é module-scoped: uma execução só.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.composition_root import (
    ApplicationDependencies,
    wire_dependencies,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantileCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTftCommand,
    TrainTftResult,
    known_feature_names,
    unknown_feature_names,
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

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )

pytestmark = pytest.mark.integration

_ASSET = "TEST"
_FEATURE_SET = "fs_e2e"
_COHORT_ID = "cohort-e2e"
_N_SESSIONS = 120
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_LEVELS = (0.1, 0.5, 0.9)
_N_FOLDS = 2
_TEST_SIZE = 3
_VAL_SIZE = 5
_CALIB_SIZE = 5
_EMBARGO = 1
_SEED = 42
_SCHEMA_VERSION = 1
_SILVER = "silver"
_FACTS = "fact_oos_predictions"
_DIM_RUN = "dim_run"
_TFT_VERSION = "tft_quantile"
_GBM_VERSION = "gbm_quantile"
# LightGBM ergue C3 abaixo do default 20 com o bloco de treino desta geometria;
# o run de paridade existe para comparar CONJUNTOS de pontos, não desempenho.
_GBM_MIN_DATA_IN_LEAF = 5
_GBM_CEILING = 10

_FEATURE_NAMES = unknown_feature_names() + known_feature_names()
_PARAMS = TftTrainingParams(
    seed=_SEED,
    max_encoder_length=12,
    hidden_size=4,
    attention_head_size=1,
    hidden_continuous_size=2,
    max_epochs=2,
    patience=2,
    batch_size=8,
    learning_rate=0.01,
)
_SCOPE = ScopeSpec(
    asset_id=_ASSET,
    feature_set_name=_FEATURE_SET,
    max_horizon=_MAX_HORIZON,
    cohort_id=_COHORT_ID,
)


def _command() -> TrainTftCommand:
    return TrainTftCommand(
        scope=_SCOPE,
        params=_PARAMS,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        n_folds=_N_FOLDS,
        test_size=_TEST_SIZE,
        val_size=_VAL_SIZE,
        calib_size=_CALIB_SIZE,
        embargo=_EMBARGO,
        schema_version=_SCHEMA_VERSION,
    )


def _gbm_command() -> TrainGbmQuantileCommand:
    """Mesmo escopo e MESMA geometria de fold — é o que torna A13 comparável."""
    return TrainGbmQuantileCommand(
        scope=_SCOPE,
        params=GbmTrainingParams(
            seed=_SEED,
            num_boost_round_max=_GBM_CEILING,
            min_data_in_leaf=_GBM_MIN_DATA_IN_LEAF,
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


def _wire(data_root: Path) -> ApplicationDependencies:
    seed_dataset(data_root, xnys_sessions(_N_SESSIONS), _FEATURE_NAMES, asset=_ASSET)
    return wire_dependencies(
        settings=Settings(
            _env_file=None,
            data_root=data_root,
            artifacts_root=data_root / "artifacts",
            mlflow_tracking_uri=f"sqlite:///{data_root}/mlruns.db",
        )
    )


@dataclass(frozen=True)
class _PipelineRun:
    deps: ApplicationDependencies
    result: TrainTftResult
    data_root: Path

    def facts(self, model_version: str) -> Sequence[Row]:
        rows = self.deps.analytics_repository.read(layer=_SILVER, table=_FACTS)
        return [row for row in rows if row["model_version"] == model_version]

    def dim_run(self, model_version: str) -> Sequence[Row]:
        rows = self.deps.analytics_repository.read(layer=_SILVER, table=_DIM_RUN)
        return [row for row in rows if row["model_version"] == model_version]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> _PipelineRun:
    """Semeia o dataset, wireia o grafo real e roda o TFT e o GBM UMA vez."""
    data_root = tmp_path_factory.mktemp("e2e-train-tft")
    deps = _wire(data_root)
    result = deps.train_tft(_command())
    # Comparador na MESMA geometria, para a paridade de A13.
    deps.train_gbm_quantile(_gbm_command())
    return _PipelineRun(deps=deps, result=result, data_root=data_root)


class TestPersistedIdentity:
    """A7 — identidade e guardrail do que foi persistido."""

    def test_one_run_per_fold_with_filled_seed(self, pipeline: _PipelineRun) -> None:
        rows = pipeline.dim_run(_TFT_VERSION)

        assert len(rows) == _N_FOLDS
        assert all(row["seed"] == _SEED for row in rows)
        assert all(row["parent_sweep_id"] == _COHORT_ID for row in rows)

    def test_facts_carry_the_candidate_identity(self, pipeline: _PipelineRun) -> None:
        rows = pipeline.facts(_TFT_VERSION)

        assert rows
        assert all(row["split"] == "test" for row in rows)
        assert all(row["asset"] == _ASSET for row in rows)
        assert all(row["schema_version"] == _SCHEMA_VERSION for row in rows)

    def test_guardrail_leaves_every_grid_monotone(self, pipeline: _PipelineRun) -> None:
        by_key: dict[tuple[Any, Any, Any], list[tuple[float, float]]] = {}
        for row in pipeline.facts(_TFT_VERSION):
            key = (row["run_id"], row["target_timestamp_utc"], row["horizon"])
            by_key.setdefault(key, []).append(
                (float(row["quantile_level"]), float(row["value_guardrail"]))
            )

        assert by_key
        for grid in by_key.values():
            values = [value for _, value in sorted(grid)]
            assert values == sorted(values)


class TestSampleParityWithTheComparator:
    """A13 — o candidato cobre exatamente os mesmos pontos alinhados do GBM."""

    @pytest.mark.parametrize("horizon", _HORIZONS)
    def test_same_target_timestamps_per_horizon(self, pipeline: _PipelineRun, horizon: int) -> None:
        tft = {
            row["target_timestamp_utc"]
            for row in pipeline.facts(_TFT_VERSION)
            if row["horizon"] == horizon
        }
        gbm = {
            row["target_timestamp_utc"]
            for row in pipeline.facts(_GBM_VERSION)
            if row["horizon"] == horizon
        }

        assert tft
        assert tft == gbm


class TestTrackingWithTheRealBackend:
    """A16 — o item do DoD fechado com o `MlflowTracker` real."""

    def test_every_fold_has_a_run_with_params_tags_and_artifact(
        self, pipeline: _PipelineRun
    ) -> None:
        from mlflow.tracking import MlflowClient  # noqa: PLC0415

        client = MlflowClient(tracking_uri=f"sqlite:///{pipeline.data_root}/mlruns.db")

        assert all(summary.tracking_run_id for summary in pipeline.result.runs)
        for summary in pipeline.result.runs:
            run = client.get_run(summary.tracking_run_id)
            assert run.data.params["run_id"] == summary.run_id
            assert run.data.tags["model_version"] == _TFT_VERSION
            assert run.data.tags["phase"] == "confirmatory_ready"
            assert "best_val_loss" in run.data.metrics
            artifacts = client.list_artifacts(summary.tracking_run_id)
            assert artifacts, "o checkpoint precisa estar registrado no run"

    def test_artifact_exists_on_disk(self, pipeline: _PipelineRun) -> None:
        from pathlib import Path as _Path  # noqa: PLC0415

        for summary in pipeline.result.runs:
            assert _Path(summary.artifact_path).is_file()


class TestDeterminismAcrossRuns:
    """A9 — duas execuções isoladas produzem as mesmas predições."""

    def test_two_isolated_runs_agree(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        first_root = tmp_path_factory.mktemp("e2e-tft-a")
        second_root = tmp_path_factory.mktemp("e2e-tft-b")
        first_deps = _wire(first_root)
        second_deps = _wire(second_root)

        first_deps.train_tft(_command())
        second_deps.train_tft(_command())

        def _values(deps: ApplicationDependencies) -> list[tuple[Any, ...]]:
            rows = deps.analytics_repository.read(layer=_SILVER, table=_FACTS)
            return sorted(
                (
                    row["target_timestamp_utc"],
                    row["horizon"],
                    row["quantile_level"],
                    round(float(row["value_guardrail"]), 9),
                )
                for row in rows
                if row["model_version"] == _TFT_VERSION
            )

        assert _values(first_deps) == _values(second_deps)


class TestReplaySemantics:
    """C7 — a semântica de replay fica PINADA aqui para a Stage 5.5 encontrá-la."""

    def test_identical_rerun_against_the_same_store_raises(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        data_root = tmp_path_factory.mktemp("e2e-tft-replay")
        deps = _wire(data_root)
        deps.train_tft(_command())

        with pytest.raises(DuplicateKeyError):
            deps.train_tft(_command())


class TestWiring:
    def test_both_use_cases_are_exposed(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        deps = wire_dependencies(
            settings=Settings(_env_file=None, data_root=tmp_path_factory.mktemp("e2e-tft-wiring"))
        )

        assert deps.train_tft is not None
        assert deps.run_tft_sweep is not None

    def test_importing_the_composition_root_does_not_import_torch_or_optuna(self) -> None:
        """Proxy lazy: importar o grafo não pode custar segundos de carga.

        `torch` é dependência principal desde a 5.4 (ADR 5.4.0003), então a
        razão do proxy não é opcionalidade — é que `wire_dependencies` roda em
        qualquer entrypoint, inclusive os que não treinam nada.
        """
        probe = (
            "import sys;"
            "import financial_forecasting.composition_root as cr;"
            "cr.wire_dependencies();"
            "print('torch' in sys.modules, 'optuna' in sys.modules)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
        )

        assert completed.stdout.strip() == "False False"
