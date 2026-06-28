"""Hierarquia base de exceções do sistema.

DomainError: raiz de todos os erros de negócio. Capturado pelo error handler HTTP
e convertido em 422 Unprocessable Entity. Subclasse para criar erros específicos
de cada feature (ex: PaymentNotFoundError, InvalidAmountError).

ApplicationError: erros de orquestração de use case — ex: estado inconsistente
detectado na camada de application, mas não necessariamente uma violação de regra
de domínio. Capturado separadamente se necessário.

NotFoundError: subclasse de DomainError para entidades inexistentes. Convertido
em 404 Not Found pelo error handler HTTP.
"""


class DomainError(Exception):
    """Erro de negócio — representa uma violação de regra de domínio."""


class ApplicationError(Exception):
    """Erro de aplicação — representa um erro de orquestração de use case."""


class NotFoundError(DomainError):
    """Entidade não encontrada — convertida em HTTP 404."""
