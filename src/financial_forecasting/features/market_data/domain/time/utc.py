"""Helpers UTC de domínio (stdlib `datetime` only) — concept 2.2 §1/§5 (I4).

Reimplementa, em domínio puro, os helpers UTC do old
(`financial-time-series-forecasting/src/domain/time/utc.py`) com julgamento, e
acrescenta a normalização ao `00:00 UTC` do dia usada pelos adapters no diário
(Tasks 05/06). Sem dependência externa — só `datetime` stdlib —, para manter a
pureza do domínio (`import-linter` `hexagonal-layers`/`domain-purity`).

Semântica:

- `require_tz_aware(dt, name)` — levanta `ValueError` se `dt` for naive (uso em
  fronteira: use case, adapters). Espelha o old.
- `to_utc(dt)` — exige tz-aware e converte para UTC (`astimezone(UTC)`).
- `ensure_utc(dt)` — assume UTC se naive, converte se aware. SÓ para parse/CLI
  (entry points), NUNCA em domínio puro de adapter (concept 2.2: a entity exige
  tz-aware, não assume).
- `parse_iso_utc(value)` — parse ISO (`Z`/offset/sem tz) → tz-aware UTC.
- `normalize_to_utc_day(dt)` — converte para UTC e ZERA a hora (`00:00 UTC`),
  alinhando candles diários com `datetime64[ns, UTC]` a `00:00` do bronze (I4).
"""

from __future__ import annotations

from datetime import UTC, datetime, time


def require_tz_aware(dt: datetime, name: str = "datetime") -> None:
    """Exige `dt` tz-aware; naive → `ValueError` (concept 2.2 C5/I4)."""
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware (UTC enforced)")


def to_utc(dt: datetime) -> datetime:
    """Converte um `datetime` tz-aware para UTC; naive → `ValueError`."""
    require_tz_aware(dt, "dt")
    return dt.astimezone(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Garante UTC: naive → assume UTC; aware → converte. SÓ para parse/entry-point."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_iso_utc(value: str) -> datetime:
    """Parseia uma string ISO (data ou datetime) e devolve tz-aware UTC.

    Aceita: `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SS`, com/sem timezone, e `Z` final.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(text))


def normalize_to_utc_day(dt: datetime) -> datetime:
    """Normaliza `dt` para `00:00 UTC` do seu dia (candle diário); naive → `ValueError`.

    Converte para UTC (exige tz-aware) e zera a hora — alinha o `Candle.timestamp`
    diário com a coluna `datetime64[ns, UTC]` a `00:00` do bronze (concept 2.2 I4).
    """
    dt_utc = to_utc(dt)
    return datetime.combine(dt_utc.date(), time(0, 0), tzinfo=UTC)
