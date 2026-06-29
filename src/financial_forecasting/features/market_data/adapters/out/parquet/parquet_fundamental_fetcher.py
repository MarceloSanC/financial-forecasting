"""Adapter `ParquetFundamentalFetcher` — origem DEFAULT de fundamentos (concept 2.3 D2).

Lê o parquet EXISTENTE de fundamentos
(`data/processed/fundamentals/<symbol>/fundamentals_<symbol>.parquet`, 81 linhas x
10 colunas para AAPL, 17 `NaT` em `reported_date`) e mapeia cada linha para uma
entity `FundamentalReport`, sem re-baixar nada — o reuso é decisão do autor (ledger
§A / ADR 2.3.0002) e a origem default (`AlphaVantageFundamentalFetcher` existe mas
NÃO é default). Implementa o port `FundamentalFetcher` por duck-typing.

`pandas`/`pyarrow` vivem SÓ aqui (concept 2.3 I3/D2): o gate `import-linter`
`hexagonal-layers` reprova se a `application`/`domain` do BC importar essas libs.

Mapeamento (concept 2.3 §9, espelhando o old `parquet_fundamental_repository.py`
`:54`,`:93-94` na VOLTA — `datetime64 UTC → date`):
- `fiscal_date_end` (`datetime64[ns, UTC]` → `.date()`, non-null);
- `reported_date` (`NaT → None`, senão `.date()`);
- os cinco floats (`NaN → None`); `asset_id` normalizado.

O adapter NÃO filtra por `report_type`/intervalo (isso é do use case, I10) — devolve
TODOS os reports do ativo. Arquivo ausente/ilegível → `ApplicationError` (C6).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError

# Raiz default dos fundamentos processados (injetável p/ teste — concept 2.3 §13).
# Layout: <root>/<symbol>/fundamentals_<symbol>.parquet.
DEFAULT_FUNDAMENTALS_ROOT = Path("data/processed/fundamentals")

_REQUIRED_COLUMNS = (
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


class ParquetFundamentalFetcher:
    """Implementação do `FundamentalFetcher` que lê o parquet existente (default)."""

    def __init__(self, root: Path | str = DEFAULT_FUNDAMENTALS_ROOT) -> None:
        self._root = Path(root)

    @staticmethod
    def _normalize_symbol(asset_id: str) -> str:
        """Normaliza o ativo (sufixo de bolsa removido, uppercase) — old `:54`."""
        return asset_id.split(".", maxsplit=1)[0].upper()

    def _parquet_path(self, symbol: str) -> Path:
        return self._root / symbol / f"fundamentals_{symbol}.parquet"

    def fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]:
        """Lê e mapeia TODOS os fundamentos de `asset_id` do parquet existente."""
        symbol = self._normalize_symbol(asset_id)
        path = self._parquet_path(symbol)
        if not path.exists():
            raise ApplicationError(f"Fundamentals source not found for {asset_id!r}: {path}")
        try:
            frame = pd.read_parquet(path)
        except (OSError, ValueError, pd.errors.ParserError) as exc:  # pragma: no cover
            raise ApplicationError(
                f"Fundamentals source unreadable for {asset_id!r}: {path} ({exc})"
            ) from exc

        missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
        if missing:
            raise ApplicationError(
                f"Fundamentals source for {asset_id!r} missing columns {missing}: {path}"
            )

        reports: list[FundamentalReport] = []
        for record in frame.to_dict(orient="records"):
            reports.append(
                FundamentalReport(
                    asset_id=self._normalize_symbol(str(record["asset_id"])),
                    report_type=str(record["report_type"]),
                    fiscal_date_end=_to_date_required(record["fiscal_date_end"]),
                    reported_date=_to_date_optional(record["reported_date"]),
                    revenue=_to_float(record["revenue"]),
                    net_income=_to_float(record["net_income"]),
                    operating_cash_flow=_to_float(record["operating_cash_flow"]),
                    total_shareholder_equity=_to_float(record["total_shareholder_equity"]),
                    total_liabilities=_to_float(record["total_liabilities"]),
                    source=str(record["source"]),
                )
            )
        reports.sort(key=lambda r: (r.report_type, r.fiscal_date_end))
        return reports


def _to_date_required(value: object) -> date:
    """Converte um `datetime64 UTC`/`Timestamp` non-null para `date` (sem hora)."""
    timestamp = pd.Timestamp(value)
    result: datetime = timestamp.to_pydatetime()
    return result.date()


def _to_date_optional(value: object) -> date | None:
    """Converte `datetime64 UTC` → `date`; `NaT`/nulo → `None` (os 17 `NaT` reais)."""
    if value is None or pd.isna(value):
        return None
    return _to_date_required(value)


def _to_float(value: object) -> float | None:
    """Coage um numérico do parquet para `float` Python; `NaN`/nulo → `None`."""
    if value is None or pd.isna(value):
        return None
    return float(value)  # type: ignore[arg-type]
