"""Value object Pagination — parâmetros de paginação para queries de listagem.

Imutável e auto-validado: page >= 1, page_size entre 1 e MAX_PAGE_SIZE. A
property `offset` calcula o deslocamento SQL automaticamente. Usado por use
cases de listagem em qualquer feature — é genuinamente transversal, portanto
vive em shared/domain/.
"""

from dataclasses import dataclass

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Pagination:
    """Parâmetros de paginação para listagens.

    Attributes:
        page: número da página (base 1).
        page_size: quantidade de registros por página (máximo MAX_PAGE_SIZE).
    """

    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError(f"page deve ser >= 1, recebido: {self.page}")
        if not (1 <= self.page_size <= MAX_PAGE_SIZE):
            raise ValueError(
                f"page_size deve estar entre 1 e {MAX_PAGE_SIZE}, "
                f"recebido: {self.page_size}"
            )

    @property
    def offset(self) -> int:
        """Deslocamento SQL equivalente: (page - 1) * page_size."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias para page_size — legibilidade em queries SQL."""
        return self.page_size
