"""Fábrica da aplicação FastAPI.

`create_app()` é o único lugar que monta a aplicação: registra middlewares,
error handlers e routers. Também aciona o composition_root para fazer o wiring
das dependências e registrá-las via dependency_overrides. Usar uma factory
(em vez de um app global) facilita testes: cada teste pode chamar create_app()
com configurações diferentes.

Este arquivo nasce sem routers de feature no template — registre o router de
cada feature em `_register_feature_routers()` conforme as features forem
sendo criadas.

NOTA sobre o diretório `adapters/in/` em features:
O nome `in` é uma keyword do Python, então não pode ser importado diretamente.
Use `importlib.import_module()` para carregar o módulo do router, ou injete o
use case via `FastAPI Depends` a partir do composition_root. Ver
`docs/LAYOUT.md` §5/§8 para o padrão recomendado.
"""

from fastapi import FastAPI

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.shared.infrastructure.config.settings import get_settings
from financial_forecasting.shared.infrastructure.http.error_handlers import register_error_handlers
from financial_forecasting.shared.infrastructure.http.middlewares import register_middlewares


def create_app() -> FastAPI:
    """Cria, configura e retorna a instância FastAPI pronta para uso.

    Ordem de inicialização:
    1. Cria o app FastAPI com metadados das settings
    2. Registra middlewares (CORS, etc.)
    3. Registra error handlers (DomainError → 422, NotFoundError → 404)
    4. Faz o wiring das dependências via composition_root
    5. Registra os routers de cada feature
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    register_middlewares(app)
    register_error_handlers(app)

    deps = wire_dependencies(settings)
    _register_feature_routers(app, deps)

    return app


def _register_feature_routers(app: FastAPI, deps: ApplicationDependencies) -> None:
    """Registra os routers HTTP de cada feature.

    Para cada feature, importe seu router e dê `app.include_router(...)`. Use
    `importlib.import_module()` quando o caminho do módulo contiver o segmento
    `in` (keyword do Python). Template:

        import importlib

        <feature>_router_module = importlib.import_module(
            "financial_forecasting.features.<feature>.adapters.in.http.router"
        )
        app.dependency_overrides[
            <feature>_router_module._get_<use_case>
        ] = lambda: deps.<use_case>
        app.include_router(<feature>_router_module.router, prefix="/api/v1")
    """
    # `deps` é mantido na assinatura para deixar explícito que o registro de
    # routers consome os use cases do composition root. Quando a primeira
    # feature chegar, este parâmetro deixa de estar "não utilizado".
    _ = deps
