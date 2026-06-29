"""Adapter `ParquetRawNewsFetcher` — origem DEFAULT da ingestão de news (concept 2.3 D2).

Lê o parquet raw EXISTENTE de notícias
(`data/raw/news/<symbol>/news_<symbol>.parquet`, 6921 linhas x 8 colunas para AAPL)
e mapeia cada linha para uma entity `NewsArticle`, sem re-baixar nada — o reuso de
`raw/` é decisão do autor (ledger §A / ADR 2.3.0002) e a origem default do pipeline
(`AlphaVantageNewsFetcher` existe mas NÃO é default). Implementa o port
`NewsFetcher` por duck-typing.

`pandas`/`pyarrow` vivem SÓ aqui (concept 2.3 I3/D2): o gate `import-linter`
`hexagonal-layers` reprova se a `application`/`domain` do BC importar essas libs.

Mapeamento (concept 2.3 §9): as 8 colunas do raw (`article_id`, `headline`,
`published_at` `datetime64[ns, UTC]`, `asset_id`, `url`, `source`, `language`,
`summary`, todas non-null) viram os campos da `NewsArticle`; `published_at` é
convertido para `datetime` tz-aware UTC; as invariantes I1 são validadas na
construção.

Erros (concept 2.3 C6):
- `start_date`/`end_date` naive ou `start_date > end_date` → `ValueError` (fronteira);
- arquivo de origem ausente/ilegível → `ApplicationError` (NÃO silencia em lista
  vazia, distinto de "sem dados no intervalo" → `[]`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.features.market_data.domain.time.utc import (
    require_tz_aware,
    to_utc,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError

# Raiz default do raw de news (simples-e-trocável; injetável p/ teste — concept 2.3
# §13). Layout: <root>/<symbol>/news_<symbol>.parquet.
DEFAULT_RAW_ROOT = Path("data/raw/news")

_REQUIRED_COLUMNS = (
    "article_id",
    "headline",
    "published_at",
    "asset_id",
    "url",
    "source",
    "language",
    "summary",
)


class ParquetRawNewsFetcher:
    """Implementação do `NewsFetcher` que lê o raw existente (origem default)."""

    def __init__(self, raw_root: Path | str = DEFAULT_RAW_ROOT) -> None:
        self._raw_root = Path(raw_root)

    def _parquet_path(self, symbol: str) -> Path:
        return self._raw_root / symbol / f"news_{symbol}.parquet"

    def fetch_company_news(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[NewsArticle]:
        """Lê e mapeia as notícias de `ticker` do raw, filtrando `[start, end]`."""
        require_tz_aware(start_date, "start_date")
        require_tz_aware(end_date, "end_date")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        path = self._parquet_path(ticker)
        if not path.exists():
            raise ApplicationError(f"Raw news source not found for {ticker!r}: {path}")
        try:
            frame = pd.read_parquet(path)
        except (OSError, ValueError, pd.errors.ParserError) as exc:  # pragma: no cover
            raise ApplicationError(
                f"Raw news source unreadable for {ticker!r}: {path} ({exc})"
            ) from exc

        missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
        if missing:
            raise ApplicationError(
                f"Raw news source for {ticker!r} missing columns {missing}: {path}"
            )

        start_utc = to_utc(start_date)
        end_utc = to_utc(end_date)
        articles: list[NewsArticle] = []
        for record in frame.to_dict(orient="records"):
            published_at = _as_utc_datetime(record["published_at"])
            if not (start_utc <= published_at <= end_utc):
                continue
            articles.append(
                NewsArticle(
                    asset_id=str(record["asset_id"]),
                    published_at=published_at,
                    headline=str(record["headline"]),
                    summary=str(record["summary"]),
                    source=str(record["source"]),
                    url=_optional_str(record["url"]),
                    article_id=_optional_str(record["article_id"]),
                    language=_optional_str(record["language"]),
                )
            )
        articles.sort(key=lambda a: a.published_at)
        return articles


def _as_utc_datetime(value: object) -> datetime:
    """Converte um valor de timestamp do parquet (pd.Timestamp/str) em `datetime` UTC."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    converted: datetime = timestamp.to_pydatetime()
    return converted.astimezone(UTC)


def _optional_str(value: object) -> str | None:
    """Coage um valor opcional do parquet para `str` (ou `None` se nulo)."""
    if value is None or pd.isna(value):
        return None
    return str(value)
