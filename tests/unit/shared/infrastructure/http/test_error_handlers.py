"""Unit dos handlers globais de erro HTTP (Stage 7.4, Task 05) — concept D11; CA7, CA8 (formato).

App FastAPI mínima com `register_error_handlers` e rotas que erguem cada hierarquia;
`raise_server_exceptions=False` para ver a resposta que o cliente recebe.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from financial_forecasting.shared.application.exceptions import (
    ApplicationError,
    DuplicateKeyError,
)
from financial_forecasting.shared.domain.exceptions.base import DomainError, NotFoundError
from financial_forecasting.shared.infrastructure.http.error_handlers import (
    register_error_handlers,
)

pytestmark = pytest.mark.unit


class _Body(BaseModel):
    value: int


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    def not_found() -> None:
        raise NotFoundError("não há dados para o pedido solicitado: ativo 'X'")

    @app.get("/domain")
    def domain() -> None:
        raise DomainError("regra violada")

    @app.get("/application")
    def application() -> None:
        raise ApplicationError("geração gold corrompida")

    @app.get("/application-subclass")
    def application_subclass() -> None:
        raise DuplicateKeyError("chave repetida")

    @app.post("/body")
    def body(payload: _Body) -> dict[str, int]:
        return {"value": payload.value}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("path", "status", "body"),
    [
        (
            "/not-found",
            404,
            {"detail": "não há dados para o pedido solicitado: ativo 'X'", "type": "not_found"},
        ),
        ("/domain", 422, {"detail": "regra violada", "type": "domain_error"}),
        ("/application", 500, {"detail": "geração gold corrompida", "type": "application_error"}),
        ("/application-subclass", 500, {"detail": "chave repetida", "type": "application_error"}),
    ],
)
def test_project_errors_map_to_status_and_body(
    path: str, status: int, body: dict[str, str]
) -> None:
    response = _client().get(path)
    assert response.status_code == status
    assert response.json() == body


def test_body_validation_keeps_the_fastapi_default_list_body() -> None:
    response = _client().post("/body", json={"value": "não é número"})
    assert response.status_code == 422  # noqa: PLR2004
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "value"]
    assert "type" not in response.json()


def test_application_error_is_logged_with_its_traceback(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="financial_forecasting.shared.infrastructure.http"):
        response = _client().get("/application")
    assert response.status_code == 500  # noqa: PLR2004
    (record,) = (r for r in caplog.records if r.name.endswith("error_handlers"))
    assert record.levelno == logging.ERROR
    assert "GET /application" in record.getMessage()
    assert "geração gold corrompida" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is ApplicationError


def test_not_found_is_not_logged_as_error(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="financial_forecasting.shared.infrastructure.http"):
        _client().get("/not-found")
    assert not [r for r in caplog.records if r.name.endswith("error_handlers")]
