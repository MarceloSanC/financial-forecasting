"""Use case `BuildDataset` — orquestra a montagem do dataset TFT (application).

Junta as 4 famílias (preço+técnico 3.1, sentimento 3.2, fundamentos as-of 3.3,
derivadas 3.4) sobre a grade densa de dias de pregão e delega a montagem física +
validação anti-leakage + persistência ao `DatasetAssemblerPort` (3.5 Task 03). É a
**Stage de integração do Step 3**: o consumidor que resolve os findings F2 de wiring
deferido — sem ele os ports/adapters de 3.1/3.2/3.3 seriam dead-code.

Depende **só de ports/domain** (LAYOUT §3): nenhum import de `adapters`/`pandas`/
`duckdb`/`torch`. Recebe/devolve **DTO frozen** — nunca uma entity nem um `DataFrame`
cruza a fronteira (I6/A2). Os colaboradores são injetados no construtor (composition
root / testes com fakes).

Pipeline (concept 3.5 §4):

1. lê a bronze `candle` de `asset` (`MedallionStore`, 2.1) → `Row`s OHLCV;
2. calcula os indicadores (`IndicatorCalculator`, 3.1) alinhados por barra;
3. escora + agrega o sentimento diário (`ScoreAndAggregateSentiment`, 3.2);
4. lê a bronze `fundamental`, calcula `effective_date` (`FundamentalsAsofPolicy`,
   3.3) e faz o as-of backward (`AsofJoinAdapter`, 3.3) sobre a grade de dias;
5. delega a montagem ao `DatasetAssemblerPort.assemble` (derivadas via oráculo puro,
   alvo backward via `TargetDefinition`, validadores anti-leakage, schema);
6. persiste via `DatasetAssemblerPort.persist`;
7. devolve `BuildDatasetResult` (contagens + `feature_set_hash` do `FeatureRegistry`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from financial_forecasting.features.feature_engineering.application.ports.out.asof_join import (
    AsofJoinAdapter,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblerPort,
    DatasetAssemblyInputs,
)
from financial_forecasting.features.feature_engineering.application.ports.out.indicator_calculator import (  # noqa: E501
    IndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.application.use_cases.score_and_aggregate_sentiment import (  # noqa: E501
    ScoreAndAggregateSentiment,
    ScoreAndAggregateSentimentRequest,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityGate,
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    FundamentalsAsofPolicy,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
)

_BRONZE = "bronze"
_CANDLE_TABLE = "candle"
_FUNDAMENTAL_TABLE = "fundamental"
# Horário de corte de publicação do sentimento (NYSE close ~16:00 ET ≈ 21:00 UTC).
_DEFAULT_CLOSE_HOUR = time(21, 0)


@dataclass(frozen=True)
class BuildDatasetRequest:
    """Entrada do use case: ativo e janela opcional `[start, end]` (datas)."""

    asset: str
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class BuildDatasetResult:
    """Saída do use case (DTO frozen): contagens + rastreabilidade (sem DataFrame)."""

    asset: str
    n_rows: int
    start: date
    end: date
    feature_set_hash: str
    n_features: int


class BuildDataset:
    """Orquestra o join das 4 famílias + alvo + gate + montagem (concept 3.5 §4)."""

    def __init__(  # noqa: PLR0913 — ports coesos da integração, injetados no composition root
        self,
        *,
        store: MedallionStore,
        indicator_calculator: IndicatorCalculator,
        sentiment: ScoreAndAggregateSentiment,
        asof_join: AsofJoinAdapter,
        assembler: DatasetAssemblerPort,
        asof_policy: FundamentalsAsofPolicy | None = None,
        quality_gate: DatasetQualityGate | None = None,
        quality_gate_config: DatasetQualityGateConfig | None = None,
        close_hour: time = _DEFAULT_CLOSE_HOUR,
    ) -> None:
        self._store = store
        self._indicator_calculator = indicator_calculator
        self._sentiment = sentiment
        self._asof_join = asof_join
        self._assembler = assembler
        self._asof_policy = asof_policy or FundamentalsAsofPolicy()
        self._quality_gate = quality_gate or DatasetQualityGate()
        self._quality_gate_config = quality_gate_config or DatasetQualityGateConfig()
        self._close_hour = close_hour

    def execute(self, request: BuildDatasetRequest) -> BuildDatasetResult:
        """Monta, valida (gate + anti-leakage no assembler) e persiste; devolve DTO."""
        candles = self._load_candles(request.asset, request.start, request.end)
        if len(candles) < 2:  # noqa: PLR2004 — precisa de >=2 barras para 1 alvo backward
            raise ValueError("not enough rows to compute target_return")

        grid_days = [c.timestamp.date() for c in candles]
        candle_rows = [_candle_to_row(c) for c in candles]
        indicators = self._indicator_calculator.calculate(request.asset, candles)
        daily_sentiment = self._daily_sentiment(request.asset, candles)
        asof_rows = self._asof(request.asset, grid_days)

        inputs = DatasetAssemblyInputs(
            asset=request.asset,
            candles=candle_rows,
            indicators=list(indicators),
            daily_sentiment=daily_sentiment,
            asof_rows=asof_rows,
            grid_days=grid_days,
        )
        result = self._assembler.assemble(inputs)

        # Gate de qualidade de domínio sobre os primitivos do frame montado
        # (warmup/missing/monotonia) — `DatasetQualityGate` é stdlib-only e recebe
        # `timestamps`/`feature_rows` (sem `DataFrame` cruzar a fronteira, I6).
        self._quality_gate.validate(
            timestamps=list(result.timestamps),
            rows=list(result.feature_rows),
            feature_cols=list(result.feature_columns),
            config=self._quality_gate_config,
        )
        self._assembler.persist(request.asset)

        return BuildDatasetResult(
            asset=request.asset,
            n_rows=result.n_rows,
            start=result.start,
            end=result.end,
            feature_set_hash=feature_set_hash(),
            n_features=len(result.feature_columns),
        )

    # -- carregamento --------------------------------------------------------

    def _load_candles(self, asset: str, start: date | None, end: date | None) -> list[Candle]:
        """Lê a bronze `candle` de `asset`, mapeia para `Candle` e filtra pela janela."""
        rows = self._store.read(layer=_BRONZE, table=_CANDLE_TABLE, filters={"asset": asset})
        candles = sorted((_row_to_candle(row) for row in rows), key=lambda c: c.timestamp)
        if start is not None:
            candles = [c for c in candles if c.timestamp.date() >= start]
        if end is not None:
            candles = [c for c in candles if c.timestamp.date() <= end]
        return candles

    def _daily_sentiment(self, asset: str, candles: Sequence[Candle]) -> list[Mapping[str, object]]:
        """Escora + agrega o sentimento diário na janela dos candles (DTO → `Row`)."""
        start = candles[0].timestamp
        end = candles[-1].timestamp
        sentiment_result = self._sentiment.execute(
            ScoreAndAggregateSentimentRequest(
                asset=asset, start=start, end=end, close_hour=self._close_hour
            )
        )
        return [
            {
                "day": dto.day,
                "sentiment_score": dto.sentiment_score,
                "news_volume": dto.n_articles,
                "sentiment_std": dto.sentiment_std,
            }
            for dto in sentiment_result.daily
        ]

    def _asof(self, asset: str, grid_days: Sequence[date]) -> list[Mapping[str, object]]:
        """Lê a bronze `fundamental`, calcula `effective_date` e faz o as-of backward."""
        rows = self._store.read(layer=_BRONZE, table=_FUNDAMENTAL_TABLE, filters={"asset": asset})
        reports: list[Mapping[str, object]] = []
        for row in rows:
            report = _row_to_report(row)
            reports.append(
                {
                    "effective_date": self._asof_policy.effective_date(report),
                    "revenue": report.revenue,
                    "net_income": report.net_income,
                    "operating_cash_flow": report.operating_cash_flow,
                    "total_shareholder_equity": report.total_shareholder_equity,
                    "total_liabilities": report.total_liabilities,
                }
            )
        return list(self._asof_join.asof_join_backward(grid_days=list(grid_days), reports=reports))


def _candle_to_row(candle: Candle) -> Mapping[str, object]:
    """Mapeia a entity `Candle` para a `Row` da fronteira do assembler (I7)."""
    return {
        "timestamp": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": float(candle.volume),
    }


def _row_to_candle(row: Mapping[str, object]) -> Candle:
    """Mapeia uma linha da bronze `candle` para a entity `Candle` (2.2)."""
    timestamp = row["timestamp"]
    if not isinstance(timestamp, datetime):
        raise ValueError("bronze candle row 'timestamp' must be a datetime")
    return Candle(
        asset=str(row["asset"]),
        timestamp=timestamp,
        open=_as_float(row["open"]),
        high=_as_float(row["high"]),
        low=_as_float(row["low"]),
        close=_as_float(row["close"]),
        volume=int(_as_float(row["volume"])),
    )


def _row_to_report(row: Mapping[str, object]) -> FundamentalReport:
    """Mapeia uma linha da bronze `fundamental` para a entity `FundamentalReport` (2.3)."""
    return FundamentalReport(
        asset_id=str(row["asset_id"]),
        report_type=str(row["report_type"]),
        fiscal_date_end=_as_date(row["fiscal_date_end"]),
        reported_date=_as_optional_date(row.get("reported_date")),
        revenue=_as_optional_float(row.get("revenue")),
        net_income=_as_optional_float(row.get("net_income")),
        operating_cash_flow=_as_optional_float(row.get("operating_cash_flow")),
        total_shareholder_equity=_as_optional_float(row.get("total_shareholder_equity")),
        total_liabilities=_as_optional_float(row.get("total_liabilities")),
        source=str(row.get("source", "")),
    )


def _as_date(value: object) -> date:
    """Coage para `date` (datetime → `.date()`); rejeita tipos inesperados."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError(f"expected a date, got {type(value).__name__}")


def _as_optional_date(value: object) -> date | None:
    """Coage para `date | None` (datetime → `.date()`; None/NaT → None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _as_float(value: object) -> float:
    """Coage um valor numérico (int/float/str) para `float`, rejeitando o resto."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"expected a numeric value, got {type(value).__name__}")
    return float(value)


def _as_optional_float(value: object) -> float | None:
    """Coage para `float | None` (None/não-numérico → None)."""
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
