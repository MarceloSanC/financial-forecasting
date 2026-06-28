"""Entrypoint da aplicação — inicia o servidor HTTP.

Este módulo é o ponto de entrada ASGI. Ele cria a instância do FastAPI via
`create_app()` (definida em shared/infrastructure/http/app.py) e a expõe como
`app` para que uvicorn possa encontrá-la. Em produção, nunca importe este módulo
diretamente — use `uvicorn financial_forecasting.main:app`.
"""

import uvicorn

from financial_forecasting.shared.infrastructure.http.app import create_app

app = create_app()

if __name__ == "__main__":
    # Execução direta para debug local: python -m financial_forecasting.main
    # Em produção, prefira: uvicorn financial_forecasting.main:app --workers 4
    uvicorn.run("financial_forecasting.main:app", host="0.0.0.0", port=8000, reload=False)
