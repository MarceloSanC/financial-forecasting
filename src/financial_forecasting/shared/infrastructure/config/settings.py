"""Configuração da aplicação via pydantic-settings.

Lê variáveis de ambiente e/ou arquivo .env automaticamente. Campos com valores
padrão permitem que a aplicação inicie sem .env (útil em testes). Em produção,
sempre defina DATABASE_URL, SECRET_KEY e DEBUG=false via variáveis de ambiente
— nunca commite um .env com credenciais reais.

Uso em qualquer módulo:
    from financial_forecasting.shared.infrastructure.config.settings import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do ambiente ou do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Ignora variáveis de ambiente extras não declaradas aqui
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------
    app_name: str = "financial_forecasting"
    debug: bool = False  # Em produção: DEBUG=false

    # ---------------------------------------------------------------------------
    # Database
    # ---------------------------------------------------------------------------
    # Formato: postgresql://usuario:senha@host:porta/banco
    # Em testes: pode ser sobrescrito para sqlite:///./test.db
    database_url: str = "postgresql://user:pass@localhost:5432/financial_forecasting"

    # ---------------------------------------------------------------------------
    # Server
    # ---------------------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000

    # ---------------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------------
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # ---------------------------------------------------------------------------
    # MLflow / Experiment tracking
    # ---------------------------------------------------------------------------
    # Backend store do MLflow (ADR 1.5.0001). Default relativo `sqlite:///mlruns.db`
    # mantém o tracking junto ao repo/worktree, sem servidor remoto nem SaaS.
    # Trocável por env (`MLFLOW_TRACKING_URI`) para Postgres/servidor sem tocar
    # código. Em testes, usa-se `sqlite:///<tmp_path>/mlruns.db` para isolamento.
    mlflow_tracking_uri: str = "sqlite:///mlruns.db"

    # ---------------------------------------------------------------------------
    # Medallion storage (Stage 2.1)
    # ---------------------------------------------------------------------------
    # Raiz dos dados medalhão (bronze/silver/gold). O `ParquetMedallionStore`
    # recebe este `data_root` e aplica o sufixo `bronze/<table>/...` por dentro
    # (concept 2.1 D4). Default relativo `data/` mantém os dados junto ao
    # repo/worktree. Override por env (`DATA_ROOT`) sem tocar código (12-factor);
    # em testes, aponta para `tmp_path` para isolamento.
    data_root: Path = Path("data")


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância singleton de Settings.

    O cache é mantido pelo functools.lru_cache do Python — uma única instância
    por processo. Em testes, sobrescreva via:

        from financial_forecasting.shared.infrastructure.config.settings import (
            Settings,
            get_settings,
        )

        get_settings.cache_clear()
        # então monkeypatch ou substitua via dependency_overrides do FastAPI
    """
    return Settings()
