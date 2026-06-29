"""Testes do use case `IngestFundamentals` com fakes (concept 2.3 §5 I5/I7/I10, A6).

Usa `FakeFundamentalFetcher` + `FakeMedallionStore` (reusado da 2.1). Cobre: filtro
por `report_type` e por intervalo de `fiscal_date_end` (inclusivo); report SEM
`reported_date` → Row com `reported_date=None`; conversão `date → datetime` UTC; 10
colunas na Row; `Result.ingested` == nº gravado; retorno é
`IngestFundamentalsResult` (nunca entity); colisão de PK → `DuplicateKeyError`;
`start`/`end` naive → `ValueError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from financial_forecasting.features.market_data.application.use_cases.ingest_fundamentals import (
    IngestFundamentals,
    IngestFundamentalsRequest,
    IngestFundamentalsResult,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.application.ports.out.medallion_store import Row
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from tests.fakes.features.market_data.in_memory_fundamental_fetcher import (
    FakeFundamentalFetcher,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_SYMBOL = "AAPL"
_FUND_COLUMNS = (
    "asset_id",
    "report_type",
    "fiscal_date_end",
    "reported_date",
    "revenue",
    "net_income",
    "operating_cash_flow",
    "total_shareholder_equity",
    "total_liabilities",
    "source",
)


def _report(**overrides: object) -> FundamentalReport:
    kwargs: dict[str, object] = {
        "asset_id": _SYMBOL,
        "report_type": "annual",
        "fiscal_date_end": date(2022, 9, 30),
        "reported_date": date(2022, 11, 1),
        "revenue": 394_328_000_000.0,
        "net_income": 99_803_000_000.0,
        "operating_cash_flow": 122_151_000_000.0,
        "total_shareholder_equity": 50_672_000_000.0,
        "total_liabilities": 302_083_000_000.0,
        "source": "alpha_vantage",
    }
    kwargs.update(overrides)
    return FundamentalReport(**kwargs)  # type: ignore[arg-type]


def _stored(store: FakeMedallionStore) -> Sequence[Row]:
    return store.read(layer="bronze", table="fundamental", filters={"asset": _SYMBOL})


@pytest.mark.unit
def test_ingests_and_returns_count() -> None:
    """Grava os reports e devolve `IngestFundamentalsResult` (nunca entity)."""
    fetcher = FakeFundamentalFetcher(
        [_report(), _report(report_type="quarterly", fiscal_date_end=date(2022, 12, 31))]
    )
    store = FakeMedallionStore()

    result = IngestFundamentals(fetcher, store).execute(IngestFundamentalsRequest(_SYMBOL))

    assert isinstance(result, IngestFundamentalsResult)
    assert result.ingested == len(["r1", "r2"])
    assert len(_stored(store)) == len(["r1", "r2"])


@pytest.mark.unit
def test_rows_have_ten_columns_and_dates_are_utc() -> None:
    """Toda Row tem as 10 colunas; `fiscal_date_end` é `datetime` UTC a 00:00 (I7)."""
    store = FakeMedallionStore()
    IngestFundamentals(FakeFundamentalFetcher([_report()]), store).execute(
        IngestFundamentalsRequest(_SYMBOL)
    )

    row = _stored(store)[0]
    assert set(row.keys()) == set(_FUND_COLUMNS)
    fiscal = row["fiscal_date_end"]
    assert isinstance(fiscal, datetime)
    assert fiscal == datetime(2022, 9, 30, tzinfo=UTC)
    reported = row["reported_date"]
    assert isinstance(reported, datetime)
    assert reported == datetime(2022, 11, 1, tzinfo=UTC)


@pytest.mark.unit
def test_report_without_reported_date_maps_to_none() -> None:
    """Report sem `reported_date` → Row com `reported_date=None` (NaT, I7)."""
    store = FakeMedallionStore()
    IngestFundamentals(FakeFundamentalFetcher([_report(reported_date=None)]), store).execute(
        IngestFundamentalsRequest(_SYMBOL)
    )

    assert _stored(store)[0]["reported_date"] is None


@pytest.mark.unit
def test_filters_by_report_type() -> None:
    """Descarta reports cujo `report_type` ∉ `request.report_types` (I10)."""
    fetcher = FakeFundamentalFetcher(
        [
            _report(report_type="annual"),
            _report(report_type="quarterly", fiscal_date_end=date(2022, 12, 31)),
        ]
    )
    store = FakeMedallionStore()
    result = IngestFundamentals(fetcher, store).execute(
        IngestFundamentalsRequest(_SYMBOL, report_types=("annual",))
    )

    assert result.ingested == 1
    assert _stored(store)[0]["report_type"] == "annual"


@pytest.mark.unit
def test_filters_by_fiscal_date_interval_inclusive() -> None:
    """Filtra por `fiscal_date_end` ∈ `[start, end]` inclusivo nos dois extremos."""
    fetcher = FakeFundamentalFetcher(
        [
            _report(fiscal_date_end=date(2021, 9, 30)),  # antes
            _report(fiscal_date_end=date(2022, 9, 30)),  # limite inferior (inclusivo)
            _report(fiscal_date_end=date(2023, 9, 30)),  # limite superior (inclusivo)
            _report(fiscal_date_end=date(2024, 9, 30)),  # depois
        ]
    )
    store = FakeMedallionStore()
    result = IngestFundamentals(fetcher, store).execute(
        IngestFundamentalsRequest(
            _SYMBOL,
            start=datetime(2022, 9, 30, tzinfo=UTC),
            end=datetime(2023, 9, 30, tzinfo=UTC),
        )
    )

    assert result.ingested == len(["lo", "hi"])
    kept = {r["fiscal_date_end"] for r in _stored(store)}
    assert kept == {datetime(2022, 9, 30, tzinfo=UTC), datetime(2023, 9, 30, tzinfo=UTC)}


@pytest.mark.unit
def test_start_only_filters_lower_bound() -> None:
    """Só `start` (sem `end`) filtra apenas o limite inferior."""
    fetcher = FakeFundamentalFetcher(
        [
            _report(fiscal_date_end=date(2021, 9, 30)),
            _report(fiscal_date_end=date(2023, 9, 30)),
        ]
    )
    store = FakeMedallionStore()
    result = IngestFundamentals(fetcher, store).execute(
        IngestFundamentalsRequest(_SYMBOL, start=datetime(2022, 1, 1, tzinfo=UTC))
    )
    assert result.ingested == 1


@pytest.mark.unit
def test_end_only_filters_upper_bound() -> None:
    """Só `end` (sem `start`) filtra apenas o limite superior."""
    fetcher = FakeFundamentalFetcher(
        [
            _report(fiscal_date_end=date(2021, 9, 30)),
            _report(fiscal_date_end=date(2023, 9, 30)),
        ]
    )
    store = FakeMedallionStore()
    result = IngestFundamentals(fetcher, store).execute(
        IngestFundamentalsRequest(_SYMBOL, end=datetime(2022, 1, 1, tzinfo=UTC))
    )
    assert result.ingested == 1


@pytest.mark.unit
def test_non_utc_bound_is_normalized_to_utc_before_filtering() -> None:
    """Bound tz-aware não-UTC é convertido a UTC ANTES de comparar `.date()` (C5/I10).

    `end = 2022-12-31 22:00 -05:00` ⇒ em UTC = `2023-01-01 03:00`, logo `end.date()`
    correto é `2023-01-01`. Um report com `fiscal_date_end = 2023-01-01` DEVE entrar
    (limite superior inclusivo após normalização). Sem o `astimezone(UTC)` o bound
    cairia em `2022-12-31` e o report seria descartado por engano — mutação detectada.
    """
    fetcher = FakeFundamentalFetcher([_report(fiscal_date_end=date(2023, 1, 1))])
    store = FakeMedallionStore()
    minus_five = timezone(timedelta(hours=-5))
    result = IngestFundamentals(fetcher, store).execute(
        IngestFundamentalsRequest(_SYMBOL, end=datetime(2022, 12, 31, 22, 0, tzinfo=minus_five))
    )
    assert result.ingested == 1


@pytest.mark.unit
def test_none_numeric_fields_preserved() -> None:
    """Numéricos `None` permanecem `None` na Row (schema nullable)."""
    store = FakeMedallionStore()
    IngestFundamentals(
        FakeFundamentalFetcher([_report(revenue=None, net_income=None)]), store
    ).execute(IngestFundamentalsRequest(_SYMBOL))
    row = _stored(store)[0]
    assert row["revenue"] is None
    assert row["net_income"] is None


@pytest.mark.unit
def test_append_only_collision_raises() -> None:
    """Segundo write da MESMA PK → `DuplicateKeyError` (C3)."""
    fetcher = FakeFundamentalFetcher([_report()])
    store = FakeMedallionStore()
    uc = IngestFundamentals(fetcher, store)

    uc.execute(IngestFundamentalsRequest(_SYMBOL))
    with pytest.raises(DuplicateKeyError):
        uc.execute(IngestFundamentalsRequest(_SYMBOL))


@pytest.mark.unit
def test_naive_start_raises() -> None:
    """`start` naive → `ValueError` (C5)."""
    uc = IngestFundamentals(FakeFundamentalFetcher([]), FakeMedallionStore())
    with pytest.raises(ValueError, match="timezone-aware"):
        uc.execute(IngestFundamentalsRequest(_SYMBOL, start=datetime(2022, 1, 1)))


@pytest.mark.unit
def test_naive_end_raises() -> None:
    """`end` naive → `ValueError` (C5)."""
    uc = IngestFundamentals(FakeFundamentalFetcher([]), FakeMedallionStore())
    with pytest.raises(ValueError, match="timezone-aware"):
        uc.execute(IngestFundamentalsRequest(_SYMBOL, end=datetime(2022, 1, 1)))


@pytest.mark.unit
def test_start_after_end_raises() -> None:
    """`start > end` (ambos dados) → `ValueError` (C5)."""
    uc = IngestFundamentals(FakeFundamentalFetcher([]), FakeMedallionStore())
    with pytest.raises(ValueError, match="start must be <= end"):
        uc.execute(
            IngestFundamentalsRequest(
                _SYMBOL,
                start=datetime(2023, 1, 1, tzinfo=UTC),
                end=datetime(2022, 1, 1, tzinfo=UTC),
            )
        )
