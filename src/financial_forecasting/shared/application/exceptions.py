"""Exceções de aplicação compartilhadas (orquestração, não regra de negócio).

Saíram de `shared/domain/exceptions/base.py` na issue #69 (a): o domínio não deve
depender de lógica de aplicação que não é regra de negócio (Evans, LAYERED
ARCHITECTURE). Colisão de chave é fato de persistência/orquestração, não de
negócio — por isso `DuplicateKeyError` mora aqui, ao lado de `ApplicationError`.

ApplicationError: erros de orquestração de use case — ex: estado inconsistente
detectado na camada de application, mas não necessariamente uma violação de regra
de domínio. Capturado separadamente se necessário.

DuplicateKeyError: subclasse de ApplicationError para colisão de chave primária
lógica em write append-only sem overwrite (storage medalhão, Stage 2.1).
"""


class ApplicationError(Exception):
    """Erro de aplicação — representa um erro de orquestração de use case."""


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
