"""Hierarquia base de exceções do domínio.

DomainError: raiz de todos os erros de negócio. Capturado pelo error handler HTTP
e convertido em 422 Unprocessable Entity. Subclasse para criar erros específicos
de cada feature (ex: PaymentNotFoundError, InvalidAmountError).

NotFoundError: subclasse de DomainError para entidades inexistentes. Convertido
em 404 Not Found pelo error handler HTTP. Fica no domínio: "a entidade X não
existe" é fato do modelo, não da orquestração (issue #69 a).

`ApplicationError` e `DuplicateKeyError` (orquestração/persistência) moram em
`shared/application/exceptions.py` desde a issue #69 (a).
"""


class DomainError(Exception):
    """Erro de negócio — representa uma violação de regra de domínio."""


class NotFoundError(DomainError):
    """Entidade não encontrada — convertida em HTTP 404."""
