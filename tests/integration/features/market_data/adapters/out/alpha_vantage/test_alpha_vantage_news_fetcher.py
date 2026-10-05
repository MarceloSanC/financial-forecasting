"""Teste de integração do `AlphaVantageNewsFetcher` — SEM rede (concept 2.3 I13/A8/A10).

Injeta um cliente `httpx` FALSO (`_FakeClient`) devolvendo fixtures JSON — NUNCA bate
na API ao vivo (free-tier ~25 req/dia, robustez overnight). Cobre: mapeamento →
`NewsArticle` (parse regex de `time_published`, ID estável `url > time:title`),
guard `Note`/`Information` e formato inesperado → `ApplicationError`, item com
`time_published` inválido ignorado sem quebrar o lote, throttle exercitado (sem dormir
de verdade). As falhas do `httpx` (status, transporte, JSON inválido) usam um
`httpx.Client` REAL sobre `httpx.MockTransport` — a lib erguendo o próprio tipo, sem
rede — e provam a tradução para `ApplicationError` com a original em `__cause__`
(issue #69). Há um teste live OPCIONAL com `skipif` (não roda no CI overnight).
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from financial_forecasting.features.market_data.adapters.out.alpha_vantage import (
    alpha_vantage_news_fetcher as module,
)
from financial_forecasting.features.market_data.adapters.out.alpha_vantage.alpha_vantage_news_fetcher import (  # noqa: E501
    AlphaVantageNewsFetcher,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 12, 31, tzinfo=UTC)
_TWO = 2


class _FakeResponse:
    """Resposta `httpx`-like mínima: `raise_for_status` + `json`."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeClient:
    """Cliente `httpx`-like que devolve um payload fixo (sem rede)."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: object = None, headers: object = None) -> _FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        return _FakeResponse(self._payload)


def _feed_payload() -> dict[str, object]:
    """Payload `NEWS_SENTIMENT` válido com 3 itens (1 com `time_published` inválido)."""
    return {
        "feed": [
            {
                "time_published": "20240301T0930",
                "title": "Apple beats estimates",
                "summary": "Strong quarter.",
                "source": "Reuters",
                "url": "https://example.com/aapl-1",
            },
            {
                # sem url → ID estável cai em time:title
                "time_published": "20240302T101500",
                "title": "Apple supply chain update",
                "summary": "Logistics improving.",
                "source": "Bloomberg",
            },
            {
                # time_published inválido → item ignorado (parse defensivo)
                "time_published": "not-a-date",
                "title": "Garbage",
                "summary": "Ignored.",
                "source": "X",
                "url": "https://example.com/x",
            },
            {
                # sem time_published → item ignorado (falsy guard)
                "title": "No date",
                "summary": "Ignored too.",
                "source": "Y",
            },
        ]
    }


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutraliza `time.sleep` no throttle (não dorme de verdade no teste)."""
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)


def _fetcher(payload: object) -> tuple[AlphaVantageNewsFetcher, _FakeClient]:
    client = _FakeClient(payload)
    return AlphaVantageNewsFetcher(api_key="demo", client=client), client


@pytest.mark.integration
def test_maps_feed_to_news_articles() -> None:
    """Mapeia os itens válidos do `feed` → `NewsArticle` (parse + ID estável)."""
    fetcher, client = _fetcher(_feed_payload())

    articles = fetcher.fetch_company_news("AAPL", _START, _END)

    assert len(articles) == _TWO  # o item com time_published inválido é ignorado
    assert all(isinstance(a, NewsArticle) for a in articles)
    first = articles[0]
    assert first.asset_id == "AAPL"
    assert first.published_at == datetime(2024, 3, 1, 9, 30, tzinfo=UTC)
    assert first.article_id == "https://example.com/aapl-1"  # url como ID
    # segundo item sem url → ID estável time:title
    second = articles[1]
    assert second.published_at == datetime(2024, 3, 2, 10, 15, 0, tzinfo=UTC)
    assert second.article_id == "20240302T101500:Apple supply chain update"
    # uma chamada de rede (throttled) foi feita
    assert len(client.calls) == 1
    assert client.calls[0]["params"]["function"] == "NEWS_SENTIMENT"


