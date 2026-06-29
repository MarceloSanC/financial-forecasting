"""Adapter `AlphaVantageNewsFetcher` — origem NÃO-default (concept 2.3 D2 / I12).

Porta do old (`financial-time-series-forecasting/src/adapters/alpha_vantage_news_fetcher.py`)
com julgamento, trocando `requests` por **`httpx`** (já em `[project].dependencies`,
sem nova dep — concept 2.3 §5 / `[decision]` §7). Busca notícias do endpoint
`NEWS_SENTIMENT` e converte para entities `NewsArticle`. Implementa o port
`NewsFetcher` por duck-typing.

NÃO é a origem default — o pipeline reusa o parquet existente
(`ParquetRawNewsFetcher`). Este adapter existe para re-ingestão ao vivo consciente;
o teste de integração usa `monkeypatch`/injeção do cliente `httpx` e NUNCA bate na
API ao vivo (free-tier ~25 req/dia, robustez overnight — concept 2.3 I13). `httpx`
vive SÓ aqui (concept 2.3 I3).

Throttle `1.1s` (`_MIN_INTERVAL` + lock + `time.monotonic`) vive no adapter (I9, old
`:32`); não acopla domínio nem use case. ID estável `url > f"{time_published}:
{headline[:80]}"` (old `:169-170`). Guard `Note`/`Information` → `RuntimeError`
(C7); itens com `time_published` inválido são ignorados (parse defensivo) sem
quebrar o lote. Nenhuma chamada de rede em import/instanciação.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import UTC, datetime

import httpx

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware

_TIME_PUBLISHED_RE = re.compile(r"^\d{8}T\d{4}(\d{2})?$")  # YYYYMMDDTHHMM[SS]
_LEN_HHMM = 13
_LEN_HHMMSS = 15
_HEADLINE_ID_LEN = 80


class AlphaVantageNewsFetcher:
    """Implementação do `NewsFetcher` sobre Alpha Vantage `NEWS_SENTIMENT` (não-default)."""

    BASE_URL = "https://www.alphavantage.co/query"
    _MIN_INTERVAL = 1.1  # segundos (~1 req/s)

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        user_agent: str = "financial-forecasting/1.0",
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._user_agent = user_agent
        self._last_request_ts: float | None = None
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        """Respeita `_MIN_INTERVAL` entre requisições (lock + `time.monotonic`)."""
        with self._lock:
            now = time.monotonic()
            if self._last_request_ts is not None:
                sleep_for = self._MIN_INTERVAL - (now - self._last_request_ts)
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._last_request_ts = time.monotonic()

    @staticmethod
    def _parse_time_published(value: str) -> datetime:
        """Parseia `time_published` (`YYYYMMDDTHHMM[SS]`) → `datetime` UTC."""
        text = (value or "").strip()
        if not _TIME_PUBLISHED_RE.match(text):
            raise ValueError(f"Unsupported time_published format: {value!r}")
        if len(text) == _LEN_HHMM:
            return datetime.strptime(text, "%Y%m%dT%H%M").replace(tzinfo=UTC)
        if len(text) == _LEN_HHMMSS:
            return datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        raise ValueError(f"Unsupported time_published length: {value!r}")  # pragma: no cover

    def fetch_company_news(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[NewsArticle]:
        """Busca notícias de `ticker` em `[start_date, end_date]` (NEWS_SENTIMENT)."""
        require_tz_aware(start_date, "start_date")
        require_tz_aware(end_date, "end_date")
        start_utc = start_date.astimezone(UTC)
        end_utc = end_date.astimezone(UTC)
        if start_utc > end_utc:
            raise ValueError("start_date must be <= end_date")

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "time_from": start_utc.strftime("%Y%m%dT%H%M"),
            "time_to": end_utc.strftime("%Y%m%dT%H%M"),
            "sort": "EARLIEST",
            "limit": "1000",
            "apikey": self._api_key,
        }
        data = self._get(params)
        feed = _extract_feed(data)
        return [
            article
            for item in feed
            if isinstance(item, dict)
            and (article := self._item_to_article(ticker, item)) is not None
        ]

    def _get(self, params: dict[str, str]) -> dict[str, object]:
        """Faz o GET throttled e valida a resposta (guard de rate-limit, C7)."""
        self._throttle()
        response = self._client.get(
            self.BASE_URL,
            params=params,
            headers={"Accept": "application/json", "User-Agent": self._user_agent},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected Alpha Vantage response format: expected dict")
        if "Note" in data:
            raise RuntimeError(f"Alpha Vantage rate limit hit: {data['Note']}")
        if "Information" in data:
            raise RuntimeError(f"Alpha Vantage Information: {data['Information']}")
        return data

    def _item_to_article(self, ticker: str, item: dict[str, object]) -> NewsArticle | None:
        """Mapeia um item do `feed` → `NewsArticle`; item inválido → `None` (ignorado)."""
        time_published = item.get("time_published")
        if not time_published:
            return None
        try:
            published_at = self._parse_time_published(str(time_published))
        except ValueError:
            return None  # item com data inválida é ignorado, sem quebrar o lote (C7)

        headline = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        source = str(item.get("source") or "").strip()
        url = item.get("url")
        url_str = str(url) if url else None

        if not headline and not summary:
            headline = " "
            summary = " "

        article_id = url_str or f"{time_published}:{headline[:_HEADLINE_ID_LEN]}"
        return NewsArticle(
            asset_id=ticker,
            published_at=published_at,
            headline=headline,
            summary=summary,
            source=source or "alpha_vantage",
            url=url_str,
            article_id=article_id,
            language="en",
        )


def _extract_feed(data: dict[str, object]) -> list[object]:
    """Extrai a lista `feed` da resposta; ausente/não-lista → erro (C7)."""
    feed = data.get("feed")
    if feed is None:
        raise ValueError(f"Unexpected response shape. Keys: {sorted(data.keys())}")
    if not isinstance(feed, list):
        raise ValueError("Unexpected Alpha Vantage response: 'feed' is not a list")
    return feed
