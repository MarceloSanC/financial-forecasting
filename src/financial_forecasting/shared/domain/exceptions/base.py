"""Hierarquia base de exceções do sistema.

DomainError: raiz de todos os erros de negócio. Capturado pelo error handler HTTP
e convertido em 422 Unprocessable Entity. Subclasse para criar erros específicos
de cada feature (ex: PaymentNotFoundError, InvalidAmountError).

ApplicationError: erros de orquestração de use case — ex: estado inconsistente
detectado na camada de application, mas não necessariamente uma violação de regra
de domínio. Capturado separadamente se necessário.

NotFoundError: subclasse de DomainError para entidades inexistentes. Convertido
em 404 Not Found pelo error handler HTTP.

DuplicateKeyError: subclasse de ApplicationError para colisão de chave primária
lógica em write append-only sem overwrite (storage medalhão, Stage 2.1).
"""


class DomainError(Exception):
    """Erro de negócio — representa uma violação de regra de domínio."""


class ApplicationError(Exception):
    """Erro de aplicação — representa um erro de orquestração de use case."""


class NotFoundError(DomainError):
    """Entidade não encontrada — convertida em HTTP 404."""


class DuplicateKeyError(ApplicationError):
    """Colisão de chave primária lógica em write append-only sem ``overwrite``.

    Levantada pelo `MedallionStore` (port-out, Stage 2.1) quando um `write`
    append-only recebe linhas cuja PK lógica já existe na partição alvo e
    `overwrite=False`. É erro de **orquestração/estado** (não violação de regra
    de negócio pura nem erro de I/O), por isso é `ApplicationError` — não
    `DomainError` nem `ValueError` cru (concept 2.1 D5).

    A mensagem (citando `(layer, table)`, colunas de PK e amostra das colisões)
    é montada por quem levanta (o adapter `ParquetMedallionStore` ou o
    `FakeMedallionStore`), que assim expõem o MESMO tipo observável ao contract
    test. Stdlib-only — o port permanece agnóstico de `pandas`.
    """
