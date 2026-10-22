"""Integração do router `POST /inference/run` (Stage 7.4, Task 06) — CA4, CA8, CA11 (parte).

App FastAPI mínima com `register_error_handlers`, o router e `dependency_overrides`
para um use case de teste que registra a consulta e devolve um payload fixo (ou
ergue). O pacote do router está sob `adapters/in/` (keyword): `importlib`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import math
from datetime import date
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    OK,
    UNAVAILABLE,
    H3ReadingRecord,
    H3ShareRecord,
    VsnRecord,
)
from financial_forecasting.features.inference.application.use_cases.serve_inference import (
    ConformalBlock,
    ConformalInterval,
    ExplainabilityBlock,
    GoldProvenance,
    HorizonForecast,
    InferencePayload,
    SeedForecast,
    ServeInferenceQuery,
)
from financial_forecasting.features.inference.domain.exceptions.serving import (
    NoServedDataError,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.infrastructure.http.error_handlers import (
    register_error_handlers,
)

pytestmark = pytest.mark.integration

_ROUTER: ModuleType = importlib.import_module(
    "financial_forecasting.features.inference.adapters.in.http.inference_router"
)
_SPLIT = "split_cqr_asymmetric_unweighted_v1"
_DAY = date(2024, 3, 15)


def _interval(
    lo: float, hi: float, status: str, lower: float | None, upper: float | None
) -> ConformalInterval:
    gold_status = OK if status == OK else "undefined"
    reason = None if status == OK else "n < 1/alpha"
    return ConformalInterval(lo, hi, status, gold_status, reason, lower, upper)


def _payload() -> InferencePayload:
    intervals = (
        _interval(0.02, 0.98, OK, -math.inf, math.inf),
        _interval(0.1, 0.9, OK, -0.035, math.inf),
        _interval(0.25, 0.75, OK, 0.0078125, -0.0078125),  # cruzado
        _interval(0.3, 0.7, UNAVAILABLE, None, None),
    )
    member = SeedForecast(
        seed=1,
        fold="4",
        run_id="run-1",
        quantiles=(-0.03, -0.01, 0.0, 0.01, 0.03),
        conformal=ConformalBlock(AVAILABLE, None, "rótulo c", _SPLIT, intervals),
    )
    shares = (
        H3ShareRecord(
            "permutation",
            "price",
            0.4,
            0.3,
            -0.1,
            -0.2,
            math.inf,
            0.9,
            1,
            False,
            OK,
            None,
        ),
        H3ShareRecord(
            "ablation",
            "price",
            0.4,
            0.3,
            -0.1,
            -math.inf,
            0.05,
            0.9,
            -1,
            False,
            OK,
            None,
        ),
        H3ShareRecord(
            "ablation",
            "technical",
            0.1,
            0.2,
            0.1,
            -0.5,
            None,
            0.9,
            0,
            None,
            "undefined",
            "Σ* <= 0",
        ),
        H3ShareRecord(
            "permutation",
            "technical",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "undefined",
            "método indefinido",
        ),
    )
    reading = H3ReadingRecord("regra", True, False, False, ("price",), 1505, OK, None)
    vsn = (VsnRecord("family", "price", "price", 0.1, 0.2, 0.3, 1505, OK, None),)
    return InferencePayload(
        asset="AAPL",
        decision_date=_DAY,
        cohort_id="cohort-r0-abc",
        model_version="tft_quantile",
        quantile_levels=(0.1, 0.25, 0.5, 0.75, 0.9),
        forecasts=(HorizonForecast(1, date(2024, 3, 18), (member,)),),
        explainability=ExplainabilityBlock(
            AVAILABLE, None, "rótulo h3", shares, reading, vsn, "rótulo vsn"
        ),
        gold=GoldProvenance(True, "COMPLETED", "ref-r3", "tft_quantile", "2026-10-21T12:00:00"),
    )


class _StubServeInference:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.queries: list[ServeInferenceQuery] = []
        self._error = error

    def __call__(self, query: ServeInferenceQuery) -> InferencePayload:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return _payload()


def _client(stub: _StubServeInference | None = None) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(_ROUTER.router)
    if stub is not None:

        def provider() -> _StubServeInference:
            return stub

        app.dependency_overrides[_ROUTER.get_serve_inference] = provider
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    response = client.post("/inference/run", json=body)
    return response.status_code, response.json()


# --- CA8: o pedido vira a consulta tipada ----------------------------------------------


def test_request_becomes_a_typed_query() -> None:
    stub = _StubServeInference()
    status, _ = _post(
        _client(stub),
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": [1, 7], "seeds": [2, 1]},
    )
    assert status == 200  # noqa: PLR2004
    assert stub.queries == [ServeInferenceQuery("AAPL", _DAY, (1, 7), (2, 1))]


def test_omitted_lists_become_none() -> None:
    stub = _StubServeInference()
    _post(_client(stub), {"asset": "AAPL", "decision_date": "2024-03-15"})
    assert stub.queries == [ServeInferenceQuery("AAPL", _DAY, None, None)]


@pytest.mark.parametrize(
    "body",
    [
        {"asset": "AAPL", "decision_date": "15/03/2024"},
        {"asset": "AAPL", "decision_date": "2024-02-30"},
        {"asset": "AAPL", "decision_date": 1710460800},
        {"asset": "AAPL", "decision_date": "1710460800"},
        {"asset": "AAPL", "decision_date": "2024-03-15T00:00:00"},
        {"asset": "AAPL", "decision_date": "20240315"},
        {"asset": "AAPL", "decision_date": "2024-W11-5"},
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": [0]},
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": [-1, 1]},
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": []},
        {"asset": "AAPL", "decision_date": "2024-03-15", "seeds": []},
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": [1, 1]},
        {"asset": "AAPL", "decision_date": "2024-03-15", "seeds": [3, 3]},
        {"asset": "AAPL", "decision_date": "2024-03-15", "horizons": [True]},
        {"asset": "", "decision_date": "2024-03-15"},
        {"decision_date": "2024-03-15"},
    ],
    ids=[
        "malformed-date",
        "impossible-date",
        "numeric-date",
        "numeric-text-date",
        "datetime-text",
        "basic-iso-date",
        "iso-week-date",
        "zero-horizon",
        "negative-horizon",
        "empty-horizons",
        "empty-seeds",
        "repeated-horizons",
        "repeated-seeds",
        "boolean-horizon",
        "empty-asset",
        "missing-asset",
    ],
)
def test_invalid_request_is_a_422_with_the_fastapi_list_body(body: dict[str, object]) -> None:
    stub = _StubServeInference()
    status, response = _post(_client(stub), body)
    assert status == 422  # noqa: PLR2004
    assert isinstance(response["detail"], list)
    assert stub.queries == []  # o use case não é chamado


# --- CA8: erros dos handlers globais ---------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status", "kind"),
    [
        (NoServedDataError("ativo 'MSFT'"), 404, "not_found"),
        (ApplicationError("silver inconsistente"), 500, "application_error"),
    ],
)
def test_errors_come_from_the_global_handlers(error: Exception, status: int, kind: str) -> None:
    code, body = _post(
        _client(_StubServeInference(error=error)), {"asset": "AAPL", "decision_date": "2024-03-15"}
    )
    assert (code, body) == (status, {"detail": str(error), "type": kind})


def test_without_override_the_route_answers_500_not_configured() -> None:
    code, body = _post(_client(), {"asset": "AAPL", "decision_date": "2024-03-15"})
    assert (code, body) == (
        500,
        {"detail": "serviço de inferência sem cohort configurado", "type": "application_error"},
    )


def test_router_catches_no_exception() -> None:
    tree = ast.parse(inspect.getsource(_ROUTER))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Try | ast.TryStar)]


# --- CA4: resposta com schema_version e os pares (valor, flag) ------------------------


def _ok_response() -> dict[str, object]:
    status, body = _post(
        _client(_StubServeInference()), {"asset": "AAPL", "decision_date": "2024-03-15"}
    )
    assert status == 200  # noqa: PLR2004
    return body


def test_response_carries_schema_version_and_the_payload() -> None:
    body = _ok_response()
    assert body["schema_version"] == 1
    assert (body["asset"], body["decision_date"], body["cohort_id"], body["model_version"]) == (
        "AAPL",
        "2024-03-15",
        "cohort-r0-abc",
        "tft_quantile",
    )
    (forecast,) = body["forecasts"]
    assert forecast["target_date"] == "2024-03-18"
    (member,) = forecast["members"]
    assert (member["seed"], member["fold"], member["run_id"]) == (1, "4", "run-1")
    assert member["quantiles"] == [-0.03, -0.01, 0.0, 0.01, 0.03]
    assert member["conformal"]["label"] == "rótulo c"
    explainability = body["explainability"]
    assert (explainability["label"], explainability["vsn_label"]) == ("rótulo h3", "rótulo vsn")
    assert explainability["reading"]["agreeing_families"] == ["price"]
    assert body["gold"] == {
        "published": True,
        "generation_status": "COMPLETED",
        "preregistration_ref": "ref-r3",
        "candidate": "tft_quantile",
        "finished_at": "2026-10-21T12:00:00",
    }


def test_conformal_limits_follow_the_value_flag_rule() -> None:
    body = _ok_response()
    intervals = body["forecasts"][0]["members"][0]["conformal"]["intervals"]
    pairs = [(i["lower"], i["lower_infinite"], i["upper"], i["upper_infinite"]) for i in intervals]
    assert pairs == [
        (None, True, None, True),  # -inf e +inf
        (-0.035, False, None, True),  # finito e +inf
        (0.0078125, False, -0.0078125, False),  # cruzado, servido como está
        (None, False, None, False),  # unavailable: sem valor
    ]


def test_share_limits_follow_the_value_flag_rule() -> None:
    body = _ok_response()
    shares = body["explainability"]["shares"]
    pairs = [(s["lower"], s["lower_infinite"], s["upper"], s["upper_infinite"]) for s in shares]
    assert pairs == [
        (-0.2, False, None, True),
        (None, True, 0.05, False),
        (-0.5, False, None, False),  # não-ok com limite finito gravado: número + false
        (None, False, None, False),  # sem valor
    ]


def test_share_side_is_the_integer_sign_of_delta() -> None:
    shares = _ok_response()["explainability"]["shares"]
    assert [s["side"] for s in shares] == [1, -1, 0, None]


def test_no_other_value_flag_pair_is_emitted() -> None:
    body = _ok_response()
    intervals = body["forecasts"][0]["members"][0]["conformal"]["intervals"]
    shares = body["explainability"]["shares"]
    for record in [*intervals, *shares]:
        for side in ("lower", "upper"):
            value, flag = record[side], record[f"{side}_infinite"]
            assert isinstance(flag, bool)
            assert not (value is not None and flag)  # nunca número com flag true
            if value is not None:
                assert math.isfinite(value)
