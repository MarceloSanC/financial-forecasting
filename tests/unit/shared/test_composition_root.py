"""Teste de wiring do composition root (Stages 1.5 + 2.1).

Exercita `wire_dependencies` com um `Settings` INJETADO (não o `lru_cache`
global, I6) cujo `mlflow_tracking_uri` aponta para um SQLite em `tmp_path` (D4)
e cujo `data_root` aponta para `tmp_path` (2.1 I9), e verifica que o contêiner
expõe os concretos certos atrás dos ports: `hasher: Hasher` =
`CanonicalJsonHasher`, `tracker: ExperimentTracker` = `MlflowTracker` e
`store: MedallionStore` = `ParquetMedallionStore` (A5/A7). Cobre o caminho real
de `wire_dependencies` — necessário para a cobertura ≥90% (composition_root fora
do omit).
"""

from datetime import date
from pathlib import Path

import pytest

from financial_forecasting.composition_root import (
    ApplicationDependencies,
    _LazyFinbertSentimentModel,
    wire_dependencies,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.feature_engineering.adapters.out.duckdb.asof_join_adapter import (  # noqa: E501
    AsofJoinDuckdbAdapter,
)
from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.application.use_cases.build_dataset import (
    BuildDataset,
)
from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
    StatsforecastBaselineForecaster,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.mlflow.mlflow_tracker import MlflowTracker
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from financial_forecasting.shared.infrastructure.config.settings import Settings


@pytest.mark.unit
def test_wire_dependencies_with_injected_settings(tmp_path: Path) -> None:
    """A5/A7: wiring instancia os concretos a partir do Settings injetado."""
    settings = Settings(
        _env_file=None,
        mlflow_tracking_uri=f"sqlite:///{tmp_path}/mlruns.db",
        data_root=tmp_path,
    )

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps, ApplicationDependencies)
    assert isinstance(deps.hasher, CanonicalJsonHasher)
    assert isinstance(deps.tracker, MlflowTracker)
    assert isinstance(deps.store, ParquetMedallionStore)


@pytest.mark.unit
def test_wire_dependencies_tracker_uses_settings_uri(tmp_path: Path) -> None:
    """I6: o tracker recebe o tracking_uri vindo do Settings injetado."""
    tracking_uri = f"sqlite:///{tmp_path}/mlruns.db"
    settings = Settings(_env_file=None, mlflow_tracking_uri=tracking_uri)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.tracker, MlflowTracker)
    assert deps.tracker._tracking_uri == tracking_uri


@pytest.mark.unit
def test_wire_dependencies_store_uses_settings_data_root(tmp_path: Path) -> None:
    """A7/I9: o store recebe o `data_root` vindo do Settings injetado (não o global)."""
    settings = Settings(_env_file=None, data_root=tmp_path)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.store, ParquetMedallionStore)
    assert deps.store._data_root == tmp_path


@pytest.mark.unit
def test_wire_dependencies_wires_feature_engineering_bc(tmp_path: Path) -> None:
    """Stage 3.5 I8/A7: os 3 adapters do BC + BuildDataset estão wirados (não fakes).

    Resolve os findings F2 de wiring deferido (3.1/3.2/3.3): instanciar os concretos
    reais atrás dos ports. O `SentimentModel` é o proxy lazy (sem torch ao wirar).
    """
    settings = Settings(_env_file=None, data_root=tmp_path)

    deps = wire_dependencies(settings=settings)

    # Campos tipados pelos ports, instanciados pelos concretos REAIS (I9).
    assert isinstance(deps.indicator_calculator, PandasTaIndicatorCalculator)
    assert isinstance(deps.sentiment_model, _LazyFinbertSentimentModel)
    assert isinstance(deps.asof_join, AsofJoinDuckdbAdapter)
    assert isinstance(deps.dataset_assembler, DatasetAssembler)
    assert isinstance(deps.build_dataset, BuildDataset)


@pytest.mark.unit
def test_build_dataset_is_wired_with_real_adapters_not_fakes(tmp_path: Path) -> None:
    """I8: `BuildDataset` consome os adapters reais wirados (não dead-code)."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    build_dataset = deps.build_dataset
    # O use case usa o MESMO assembler/store reais expostos no contêiner.
    assert build_dataset._assembler is deps.dataset_assembler
    assert build_dataset._store is deps.store
    assert isinstance(build_dataset._assembler, DatasetAssembler)


@pytest.mark.unit
def test_lazy_finbert_proxy_exposes_metadata_without_torch() -> None:
    """O proxy lazy expõe `model_name`/`revision` sem construir o FinBERT real."""
    proxy = _LazyFinbertSentimentModel()
    assert proxy.model_name == "ProsusAI/finbert"
    assert isinstance(proxy.revision, str)
    assert proxy._delegate is None  # ainda não construiu o FinBERT (sem torch)


@pytest.mark.unit
def test_wire_dependencies_wires_analytics_repository(tmp_path: Path) -> None:
    """Stage 4.2 A11: o adapter Parquet silver é wirado com data_root + SystemClock.

    Exposto em `ApplicationDependencies.analytics_repository`, tipado pelo port; o
    `data_root` vem do Settings injetado (I9/I10) e o `Clock` é o `SystemClock`.
    """
    settings = Settings(_env_file=None, data_root=tmp_path)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.analytics_repository, ParquetAnalyticsRepository)
    assert deps.analytics_repository._data_root == tmp_path
    assert isinstance(deps.analytics_repository._clock, SystemClock)


@pytest.mark.unit
def test_wire_dependencies_wires_run_baselines(tmp_path: Path) -> None:
    """Stage 5.2 Task 09: `run_baselines` montado com os colaboradores REAIS.

    Campos tipados pelos ports/contratos (concept 5.2 §4): store/hasher/repo são
    as MESMAS instâncias expostas no contêiner (I9 — grafo único, sem duplicar
    concretos) e o forecaster é o adapter real `StatsforecastBaselineForecaster`.
    """
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    run_baselines = deps.run_baselines
    assert isinstance(run_baselines, RunBaselines)
    assert run_baselines._store is deps.store
    assert run_baselines._analytics_repository is deps.analytics_repository
    assert run_baselines._hasher is deps.hasher
    assert isinstance(run_baselines._forecaster, StatsforecastBaselineForecaster)
    assert isinstance(run_baselines._splitter, WalkForwardSplitter)
    assert isinstance(run_baselines._persist_predictions, PersistPredictions)
    # PersistPredictions reusa o MESMO repositório silver (ADR 4.3.0001 — dono
    # único do target_timestamp atrás de um único adapter).
    assert run_baselines._persist_predictions._repository is deps.analytics_repository


@pytest.mark.unit
def test_run_baselines_splitter_calendar_covers_wide_fixed_window(tmp_path: Path) -> None:
    """F-T1 opção A: o calendário do splitter cobre a janela ampla fixa 1990-2035.

    Sessões bem além dos bounds default da lib (~hoje-20a .. hoje+1a) devem estar
    materializadas — prova que o wiring pediu a janela ampla, não a default.
    """
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    calendar = deps.run_baselines._splitter._calendar
    assert calendar.is_session(date(1995, 5, 5))  # sexta comum de 1995
    assert calendar.is_session(date(2035, 12, 31))  # última sessão da janela
    assert not calendar.is_session(date(1995, 7, 4))  # feriado XNYS
