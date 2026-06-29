"""Entity `FundamentalReport` — snapshot fundamental de um período (domínio puro).

`FundamentalReport` é a entity de domínio do bounded context `market_data` para
fundamentos: identidade lógica `(asset_id, report_type, fiscal_date_end)` (mesma
PK lógica da bronze `fundamental`, Stage 2.1) e invariantes validadas na construção
(`__post_init__`). Portada do old
(`financial-time-series-forecasting/src/entities/fundamental_report.py:32-60`).

Domínio puro: importa SÓ `dataclasses` + `datetime` (stdlib). Sem
`pandas`/`pyarrow`/`pydantic` — o gate `import-linter` `domain-purity` reprova
qualquer vazamento (concept 2.3 I3).

Ordem dos campos: alinhada ao schema bronze `FUNDAMENTAL`
(`bronze_schemas.py:95-110`) — `asset_id`, `report_type`, `fiscal_date_end`,
`reported_date`, os cinco floats, `source` — facilitando o row-mapper do use case
(concept 2.3 nota de porte §4). Diferença vs old: `source` é non-default e a ordem
segue o schema (o old ordenava diferente e dava default a `reported_date`/`source`).

Invariantes (concept 2.3 §5 I2, levantadas no `__post_init__`):

- `asset_id`/`source` são `str` não-vazias.
- `fiscal_date_end` é `date` **sem hora**: como `datetime` é subclasse de `date`,
  checa-se `isinstance(x, datetime)` explicitamente PRIMEIRO (`datetime` →
  `TypeError`), depois `isinstance(x, date)`.
- `report_type` ∈ `{"annual", "quarterly"}` (senão `ValueError`).
- os cinco numéricos são `float`-ou-`None`; `int` é aceito como numérico (espelha o
  old `isinstance(value, (int, float))` — concept 2.3 Task 02 detalhe técnico).
- `reported_date` é `date`-ou-`None` (`datetime` → `TypeError`); os 17/81 `NaT`
  reais do parquet chegam como `None`.
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class FundamentalReport:
    """Snapshot fundamental imutável com invariantes validadas (concept 2.3 §5 I2).

    Identidade lógica: `(asset_id, report_type, fiscal_date_end)`. `fiscal_date_end`
    é `date` puro (sem hora); `reported_date` é `date`-ou-`None` (a única fonte ao
    vivo é o endpoint EARNINGS — concept 2.3 I11). Construir um `FundamentalReport`
    que viole qualquer invariante levanta `ValueError`/`TypeError` (concept 2.3 C2).
    """

    asset_id: str
    report_type: str
    fiscal_date_end: date
    reported_date: date | None
    revenue: float | None
    net_income: float | None
    operating_cash_flow: float | None
    total_shareholder_equity: float | None
    total_liabilities: float | None
    source: str

    def __post_init__(self) -> None:
        self._require_non_empty_strings()
        self._require_fiscal_date_end_is_date()
        self._require_report_type()
        self._require_numeric_fields()
        self._require_reported_date()

    # -- invariantes ---------------------------------------------------------

    def _require_non_empty_strings(self) -> None:
        """`asset_id`/`source` são `str` não-vazias."""
        for field_name in ("asset_id", "source"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def _require_fiscal_date_end_is_date(self) -> None:
        """`fiscal_date_end` é `date` SEM hora (`datetime` → `TypeError`)."""
        if isinstance(self.fiscal_date_end, datetime):
            raise TypeError("fiscal_date_end must be a date without time")
        if not isinstance(self.fiscal_date_end, date):
            raise TypeError("fiscal_date_end must be a date instance")

    def _require_report_type(self) -> None:
        """`report_type` ∈ `{"annual", "quarterly"}`."""
        if self.report_type not in {"annual", "quarterly"}:
            raise ValueError("report_type must be 'annual' or 'quarterly'")

    def _require_numeric_fields(self) -> None:
        """Os cinco numéricos são `float`-ou-`None` (`int` aceito, espelha o old)."""
        for name, value in (
            ("revenue", self.revenue),
            ("net_income", self.net_income),
            ("operating_cash_flow", self.operating_cash_flow),
            ("total_shareholder_equity", self.total_shareholder_equity),
            ("total_liabilities", self.total_liabilities),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"{name} must be numeric when provided")

    def _require_reported_date(self) -> None:
        """`reported_date` é `date`-ou-`None` (`datetime` → `TypeError`)."""
        if self.reported_date is None:
            return
        if isinstance(self.reported_date, datetime):
            raise TypeError("reported_date must be a date without time")
        if not isinstance(self.reported_date, date):
            raise TypeError("reported_date must be a date instance")
