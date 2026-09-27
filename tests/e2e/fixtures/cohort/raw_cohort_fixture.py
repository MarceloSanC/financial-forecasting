"""Dado bruto sintético e determinístico para o ponta a ponta do cohort (Stage 5.5, A6).

Grava os três brutos que o wiring da ingestão local lê sob `data_root`
(`raw/market/candles`, `raw/news`, `processed/fundamentals`), no layout e com as
colunas dos fetchers Parquet. As sessões são as do calendário XNYS real (o
splitter valida contra ele); preços são um passeio aleatório com semente fixa;
há notícias em parte dos dias (o sentimento vem do modelo fake injetado) e
fundamentos trimestrais e anuais desde bem antes do primeiro candle, para o
as-of não deixar lacuna.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)

if TYPE_CHECKING:
    from pathlib import Path

_SEED = 20260927
_QUARTER_DAYS = 91
_REPORT_LAG_DAYS = 30


def sessions(first: date, n_sessions: int) -> list[date]:
    """As `n_sessions` primeiras sessões XNYS a partir de `first`."""
    calendar = ExchangeCalendarsProvider().sessions(
        start=first, end=first + timedelta(days=2 * n_sessions)
    )
    days = [day for day in calendar.sessions if day >= first][:n_sessions]
    if len(days) != n_sessions:
        raise ValueError(f"calendar window too short for {n_sessions} sessions")
    return days


def write_raw(
    data_root: Path,
    *,
    asset: str,
    first: date,
    n_sessions: int,
    fundamentals_lead_days: int = 3 * 365,
) -> list[date]:
    """Grava candles, notícias e fundamentos de `asset`; devolve as sessões.

    `fundamentals_lead_days` é quanto o primeiro fundamento antecede o primeiro
    candle; negativo faz os fundamentos começarem DEPOIS — o gate de qualidade
    do dataset rejeita (warmup efetivo acima do declarado).
    """
    rng = random.Random(_SEED)
    days = sessions(first, n_sessions)
    _write_candles(data_root, asset, days, rng)
    _write_news(data_root, asset, days, rng)
    _write_fundamentals(
        data_root, asset, days[0] - timedelta(days=fundamentals_lead_days), days[-1], rng
    )
    return days


def _write_candles(data_root: Path, asset: str, days: list[date], rng: random.Random) -> None:
    close = 100.0
    records = []
    for day in days:
        opened = close
        close = max(1.0, close * math.exp(rng.gauss(0.0003, 0.015)))
        high = max(opened, close) * (1.0 + abs(rng.gauss(0.0, 0.004)))
        low = min(opened, close) * (1.0 - abs(rng.gauss(0.0, 0.004)))
        records.append(
            {
                "timestamp": pd.Timestamp(day, tz="UTC"),
                "open": opened,
                "high": high,
                "low": low,
                "close": close,
                "volume": int(1_000_000 + rng.randrange(500_000)),
            }
        )
    path = data_root / "raw" / "market" / "candles" / asset / f"candles_{asset}_1d.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(path, index=False)


def _write_news(data_root: Path, asset: str, days: list[date], rng: random.Random) -> None:
    records = []
    for index, day in enumerate(days):
        for article in range(rng.randrange(3)):
            published = datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC)
            article_id = f"{asset}-{index}-{article}"
            records.append(
                {
                    "article_id": article_id,
                    "headline": f"headline {article_id}",
                    "published_at": pd.Timestamp(published + timedelta(minutes=article)),
                    "asset_id": asset,
                    "url": f"https://example.invalid/{article_id}",
                    "source": "synthetic",
                    "language": "en",
                    "summary": f"summary {article_id}",
                }
            )
    path = data_root / "raw" / "news" / asset / f"news_{asset}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(path, index=False)


def _write_fundamentals(
    data_root: Path, asset: str, first_fiscal: date, last: date, rng: random.Random
) -> None:
    records = []
    fiscal = first_fiscal
    revenue = 50_000.0
    quarter = 0
    while fiscal <= last:
        revenue *= 1.0 + rng.gauss(0.01, 0.03)
        for report_type, scale in (("quarterly", 1.0), ("annual", 4.0)):
            if report_type == "annual" and quarter % 4 != 3:  # noqa: PLR2004 — 4º trimestre
                continue
            records.append(
                {
                    "asset_id": asset,
                    "report_type": report_type,
                    "fiscal_date_end": pd.Timestamp(fiscal, tz="UTC"),
                    "reported_date": pd.Timestamp(
                        fiscal + timedelta(days=_REPORT_LAG_DAYS), tz="UTC"
                    ),
                    "revenue": revenue * scale,
                    "net_income": revenue * scale * 0.2,
                    "operating_cash_flow": revenue * scale * 0.25,
                    "total_shareholder_equity": 60_000.0 + 100.0 * quarter,
                    "total_liabilities": 90_000.0 + 50.0 * quarter,
                    "source": "synthetic",
                }
            )
        fiscal += timedelta(days=_QUARTER_DAYS)
        quarter += 1
    path = data_root / "processed" / "fundamentals" / asset / f"fundamentals_{asset}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_parquet(path, index=False)
