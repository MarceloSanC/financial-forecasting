"""Configuração de ambiente do Alembic.

Este arquivo é executado pelo Alembic em todas as operações (migrate, revision, etc.).
Lê a DATABASE_URL das Settings do projeto em vez do alembic.ini, garantindo que
o mesmo arquivo .env usado pela aplicação seja usado pelas migrations. Suporta
tanto o modo offline (gera SQL sem conectar) quanto o modo online (executa no banco).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa as Settings do projeto para ler DATABASE_URL do .env
from financial_forecasting.shared.infrastructure.config.settings import get_settings

# Objeto de configuração do Alembic — acessa valores do alembic.ini
config = context.config

# Sobrescreve sqlalchemy.url com o valor real das Settings
# Garante que o mesmo .env da aplicação é usado nas migrations
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Configura logging conforme definido no alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData para autogenerate — adicione os modelos SQLAlchemy aqui quando usar ORM
# from financial_forecasting.shared.infrastructure.database.models import Base
# target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Executa migrations em modo offline (gera SQL sem conexão com o banco).

    Útil para revisar as queries antes de aplicar em produção, ou para
    ambientes sem acesso direto ao banco.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrations em modo online (conecta ao banco e aplica imediatamente).

    Modo padrão para `alembic upgrade head`. Usa NullPool em vez do pool padrão
    para evitar problemas com migrações em ambientes de CI/CD.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
