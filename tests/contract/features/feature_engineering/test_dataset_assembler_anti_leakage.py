"""Contract test do `DatasetAssembler` (Task 03) — validadores anti-leakage.

Cobre concept 3.5 I2/I3/I4/I7 / C2/C3:

- happy path: monta um dataset sintético sem leakage; ordem de colunas = registry.
- I2/C2: injeta divergência sintética numa feature derivada → `AntiLeakageError`
  nomeando-a (re-derivação via oráculo puro `DerivedFeatures`).
- I3/C3: `fundamentals_effective_date > day` → `AntiLeakageError` (guarda as-of).
- I4: invariante causal — anexar uma barra futura não muda o prefixo das features.
- regimes/flags em `float64` (D2 / ADR 3.5.0002).

Usa o `FakeIndicatorCalculator` (3.1) para os indicadores e dados OHLCV sintéticos
determinísticos. Não depende de DuckDB/FinBERT.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pyarrow.parquet as pq
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

_N = 300  # > maior warmup (252 YoY) para ter linhas pós-warmup avaliáveis


def _candles(n: int = _N) -> list[Candle]:
    """`n` candles OHLCV sintéticos determinísticos (preço crescente suave)."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    out: list[Candle] = []
    for i in range(n):
        close = 100.0 + math.sin(i / 7.0) * 5.0 + i * 0.05
        high = close + 1.0
        low = close - 1.0
        open_ = close - 0.2
        out.append(
            Candle(
                asset="AAPL",
                timestamp=base + timedelta(days=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1_000_000 + i * 1000,
            )
        )
    return out


def _candle_rows(candles: list[Candle]) -> list[dict[str, object]]:
    """Mapeia `Candle` para a `Row` da fronteira do port (timestamp + OHLCV)."""
    return [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": float(c.volume),
        }
        for c in candles
    ]


def _asof_rows(days: list[date], *, effective_offset_days: int = 30) -> list[dict[str, object]]:
    """1 linha as-of por dia: fundamentos constantes, `effective_date` no passado."""
    rows: list[dict[str, object]] = []
    for day in days:
        eff = day - timedelta(days=effective_offset_days)
        rows.append(
            {
                "day": day,
                "fundamentals_effective_date": eff,
                "revenue": 1000.0,
                "net_income": 100.0,
                "operating_cash_flow": 120.0,
                "total_shareholder_equity": 500.0,
                "total_liabilities": 250.0,
                "net_margin": 0.1,
                "leverage_ratio": 0.5,
                "cashflow_efficiency": 0.12,
            }
        )
    return rows


def _build_inputs(*, effective_offset_days: int = 30) -> DatasetAssemblyInputs:
    """Monta os insumos sintéticos completos para o assembler."""
    candles = _candles()
    indicators = FakeIndicatorCalculator().calculate("AAPL", candles)
    days = [c.timestamp.date() for c in candles]
    return DatasetAssemblyInputs(
        asset="AAPL",
        candles=_candle_rows(candles),
        indicators=list(indicators),
        daily_sentiment=[],  # sem sentimento → fillna(0.0) (paridade old)
        asof_rows=_asof_rows(days, effective_offset_days=effective_offset_days),
        grid_days=days,
    )


def test_happy_path_assembles_62_columns_in_registry_order() -> None:
    """Monta sem leakage; 62 colunas; ordem do bloco de feature = registry (I7)."""
    assembler = DatasetAssembler()
    result = assembler.assemble(_build_inputs())

    expected_cols = 62
    assert len(result.columns) == expected_cols
    assert result.n_rows == _N - 1  # drop da 1ª linha (alvo backward)
    # bloco de feature na ordem do registry, entre timestamp/asset_id e a cauda.
    assert result.columns[0] == "timestamp"
    assert result.columns[1] == "asset_id"
    assert result.columns[2 : 2 + len(result.feature_columns)] == result.feature_columns
    assert result.columns[-5:] == (
        "fundamentals_effective_date",
        "day_of_week",
        "month",
        "target_return",
        "time_idx",
    )


def test_anti_leakage_synthetic_divergence_raises_naming_feature() -> None:
    """I2/C2 — divergência sintética numa derivada → `AntiLeakageError` nomeando-a."""
    assembler = DatasetAssembler()
    inputs = _build_inputs()

    # Monkeypatch: corrompe a coluna `momentum_5d` APÓS o cálculo, antes da validação.
    real_attach = assembler._attach_price_derived

    def corrupt(frame: object) -> None:
        real_attach(frame)  # type: ignore[arg-type]
        frame.loc[100, "momentum_5d"] = 999.0  # type: ignore[attr-defined]

    assembler._attach_price_derived = corrupt  # type: ignore[method-assign]

    with pytest.raises(AntiLeakageError, match="momentum_5d"):
        assembler.assemble(inputs)


def test_asof_guard_raises_when_effective_date_in_future() -> None:
    """I3/C3 — `fundamentals_effective_date > day` levanta `AntiLeakageError`."""
    assembler = DatasetAssembler()
    inputs = _build_inputs(effective_offset_days=-30)  # effective_date = day + 30 (futuro)

    with pytest.raises(AntiLeakageError, match="posterior to sample date"):
        assembler.assemble(inputs)