@pytest.mark.integration
def test_api_gets_raw_ticker_and_articles_get_canonical_asset() -> None:
    """A API recebe `aapl.us` como veio; o artigo leva `AAPL` (#69 c)."""
    fetcher, client = _fetcher(_feed_payload())

    articles = fetcher.fetch_company_news("aapl.us", _START, _END)

    assert client.calls[0]["params"]["tickers"] == "aapl.us"
    assert {a.asset_id for a in articles} == {"AAPL"}


@pytest.mark.integration
def test_invalid_ticker_fails_before_any_request() -> None:
    """Ticker que não vira `AssetId` falha já, sem chamada de rede."""
    fetcher, client = _fetcher(_feed_payload())

    with pytest.raises(ValueError, match="asset_id"):
        fetcher.fetch_company_news("AA PL", _START, _END)

    assert client.calls == []


@pytest.mark.integration
def test_rate_limit_note_raises_application_error() -> None:
    """Resposta com chave `Note` → `ApplicationError` (guard de rate-limit, C7; #69)."""
    fetcher, _ = _fetcher({"Note": "Thank you for using Alpha Vantage! Rate limit..."})
    with pytest.raises(ApplicationError, match="rate limit"):
        fetcher.fetch_company_news("AAPL", _START, _END)


@pytest.mark.integration
def test_information_key_raises_application_error() -> None:
    """Resposta com chave `Information` → `ApplicationError` (C7; #69)."""
    fetcher, _ = _fetcher({"Information": "Our standard API rate limit is 25 requests/day"})
    with pytest.raises(ApplicationError, match="Information"):
        fetcher.fetch_company_news("AAPL", _START, _END)


@pytest.mark.integration
def test_non_dict_response_raises() -> None:
    """Resposta JSON não-dict → `ApplicationError` (C7; #69)."""
    fetcher, _ = _fetcher(["not", "a", "dict"])
    with pytest.raises(ApplicationError, match="expected dict"):
        fetcher.fetch_company_news("AAPL", _START, _END)


@pytest.mark.integration
def test_missing_feed_raises() -> None:
    """Resposta sem `feed` → `ApplicationError` (C7; #69)."""
    fetcher, _ = _fetcher({"something": "else"})
    with pytest.raises(ApplicationError, match="Unexpected response shape"):
        fetcher.fetch_company_news("AAPL", _START, _END)


@pytest.mark.integration
def test_feed_not_a_list_raises() -> None:
    """`feed` que não é lista → `ApplicationError` (C7; #69)."""
    fetcher, _ = _fetcher({"feed": {"not": "a list"}})
    with pytest.raises(ApplicationError, match="'feed' is not a list"):
        fetcher.fetch_company_news("AAPL", _START, _END)


# -- falhas do httpx: Client REAL + MockTransport, sem rede (issue #69) ----------


def _mock_fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> AlphaVantageNewsFetcher:
    """Adapter sobre um `httpx.Client` real cujo transporte é o `handler` (sem rede)."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AlphaVantageNewsFetcher(api_key="demo", client=client)


def _service_unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="Service Unavailable", request=request)


def _connect_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("timed out", request=request)


def _html_body(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>maintenance</html>", request=request)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("handler", "cause_type"),
    [
        (_service_unavailable, httpx.HTTPStatusError),
        (_connect_timeout, httpx.ConnectTimeout),
        (_html_body, json.JSONDecodeError),
    ],
    ids=["http-503", "connect-timeout", "invalid-json"],
)
def test_httpx_failure_is_translated_with_cause(
    handler: Callable[[httpx.Request], httpx.Response], cause_type: type[Exception]
) -> None:
    """Falha do `httpx` → `ApplicationError` com a exceção da lib em `__cause__` (#69)."""
    with pytest.raises(ApplicationError, match="NEWS_SENTIMENT") as excinfo:
        _mock_fetcher(handler).fetch_company_news("AAPL", _START, _END)

    assert isinstance(excinfo.value.__cause__, cause_type)


@pytest.mark.integration
def test_mock_transport_happy_path_still_maps() -> None:
    """Controle: o mesmo `httpx.Client` real, com resposta saudável, mapeia o feed."""

    def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_feed_payload(), request=request)

    articles = _mock_fetcher(_ok).fetch_company_news("AAPL", _START, _END)

    assert len(articles) == _TWO


