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

# Testes que leem (ou escrevem temporariamente) a árvore REAL de `src/`: a
# injeção de violação em `test_import_contracts.py` grava módulos-probe em
# `src/` e os gates de layout/port-coverage/fake-parity varrem a mesma árvore.
# Em workers paralelos um enxergaria a injeção do outro — ficam num worker só.
_REAL_SRC_TREE_DIR = "architecture"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Agrupa os testes para o `--dist loadgroup` do pytest-xdist (ADR 0.0.0055).

    - `tests/architecture/**` → um grupo só (compartilham a árvore real de `src/`);
    - demais → um grupo por arquivo, a semântica de `--dist loadfile`: fixtures
      module-scoped caras (ex.: o treino real do TFT) rodam uma vez, não por worker.

    `tryfirst` porque o xdist lê o marker no seu próprio `modifyitems`. Sem xdist
    o marker é inerte.
    """
    for item in items:
        if item.get_closest_marker("xdist_group") is not None:
            continue
        parts = item.path.parts
        in_real_tree = "tests" in parts and _REAL_SRC_TREE_DIR in parts
        # nodeid até o `::` = caminho relativo do arquivo (sufixo legível no -v)
        group = "real-src-tree" if in_real_tree else item.nodeid.split("::", 1)[0]
        item.add_marker(pytest.mark.xdist_group(name=group))


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
