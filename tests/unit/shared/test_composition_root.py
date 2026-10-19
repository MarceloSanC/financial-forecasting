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

import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.composition_root import (
    _DATASET_MAX_NAN_RATIO_PER_FEATURE,
    _SILVER_SCHEMA_VERSION,
    _SUPPORTED_DEVICES,
    ApplicationDependencies,
    _LazyArchMcs,
    _LazyFinbertSentimentModel,
    _LazyLightgbmQuantileTrainer,
    _LazyOptunaSearch,
    _LazyPfTftTrainer,
    _LazyStatsforecastBaselineForecaster,
    _tft_trainer_factory,
    wire_dependencies,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_cohort_run_index import (  # noqa: E501
    ParquetCohortRunIndex,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_registry import (  # noqa: E501
    SILVER_REGISTRY,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecord,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import (  # noqa: E501
    TomlPreregistrationSource,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import GoldPartition
from financial_forecasting.features.evaluation.application.use_cases.build_confirmatory_scorecard import (  # noqa: E501
    BuildConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
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
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.inference.adapters.out.filesystem.json_inference_manifest import (  # noqa: E501
    JsonInferenceManifest,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
)
from financial_forecasting.features.inference.application.use_cases.run_inference import (
    RunInference,
)
from financial_forecasting.features.market_data.adapters.out.parquet.parquet_fundamental_fetcher import (  # noqa: E501
    ParquetFundamentalFetcher,
)
from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_candle_fetcher import (  # noqa: E501
    ParquetRawCandleFetcher,
)
from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_news_fetcher import (  # noqa: E501
    ParquetRawNewsFetcher,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_candles import (
    IngestCandles,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_fundamentals import (
    IngestFundamentals,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_news import (
    IngestNews,
)
from financial_forecasting.features.modeling.adapters.out.filesystem.checkpoint_locator import (
    FilesystemCheckpointLocator,
)
from financial_forecasting.features.modeling.adapters.out.filesystem.json_cohort_progress_ledger import (  # noqa: E501
    JsonCohortProgressLedger,
)
from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import (  # noqa: E501
    GitRuntimeEnvironmentProbe,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    HyperparameterSearch,
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    TftCheckpointPredictor,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainer,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    PredictTftFromCheckpoints,
)
from financial_forecasting.features.modeling.application.use_cases.read_training_grid import (
    ReadTrainingGrid,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    ResolveTftCheckpoints,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    RunConfirmatoryCohort,
)
from financial_forecasting.features.modeling.application.use_cases.run_gbm_sweep import (
    RunGbmSweep,
)
from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
    RunTftSweep,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
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
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)


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
def test_build_dataset_quality_gate_is_armed_with_declared_threshold(tmp_path: Path) -> None:
    """#72 — o wiring declara o limiar de missing do gate e ele está ARMADO (< 1.0).

    O old herdava `1.0` (inalcançável para `ratio ∈ [0, 1]`); agora o domínio não tem
    default e o composition root é quem declara o número. Uma regressão que voltasse
    a wirar `1.0` (ou trocasse a constante por um "sem limite") reprovaria aqui.
    """
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    config = deps.build_dataset._quality_gate_config
    assert isinstance(config, DatasetQualityGateConfig)
    assert config.max_nan_ratio_per_feature == _DATASET_MAX_NAN_RATIO_PER_FEATURE
    assert 0.0 <= config.max_nan_ratio_per_feature < 1.0  # armado: pode reprovar
    # Teto: a faixa de partida da issue #72 é 0.02 a 0.05 pós-warmup. Afrouxar além
    # disso é decisão nova — exige editar este teste (auditável), não só a constante.
    assert config.max_nan_ratio_per_feature <= 0.05  # noqa: PLR2004


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
    concretos) e o forecaster é o proxy LAZY do adapter statsforecast (fix F3 —
    o import de ~6s é adiado ao primeiro `forecast`, precedente FinBERT).
    """
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    run_baselines = deps.run_baselines
    assert isinstance(run_baselines, RunBaselines)
    assert run_baselines._store is deps.store
    assert run_baselines._hasher is deps.hasher
    assert isinstance(run_baselines._forecaster, _LazyStatsforecastBaselineForecaster)
    assert run_baselines._forecaster._delegate is None  # statsforecast ainda não carregou
    assert isinstance(run_baselines._splitter, WalkForwardSplitter)
    assert isinstance(run_baselines._persist_predictions, PersistPredictions)
    # PersistPredictions e PersistRunRecord (issue #68) reusam o MESMO repositório
    # silver (ADR 4.3.0001 — dono único do target_timestamp atrás de um único
    # adapter); o use case não recebe mais o repositório do outro slice.
    assert run_baselines._persist_predictions._repository is deps.analytics_repository
    assert isinstance(run_baselines._persist_run_record, PersistRunRecord)
    assert run_baselines._persist_run_record._repository is deps.analytics_repository
    assert not hasattr(run_baselines, "_analytics_repository")


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


@pytest.mark.unit
def test_wire_dependencies_wires_train_tft(tmp_path: Path) -> None:
    """Stage 5.4 Task 14: `train_tft` montado com os colaboradores REAIS.

    Store/hasher/repo/tracker são as MESMAS instâncias do contêiner (I9 — grafo
    único), o trainer é o proxy LAZY (torch custa ~5s de import e o contêiner é
    construído em todo startup) e o `artifacts_root` vem do Settings injetado.
    """
    settings = Settings(_env_file=None, data_root=tmp_path, artifacts_root=tmp_path / "art")

    deps = wire_dependencies(settings=settings)

    train_tft = deps.train_tft
    assert isinstance(train_tft, TrainTft)
    assert train_tft._store is deps.store
    assert train_tft._hasher is deps.hasher
    assert train_tft._tracker is deps.tracker
    assert isinstance(train_tft._splitter, WalkForwardSplitter)
    assert isinstance(train_tft._persist_predictions, PersistPredictions)
    assert train_tft._persist_predictions._repository is deps.analytics_repository
    assert isinstance(train_tft._persist_run_record, PersistRunRecord)
    assert train_tft._persist_run_record._repository is deps.analytics_repository
    assert not hasattr(train_tft, "_analytics_repository")
    assert isinstance(train_tft._trainer, _LazyPfTftTrainer)
    assert train_tft._trainer._delegate is None  # torch ainda não foi importado
    assert train_tft._artifacts_root == tmp_path / "art"


@pytest.mark.unit
def test_wire_dependencies_wires_run_tft_sweep(tmp_path: Path) -> None:
    """Stage 5.4 Task 14 / ADR 5.4.0005: a varredura NÃO recebe persistência.

    O isolamento é estrutural, não disciplinar: `RunTftSweep` não tem campo de
    `PersistPredictions` nem de `AnalyticsRepository`, então nenhuma previsão
    exploratória tem por onde vazar para a silver. Asserir a AUSÊNCIA aqui é o
    que impede um wiring futuro de reintroduzi-los por conveniência.
    """
    settings = Settings(_env_file=None, data_root=tmp_path, artifacts_root=tmp_path / "art")

    deps = wire_dependencies(settings=settings)

    sweep = deps.run_tft_sweep
    assert isinstance(sweep, RunTftSweep)
    assert sweep._store is deps.store
    assert sweep._hasher is deps.hasher
    assert sweep._tracker is deps.tracker
    assert isinstance(sweep._trainer, _LazyPfTftTrainer)
    assert isinstance(sweep._search, _LazyOptunaSearch)
    assert sweep._search._delegate is None  # optuna ainda não foi importado
    assert not hasattr(sweep, "_persist_predictions")
    assert not hasattr(sweep, "_persist_run_record")
    assert not hasattr(sweep, "_analytics_repository")


@pytest.mark.unit
def test_lazy_tft_proxies_expose_the_port_surface_without_building(tmp_path: Path) -> None:
    """Precedente FinBERT: construir o proxy não pode puxar torch nem optuna.

    Sem isto, `wire_dependencies` — chamado no startup do app e em todo teste de
    wiring — pagaria o import de torch (~5s) sem que ninguém fosse treinar. E o
    proxy tem de expor a superfície INTEIRA do port: um método faltando só
    apareceria como `AttributeError` em produção, no meio de um treino.
    """
    trainer: TftTrainer = _LazyPfTftTrainer()
    search: HyperparameterSearch = _LazyOptunaSearch()

    assert trainer._delegate is None
    assert search._delegate is None
    for method in ("train_and_predict",):
        assert callable(getattr(trainer, method))
    for method in ("create_study", "ask", "tell", "fail", "best_trial"):
        assert callable(getattr(search, method))
    # Uma chamada real construiria o delegate — não é o que se testa aqui; o
    # e2e de `tests/integration/features/modeling/test_train_tft.py` faz isso.
    assert tmp_path.exists()


@pytest.mark.unit
def test_wire_dependencies_wires_local_ingestion_under_data_root(tmp_path: Path) -> None:
    """Stage 5.5 Task 25: os brutos são lidos sob `data_root`, e o bronze vai ao store."""
    settings = Settings(_env_file=None, data_root=tmp_path)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.ingest_candles, IngestCandles)
    assert isinstance(deps.ingest_news, IngestNews)
    assert isinstance(deps.ingest_fundamentals, IngestFundamentals)
    for use_case in (deps.ingest_candles, deps.ingest_news, deps.ingest_fundamentals):
        assert use_case._store is deps.store
    candles = deps.ingest_candles._fetcher
    news = deps.ingest_news._fetcher
    fundamentals = deps.ingest_fundamentals._fetcher
    assert isinstance(candles, ParquetRawCandleFetcher)
    assert isinstance(news, ParquetRawNewsFetcher)
    assert isinstance(fundamentals, ParquetFundamentalFetcher)
    assert candles._parquet_path("AAPL") == (
        tmp_path / "raw" / "market" / "candles" / "AAPL" / "candles_AAPL_1d.parquet"
    )
    assert news._parquet_path("AAPL") == tmp_path / "raw" / "news" / "AAPL" / "news_AAPL.parquet"
    assert fundamentals._parquet_path("AAPL") == (
        tmp_path / "processed" / "fundamentals" / "AAPL" / "fundamentals_AAPL.parquet"
    )


@pytest.mark.unit
def test_wire_dependencies_wires_run_gbm_sweep_without_persistence(tmp_path: Path) -> None:
    """Stage 5.5 Task 26 / I14: o sweep do GBM, como o do TFT, não tem por onde gravar."""
    settings = Settings(_env_file=None, data_root=tmp_path, artifacts_root=tmp_path / "art")

    deps = wire_dependencies(settings=settings)

    sweep = deps.run_gbm_sweep
    assert isinstance(sweep, RunGbmSweep)
    assert sweep._store is deps.store
    assert sweep._hasher is deps.hasher
    assert sweep._tracker is deps.tracker
    assert isinstance(sweep._splitter, WalkForwardSplitter)
    assert isinstance(sweep._trainer, _LazyLightgbmQuantileTrainer)
    assert isinstance(sweep._search, _LazyOptunaSearch)
    assert sweep._search is not deps.run_tft_sweep._search  # um estudo por sweep
    assert not hasattr(sweep, "_persist_predictions")
    assert not hasattr(sweep, "_persist_run_record")
    assert not hasattr(sweep, "_analytics_repository")


@pytest.mark.unit
def test_wire_dependencies_wires_cohort_ledger_and_run_index(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_root=tmp_path / "d", artifacts_root=tmp_path / "a")

    deps = wire_dependencies(settings=settings)

    ledger = deps.cohort_ledger
    assert isinstance(ledger, JsonCohortProgressLedger)
    assert ledger._cohorts_dir == tmp_path / "a" / "cohorts"
    assert ledger._lock_path == tmp_path / "d" / ".writer.lock"
    index = deps.cohort_run_index
    assert isinstance(index, ParquetCohortRunIndex)
    assert index._repository is deps.analytics_repository


@pytest.mark.unit
def test_confirmatory_cohort_is_built_per_cohort_path_with_the_git_probe(tmp_path: Path) -> None:
    """Sem fábrica injetada, o probe é o do git sobre `settings.repo_root`."""
    repo = tmp_path / "repo"
    settings = Settings(
        _env_file=None, data_root=tmp_path / "d", artifacts_root=tmp_path / "a", repo_root=repo
    )
    deps = wire_dependencies(settings=settings)

    cohort = deps.confirmatory_cohort_for(repo / "config" / "cohorts" / "x.toml", "cpu")

    assert isinstance(cohort, RunConfirmatoryCohort)
    probe = cohort._probe
    assert isinstance(probe, GitRuntimeEnvironmentProbe)
    assert probe._repo_root == repo
    assert cohort._store is deps.store
    assert cohort._hasher is deps.hasher
    assert cohort._ledger is deps.cohort_ledger
    assert cohort._run_index is deps.cohort_run_index
    assert cohort._run_baselines is deps.run_baselines
    assert cohort._train_gbm is deps.train_gbm_quantile
    assert cohort._train_tft is deps.train_tft
    assert cohort._modeling_columns == modeling_columns()
    assert cohort._observed_feature_set_hash == feature_set_hash()
    assert cohort._pipeline_version == PIPELINE_VERSION
    assert cohort._schema_version == _SILVER_SCHEMA_VERSION
    assert cohort._supported_device == "cpu"


@pytest.mark.unit
def test_injected_probe_factory_and_sentiment_model_replace_the_real_ones(tmp_path: Path) -> None:
    """Os dois pontos de injeção do e2e: nada de torch nem do git do processo."""
    calls: list[tuple[Path, str]] = []
    fake_probe = InMemoryRuntimeEnvironmentProbe()

    def factory(cohort_path: Path, device: str) -> InMemoryRuntimeEnvironmentProbe:
        calls.append((cohort_path, device))
        return fake_probe

    sentiment = _LazyFinbertSentimentModel()
    settings = Settings(_env_file=None, data_root=tmp_path, artifacts_root=tmp_path / "a")

    deps = wire_dependencies(
        settings=settings, sentiment_model=sentiment, runtime_probe_factory=factory
    )
    cohort = deps.confirmatory_cohort_for(tmp_path / "c.toml", "cpu")

    assert deps.sentiment_model is sentiment
    assert deps.runtime_probe_for is factory
    assert cohort._probe is fake_probe
    assert calls == [(tmp_path / "c.toml", "cpu")]


@pytest.mark.unit
def test_silver_schema_version_matches_every_silver_table() -> None:
    """A versão gravada em `dim_run` não pode divergir dos schemas do adapter."""
    versions = {table.schema_version for table in SILVER_REGISTRY.values()}

    assert versions == {_SILVER_SCHEMA_VERSION}


@pytest.mark.unit
def test_modeling_columns_are_exposed_once_for_run_and_freeze(tmp_path: Path) -> None:
    """G5 (Checkpoint C 24-31): uma fonte só para as duas impressões digitais de I4."""
    settings = Settings(_env_file=None, data_root=tmp_path, repo_root=tmp_path)
    deps = wire_dependencies(settings=settings)

    cohort = deps.confirmatory_cohort_for(tmp_path / "c.toml", "cpu")

    assert deps.modeling_columns == modeling_columns()
    assert cohort._modeling_columns == deps.modeling_columns


@pytest.mark.unit
def test_git_probe_receives_the_cohort_path_resolved_against_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G2 (Checkpoint C 24-31): o probe fotografa o MESMO arquivo que o CLI leu."""
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")  # cwd != repo_root: sem o resolve, perderia "sub/"
    settings = Settings(_env_file=None, data_root=tmp_path / "d", repo_root=tmp_path)
    deps = wire_dependencies(settings=settings)

    probe = deps.runtime_probe_for(Path("config") / "cohorts" / "x.toml", "cpu")

    assert isinstance(probe, GitRuntimeEnvironmentProbe)
    assert probe._repo_root == tmp_path.resolve()
    assert probe._cohort_path == "sub/config/cohorts/x.toml"


@pytest.mark.unit
def test_wire_dependencies_wires_refresh_gold(tmp_path: Path) -> None:
    """Stage 6.4 Task 12: `refresh_gold` com os adapters reais e o grafo do concept."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    refresh = deps.refresh_gold
    assert isinstance(refresh, RefreshGold)
    assert refresh._silver_reader is deps.analytics_repository
    assert isinstance(refresh._grid_reader, ReadTrainingGrid)
    assert refresh._grid_reader._hasher is deps.hasher  # o dono calcula o fingerprint (#128)
    assert isinstance(refresh._clock, SystemClock)
    assert isinstance(refresh._gold_store, ParquetGoldStore)
    assert refresh._gold_store.partition_root(GoldPartition("AAPL", "sweep-01")).is_relative_to(
        tmp_path / "gold"
    )
    assert refresh.build_order == (
        "quality_checks",
        "calibration_table",
        "christoffersen_monte_carlo",
        "conformal_corrections",
        "conformal_coverage",
        "differential_acf",
        "differential_breaks",
        "dm_profiles",
        "dm_results",
        "dm_seed_fraction",
        "loss_differentials",
        "mcs_block_sensitivity",
        "mcs_results",
        "metrics_by_run",
        "partial_degeneracy",
    )


@pytest.mark.unit
def test_arch_mcs_proxy_lazy(tmp_path: Path) -> None:
    """O `ArchMcs` só é construído na 1ª chamada (`import arch` adiado)."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))
    proxy = deps.refresh_gold._mcs_backend
    assert isinstance(proxy, _LazyArchMcs)
    assert proxy._delegate is None  # arch ainda não foi importado (o e2e prova a carga)


@pytest.mark.unit
def test_refresh_gold_grid_reader_wired(tmp_path: Path) -> None:
    """ADR 6.4.0009: o realizado vem do `ReadTrainingGrid` com o store e as colunas do cohort."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))
    grid_reader = deps.refresh_gold._grid_reader
    assert isinstance(grid_reader, ReadTrainingGrid)
    assert grid_reader._store is deps.store
    assert grid_reader._columns == deps.modeling_columns


@pytest.mark.unit
def test_refresh_gold_wires_calibrate_conformal(tmp_path: Path) -> None:
    """ADR 7.2.0003 item 3: o port `ConformalCalibration` é o use case da `inference`."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))
    assert isinstance(deps.refresh_gold._conformal_calibration, CalibrateConformal)


@pytest.mark.unit
def test_wires_build_confirmatory_scorecard(tmp_path: Path) -> None:
    """Stage 6.5 Task 11: o scorecard com o source TOML na raiz do repo e o hasher wirado."""
    deps = wire_dependencies(
        settings=Settings(_env_file=None, data_root=tmp_path / "data", repo_root=tmp_path)
    )

    use_case = deps.build_confirmatory_scorecard
    assert isinstance(use_case, BuildConfirmatoryScorecard)
    assert isinstance(use_case._source, TomlPreregistrationSource)
    assert use_case._source._root == tmp_path / "config" / "preregistration"
    assert use_case._hasher is deps.hasher


@pytest.mark.unit
def test_scorecard_shares_gold_store(tmp_path: Path) -> None:
    """O leitor do scorecard é o MESMO `ParquetGoldStore` em que o refresh publica."""
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=tmp_path))

    reader = deps.build_confirmatory_scorecard._reader
    assert isinstance(reader, ParquetGoldStore)
    assert reader is deps.refresh_gold._gold_store


def _inference_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_root=tmp_path / "d",
        artifacts_root=tmp_path / "a",
        repo_root=tmp_path,
        mlflow_tracking_uri=f"sqlite:///{tmp_path / 'mlruns.db'}",
    )


@pytest.mark.unit
def test_wires_run_inference_for_with_the_real_collaborators(tmp_path: Path) -> None:
    """Stage 7.1 Task 11: os fornecedores reais, com as MESMAS declarações do cohort."""
    deps = wire_dependencies(settings=_inference_settings(tmp_path))

    use_case = deps.run_inference_for(tmp_path / "c.toml", "cpu")

    assert isinstance(use_case, RunInference)
    resolver = use_case._resolver
    predictor = use_case._predictor
    assert isinstance(resolver, ResolveTftCheckpoints)
    assert isinstance(predictor, PredictTftFromCheckpoints)
    assert isinstance(use_case._persister, PersistPredictions)
    assert use_case._persister._repository is deps.analytics_repository
    assert use_case._silver is deps.analytics_repository
    assert use_case._ledger is deps.cohort_ledger
    assert use_case._hasher is deps.hasher
    assert isinstance(use_case._clock, SystemClock)
    manifest = use_case._manifest
    assert isinstance(manifest, JsonInferenceManifest)
    assert manifest.path("x") == tmp_path / "d" / "inference" / "x" / "manifest.json"
    assert isinstance(use_case._probe, GitRuntimeEnvironmentProbe)
    # Resolução e predição: o mesmo store, hasher, splitter, raiz, colunas e declarações
    # que o cohort usou para treinar (senão o run_id derivado não seria o gravado).
    for supplier in (resolver, predictor):
        assert supplier._store is deps.store
        assert supplier._hasher is deps.hasher
        assert supplier._splitter is deps.train_tft._splitter
        assert supplier._artifacts_root == tmp_path / "a"
        assert supplier._modeling_columns == deps.modeling_columns
        assert supplier._observed_feature_set_hash == feature_set_hash()
        assert supplier._pipeline_version == PIPELINE_VERSION
        assert supplier._supported_device == "cpu"
    assert resolver._run_index is deps.cohort_run_index
    assert resolver._locator is predictor._locator
    trainer: object = deps.train_tft._trainer
    assert predictor._predictor is trainer


@pytest.mark.unit
def test_checkpoint_locator_is_wired_outside_the_lazy_proxy(tmp_path: Path) -> None:
    """O locator stdlib entra direto: montar a inferência não importa a pilha de DL."""
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from financial_forecasting.composition_root import wire_dependencies
        from financial_forecasting.shared.infrastructure.config.settings import Settings
        root = Path({str(tmp_path)!r})
        deps = wire_dependencies(
            settings=Settings(
                _env_file=None,
                data_root=root / "d",
                artifacts_root=root / "a",
                repo_root=root,
                mlflow_tracking_uri="sqlite:///" + str(root / "mlruns.db"),
            )
        )
        use_case = deps.run_inference_for(root / "c.toml", "cpu")
        print(type(use_case._resolver._locator).__name__)
        print(sorted({{"torch", "lightning", "pytorch_forecasting"}} & set(sys.modules)))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    locator_name, leaked = completed.stdout.strip().splitlines()[-2:]
    assert locator_name == FilesystemCheckpointLocator.__name__
    assert leaked == "[]"


@pytest.mark.unit
def test_lazy_tft_proxy_exposes_predict_from_checkpoint_without_building() -> None:
    """O proxy satisfaz também o port do checkpoint, sem construir o adapter real."""
    proxy = _LazyPfTftTrainer()
    predictor: TftCheckpointPredictor = proxy

    assert callable(predictor.predict_from_checkpoint)
    assert proxy._delegate is None


class _RecordingDelegate:
    """Delegate gravador: guarda os kwargs e devolve um sentinela."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = object()

    def predict_from_checkpoint(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.result


@pytest.mark.unit
def test_lazy_tft_proxy_delegates_predict_from_checkpoint_field_by_field() -> None:
    """Cada argumento chega ao adapter com o próprio nome (nenhum trocado), e o retorno volta."""
    proxy = _LazyPfTftTrainer()
    recorder = _RecordingDelegate()
    proxy._delegate = recorder  # type: ignore[assignment]
    kwargs: dict[str, Any] = {
        "checkpoint_path": "/a/tft/r/epoch=0-step=1.ckpt",
        "expected_sha256": "f" * 64,
        "feature_names": ("x1", "x2"),
        "known_feature_names": ("x2",),
        "rows": ((1.0, 2.0), (3.0, 4.0)),
        "target": (0.1, 0.2),
        "decision_indices": (5, 6),
        "max_horizon": 7,
        "horizons": (1, 7),
        "quantile_levels": (0.1, 0.5, 0.9),
        "batch_size": 64,
        "num_threads": 3,
    }

    result = proxy.predict_from_checkpoint(**kwargs)

    assert result is recorder.result
    assert recorder.calls == [kwargs]


@pytest.mark.unit
def test_injected_probe_factory_reaches_run_inference(tmp_path: Path) -> None:
    calls: list[tuple[Path, str]] = []
    fake_probe = InMemoryRuntimeEnvironmentProbe()

    def factory(cohort_path: Path, device: str) -> InMemoryRuntimeEnvironmentProbe:
        calls.append((cohort_path, device))
        return fake_probe

    deps = wire_dependencies(settings=_inference_settings(tmp_path), runtime_probe_factory=factory)

    use_case = deps.run_inference_for(tmp_path / "c.toml", "cpu")

    assert use_case._probe is fake_probe
    assert calls == [(tmp_path / "c.toml", "cpu")]


def _wired_objects(root: object) -> list[object]:
    """Todo objeto do pacote alcançável pelos atributos de instância a partir de `root`."""
    seen: dict[int, object] = {}
    pending = [root]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        values: list[object]
        if isinstance(current, dict):
            values = list(current.values())
        elif isinstance(current, list | tuple | set | frozenset):
            values = list(current)
        elif type(current).__module__.startswith("financial_forecasting."):
            seen[id(current)] = current
            values = list(getattr(current, "__dict__", {}).values())
        else:
            continue
        pending.extend(values)
    return list(seen.values())


@pytest.mark.unit
def test_run_inference_for_wires_no_evaluation_use_case(tmp_path: Path) -> None:
    """Evidência do CA-10: nada do `evaluation` no grafo montado pela fábrica."""
    deps = wire_dependencies(settings=_inference_settings(tmp_path))

    graph = _wired_objects(deps.run_inference_for(tmp_path / "c.toml", "cpu"))

    modules = {type(obj).__module__ for obj in graph}
    assert (
        "financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints"
        in (modules)
    )  # o percurso entra nos use cases fornecedores
    assert not [m for m in modules if m.startswith("financial_forecasting.features.evaluation")]


# -- Stage 7.3, Task 03: device por instância do treinador do TFT (ADR 7.3.0004) --------


@pytest.mark.unit
def test_supported_devices_map_is_cpu_and_rocm() -> None:
    assert dict(_SUPPORTED_DEVICES) == {"cpu": "cpu", "rocm": "gpu"}


@pytest.mark.unit
def test_trainer_factory_keeps_one_lazy_proxy_per_device() -> None:
    trainer_for = _tft_trainer_factory()

    cpu, rocm = trainer_for("cpu"), trainer_for("rocm")

    assert trainer_for("cpu") is cpu
    assert trainer_for("rocm") is rocm
    assert cpu is not rocm
    assert (cpu._accelerator, rocm._accelerator) == ("cpu", "gpu")
    assert cpu._delegate is None
    assert rocm._delegate is None


@pytest.mark.unit
def test_device_outside_the_map_refused_without_importing_torch() -> None:
    script = textwrap.dedent(
        """
        import sys
        from financial_forecasting.composition_root import _tft_trainer_factory
        trainer_for = _tft_trainer_factory()
        trainer_for("rocm")
        for device in ("cuda", "gpu", "", "CPU"):
            try:
                trainer_for(device)
            except ValueError as exc:
                print("refused", device, "not supported" in str(exc))
            else:
                print("accepted", device)
        print(sorted({"torch", "lightning", "pytorch_forecasting"} & set(sys.modules)))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    lines = completed.stdout.strip().splitlines()
    assert lines[:-1] == [
        "refused cuda True",
        "refused gpu True",
        "refused  True",
        "refused CPU True",
    ]
    assert lines[-1] == "[]"


@pytest.mark.unit
def test_confirmatory_and_inference_factories_use_cpu(tmp_path: Path) -> None:
    deps = wire_dependencies(settings=_inference_settings(tmp_path))

    trainer = deps.train_tft._trainer
    assert isinstance(trainer, _LazyPfTftTrainer)
    assert trainer._accelerator == "cpu"
    assert deps.run_tft_sweep._trainer is trainer
    cohort = deps.confirmatory_cohort_for(tmp_path / "c.toml", "cpu")
    assert cohort._train_tft._trainer is trainer
    inference = deps.run_inference_for(tmp_path / "c.toml", "cpu")
    assert inference._predictor._predictor is trainer


# -- Stage 7.3, Task 10: fábricas do cohort de ablação ---------------------------------


def _ablation_files(tmp_path: Path, *, device: str) -> Path:
    """Base e arquivo de ablação sob `repo_root = tmp_path` (base sintética congelada)."""
    import importlib  # noqa: PLC0415 — `adapters/in` (keyword `in`), LAYOUT §8

    from tests.unit.features.modeling.adapters.in_.test_ablation_cohort_file import (  # noqa: PLC0415
        _draft,
    )
    from tests.unit.features.modeling.application.test_cohort_spec import (  # noqa: PLC0415
        _spec as _base_spec,
    )

    cohort_file: Any = importlib.import_module(
        "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
    )
    ablation_file: Any = importlib.import_module(
        "financial_forecasting.features.modeling.adapters.in.cli.ablation_cohort_file"
    )
    base = _base_spec()
    base_path = tmp_path / "config" / "cohorts" / "base.toml"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(cohort_file.dump(base), encoding="utf-8")
    ablation = tmp_path / "config" / "cohorts" / "ablation.toml"
    ablation.write_text(ablation_file.dump_ablation_cohort(_draft(device=device)), encoding="utf-8")
    return ablation


@pytest.mark.unit
def test_ablation_factory_reads_the_device_from_the_spec(tmp_path: Path) -> None:
    deps = wire_dependencies(settings=_inference_settings(tmp_path))
    ablation = _ablation_files(tmp_path, device="rocm")

    spec, base = deps.load_ablation_spec(ablation)
    use_case = deps.ablation_cohort_for(ablation)
    pilot = deps.measure_ablation_cost_for(ablation)

    assert spec.device == "rocm"
    assert base.name == "aapl_confirmatory"
    trainer = use_case._train_tft._trainer
    assert isinstance(trainer, _LazyPfTftTrainer)
    assert trainer._accelerator == "gpu"
    assert trainer._delegate is None
    assert pilot._trainer is trainer
    assert use_case._base_supported_device == "cpu"
    assert deps.train_tft._trainer._accelerator == "cpu"
    assert use_case._run_index is deps.cohort_run_index
    assert use_case._ledger is deps.cohort_ledger
    assert deps.load_ablation_spec(ablation)[0] == spec
    assert deps.dump_ablation_spec(spec) == ablation.read_text(encoding="utf-8")


@pytest.mark.unit
def test_ablation_factory_refuses_device_outside_the_map_without_importing_torch(
    tmp_path: Path,
) -> None:
    ablation = _ablation_files(tmp_path, device="cuda")
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from financial_forecasting.composition_root import wire_dependencies
        from financial_forecasting.shared.infrastructure.config.settings import Settings
        root = Path({str(tmp_path)!r})
        deps = wire_dependencies(
            settings=Settings(
                _env_file=None,
                data_root=root / "d",
                artifacts_root=root / "a",
                repo_root=root,
                mlflow_tracking_uri="sqlite:///" + str(root / "mlruns.db"),
            )
        )
        for factory in (deps.ablation_cohort_for, deps.measure_ablation_cost_for):
            try:
                factory(Path({str(ablation)!r}))
            except ValueError as exc:
                print("refused", "not supported" in str(exc))
            else:
                print("accepted")
        print(sorted({{"torch", "lightning", "pytorch_forecasting"}} & set(sys.modules)))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    lines = completed.stdout.strip().splitlines()
    assert lines[-3:] == ["refused True", "refused True", "[]"]
