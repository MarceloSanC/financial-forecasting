"""Use case `IngestFundamentals` + DTOs frozen (concept 2.3 §4, A6).

Orquestra a ingestão de relatórios fundamentais para a bronze: lê de uma origem
(`FundamentalFetcher`, port-out — default = parquet existente), FILTRA por
`report_type` ∈ `request.report_types` e por intervalo de `fiscal_date_end` ∈
`[start, end]` inclusivo (quando dados — lógica do old
`fetch_fundamentals_use_case.py:55-65`, concept 2.3 I10), mapeia cada
`FundamentalReport → Row` (10 colunas, convertendo `date → datetime UTC`;
`reported_date None → None`/`NaT` — concept 2.3 I7) e grava via `MedallionStore`
(port-out 2.1) em `(bronze, fundamental)`, append-only. Recebe/devolve DTO frozen —
NUNCA vaza `FundamentalReport` nem `list` para fora (concept 2.3 I5/D6).

O use case é stdlib-only (não usa `pandas`): a conversão `date → datetime` UTC usa
`datetime.combine(d, time(0,0), tzinfo=UTC)`; a coerção de dtype final
(`float64`/`datetime64[ns, UTC]`) é do `ParquetMedallionStore` (2.1, I7). A rede de
segurança `pandera` no `write` rejeita drift (C4).

Dedup por PK lógica `(asset_id, report_type, fiscal_date_end)` delegada ao store
(`DuplicateKeyError` sem `overwrite`, concept 2.3 C3) — não reimplementado aqui.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from financial_forecasting.features.market_data.application.ports.out.fundamental_fetcher import (
    FundamentalFetcher,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
    Row,
)

_BRONZE_LAYER = "bronze"
_FUNDAMENTAL_TABLE = "fundamental"
_DEFAULT_REPORT_TYPES = ("annual", "quarterly")


@dataclass(frozen=True)
class IngestFundamentalsRequest:
    """Comando de ingestão de fundamentos: ativo + filtros opcionais (concept 2.3 §4).

    `start`/`end` (tz-aware quando dados) filtram o intervalo de `fiscal_date_end`
    inclusivo; `report_types` restringe os tipos de relatório.
    """

    asset_id: str
    start: datetime | None = None
    end: datetime | None = None
    report_types: tuple[str, ...] = _DEFAULT_REPORT_TYPES


@dataclass(frozen=True)
class IngestFundamentalsResult:
    """Resultado da ingestão: contagem gravada (NUNCA `FundamentalReport`)."""

    asset_id: str
    ingested: int = 0


def _date_to_utc_datetime(value: date | None) -> datetime | None:
    """Converte `date → datetime` UTC a `00:00` (`None → None`), stdlib-only (I7).

    A entity garante que `fiscal_date_end`/`reported_date` são `date` puro (nunca
    `datetime` — invariante I2), por isso `datetime.combine` é seguro e correto.
    """
    if value is None:
        return None
    return datetime.combine(value, time(0, 0), tzinfo=UTC)


def _fundamental_to_row(report: FundamentalReport) -> Row:
    """Mapeia `FundamentalReport → Row` bronze (10 colunas, ordem do schema, I7).

    `fiscal_date_end` → `datetime` UTC (non-null); `reported_date` → `datetime` UTC
    ou `None`; os cinco numéricos como `float` Python (ou `None`); `report_type`/
    `source` non-null. As chaves casam EXATAMENTE o schema `FUNDAMENTAL` (2.1).
    """
    return {
        "asset_id": report.asset_id,
        "report_type": report.report_type,
        "fiscal_date_end": _date_to_utc_datetime(report.fiscal_date_end),
        "reported_date": _date_to_utc_datetime(report.reported_date),
        "revenue": _as_float(report.revenue),
        "net_income": _as_float(report.net_income),
        "operating_cash_flow": _as_float(report.operating_cash_flow),
        "total_shareholder_equity": _as_float(report.total_shareholder_equity),
        "total_liabilities": _as_float(report.total_liabilities),
        "source": report.source,
    }


def _as_float(value: float | None) -> float | None:
    """Coage um numérico opcional para `float` Python (ou `None`)."""
    return None if value is None else float(value)


class IngestFundamentals:
    """Use case: ingere fundamentos de um ativo para a bronze via `MedallionStore`."""

    def __init__(self, fetcher: FundamentalFetcher, store: MedallionStore) -> None:
        self._fetcher = fetcher
        self._store = store

    def execute(self, request: IngestFundamentalsRequest) -> IngestFundamentalsResult:
        """Lê fundamentos da origem, filtra, mapeia e grava `(bronze, fundamental)`.

        Quando `start`/`end` são dados, valida tz-aware (C5) antes de filtrar; o
        filtro de `fiscal_date_end` é inclusivo nos dois extremos (espelha o old).
        Filtra também por `report_type` ∈ `request.report_types` (I10). A escrita é
        append-only (`overwrite=False`): colisão de PK propaga `DuplicateKeyError`
        (C3). Devolve `IngestFundamentalsResult` com a contagem (NUNCA entity).
        """
        start_date, end_date = self._validated_bounds(request)

        reports = self._fetcher.fetch_fundamentals(request.asset_id)
        filtered = [
            r
            for r in reports
            if r.report_type in request.report_types
            and self._in_interval(r.fiscal_date_end, start_date, end_date)
        ]
        rows: list[Mapping[str, object]] = [_fundamental_to_row(r) for r in filtered]
        self._store.write(layer=_BRONZE_LAYER, table=_FUNDAMENTAL_TABLE, rows=rows, overwrite=False)

        return IngestFundamentalsResult(asset_id=request.asset_id, ingested=len(rows))

    @staticmethod
    def _validated_bounds(
        request: IngestFundamentalsRequest,
    ) -> tuple[datetime | None, datetime | None]:
        """Valida `start`/`end` tz-aware quando dados; converte para UTC (C5)."""
        start = request.start
        end = request.end
        if start is not None:
            require_tz_aware(start, "start")
            start = start.astimezone(UTC)
        if end is not None:
            require_tz_aware(end, "end")
            end = end.astimezone(UTC)
        if start is not None and end is not None and start > end:
            raise ValueError("start must be <= end")
        return start, end

    @staticmethod
    def _in_interval(fiscal_date_end: date, start: datetime | None, end: datetime | None) -> bool:
        """`fiscal_date_end` ∈ `[start.date(), end.date()]` inclusivo (old :55-65)."""
        if start is not None and fiscal_date_end < start.date():
            return False
        return not (end is not None and fiscal_date_end > end.date())
