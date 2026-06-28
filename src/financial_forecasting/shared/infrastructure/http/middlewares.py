"""Registro de middlewares FastAPI.

Centraliza a configuração de middlewares para manter create_app() limpo.
Adicione novos middlewares aqui: autenticação, rate limiting, request ID, etc.
A ordem de registro importa: middlewares são executados de baixo para cima
(o último registrado é o primeiro a processar a requisição).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def register_middlewares(app: FastAPI) -> None:
    """Registra todos os middlewares na aplicação FastAPI.

    Configuração atual:
    - CORS: permite todas as origens (ajuste para produção com lista explícita)
    """
    # CORS — em produção, substitua allow_origins=["*"] pela lista de domínios reais
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],        # FIXME: restringir em produção
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
