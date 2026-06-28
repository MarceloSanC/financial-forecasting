"""Handlers de erro HTTP globais.

Converte exceções de domínio em respostas HTTP adequadas, mantendo o domínio
isolado do protocolo HTTP. O handler mais específico (NotFoundError) é registrado
antes do mais genérico (DomainError) para que FastAPI use o correto. ApplicationError
pode ser adicionado com status 500 se necessário.

Regra: adicione um handler aqui para cada nova hierarquia de exceção que precise
de tratamento HTTP específico. Nunca coloque lógica de negócio nos handlers.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from financial_forecasting.shared.domain.exceptions.base import DomainError, NotFoundError


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