@pytest.mark.integration
def test_empty_title_and_summary_get_placeholder() -> None:
    """Item sem título E sem resumo recebe placeholder (entity exige str)."""
    payload = {"feed": [{"time_published": "20240301T0930", "url": "https://example.com/blank"}]}
    fetcher, _ = _fetcher(payload)
    articles = fetcher.fetch_company_news("AAPL", _START, _END)
    assert len(articles) == 1
    assert articles[0].headline == " "
    assert articles[0].summary == " "
    assert articles[0].source == "alpha_vantage"


@pytest.mark.integration
@pytest.mark.parametrize("bad_url", ["www.example.com/a", "ftp://x"])
def test_item_violating_the_entity_is_skipped_and_batch_survives(bad_url: str) -> None:
    """Item com `url` que a `NewsArticle` recusa é ignorado; o resto do lote fica (#69)."""
    payload = _feed_payload()
    feed = payload["feed"]
    assert isinstance(feed, list)
    feed.insert(0, {"time_published": "20240301T0800", "title": "Bad url", "url": bad_url})
    fetcher, _ = _fetcher(payload)

    articles = fetcher.fetch_company_news("AAPL", _START, _END)

    assert len(articles) == _TWO
    assert all(a.url != bad_url for a in articles)
    assert "Bad url" not in {a.headline for a in articles}


@pytest.mark.integration
def test_throttle_sleeps_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Duas chamadas em sequência exercitam o ramo de `sleep` do throttle (I9)."""
    slept: list[float] = []
    monkeypatch.setattr(module.time, "sleep", slept.append)
    # monotonic constante → elapsed=0 < _MIN_INTERVAL → dorme na 2ª chamada
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    fetcher, _ = _fetcher(_feed_payload())
    fetcher.fetch_company_news("AAPL", _START, _END)
    fetcher.fetch_company_news("AAPL", _START, _END)

    assert slept  # dormiu ao menos uma vez (segunda chamada dentro do intervalo)


@pytest.mark.integration
def test_invalid_bounds_raise() -> None:
    """`start > end`/naive → `ValueError` antes de qualquer chamada de rede (C5)."""
    fetcher, client = _fetcher(_feed_payload())
    with pytest.raises(ValueError, match="start_date must be <="):
        fetcher.fetch_company_news("AAPL", _END, _START)
    with pytest.raises(ValueError, match="timezone-aware"):
        fetcher.fetch_company_news("AAPL", datetime(2024, 1, 1), _END)
    assert client.calls == []  # nenhuma chamada de rede


@pytest.mark.integration
def test_default_client_is_httpx_without_network() -> None:
    """Sem `client` injetado, cria um `httpx.Client` na construção — sem rede."""
    fetcher = AlphaVantageNewsFetcher(api_key="demo")
    assert isinstance(fetcher._client, httpx.Client)


def _has_network() -> bool:
    try:
        socket.create_connection(("www.alphavantage.co", 443), timeout=2).close()
    except OSError:
        return False
    return True


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("FF_LIVE_ALPHAVANTAGE") != "1"
    or not os.environ.get("ALPHAVANTAGE_API_KEY")
    or not _has_network(),
    reason="teste live opcional: requer FF_LIVE_ALPHAVANTAGE=1, chave e rede (não roda no CI)",
)
def test_live_fetch_optional() -> None:  # pragma: no cover - live, opt-in
    """Teste LIVE opt-in (não roda no CI): bate na API real só se habilitado."""
    key = os.environ["ALPHAVANTAGE_API_KEY"]
    fetcher = AlphaVantageNewsFetcher(api_key=key)
    articles = fetcher.fetch_company_news(
        "AAPL", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC)
    )
    assert all(a.asset_id == "AAPL" for a in articles)