def test_appending_future_bar_does_not_change_prefix() -> None:
    """I4 — anexar uma barra futura não muda o prefixo das features (causalidade)."""
    assembler = DatasetAssembler()
    candles = _candles()
    indicators = FakeIndicatorCalculator().calculate("AAPL", candles)
    days = [c.timestamp.date() for c in candles]

    short = DatasetAssemblyInputs(
        asset="AAPL",
        candles=_candle_rows(candles),
        indicators=list(indicators),
        daily_sentiment=[],
        asof_rows=_asof_rows(days),
        grid_days=days,
    )
    assembler.assemble(short)
    frame_short = assembler._assembled["AAPL"]

    candles_long = _candles(_N + 5)
    indicators_long = FakeIndicatorCalculator().calculate("AAPL", candles_long)
    days_long = [c.timestamp.date() for c in candles_long]
    long = DatasetAssemblyInputs(
        asset="AAPL",
        candles=_candle_rows(candles_long),
        indicators=list(indicators_long),
        daily_sentiment=[],
        asof_rows=_asof_rows(days_long),
        grid_days=days_long,
    )
    assembler.assemble(long)
    frame_long = assembler._assembled["AAPL"]

    # O prefixo das colunas de feature derivadas de janela trailing não muda.
    for col in ("log_return_5d", "vol_of_vol", "momentum_63d"):
        prefix_short = frame_short[col].tolist()
        prefix_long = frame_long[col].tolist()[: len(prefix_short)]
        for a, b in zip(prefix_short, prefix_long, strict=True):
            a_missing = a is None or (isinstance(a, float) and math.isnan(a))
            b_missing = b is None or (isinstance(b, float) and math.isnan(b))
            assert a_missing == b_missing
            if not a_missing:
                assert a == pytest.approx(b)


def test_regime_flag_columns_are_float64() -> None:
    """D2 / ADR 3.5.0002 — regimes/flags montados como float64 (com NaN no warmup)."""
    assembler = DatasetAssembler()
    assembler.assemble(_build_inputs())
    frame = assembler._assembled["AAPL"]
    for col in ("volatility_regime", "trend_regime", "stress_tail_return_flag"):
        assert str(frame[col].dtype) == "float64"


def test_persist_without_assemble_raises() -> None:
    """`persist` sem `assemble` prévio levanta erro claro."""
    assembler = DatasetAssembler()
    with pytest.raises(ValueError, match="no assembled dataset retained"):
        assembler.persist("AAPL")


def test_persist_writes_parquet_with_62_columns(tmp_path: object) -> None:
    """`persist` grava o Parquet processed com as 62 colunas do dataset montado."""
    assembler = DatasetAssembler(dataset_root=tmp_path)  # type: ignore[arg-type]
    assembler.assemble(_build_inputs())
    assembler.persist("AAPL")

    path = tmp_path / "AAPL" / "dataset_tft_AAPL.parquet"  # type: ignore[operator]
    assert path.exists()
    schema = pq.read_schema(path)
    expected_cols = 62
    assert len(schema.names) == expected_cols
    assert schema.names[0] == "timestamp"
    assert schema.names[-1] == "time_idx"


def test_sentiment_merge_path_populates_columns() -> None:
    """O merge de sentimento por dia preenche sentiment_score/news_volume/has_news."""
    inputs = _build_inputs()
    days = list(inputs.grid_days)
    daily_sentiment = [
        {"day": day, "sentiment_score": 0.3, "news_volume": 2, "sentiment_std": 0.1}
        for day in days[:50]  # sentimento só nos primeiros 50 dias
    ]
    populated = DatasetAssemblyInputs(
        asset=inputs.asset,
        candles=inputs.candles,
        indicators=inputs.indicators,
        daily_sentiment=daily_sentiment,
        asof_rows=inputs.asof_rows,
        grid_days=inputs.grid_days,
    )
    assembler = DatasetAssembler()
    assembler.assemble(populated)
    frame = assembler._assembled["AAPL"]

    # Onde houve sentimento, has_news=1 e news_volume>0; onde não, fillna(0).
    assert (frame["news_volume"] >= 0).all()
    assert set(frame["has_news"].unique()) <= {0, 1}
    assert (frame["sentiment_score"].abs() > 0).any()


def test_indicators_misaligned_raises() -> None:
    """Indicadores com contagem != candles levanta erro de alinhamento (1:1)."""
    inputs = _build_inputs()
    misaligned = DatasetAssemblyInputs(
        asset=inputs.asset,
        candles=inputs.candles,
        indicators=list(inputs.indicators)[:-3],  # 3 a menos
        daily_sentiment=inputs.daily_sentiment,
        asof_rows=inputs.asof_rows,
        grid_days=inputs.grid_days,
    )
    assembler = DatasetAssembler()
    with pytest.raises(ValueError, match="must align 1:1 with candles"):
        assembler.assemble(misaligned)
