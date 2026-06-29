"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB, MlflowTracker → outro
tracker), mude APENAS aqui. Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/out/`. Sempre receba dependências via construtor (injeção explícita).
Os campos de `ApplicationDependencies` são tipados pelos PORTS (`ExperimentTracker`,
`Hasher`), não pelos concretos — wiring centralizado, contrato exposto.
"""

from dataclasses import dataclass

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.mlflow.mlflow_tracker import MlflowTracker
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.application.ports.out.experiment_tracker import (
    ExperimentTracker,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings, get_settings


@dataclass
class ApplicationDependencies:
    """Contêiner com as dependências montadas e prontas para uso.

    Exponha aqui apenas o que as camadas superiores (use cases, adapters
    primários) precisam. Os campos são tipados pelos PORTS — os concretos
    (`CanonicalJsonHasher`, `MlflowTracker`) são detalhe do wiring abaixo.

    Adicione campos conforme as features forem criadas (use cases, etc.).
    """

    hasher: Hasher
    tracker: ExperimentTracker
    store: MedallionStore


def wire_dependencies(settings: Settings | None = None) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e retorna o contêiner pronto.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode ser chamado com um `Settings` fake apontando o
    `mlflow_tracking_uri` para um SQLite em `tmp_path` (sem depender do
    `lru_cache` global de `get_settings`).

    Resolve `cfg = settings or get_settings()` e instancia os concretos AQUI
    (único lugar): `CanonicalJsonHasher` (1.4), `MlflowTracker(
    cfg.mlflow_tracking_uri)` (1.5) e `ParquetMedallionStore(cfg.data_root)`
    (2.1). `ApplicationDependencies.store` é tipado pelo PORT `MedallionStore`,
    não pelo concreto (I9).
    """
    cfg = settings or get_settings()
    hasher = CanonicalJsonHasher()
    tracker = MlflowTracker(tracking_uri=cfg.mlflow_tracking_uri)
    store = ParquetMedallionStore(data_root=cfg.data_root)
    return ApplicationDependencies(hasher=hasher, tracker=tracker, store=store)
