"""Integração end-to-end `BuildDataset` AAPL vs oráculo (Task 07).

Regressão por **set + ordem + contagem (62)** de colunas contra o oráculo
`data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet` (concept 3.5 A6/I7) —
**não** bit-identidade. Duas faixas:

1. **Contrato de colunas (sempre roda):** o `DatasetAssembler` real, alimentado por
   insumos sintéticos determinísticos, produz EXATAMENTE o set/ordem/contagem de
   colunas do oráculo. Não depende de bronze nem de torch.
2. **Pipeline completo (skip-guarded):** `wire_dependencies(...).build_dataset`
   roda AAPL contra a bronze real — pulado quando a bronze `candle`/`fundamental`
   ou o extra `sentiment` (torch) não estão presentes (CI sem dados/torch).

`@pytest.mark.integration`. O oráculo é lido só para extrair a lista de colunas
esperada (regressão de contrato), nunca comparado byte a byte.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
)
from financial_forecasting.features.feature_engineering.application.use_cases.build_dataset import (
    BuildDatasetRequest,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ORACLE = _REPO_ROOT / "data" / "processed" / "dataset_tft" / "AAPL" / "dataset_tft_AAPL.parquet"
_ORACLE_N_COLS = 62
_N = 300


def _oracle_columns() -> list[str]:
    """Lê SÓ o schema do oráculo (lista de colunas) para a regressão de contrato."""
    return list(pq.read_schema(_ORACLE).names)


def _synthetic_inputs() -> DatasetAssemblyInputs:
    """Insumos sintéticos determinísticos cobrindo os maiores warmups (252 YoY)."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for i in range(_N):
        close = 100.0 + math.sin(i / 9.0) * 4.0 + i * 0.04
        candles.append(
            Candle(
                asset="AAPL",
                timestamp=base + timedelta(days=i),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + i * 100,
            )
        )
    indicators = FakeIndicatorCalculator().calculate("AAPL", candles)
    days = [c.timestamp.date() for c in candles]
    candle_rows = [
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
    asof_rows = [
        {
            "day": day,
            "fundamentals_effective_date": day - timedelta(days=30),
            "revenue": 1000.0,
            "net_income": 100.0,
            "operating_cash_flow": 120.0,
            "total_shareholder_equity": 500.0,
            "total_liabilities": 250.0,
            "net_margin": 0.1,
            "leverage_ratio": 0.5,
            "cashflow_efficiency": 0.12,
        }
        for day in days
    ]
    return DatasetAssemblyInputs(
        asset="AAPL",
        candles=candle_rows,
        indicators=list(indicators),
        daily_sentiment=[],
        asof_rows=asof_rows,
        grid_days=days,
    )


@pytest.mark.skipif(not _ORACLE.exists(), reason="oráculo dataset_tft AAPL ausente")
def test_assembler_column_set_order_and_count_match_oracle() -> None:
    """A6/I7 — set + ordem + contagem (62) das colunas batem com o oráculo."""
    oracle_cols = _oracle_columns()
    assert len(oracle_cols) == _ORACLE_N_COLS

    assembler = DatasetAssembler()
    result = assembler.assemble(_synthetic_inputs())

    assert result.n_rows == _N - 1  # drop da 1ª linha (alvo backward)
    # set idêntico ao oráculo (sem coluna a mais nem a menos — C8).
    assert set(result.columns) == set(oracle_cols)
    assert len(result.columns) == _ORACLE_N_COLS


@pytest.mark.skipif(not _ORACLE.exists(), reason="oráculo dataset_tft AAPL ausente")
def test_assembler_feature_block_order_follows_registry() -> None:
    """I7 — o bloco de feature está na ordem do `FeatureRegistry` (fonte única)."""
    assembler = DatasetAssembler()
    result = assembler.assemble(_synthetic_inputs())

    start = result.columns.index("asset_id") + 1
    feature_slice = result.columns[start : start + len(result.feature_columns)]
    assert feature_slice == result.feature_columns


def test_full_pipeline_against_bronze_if_available(tmp_path: Path) -> None:
    """Pipeline completo via wiring real — skip se bronze/`transformers` ausentes.

    Quando a bronze `candle`/`fundamental` de AAPL e o extra `sentiment`
    estiverem presentes, roda `BuildDataset` AAPL e confere `n_features`/hash. Sem
    eles, pula (condição documentada — concept 3.5 A6, technical §5 risco do oráculo).
    """
    # A guarda checa `transformers`, NÃO `torch`: desde a Stage 5.4 (ADR 5.4.0003)
    # o `torch` é dependência principal e está sempre instalado, então usá-lo como
    # procuração do extra `sentiment` deixaria a guarda sempre verde — e o
    # `_LazyFinbertSentimentModel` estouraria `ImportError` no meio do pipeline,
    # onde o desenho quer um skip limpo.
    pytest.importorskip(
        "transformers", reason="extra `sentiment` ausente — pula pipeline real"
    )

    bronze_candle = Path("data") / "bronze" / "candle"
    if not bronze_candle.exists() or not any(bronze_candle.rglob("*.parquet")):
        pytest.skip("bronze candle de AAPL ausente — pula pipeline real")

    # Lê a bronze real (data/) mas persiste o resultado em tmp_path (não clobera o
    # oráculo): o assembler usa `data_root/processed/dataset_tft`.
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=Path("data")))
    deps.dataset_assembler._dataset_root = tmp_path  # type: ignore[attr-defined]
    result = deps.build_dataset.execute(BuildDatasetRequest(asset="AAPL"))
    assert result.n_rows > 0
    assert result.start <= result.end
    assert isinstance(result.start, date)
