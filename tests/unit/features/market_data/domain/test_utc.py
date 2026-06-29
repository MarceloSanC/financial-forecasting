"""Testes dos helpers UTC de domínio (concept 2.2 §5 I4, A2).

Cobre tz-aware ok, naive → `ValueError`, conversão de outra tz para UTC, parse de
cada formato ISO aceito, e normalização a `00:00 UTC`. Domínio puro: só
`datetime` stdlib.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from financial_forecasting.features.market_data.domain.time.utc import (
    ensure_utc,
    normalize_to_utc_day,
    parse_iso_utc,
    require_tz_aware,
    to_utc,
)

_NY = ZoneInfo("America/New_York")


# -- require_tz_aware --------------------------------------------------------


@pytest.mark.unit
def test_require_tz_aware_accepts_aware() -> None:
    """Aware não levanta."""
    require_tz_aware(datetime(2024, 1, 2, tzinfo=UTC), "ts")


@pytest.mark.unit
def test_require_tz_aware_rejects_naive() -> None:
    """Naive → ValueError com o nome do campo."""
    with pytest.raises(ValueError, match="ts must be timezone-aware"):
        require_tz_aware(datetime(2024, 1, 2), "ts")


# -- to_utc ------------------------------------------------------------------


@pytest.mark.unit
def test_to_utc_converts_other_tz() -> None:
    """Converte outra tz para UTC preservando o instante."""
    aware_ny = datetime(2024, 1, 2, 9, 30, tzinfo=_NY)
    result = to_utc(aware_ny)

    assert result.tzinfo == UTC
    assert result == aware_ny  # mesmo instante


@pytest.mark.unit
def test_to_utc_normalizes_offset_to_utc() -> None:
    """Offset fixo +05:00 vira UTC (instante preservado)."""
    aware = datetime(2024, 1, 2, 5, 0, tzinfo=timezone(timedelta(hours=5)))
    result = to_utc(aware)

    assert result.tzinfo == UTC
    assert result == datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_to_utc_rejects_naive() -> None:
    """Naive → ValueError."""
    with pytest.raises(ValueError, match="timezone-aware"):
        to_utc(datetime(2024, 1, 2))


# -- ensure_utc --------------------------------------------------------------


@pytest.mark.unit
def test_ensure_utc_assumes_utc_for_naive() -> None:
    """Naive → assume UTC (entry point only)."""
    result = ensure_utc(datetime(2024, 1, 2, 12, 0))
    assert result == datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


@pytest.mark.unit
def test_ensure_utc_converts_aware() -> None:
    """Aware → converte para UTC."""
    result = ensure_utc(datetime(2024, 1, 2, 9, 30, tzinfo=_NY))
    assert result.tzinfo == UTC


# -- parse_iso_utc -----------------------------------------------------------


@pytest.mark.unit
def test_parse_iso_date_only() -> None:
    """`YYYY-MM-DD` (sem hora/tz) → 00:00 UTC."""
    assert parse_iso_utc("2025-12-31") == datetime(2025, 12, 31, tzinfo=UTC)


@pytest.mark.unit
def test_parse_iso_datetime_no_tz() -> None:
    """`YYYY-MM-DDTHH:MM:SS` (sem tz) → assume UTC."""
    assert parse_iso_utc("2025-12-31T15:30:00") == datetime(2025, 12, 31, 15, 30, tzinfo=UTC)


@pytest.mark.unit
def test_parse_iso_datetime_with_z() -> None:
    """`Z` final → UTC."""
    assert parse_iso_utc("2025-12-31T15:30:00Z") == datetime(2025, 12, 31, 15, 30, tzinfo=UTC)


@pytest.mark.unit
def test_parse_iso_datetime_with_offset() -> None:
    """Offset explícito → convertido para UTC."""
    assert parse_iso_utc("2025-12-31T15:30:00+05:00") == datetime(2025, 12, 31, 10, 30, tzinfo=UTC)


# -- normalize_to_utc_day ----------------------------------------------------


@pytest.mark.unit
def test_normalize_to_utc_day_zeroes_time() -> None:
    """Zera a hora para 00:00 UTC do dia."""
    result = normalize_to_utc_day(datetime(2024, 1, 2, 15, 45, 30, tzinfo=UTC))
    assert result == datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_normalize_to_utc_day_crosses_day_boundary() -> None:
    """Converte tz antes de zerar: 23:30 NY (04:30 UTC do dia+1) → 00:00 UTC do dia+1."""
    aware_ny = datetime(2024, 1, 2, 23, 30, tzinfo=_NY)
    result = normalize_to_utc_day(aware_ny)
    assert result == datetime(2024, 1, 3, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_normalize_to_utc_day_rejects_naive() -> None:
    """Naive → ValueError (via to_utc)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_to_utc_day(datetime(2024, 1, 2))
