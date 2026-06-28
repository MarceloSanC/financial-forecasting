"""Implementação concreta do port IdGenerator usando UUID v4.

Uuid4Generator satisfaz o Protocol IdGenerator sem herança explícita.
UUID v4 é aleatório — adequado para IDs de entidades de domínio. Se precisar
de IDs ordenados no tempo (ex: para queries de range), considere ULID ou UUID v7.
Use cases nunca importam este módulo diretamente — recebem IdGenerator via construtor.
"""

import uuid


class Uuid4Generator:
    """Gerador de IDs baseado em UUID versão 4 (aleatório)."""

    def next_id(self) -> uuid.UUID:
        """Gera e retorna um novo UUID v4 único."""
        return uuid.uuid4()
