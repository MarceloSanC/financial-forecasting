"""Handlers de erro HTTP globais.

Converte exceções de domínio em respostas HTTP adequadas, mantendo o domínio
isolado do protocolo HTTP, com o corpo de erro do projeto `{"detail", "type"}`:

- `NotFoundError` → 404 `not_found` (registrado antes do `DomainError`, mais genérico);
- `DomainError` → 422 `domain_error`;
- `ApplicationError` → 500 `application_error` (Stage 7.4, ADR 7.4.0002 item 5): estado
  inconsistente detectado na orquestração (gold corrompido, silver inconsistente,
  serviço sem cohort configurado). Sem ele o FastAPI responderia 500 em texto puro.
  As hierarquias são disjuntas (`ApplicationError` não é `DomainError`), então a
  ordem de registro não importa.

A validação de corpo segue o 422 padrão do FastAPI (`{"detail": [...]}`, lista).

Regra: adicione um handler aqui para cada nova hierarquia de exceção que precise
de tratamento HTTP específico. Nunca coloque lógica de negócio nos handlers.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.exceptions.base import (
    DomainError,
    NotFoundError,
)


def register_error_handlers(app: FastAPI) -> None:
    """Registra todos os exception handlers na aplicação FastAPI."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        """NotFoundError → 404 Not Found."""
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "type": "not_found"},
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        """DomainError genérico → 422 Unprocessable Entity."""
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "domain_error"},
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        """ApplicationError → 500 Internal Server Error, com o corpo do projeto."""
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": "application_error"},
        )
