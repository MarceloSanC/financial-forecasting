"""Fábrica de Engine SQLAlchemy.

`build_engine()` cria o pool de conexões configurado para produção: pool_pre_ping
detecta conexões mortas antes de usá-las; pool_size e max_overflow controlam
a concorrência. Em testes de integração, substitua database_url por SQLite
in-memory para isolar o banco sem precisar de PostgreSQL rodando.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from financial_forecasting.shared.infrastructure.config.settings import get_settings


def build_engine(database_url: str | None = None) -> Engine:
    """Cria e retorna um Engine SQLAlchemy configurado.

    Args:
        database_url: URL de conexão. Se None, usa settings.database_url.
                      Passe explicitamente em testes para usar SQLite.

    Returns:
        Engine com pool de conexões pronto para uso.
    """
    url = database_url or get_settings().database_url

    # pool_pre_ping=True: verifica a conexão antes de entregá-la ao código
    # pool_size=5: conexões mantidas abertas no pool (ajuste para produção)
    # max_overflow=10: conexões extras além do pool_size em picos de carga
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
