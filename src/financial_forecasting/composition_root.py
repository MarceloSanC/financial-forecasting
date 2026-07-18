"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB, MlflowTracker → outro
tracker), mude APENAS aqui. Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/out/`. Sempre receba dependências via construtor (injeção explícita).
Os campos de `ApplicationDependencies` são tipados pelos PORTS (`ExperimentTracker`,
`Hasher`, `IndicatorCalculator`, `SentimentModel`, `AsofJoinAdapter`,
`DatasetAssemblerPort`), não pelos concretos — wiring centralizado, contrato exposto.

Stage 3.5 (I8/A7): aqui os 3 adapters do BC `feature_engineering`
(`PandasTaIndicatorCalculator` 3.1, `FinbertSentimentModel` 3.2,
`AsofJoinDuckdbAdapter` 3.3) + `DatasetAssembler` + o use case `BuildDataset` são
wirados — **resolvendo os findings F2 de wiring deferido** das auditorias 3.1/3.2/3.3
(sem isso, esses ports/adapters seriam dead-code). O `SentimentModel` (FinBERT) é
wirado por um **proxy lazy** (`_LazyFinbertSentimentModel`): torch/transformers só
carregam no PRIMEIRO `score_articles`, mantendo o wiring leve e testável sem GPU/torch.

Stage 5.2 (Task 09): o use case `RunBaselines` é montado aqui com colaboradores
REAIS — `ParquetMedallionStore` (par read-only `("processed", "dataset_tft")`),
`WalkForwardSplitter` sobre `TradingCalendar` materializado numa **janela ampla
fixa** do XNYS (F-T1 opção A; constantes comentadas abaixo), o
`StatsforecastBaselineForecaster` atrás do port `BaselineForecaster` via **proxy
lazy** (`_LazyStatsforecastBaselineForecaster` — statsforecast só carrega no
primeiro `forecast`, precedente FinBERT), `PersistPredictions` +
`ParquetAnalyticsRepository` (silver) e o `Hasher` 1.4.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
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
from financial_forecasting.features.feature_engineering.application.ports.out.asof_join import (
    AsofJoinAdapter,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblerPort,
)
from financial_forecasting.features.feature_engineering.application.ports.out.indicator_calculator import (  # noqa: E501
    IndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
    SentimentModel,
)
from financial_forecasting.features.feature_engineering.application.use_cases.build_dataset import (
    BuildDataset,
)
from financial_forecasting.features.feature_engineering.application.use_cases.score_and_aggregate_sentiment import (  # noqa: E501
    ScoreAndAggregateSentiment,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    BaselineForecaster,
    GridByHorizon,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.mlflow.mlflow_tracker import MlflowTracker
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.application.ports.out.exchange_calendar_provider import (
    ExchangeCalendarProvider,
)
from financial_forecasting.shared.application.ports.out.experiment_tracker import (
    ExperimentTracker,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from financial_forecasting.shared.infrastructure.config.settings import Settings, get_settings

# Revisão pinada do FinBERT (espelha o default do adapter; ADR 0.0.0017).
_FINBERT_PINNED_REVISION = "4556d13015211d73dccd3fdd39d39232506f3e43"

# Janela ampla FIXA do calendário XNYS para o wiring do `WalkForwardSplitter`
# (Stage 5.2 Task 09; decisão F-T1 opção A do technical 5.2 §5): cobre o span
# plausível de QUALQUER dataset do piloto (e além), de modo que o splitter possa
# validar/deslocar sessões sem re-materializar calendário por invocação. O
# adapter `ExchangeCalendarsProvider` materializa bounds explícitos quando a
# janela excede o default da lib. Se um dataset futuro apertar estes limites,
# promover a campo de `Settings` ou a factory por invocação (registrado como
# risco na tabela do technical 5.2 §5 — não muda o contrato do use case).
_CALENDAR_WINDOW_START = date(1990, 1, 1)
_CALENDAR_WINDOW_END = date(2035, 12, 31)


class _LazyFinbertSentimentModel:
    """Proxy lazy do `FinbertSentimentModel` (satisfaz o port `SentimentModel`).

    Adia a construção do `FinbertSentimentModel` (que carrega torch/transformers e
    baixa os pesos) até o PRIMEIRO `score_articles`, mantendo `wire_dependencies`
    leve e testável sem o extra `sentiment`. Expõe `model_name`/`revision` sem
    importar torch (metadados estáticos, rastreabilidade ADR 0.0.0017).
    """

    model_name = "ProsusAI/finbert"

    def __init__(self, *, revision: str = _FINBERT_PINNED_REVISION) -> None:
        self.revision = revision
        self._delegate: SentimentModel | None = None

    def _ensure(self) -> SentimentModel:
        if self._delegate is None:
            # Import LAZY proposital (PLC0415 ignorado no pyproject p/ este arquivo):
            # adia torch/transformers até o 1º uso, mantendo o wiring leve/testável.
            from financial_forecasting.features.feature_engineering.adapters.out.finbert.finbert_sentiment_model import (  # noqa: E501
                FinbertSentimentModel,
            )

            self._delegate = FinbertSentimentModel(revision=self.revision)
        return self._delegate

    def score_articles(self, articles: Sequence[NewsArticle]) -> Sequence[float]:
        """Constrói o FinBERT real na 1ª chamada e delega o scoring (I1/I2)."""
        return self._ensure().score_articles(articles)


class _LazyStatsforecastBaselineForecaster:
    """Proxy lazy do `StatsforecastBaselineForecaster` (satisfaz o port `BaselineForecaster`).

    Adia o import de `statsforecast` (~6s frios por processo) até o PRIMEIRO
    `forecast`, mantendo `wire_dependencies` — e o import deste módulo — leves
    (mesmo precedente do `_LazyFinbertSentimentModel` acima; fix F3 do
    Checkpoint C da Stage 5.2). O contrato semântico do port (I3/I4/C1/C5) é
    integralmente do delegate real.
    """

    def __init__(self) -> None:
        self._delegate: BaselineForecaster | None = None

    def _ensure(self) -> BaselineForecaster:
        if self._delegate is None:
            # Import LAZY proposital (PLC0415 ignorado no pyproject p/ este
            # arquivo): adia statsforecast até o 1º uso.
            from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
                StatsforecastBaselineForecaster,
            )

            self._delegate = StatsforecastBaselineForecaster()
        return self._delegate

    def forecast(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        spec: BaselineSpec,
        returns: Sequence[float],
        train_end_idx: int,
        decision_indices: Sequence[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> Mapping[int, GridByHorizon]:
        """Constrói o adapter statsforecast real na 1ª chamada e delega a emissão."""
        return self._ensure().forecast(
            spec=spec,
            returns=returns,
            train_end_idx=train_end_idx,
            decision_indices=decision_indices,
            horizons=horizons,
            quantile_levels=quantile_levels,
        )


@dataclass
class ApplicationDependencies:
    """Contêiner com as dependências montadas e prontas para uso.

    Exponha aqui apenas o que as camadas superiores (use cases, adapters
    primários) precisam. Os campos são tipados pelos PORTS — os concretos
    (`CanonicalJsonHasher`, `MlflowTracker`, `PandasTaIndicatorCalculator`, …) são
    detalhe do wiring abaixo (I9).

    Adicione campos conforme as features forem criadas (use cases, etc.).
    """

    hasher: Hasher
    tracker: ExperimentTracker
    store: MedallionStore
    # BC feature_engineering (Stage 3.5, I8): ports tipando os 3 adapters + o use case.
    indicator_calculator: IndicatorCalculator
    sentiment_model: SentimentModel
    asof_join: AsofJoinAdapter
    dataset_assembler: DatasetAssemblerPort
    calendar_provider: ExchangeCalendarProvider
    build_dataset: BuildDataset
    # BC analytics_store (Stage 4.2, A11): adapter Parquet silver tipado pelo port.
    analytics_repository: AnalyticsRepository
    # BC modeling (Stage 5.2, Task 09): use case dos 5 baselines sob o harness 5.1.
    run_baselines: RunBaselines


def wire_dependencies(settings: Settings | None = None) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e retorna o contêiner pronto.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode ser chamado com um `Settings` fake apontando o
    `mlflow_tracking_uri` para um SQLite em `tmp_path` (sem depender do
    `lru_cache` global de `get_settings`).

    Instancia os concretos AQUI (único lugar): `CanonicalJsonHasher` (1.4),
    `MlflowTracker(cfg.mlflow_tracking_uri)` (1.5), `ParquetMedallionStore(
    cfg.data_root)` (2.1) e os adapters do BC `feature_engineering` (3.1/3.2/3.3/3.5).
    Os campos de `ApplicationDependencies` são tipados pelos PORTS, não pelos
    concretos (I9). `BuildDataset` é montado com os adapters REAIS (não fakes), o
    que resolve os findings F2 de wiring deferido (I8/A7).
    """
    cfg = settings or get_settings()
    hasher = CanonicalJsonHasher()
    tracker = MlflowTracker(tracking_uri=cfg.mlflow_tracking_uri)
    store = ParquetMedallionStore(data_root=cfg.data_root)

    # BC feature_engineering — 3 adapters + assembler + use case (Stage 3.5, I8).
    indicator_calculator = PandasTaIndicatorCalculator()
    sentiment_model = _LazyFinbertSentimentModel()
    asof_join = AsofJoinDuckdbAdapter()
    dataset_assembler = DatasetAssembler(dataset_root=cfg.data_root / "processed" / "dataset_tft")
    calendar_provider = ExchangeCalendarsProvider()

    sentiment = ScoreAndAggregateSentiment(
        store=store,
        sentiment_model=sentiment_model,
        calendar_provider=calendar_provider,
    )
    build_dataset = BuildDataset(
        store=store,
        indicator_calculator=indicator_calculator,
        sentiment=sentiment,
        asof_join=asof_join,
        assembler=dataset_assembler,
    )

    # BC analytics_store (Stage 4.2, A11): adapter Parquet silver com data_root do
    # Settings + SystemClock injetado (created_at_utc write-time de dim_run, I5/I10).
    analytics_repository = ParquetAnalyticsRepository(data_root=cfg.data_root, clock=SystemClock())

    # BC modeling (Stage 5.2, Task 09): `RunBaselines` com colaboradores REAIS.
    # O splitter recebe SÓ o `TradingCalendar` (o `Hasher` é parâmetro de
    # `split(...)`, repassado pelo use case — concept 5.2 §8); o calendário é
    # materializado UMA vez na janela ampla fixa (F-T1 opção A, constantes acima).
    # `PersistPredictions` reusa o MESMO repositório silver de `dim_run` (dono
    # único do `target_timestamp` — ADR 4.3.0001).
    splitter = WalkForwardSplitter(
        TradingCalendar(
            calendar_provider.sessions(
                start=_CALENDAR_WINDOW_START, end=_CALENDAR_WINDOW_END
            )
        )
    )
    run_baselines = RunBaselines(
        store=store,
        splitter=splitter,
        forecaster=_LazyStatsforecastBaselineForecaster(),
        persist_predictions=PersistPredictions(repository=analytics_repository),
        analytics_repository=analytics_repository,
        hasher=hasher,
    )

    return ApplicationDependencies(
        hasher=hasher,
        tracker=tracker,
        store=store,
        indicator_calculator=indicator_calculator,
        sentiment_model=sentiment_model,
        asof_join=asof_join,
        dataset_assembler=dataset_assembler,
        calendar_provider=calendar_provider,
        build_dataset=build_dataset,
        analytics_repository=analytics_repository,
        run_baselines=run_baselines,
    )
