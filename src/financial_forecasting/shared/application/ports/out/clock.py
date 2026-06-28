"""Port compartilhado: Clock.

Abstrai o acesso ao tempo atual para tornar use cases testáveis: em testes,
injete um FakeClock com timestamps fixos; em produção, use SystemClock.
Use cases nunca chamam datetime.now() diretamente — sempre recebem Clock via
construtor e chamam clock.now(). Isso elimina dependências de tempo nos testes.
"""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Contrato para obter o timestamp atual."""

    def now(self) -> datetime:
        """Retorna o timestamp atual com timezone (UTC recomendado)."""
        ...
