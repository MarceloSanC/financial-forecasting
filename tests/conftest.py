"""Fixtures globais de teste.

Fixtures de escopo `session` são criadas uma vez por execução do pytest — ideal
para recursos caros como engines de banco de dados. Fixtures de escopo padrão
(function) são recriadas a cada teste — ideal para estado que deve ser isolado
entre testes (ex: client HTTP). Use pytest.mark para filtrar suites no CI.

Este arquivo nasce com fixtures genéricas no template. Cada feature deve
adicionar fixtures próprias (CREATE TABLE da entity, factories de DTO, etc.)
em `tests/<categoria>/features/<feature>/conftest.py`.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from financial_forecasting.shared.infrastructure.http.app import create_app


@pytest.fixture(scope="session")
def test_engine() -> Engine:
    """Engine SQLAlchemy em SQLite in-memory para testes de integração.

    Escopo session: o banco é criado uma vez e compartilhado por todos os
    testes de integração. Cada feature deve criar suas próprias tabelas em
    `tests/integration/features/<feature>/conftest.py` (via SQL ou aplicando
    migrations Alembic) — este conftest não conhece o schema de nenhuma feature.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        # SQLite não suporta pool_size/max_overflow
        connect_args={"check_same_thread": False},
    )

    yield engine
    engine.dispose()


@pytest.fixture
async def client() -> AsyncClient:
    """Cliente HTTP assíncrono apontando para a aplicação FastAPI em memória.

    Usa ASGITransport do httpx para fazer requisições sem abrir porta TCP.
    Ideal para testes e2e que precisam testar o ciclo completo HTTP.
    """
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c
