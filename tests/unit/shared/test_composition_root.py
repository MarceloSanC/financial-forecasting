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
    _DATASET_MAX_NAN_RATIO_PER_FEATURE,
    _SILVER_SCHEMA_VERSION,
    ApplicationDependencies,
    _LazyArchMcs,
    _LazyFinbertSentimentModel,
    _LazyLightgbmQuantileTrainer,
    _LazyOptunaSearch,
    _LazyPfTftTrainer,
    _LazyStatsforecastBaselineForecaster,
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
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainer,
)
from financial_forecasting.features.modeling.application.use_cases.read_training_grid import (
    ReadTrainingGrid,
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
    assert refresh._grid_reader._hasher is deps.hasher  # o dono calcula o fingerprint (#128)
    assert isinstance(refresh._clock, SystemClock)
    assert isinstance(refresh._gold_store, ParquetGoldStore)
    assert refresh._gold_store.partition_root(GoldPartition("AAPL", "sweep-01")).is_relative_to(
        tmp_path / "gold"
    )
    assert refresh.build_order == (
        "quality_checks",
        "calibration_table",
        "dm_results",
        "mcs_results",
        "metrics_by_run",
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
