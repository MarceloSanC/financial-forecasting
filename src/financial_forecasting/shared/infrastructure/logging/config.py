"""Configuração de logging da aplicação.

`configure_logging()` deve ser chamada uma vez, no início da aplicação (ex: em
create_app() ou main.py). Usa logging padrão da stdlib para manter compatibilidade
universal; em produção, considere estruturar os logs em JSON (ex: python-json-logger)
para facilitar ingestão em Datadog, CloudWatch ou ELK.
"""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configura o logging global da aplicação.

    Args:
        level: nível de log como string ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
               Padrão: "INFO". Valores inválidos fazem fallback para INFO.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        # Formato: timestamp  NÍVEL  nome_do_logger  mensagem
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # Reduz verbosidade de libs barulhentas
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
