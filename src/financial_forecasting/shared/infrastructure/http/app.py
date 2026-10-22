"""Fábrica da aplicação FastAPI.

`create_app()` é o único lugar que monta a aplicação: registra middlewares,
error handlers e routers. Também aciona o composition_root para fazer o wiring
das dependências. Usar uma factory (em vez de um app global) facilita testes:
cada teste pode chamar `create_app(settings)` com configurações diferentes.

Routers de feature (Stage 7.4): o registro é delegado a
`composition_root.register_http_routes`, que carrega cada router por
`importlib` (o segmento `adapters/in/` é keyword do Python, LAYOUT §8), troca o
provedor do use case por `dependency_overrides` e inclui o router. Assim o
`shared/http` importa só a composition root, nunca uma feature (contrato
`shared-no-features`; LAYOUT §6).
"""

from fastapi import FastAPI

from financial_forecasting.composition_root import (
    ApplicationDependencies,
    register_http_routes,
    wire_dependencies,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings, get_settings
from financial_forecasting.shared.infrastructure.http.error_handlers import register_error_handlers
from financial_forecasting.shared.infrastructure.http.middlewares import register_middlewares


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria, configura e retorna a instância FastAPI pronta para uso.

    Ordem de inicialização:
    1. Cria o app FastAPI com metadados das settings (as injetadas ou as do ambiente)
    2. Registra middlewares (CORS, etc.)
    3. Registra error handlers (NotFoundError → 404, DomainError → 422,
       ApplicationError → 500)
    4. Faz o wiring das dependências via composition_root
    5. Registra os routers de cada feature (com cohort configurado, o use case da
       API de inferência é montado aqui, uma vez, na subida)
    """
    cfg = settings if settings is not None else get_settings()

    app = FastAPI(
        title=cfg.app_name,
        debug=cfg.debug,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    register_middlewares(app)
    register_error_handlers(app)

    deps = wire_dependencies(cfg)
    _register_feature_routers(app, deps, cfg)

    return app


def _register_feature_routers(app: FastAPI, deps: ApplicationDependencies, cfg: Settings) -> None:
    """Registra os routers HTTP das features pela composition root."""
    register_http_routes(app, deps, serving_cohort_file=cfg.serving_cohort_file)
