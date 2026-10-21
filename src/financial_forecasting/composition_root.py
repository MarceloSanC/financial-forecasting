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
`PersistRunRecord` (issue #68) sobre o `ParquetAnalyticsRepository` (silver) e o
`Hasher` 1.4.

Stage 5.5 (Task 25): a ingestão LOCAL do BC `market_data` — `IngestCandles`,
`IngestNews` e `IngestFundamentals` sobre os fetchers Parquet que leem os brutos
sob `data_root` (`raw/market/candles`, `raw/news`, `processed/fundamentals`) —
é wirada para o runner do cohort materializar o bronze a partir dos brutos.

Stage 5.5 (Task 26): `RunGbmSweep` (sem persistência, como o sweep do TFT), o
ledger JSON e o índice de runs do cohort, e o `RunConfirmatoryCohort`. O probe
do ambiente depende do CAMINHO do arquivo do cohort, que só existe depois de o
CLI ler os argumentos: por isso o contêiner expõe fábricas —
`runtime_probe_for(cohort_path, device)` e `confirmatory_cohort_for(cohort_path,
device)` — em vez de instâncias. `wire_dependencies` aceita, opcionalmente, o
modelo de sentimento e a fábrica do probe (fakes nos testes e no e2e); sem eles,
monta os reais — não há condicional de produção.

Stage 6.4 (Tasks 12/15): o use case `RefreshGold` é montado aqui com o
`ParquetAnalyticsRepository` já wirado (como `SilverTableReader`, por duck typing), o
`ReadTrainingGrid` da `modeling` sobre o `ParquetMedallionStore` e as colunas de
modelagem (como `TrainingGridReader`, ADR 6.4.0009), o `CanonicalJsonHasher`, o
`SystemClock`, o `ArchMcs` atrás do proxy lazy `_LazyArchMcs` (`import arch` ~8 s a
frio, medido no technical 6.4 §1 — só carrega na primeira chamada), o
`ParquetGoldStore(data_root)` e os treze gold builders (cinco da 6.4, oito de perfil da 6.6).

Stage 7.1 (Task 11): a fábrica `run_inference_for(cohort_path, device)` monta o
`RunInference` do slice `inference` com os fornecedores reais — `ResolveTftCheckpoints`
e `PredictTftFromCheckpoints` do `modeling` (mesmo splitter, store, hasher,
`artifacts_root`, colunas e declarações do cohort), o `FilesystemCheckpointLocator`
direto (stdlib, fora do proxy lazy do TFT), o `PersistPredictions` e o repositório
silver, o ledger do cohort e o `JsonInferenceManifest` sob `data_root`. O probe vem
de `runtime_probe_for`, como no `confirmatory_cohort_for`.

Stage 7.3 (Task 20): a fábrica `permutation_inference_for(cohort_path)` monta o
`RunPermutationInference` com o MESMO resolvedor da 7.1, o
`PredictTftAttributionFromCheckpoints` sobre o proxy do treinador de `cpu` (a partição da
registry como referência), os dois escritores do silver de atribuição sobre o MESMO
repositório, o ledger do cohort e o `JsonAttributionManifest` sob `data_root`. Nada de
`evaluation` (I9).
"""

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_cohort_run_index import (  # noqa: E501
    ParquetCohortRunIndex,
)
from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PersistPermutedPredictions,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecord,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeights,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.calibration_table import (  # noqa: E501
    CalibrationTableGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.christoffersen_monte_carlo import (  # noqa: E501
    ChristoffersenMonteCarloGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.conformal_corrections import (  # noqa: E501
    ConformalCorrectionsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.conformal_coverage import (  # noqa: E501
    ConformalCoverageGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.differential_acf import (  # noqa: E501
    DifferentialAcfGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.differential_breaks import (  # noqa: E501
    DifferentialBreaksGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_profiles import (  # noqa: E501
    DmProfilesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_results import (
    DmResultsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_seed_fraction import (  # noqa: E501
    DmSeedFractionGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_importance import (  # noqa: E501
    H3ImportanceGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_reading import (
    H3ReadingGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_shares import (
    H3SharesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_vsn import (
    H3VsnGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.loss_differentials import (  # noqa: E501
    LossDifferentialsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.mcs_block_sensitivity import (  # noqa: E501
    McsBlockSensitivityGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.mcs_results import (  # noqa: E501
    McsResultsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.metrics_by_run import (  # noqa: E501
    MetricsByRunGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.partial_degeneracy import (  # noqa: E501
    PartialDegeneracyGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.quality_checks import (  # noqa: E501
    QualityChecksGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import (  # noqa: E501
    TomlPreregistrationSource,
)
from financial_forecasting.features.evaluation.application.ports.out.mcs_backend import (
    McsBackend,
)
from financial_forecasting.features.evaluation.application.use_cases.build_confirmatory_scorecard import (  # noqa: E501
    BuildConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
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
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.inference.adapters.out.filesystem.json_attribution_manifest import (  # noqa: E501
    JsonAttributionManifest,
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
from financial_forecasting.features.inference.application.use_cases.run_permutation_inference import (  # noqa: E501
    RunPermutationInference,
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
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
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
from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    BaselineForecaster,
    GridByHorizon,
)
from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortProgressLedger,
)
from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
    CohortRunIndex,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    HyperparameterSearch,
    SearchDimension,
    SearchTrial,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
    QuantileModelTrainer,
    QuantileTrainingResult,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    CPU_DEVICE,
    RuntimeEnvironmentProbe,
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    TftAttributionPrediction,
    TftCheckpointPrediction,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
    TftTrainingResult,
)
from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (
    MeasureAblationCost,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    PredictTftAttributionFromCheckpoints,
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
from financial_forecasting.features.modeling.application.use_cases.run_ablation_cohort import (
    RunAblationCohort,
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
    TrainGbmQuantile,
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
    registry_family_partition,
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

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
        PfTftTrainer,
    )
    from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
        AblationCohortSpec,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec

# Revisão pinada do FinBERT (espelha o default do adapter; ADR 0.0.0017).
_FINBERT_PINNED_REVISION = "4556d13015211d73dccd3fdd39d39232506f3e43"

# Limiar de missing do `DatasetQualityGate` (issue #72): NaN-ratio máximo por feature
# APÓS descontar o warmup nominal do registry. Declarado AQUI (constante revisada em
# code review, não env var — um override de ambiente poderia desarmar o gate sem
# rastro; mesmo precedente de `_FINBERT_PINNED_REVISION`: pin metodológico que não
# pode variar por ambiente) porque o domínio não tem mais default: o old herdava
# `1.0`, inalcançável para `ratio ∈ [0, 1]`. Por que 0.02 (ponta apertada da faixa
# 0.02 a 0.05 da issue): no piloto AAPL (~4023 linhas) tolera ≤ ~79 linhas faltantes
# pós-warmup. Limite HONESTO do que ele acusa: 1 trimestre de fundamento ausente
# (≈ 63 linhas ≈ 1.6%) fica ABAIXO de 0.02 e passa — a auditoria do #80 refez a
# conta; o gate só reprova a partir de ~1.3 trimestre (≈ 80 linhas). 1 ano (≈ 6%)
# reprova. Um trimestre faltante nem vira NaN aqui (o as-of faz carry-forward),
# então o instrumento desse caso é outro. Desde a #83 este ratio mede SÓ missing
# interior (real): warmup efetivo acima do declarado — o débito +19/+49 dos regimes
# que a #72 mediu e este limiar tolerava por dependência de N — é acusado pela
# checagem ABSOLUTA (d) do gate, em linhas, antes do ratio e sem knob.
_DATASET_MAX_NAN_RATIO_PER_FEATURE = 0.02

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

# Versão dos schemas silver gravada em `dim_run` pelos runs do cohort confirmatório
# (Stage 5.5, Task 26). Espelha a versão das tabelas do adapter Parquet
# (`schemas/*_schema.py`); o teste do composition root prende a igualdade, então
# uma migração de schema sem atualizar esta constante quebra o `make check`.
_SILVER_SCHEMA_VERSION = 1

# Device em que os trainers rodam: o adapter do TFT fixa `accelerator="cpu"` e o
# LightGBM roda em CPU. O cohort que declarar outro device é recusado (I4).
_TRAINERS_DEVICE = CPU_DEVICE

# Device declarado no cohort → `accelerator` do Lightning do `PfTftTrainer` (Stage 7.3,
# ADR 7.3.0004 item 2). `rocm` é o device do cohort de ablação no Linux (o build ROCm do
# torch expõe a GPU pela API `cuda`, e o Lightning a chama de `"gpu"`). Device fora do
# mapa é recusado aqui, antes de qualquer import de torch.
_SUPPORTED_DEVICES: Mapping[str, str] = MappingProxyType({CPU_DEVICE: "cpu", "rocm": "gpu"})


def _accelerator_for(device: str) -> str:
    """O `accelerator` do Lightning para o device do cohort (C1: fora do mapa ergue)."""
    if device not in _SUPPORTED_DEVICES:
        raise ValueError(
            f"device {device!r} is not supported; expected one of {sorted(_SUPPORTED_DEVICES)}"
        )
    return _SUPPORTED_DEVICES[device]


# Fábrica do probe de ambiente: (caminho do arquivo do cohort, device) → probe.
RuntimeProbeFactory = Callable[[Path, str], RuntimeEnvironmentProbe]


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


class _LazyPfTftTrainer:
    """Proxy lazy do `PfTftTrainer` (satisfaz `TftTrainer` e `TftCheckpointPredictor`).

    Adia o import de `torch`/`lightning`/`pytorch_forecasting` até o PRIMEIRO
    treino. Aqui a razão NÃO é opcionalidade — desde a Stage 5.4 a pilha é
    dependência principal (ADR 5.4.0003) — e sim custo de carga: importar torch
    leva segundos, e `wire_dependencies` é chamado por qualquer entrypoint,
    inclusive os que não treinam nada. A predição a partir do checkpoint (Stage
    7.1) passa pelo mesmo proxy: a mesma instância do adapter treina e prediz.
    """

    def __init__(self, accelerator: str = "cpu") -> None:
        # Stage 7.3: o accelerator é da instância do adapter (ADR 7.3.0004 item 1).
        self._accelerator = accelerator
        self._delegate: PfTftTrainer | None = None

    def _ensure(self) -> "PfTftTrainer":
        if self._delegate is None:
            # Import LAZY proposital (PLC0415 ignorado no pyproject p/ este arquivo).
            from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
                PfTftTrainer,
            )

            self._delegate = PfTftTrainer(accelerator=self._accelerator)
        return self._delegate

    def train_and_predict(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        params: TftTrainingParams,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        train_decision_indices: Sequence[int],
        early_stop_decision_indices: Sequence[int],
        test_decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        artifact_dir: str,
    ) -> TftTrainingResult:
        """Delega ao adapter real (o contrato semântico é integralmente dele).

        A assinatura espelha o port campo a campo, como o proxy do LightGBM
        abaixo: com `**kwargs: object` o mypy não checaria conformidade nenhuma
        — qualquer Protocol seria satisfeito por acidente.
        """
        return self._ensure().train_and_predict(
            params=params,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            rows=rows,
            target=target,
            train_decision_indices=train_decision_indices,
            early_stop_decision_indices=early_stop_decision_indices,
            test_decision_indices=test_decision_indices,
            max_horizon=max_horizon,
            horizons=horizons,
            quantile_levels=quantile_levels,
            artifact_dir=artifact_dir,
        )

    def predict_from_checkpoint(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
    ) -> TftCheckpointPrediction:
        """Delega ao adapter real, com a assinatura do port campo a campo."""
        return self._ensure().predict_from_checkpoint(
            checkpoint_path=checkpoint_path,
            expected_sha256=expected_sha256,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            rows=rows,
            target=target,
            decision_indices=decision_indices,
            max_horizon=max_horizon,
            horizons=horizons,
            quantile_levels=quantile_levels,
            batch_size=batch_size,
            num_threads=num_threads,
        )

    def predict_attribution_from_checkpoint(  # noqa: PLR0913 — assinatura do port
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
        permuted_columns: Mapping[str, Sequence[str]],
        donors: Sequence[Sequence[int]],
    ) -> TftAttributionPrediction:
        """Delega ao adapter real (Stage 7.3), com a assinatura do port campo a campo."""
        return self._ensure().predict_attribution_from_checkpoint(
            checkpoint_path=checkpoint_path,
            expected_sha256=expected_sha256,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            rows=rows,
            target=target,
            decision_indices=decision_indices,
            max_horizon=max_horizon,
            horizons=horizons,
            quantile_levels=quantile_levels,
            batch_size=batch_size,
            num_threads=num_threads,
            permuted_columns=permuted_columns,
            donors=donors,
        )


_MODELING_CLI = "financial_forecasting.features.modeling.adapters.in.cli"


def ablation_spec_loader(
    repo_root: Path, hasher: Hasher
) -> Callable[[Path], "tuple[AblationCohortSpec, CohortSpec]"]:
    """Lê o arquivo de ablação e a base que ele declara (caminho relativo ao `repo_root`).

    Os módulos de `adapters/in` são carregados por `importlib` (`in` é keyword, LAYOUT
    §8). O loader confere a base e a registry (C2) antes de devolver.
    """
    cohort_file = importlib.import_module(f"{_MODELING_CLI}.cohort_file")
    ablation_file = importlib.import_module(f"{_MODELING_CLI}.ablation_cohort_file")

    def load(path: Path) -> "tuple[AblationCohortSpec, CohortSpec]":
        bases: dict[str, CohortSpec] = {}

        def load_base(declared: str) -> "CohortSpec":
            bases[declared] = cohort_file.load(repo_root / declared)
            return bases[declared]

        spec = ablation_file.load_ablation_cohort(path, hasher=hasher, load_base=load_base)
        return spec, bases[spec.base_cohort_file]

    return load


def dump_ablation_spec(spec: "AblationCohortSpec") -> str:
    """O TOML do spec de ablação (`ablation_cohort_file.dump_ablation_cohort`)."""
    ablation_file = importlib.import_module(f"{_MODELING_CLI}.ablation_cohort_file")
    text: str = ablation_file.dump_ablation_cohort(spec)
    return text


def _tft_trainer_factory() -> Callable[[str], _LazyPfTftTrainer]:
    """Um proxy lazy do `PfTftTrainer` por device, criado na primeira vez (Stage 7.3).

    O mesmo device devolve sempre a mesma instância (treino e predição a partir do
    checkpoint seguem compartilhando o adapter, Stage 7.1). Device fora de
    `_SUPPORTED_DEVICES` ergue `ValueError` sem importar torch.
    """
    proxies: dict[str, _LazyPfTftTrainer] = {}

    def trainer_for(device: str) -> _LazyPfTftTrainer:
        accelerator = _accelerator_for(device)
        if device not in proxies:
            proxies[device] = _LazyPfTftTrainer(accelerator)
        return proxies[device]

    return trainer_for


class _LazyOptunaSearch:
    """Proxy lazy do `OptunaSearch` (satisfaz o port `HyperparameterSearch`).

    Mesmo motivo do proxy acima: `optuna` só carrega quando uma varredura de
    fato começa.
    """

    def __init__(self) -> None:
        self._delegate: HyperparameterSearch | None = None

    def _ensure(self) -> HyperparameterSearch:
        if self._delegate is None:
            from financial_forecasting.features.modeling.adapters.out.optuna.optuna_search import (
                OptunaSearch,
            )

            self._delegate = OptunaSearch()
        return self._delegate

    def create_study(self, *, seed: int, direction: str = "minimize") -> str:
        return self._ensure().create_study(seed=seed, direction=direction)

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        return self._ensure().ask(space)

    def tell(self, *, trial_number: int, objective_value: float) -> None:
        self._ensure().tell(trial_number=trial_number, objective_value=objective_value)

    def fail(self, *, trial_number: int) -> None:
        self._ensure().fail(trial_number=trial_number)

    def best_trial(self) -> SearchTrial:
        return self._ensure().best_trial()


class _LazyLightgbmQuantileTrainer:
    """Proxy lazy do `LightgbmQuantileTrainer` (satisfaz o port `QuantileModelTrainer`).

    Adia o import de `lightgbm` até o PRIMEIRO `train_and_predict`, mantendo
    `wire_dependencies` — e o import deste módulo — leves (mesmo precedente dos
    proxies `_LazyFinbertSentimentModel`/`_LazyStatsforecastBaselineForecaster`
    acima). O contrato semântico do port (C3/C4/C5/I4/I11 e a seleção 1-based
    de m* — ADR 5.3.0002) é integralmente do delegate real.
    """

    def __init__(self) -> None:
        self._delegate: QuantileModelTrainer | None = None

    def _ensure(self) -> QuantileModelTrainer:
        if self._delegate is None:
            # Import LAZY proposital (PLC0415 ignorado no pyproject p/ este
            # arquivo): adia lightgbm até o 1º uso.
            from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
                LightgbmQuantileTrainer,
            )

            self._delegate = LightgbmQuantileTrainer()
        return self._delegate

    def train_and_predict(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        """Constrói o adapter LightGBM real na 1ª chamada e delega o treino."""
        return self._ensure().train_and_predict(
            params=params,
            feature_names=feature_names,
            train_rows=train_rows,
            train_labels_by_horizon=train_labels_by_horizon,
            early_stop_rows=early_stop_rows,
            early_stop_labels_by_horizon=early_stop_labels_by_horizon,
            test_rows=test_rows,
            test_decision_indices=test_decision_indices,
            quantile_levels=quantile_levels,
        )


class _LazyArchMcs:
    """Proxy lazy do `ArchMcs` (satisfaz o port `McsBackend` do `evaluation`).

    Adia o `import arch` (~8 s a frio no container; technical 6.4 §1) até a PRIMEIRA
    chamada, mantendo `wire_dependencies` leve (precedente statsforecast/torch). O
    contrato semântico do port (validação C9, `ArithmeticError` do b̂_sb) é do
    delegate real.
    """

    def __init__(self) -> None:
        self._delegate: McsBackend | None = None

    def _ensure(self) -> McsBackend:
        if self._delegate is None:
            # Import LAZY proposital (PLC0415 ignorado no pyproject p/ este arquivo).
            from financial_forecasting.features.evaluation.adapters.out.inference.arch_mcs import (
                ArchMcs,
            )

            self._delegate = ArchMcs()
        return self._delegate

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        """Constrói o `ArchMcs` na 1ª chamada e delega a estimativa b̂_sb."""
        return self._ensure().optimal_block_length(series=series)

    def bootstrap_indices(
        self, *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
    ) -> BootstrapIndices:
        """Constrói o `ArchMcs` na 1ª chamada e delega os índices de bootstrap."""
        return self._ensure().bootstrap_indices(
            n_obs=n_obs, block_size=block_size, reps=reps, seed=seed, scheme=scheme
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
    # BC market_data (Stage 5.5, Task 25): ingestão local dos brutos para o bronze.
    ingest_candles: IngestCandles
    ingest_news: IngestNews
    ingest_fundamentals: IngestFundamentals
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
    # BC modeling (Stage 5.3, Task 06): GBM quantílico sob o mesmo harness/persister.
    train_gbm_quantile: TrainGbmQuantile
    # BC modeling (Stage 5.4, Task 14): o CANDIDATO e a varredura exploratória.
    # `run_tft_sweep` não recebe porta de persistência de resultados — o
    # isolamento exploratório/confirmatório é estrutural (ADR 5.4.0005).
    train_tft: TrainTft
    run_tft_sweep: RunTftSweep
    # BC modeling (Stage 5.5, Task 26): sweep do GBM (sem persistência, como o do
    # TFT), ledger e índice de runs do cohort, e as fábricas que dependem do
    # caminho do arquivo do cohort (conhecido só depois do parse dos argumentos).
    run_gbm_sweep: RunGbmSweep
    cohort_ledger: CohortProgressLedger
    cohort_run_index: CohortRunIndex
    runtime_probe_for: RuntimeProbeFactory
    confirmatory_cohort_for: Callable[[Path, str], RunConfirmatoryCohort]
    # As colunas de modelagem que o cohort usa em I4 — o `freeze` do CLI usa as
    # MESMAS, deste campo (uma fonte só para as duas impressões digitais).
    modeling_columns: tuple[str, ...]
    # BC evaluation (Stage 6.4, Task 12): o refresh do gold de um cohort.
    refresh_gold: RefreshGold
    # BC evaluation (Stage 6.5, Task 11): o scorecard confirmatório de uma revisão.
    build_confirmatory_scorecard: BuildConfirmatoryScorecard
    # BC inference (Stage 7.1, Task 11): a inferência de um cohort, por arquivo e device
    # (o probe depende do caminho do cohort, como em `confirmatory_cohort_for`).
    run_inference_for: Callable[[Path, str], RunInference]
    # BC modeling (Stage 7.3, Task 10): o cohort de ablação, por arquivo; o device vem do
    # spec (`_SUPPORTED_DEVICES`) e o treinador é o proxy desse device.
    load_ablation_spec: Callable[[Path], "tuple[AblationCohortSpec, CohortSpec]"]
    dump_ablation_spec: Callable[["AblationCohortSpec"], str]
    ablation_cohort_for: Callable[[Path], RunAblationCohort]
    measure_ablation_cost_for: Callable[[Path], MeasureAblationCost]
    # os devices que as fábricas de ablação sabem montar (chaves de `_SUPPORTED_DEVICES`)
    supported_devices: frozenset[str]
    # BC inference (Stage 7.3, Task 20): a atribuição do candidato, por arquivo do cohort
    # confirmatório (o probe depende do caminho); predição sempre no treinador de `cpu`.
    permutation_inference_for: Callable[[Path], RunPermutationInference]


def wire_dependencies(
    settings: Settings | None = None,
    *,
    sentiment_model: SentimentModel | None = None,
    runtime_probe_factory: RuntimeProbeFactory | None = None,
) -> ApplicationDependencies:
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

    `sentiment_model` e `runtime_probe_factory` (Stage 5.5) são os dois pontos de
    injeção do runner do cohort: omitidos, entram o FinBERT lazy e o
    `GitRuntimeEnvironmentProbe` sobre `settings.repo_root`; o e2e injeta fakes
    (sem torch e sem depender do git do processo).
    """
    cfg = settings or get_settings()
    hasher = CanonicalJsonHasher()
    tracker = MlflowTracker(tracking_uri=cfg.mlflow_tracking_uri)
    store = ParquetMedallionStore(data_root=cfg.data_root)

    # BC market_data (Stage 5.5, Task 25): ingestão LOCAL — os fetchers Parquet leem
    # os brutos já baixados sob `data_root` (nenhuma chamada de rede no runner) e os
    # use cases gravam o bronze no MESMO store que o `BuildDataset` lê.
    ingest_candles = IngestCandles(
        fetcher=ParquetRawCandleFetcher(raw_root=cfg.data_root / "raw" / "market" / "candles"),
        store=store,
    )
    ingest_news = IngestNews(
        fetcher=ParquetRawNewsFetcher(raw_root=cfg.data_root / "raw" / "news"),
        store=store,
    )
    ingest_fundamentals = IngestFundamentals(
        fetcher=ParquetFundamentalFetcher(root=cfg.data_root / "processed" / "fundamentals"),
        store=store,
    )

    # BC feature_engineering — 3 adapters + assembler + use case (Stage 3.5, I8).
    indicator_calculator = PandasTaIndicatorCalculator()
    sentiment_model = sentiment_model or _LazyFinbertSentimentModel()
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
        quality_gate_config=DatasetQualityGateConfig(
            max_nan_ratio_per_feature=_DATASET_MAX_NAN_RATIO_PER_FEATURE
        ),
    )

    # BC analytics_store (Stage 4.2, A11): adapter Parquet silver com data_root do
    # Settings + SystemClock injetado (created_at_utc write-time de dim_run, I5/I10).
    analytics_repository = ParquetAnalyticsRepository(data_root=cfg.data_root, clock=SystemClock())

    # BC modeling (Stage 5.2, Task 09): `RunBaselines` com colaboradores REAIS.
    # O splitter recebe SÓ o `TradingCalendar` (o `Hasher` é parâmetro de
    # `split(...)`, repassado pelo use case — concept 5.2 §8); o calendário é
    # materializado UMA vez na janela ampla fixa (F-T1 opção A, constantes acima).
    # `PersistPredictions` e `PersistRunRecord` (issue #68) são os use cases do
    # `analytics_store` sobre o MESMO repositório silver; entram nos use cases de
    # `modeling` pelos ports `PredictionPersister`/`RunRecordPersister` definidos
    # no consumidor e satisfeitos por duck-typing (dono único do `target_timestamp`
    # — ADR 4.3.0001; encapsulamento de `dim_run` — ADR 0.0.0053).
    splitter = WalkForwardSplitter(
        TradingCalendar(
            calendar_provider.sessions(start=_CALENDAR_WINDOW_START, end=_CALENDAR_WINDOW_END)
        )
    )
    run_baselines = RunBaselines(
        store=store,
        splitter=splitter,
        forecaster=_LazyStatsforecastBaselineForecaster(),
        persist_predictions=PersistPredictions(repository=analytics_repository),
        persist_run_record=PersistRunRecord(repository=analytics_repository),
        hasher=hasher,
    )

    # BC modeling (Stage 5.3, Task 06): `TrainGbmQuantile` compartilha o MESMO
    # splitter e o MESMO repositório silver dos baselines (grão e cohort comuns
    # — o comparador H2 persiste no mesmo canal); `PersistPredictions` e
    # `PersistRunRecord` são instâncias próprias, stateless, sobre esse mesmo
    # repositório. O trainer
    # LightGBM entra atrás do proxy lazy (import da lib só no 1º treino).
    train_gbm_quantile = TrainGbmQuantile(
        store=store,
        splitter=splitter,
        trainer=_LazyLightgbmQuantileTrainer(),
        persist_predictions=PersistPredictions(repository=analytics_repository),
        persist_run_record=PersistRunRecord(repository=analytics_repository),
        hasher=hasher,
    )

    # BC modeling (Stage 5.4, Task 14): o candidato compartilha o MESMO splitter,
    # repositório silver e tracker dos comparadores — grão, cohort e canal de
    # emissão comuns. A varredura recebe o mesmo trainer e o mesmo store (para
    # LER o dataset), mas NENHUMA porta de persistência de resultados: o
    # isolamento exploratório/confirmatório é estrutural (ADR 5.4.0005).
    # Stage 7.3: um proxy por device; o candidato, a varredura e a inferência usam o
    # de `cpu` (o caminho confirmatório da 5.4/7.1, intacto).
    tft_trainer_for = _tft_trainer_factory()
    tft_trainer = tft_trainer_for(_TRAINERS_DEVICE)
    train_tft = TrainTft(
        store=store,
        splitter=splitter,
        trainer=tft_trainer,
        persist_predictions=PersistPredictions(repository=analytics_repository),
        persist_run_record=PersistRunRecord(repository=analytics_repository),
        tracker=tracker,
        hasher=hasher,
        artifacts_root=cfg.artifacts_root,
    )
    run_tft_sweep = RunTftSweep(
        store=store,
        splitter=splitter,
        trainer=tft_trainer,
        search=_LazyOptunaSearch(),
        tracker=tracker,
        hasher=hasher,
        artifacts_root=cfg.artifacts_root,
    )

    # BC modeling (Stage 5.5, Task 26): o sweep do GBM espelha o do TFT — mesmo
    # splitter e store, trainer LightGBM lazy, busca própria, NENHUMA porta de
    # persistência (I14). O cohort orquestra os três use cases de treino acima,
    # com o ledger no `artifacts_root` (lock no `data_root`) e o índice de runs
    # sobre o MESMO repositório silver onde eles gravam.
    run_gbm_sweep = RunGbmSweep(
        store=store,
        splitter=splitter,
        trainer=_LazyLightgbmQuantileTrainer(),
        search=_LazyOptunaSearch(),
        tracker=tracker,
        hasher=hasher,
    )
    cohort_ledger = JsonCohortProgressLedger(
        artifacts_root=cfg.artifacts_root, data_root=cfg.data_root
    )
    cohort_run_index = ParquetCohortRunIndex(repository=analytics_repository)
    repo_root = cfg.repo_root

    def git_probe(cohort_path: Path, device: str) -> RuntimeEnvironmentProbe:
        # Resolvido contra o diretório corrente — o MESMO arquivo que o CLI leu —,
        # nunca reinterpretado em relação ao `repo_root`.
        return GitRuntimeEnvironmentProbe(
            repo_root=repo_root, cohort_file=cohort_path.resolve(), device=device
        )

    runtime_probe_for = runtime_probe_factory or git_probe
    observed_feature_set_hash = feature_set_hash()
    columns = modeling_columns()

    def confirmatory_cohort_for(cohort_path: Path, device: str) -> RunConfirmatoryCohort:
        return RunConfirmatoryCohort(
            store=store,
            hasher=hasher,
            clock=SystemClock(),
            ledger=cohort_ledger,
            run_index=cohort_run_index,
            probe=runtime_probe_for(cohort_path, device),
            run_baselines=run_baselines,
            train_gbm=train_gbm_quantile,
            train_tft=train_tft,
            modeling_columns=columns,
            observed_feature_set_hash=observed_feature_set_hash,
            pipeline_version=PIPELINE_VERSION,
            schema_version=_SILVER_SCHEMA_VERSION,
            supported_device=_TRAINERS_DEVICE,
        )

    # BC modeling (Stage 7.3, Task 10): cohort de ablação e piloto. O device é LIDO do
    # spec: o proxy do treinador é o do device (fora do mapa ⇒ `ValueError`, sem torch);
    # a base confirmatória é conferida com o device dos treinadores de hoje (`cpu`).
    load_ablation_spec = ablation_spec_loader(cfg.repo_root, hasher)

    def ablation_train_tft(device: str) -> TrainTft:
        return TrainTft(
            store=store,
            splitter=splitter,
            trainer=tft_trainer_for(device),
            persist_predictions=PersistPredictions(repository=analytics_repository),
            persist_run_record=PersistRunRecord(repository=analytics_repository),
            tracker=tracker,
            hasher=hasher,
            artifacts_root=cfg.artifacts_root,
        )

    def ablation_cohort_for(path: Path) -> RunAblationCohort:
        spec, _ = load_ablation_spec(path)
        train = ablation_train_tft(spec.device)
        return RunAblationCohort(
            store=store,
            hasher=hasher,
            clock=SystemClock(),
            ledger=cohort_ledger,
            run_index=cohort_run_index,
            probe=runtime_probe_for(path, spec.device),
            train_tft=train,
            modeling_columns=columns,
            observed_feature_set_hash=observed_feature_set_hash,
            pipeline_version=PIPELINE_VERSION,
            schema_version=_SILVER_SCHEMA_VERSION,
            base_supported_device=_TRAINERS_DEVICE,
            # o MESMO device com que o proxy do treinador foi montado (`tft_trainer_for`)
            trainer_device=spec.device,
        )

    def measure_ablation_cost_for(path: Path) -> MeasureAblationCost:
        spec, _ = load_ablation_spec(path)
        trainer = tft_trainer_for(spec.device)
        return MeasureAblationCost(
            store=store,
            splitter=splitter,
            trainer=trainer,
            probe=runtime_probe_for(path, spec.device),
            clock=SystemClock(),
            hasher=hasher,
        )

    # BC inference (Stage 7.1, Task 11): resolução e predição a partir do checkpoint com
    # o MESMO splitter, store, hasher, `artifacts_root`, colunas e declarações do cohort
    # (o `run_id` derivado tem de ser o que o treino gravou). O locator é stdlib e entra
    # direto, fora do proxy lazy: resolver não importa torch (ADR 7.1.0004 item 1). O
    # preditor é o MESMO proxy do treino. Nada de `evaluation` entra aqui (CA-10).
    checkpoint_locator = FilesystemCheckpointLocator()
    resolve_tft_checkpoints = ResolveTftCheckpoints(
        store=store,
        hasher=hasher,
        splitter=splitter,
        run_index=cohort_run_index,
        locator=checkpoint_locator,
        artifacts_root=cfg.artifacts_root,
        modeling_columns=columns,
        observed_feature_set_hash=observed_feature_set_hash,
        pipeline_version=PIPELINE_VERSION,
        supported_device=_TRAINERS_DEVICE,
    )
    predict_tft_from_checkpoints = PredictTftFromCheckpoints(
        store=store,
        hasher=hasher,
        splitter=splitter,
        locator=checkpoint_locator,
        predictor=tft_trainer,
        artifacts_root=cfg.artifacts_root,
        modeling_columns=columns,
        observed_feature_set_hash=observed_feature_set_hash,
        pipeline_version=PIPELINE_VERSION,
        supported_device=_TRAINERS_DEVICE,
    )
    inference_manifest = JsonInferenceManifest(data_root=cfg.data_root)

    def run_inference_for(cohort_path: Path, device: str) -> RunInference:
        return RunInference(
            resolver=resolve_tft_checkpoints,
            predictor=predict_tft_from_checkpoints,
            probe=runtime_probe_for(cohort_path, device),
            persister=PersistPredictions(repository=analytics_repository),
            silver=analytics_repository,
            ledger=cohort_ledger,
            manifest=inference_manifest,
            hasher=hasher,
            clock=SystemClock(),
        )

    # BC inference (Stage 7.3, Task 20): a atribuição reusa o resolvedor da 7.1 e prediz
    # com o MESMO proxy de `cpu` do treino e da inferência (o cohort confirmatório é
    # `cpu`, ADR 7.3.0004 item 2), contra a partição da registry (C4 do fornecedor). Os
    # dois escritores do silver de atribuição escrevem no MESMO repositório que o
    # `RunPermutationInference` lê; o manifesto é o da atribuição, ao lado do da 7.1.
    # Nada de `evaluation` entra aqui (I9).
    predict_tft_attribution = PredictTftAttributionFromCheckpoints(
        store=store,
        hasher=hasher,
        splitter=splitter,
        locator=checkpoint_locator,
        predictor=tft_trainer,
        artifacts_root=cfg.artifacts_root,
        modeling_columns=columns,
        observed_feature_set_hash=observed_feature_set_hash,
        pipeline_version=PIPELINE_VERSION,
        supported_device=_TRAINERS_DEVICE,
        registry_partition=registry_family_partition(),
    )

    def permutation_inference_for(cohort_path: Path) -> RunPermutationInference:
        return RunPermutationInference(
            resolver=resolve_tft_checkpoints,
            predictor=predict_tft_attribution,
            probe=runtime_probe_for(cohort_path, _TRAINERS_DEVICE),
            permuted_persister=PersistPermutedPredictions(repository=analytics_repository),
            vsn_persister=PersistVsnWeights(repository=analytics_repository),
            silver=analytics_repository,
            ledger=cohort_ledger,
            manifest=JsonAttributionManifest(data_root=cfg.data_root),
            hasher=hasher,
            clock=SystemClock(),
        )

    # BC evaluation (Stage 6.4, Tasks 12/15): `RefreshGold` sobre o MESMO repositório
    # silver (como `SilverTableReader`, ADR 0.0.0053/6.4.0004); o
    # realizado vem da grade de treino da 5.5 — `ReadTrainingGrid` (real do port
    # `TrainingGridReader`, ADR 6.4.0009) sobre o MESMO store e as MESMAS `columns`
    # do cohort confirmatório, então o índice 0 é a origem do `decision_idx` gravado;
    # o `ReadTrainingGrid` recebe o MESMO hasher e devolve o fingerprint (#128).
    # O `ArchMcs` entra atrás do proxy lazy e o gold vai para `<data_root>/gold/` (ADR
    # 6.4.0005). A ordem dos builders é validada no construtor (C1: falha no wiring).
    gold_store = ParquetGoldStore(cfg.data_root)
    refresh_gold = RefreshGold(
        silver_reader=analytics_repository,
        grid_reader=ReadTrainingGrid(store=store, columns=columns, hasher=hasher),
        clock=SystemClock(),
        mcs_backend=_LazyArchMcs(),
        gold_store=gold_store,
        builders=(
            QualityChecksGoldBuilder(),
            MetricsByRunGoldBuilder(),
            CalibrationTableGoldBuilder(),
            DmResultsGoldBuilder(),
            McsResultsGoldBuilder(),
            # perfis de séries novas (Stage 6.6; fora do veredito — ADR 6.6.0002)
            DmProfilesGoldBuilder(),
            DmSeedFractionGoldBuilder(),
            McsBlockSensitivityGoldBuilder(),
            ChristoffersenMonteCarloGoldBuilder(),
            PartialDegeneracyGoldBuilder(),
            DifferentialAcfGoldBuilder(),
            DifferentialBreaksGoldBuilder(),
            LossDifferentialsGoldBuilder(),
            ConformalCorrectionsGoldBuilder(),
            ConformalCoverageGoldBuilder(),
            # leitura de H3 (Stage 7.3; vazia sem bloco [h3] — ADR 7.3.0001 item 4)
            H3ImportanceGoldBuilder(),
            H3SharesGoldBuilder(),
            H3ReadingGoldBuilder(),
            H3VsnGoldBuilder(),
        ),
        # Stage 7.2 (ADR 7.2.0003 item 3): o real do port do consumidor
        # `ConformalCalibration` é o use case `CalibrateConformal` do inference, puro
        conformal_calibration=CalibrateConformal(),
    )

    # BC evaluation (Stage 6.5, Task 11): o scorecard confirmatório lê a geração viva
    # pelo MESMO `ParquetGoldStore` do refresh (real do port `GoldGenerationReader`,
    # ADR 6.5.0005) e o pré-registro de `<repo_root>/config/preregistration/` (ADR
    # 6.5.0001), com o MESMO hasher que calcula o `preregistration_ref`.
    build_confirmatory_scorecard = BuildConfirmatoryScorecard(
        source=TomlPreregistrationSource(root=cfg.repo_root / "config" / "preregistration"),
        reader=gold_store,
        hasher=hasher,
    )

    return ApplicationDependencies(
        hasher=hasher,
        tracker=tracker,
        store=store,
        ingest_candles=ingest_candles,
        ingest_news=ingest_news,
        ingest_fundamentals=ingest_fundamentals,
        indicator_calculator=indicator_calculator,
        sentiment_model=sentiment_model,
        asof_join=asof_join,
        dataset_assembler=dataset_assembler,
        calendar_provider=calendar_provider,
        build_dataset=build_dataset,
        analytics_repository=analytics_repository,
        run_baselines=run_baselines,
        train_gbm_quantile=train_gbm_quantile,
        train_tft=train_tft,
        run_tft_sweep=run_tft_sweep,
        run_gbm_sweep=run_gbm_sweep,
        cohort_ledger=cohort_ledger,
        cohort_run_index=cohort_run_index,
        runtime_probe_for=runtime_probe_for,
        confirmatory_cohort_for=confirmatory_cohort_for,
        modeling_columns=columns,
        refresh_gold=refresh_gold,
        build_confirmatory_scorecard=build_confirmatory_scorecard,
        run_inference_for=run_inference_for,
        load_ablation_spec=load_ablation_spec,
        dump_ablation_spec=dump_ablation_spec,
        ablation_cohort_for=ablation_cohort_for,
        measure_ablation_cost_for=measure_ablation_cost_for,
        supported_devices=frozenset(_SUPPORTED_DEVICES),
        permutation_inference_for=permutation_inference_for,
    )
