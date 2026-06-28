"""Port compartilhado: IdGenerator.

Abstrai a geração de IDs únicos para tornar use cases testáveis: em testes,
injete um FakeIdGenerator com UUIDs pré-determinados; em produção, use
Uuid4Generator. Qualquer feature que precise gerar IDs importa este Protocol
— nunca chama uuid.uuid4() diretamente em use cases.
"""

from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    """Contrato para geração de identificadores únicos."""

    def next_id(self) -> UUID:
        """Gera e retorna um novo UUID único."""
        ...
