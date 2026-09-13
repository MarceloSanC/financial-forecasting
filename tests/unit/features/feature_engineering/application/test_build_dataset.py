"""Testes do use case `BuildDataset` (Task 05) — orquestração com FAKES dos ports.

Cobre concept 3.5 A2 / I1 / I6 / I7:

- happy path: result com `n_rows`/`n_features`/`feature_set_hash` corretos; o
  assembler real (fake) recebe candles/indicadores/sentimento/as-of alinhados.
- DTO frozen de entrada e saída; nunca devolve entity nem `DataFrame`.
- C1: menos de 2 candles → `ValueError` ("not enough rows to compute target_return").
- propagação de erro do gate (cobertura temporal impossível → `DatasetQualityError`).
- persistência delegada ao assembler (`persist(asset)` chamado).
- #72: a `DatasetQualityGateConfig` é OBRIGATÓRIA no construtor (sem fallback
  desarmado); o helper `_make_use_case` declara o limiar explicitamente.
- #72 (caminho wireado): o fake do assembler emite `None` no warmup (geometria do
  adapter real); feature com missing INTERIOR pós-warmup acima do limiar →
  `DatasetQualityError` e NADA é persistido; abaixo do limiar / `1.0` (desarme
  explícito) → passa.
- #83 (caminho wireado): feature cujo 1º finito excede o `warmup_count` nominal é
  acusada pela checagem absoluta (d) do gate — nomeando nominal e efetivo — mesmo com
  o ratio tolerante; controle: geometria nominal passa a 0.0.

Usa SÓ fakes (não mocks): `FakeMedallionStore`, `FakeIndicatorCalculator`,
`InMemorySentimentModel` (via `ScoreAndAggregateSentiment` real),
`FakeExchangeCalendarProvider`, `InMemoryAsofJoinAdapter`,
`InMemoryDatasetAssembler` — skill `pytest-with-fakes`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.application.use_cases.build_dataset import (
    BuildDataset,
    BuildDatasetRequest,
    BuildDatasetResult,
)
from financial_forecasting.features.feature_engineering.application.use_cases.score_and_aggregate_sentiment import (  # noqa: E501
    ScoreAndAggregateSentiment,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityError,
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
    get_feature_spec,
    list_feature_specs,
)
from tests.fakes.features.feature_engineering.in_memory_asof_join_adapter import (
    InMemoryAsofJoinAdapter,
)
from tests.fakes.features.feature_engineering.in_memory_dataset_assembler import (
    InMemoryDatasetAssembler,
)
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.shared.in_memory_exchange_calendar_provider import (
    FakeExchangeCalendarProvider,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_ASSET = "AAPL"
_N = 10
# Limiar estrito para os testes que NÃO exercitam missing (o fake emite 0.0 finito):
# com 0.0 qualquer missing pós-warmup reprovaria — o gate está ARMADO aqui.
_STRICT_GATE = DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0)


def _candle_rows(n: int = _N) -> list[dict[str, object]]:
    """`n` linhas bronze `candle` (dias úteis consecutivos a partir de 2024-01-01)."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(n):
        ts = base + timedelta(days=i)
        close = 100.0 + i
        rows.append(
            {
                "asset": _ASSET,
                "timestamp": ts,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + i,
            }
        )
    return rows


def _fundamental_rows() -> list[dict[str, object]]:
    """1 report bronze `fundamental` com `reported_date` no passado."""
    return [
        {
            "asset_id": _ASSET,
            "report_type": "quarterly",
            "fiscal_date_end": datetime(2023, 9, 30, tzinfo=UTC),
            "reported_date": datetime(2023, 10, 15, tzinfo=UTC),
            "revenue": 1000.0,
            "net_income": 100.0,
            "operating_cash_flow": 120.0,
            "total_shareholder_equity": 500.0,
            "total_liabilities": 250.0,
            "source": "test",
        }
    ]


def _make_use_case(
    *,
    store: FakeMedallionStore,
    assembler: InMemoryDatasetAssembler,
    gate_config: DatasetQualityGateConfig = _STRICT_GATE,
    n: int = _N,
) -> BuildDataset:
    """Monta o `BuildDataset` com fakes de todos os ports (gate declarado, #72)."""
    calendar_provider = FakeExchangeCalendarProvider(
        sessions=[date(2024, 1, 1) + timedelta(days=i) for i in range(n + 5)]
    )
    sentiment = ScoreAndAggregateSentiment(
        store=store,
        sentiment_model=InMemorySentimentModel(default_score=0.2),
        calendar_provider=calendar_provider,
    )
    return BuildDataset(
        store=store,
        indicator_calculator=FakeIndicatorCalculator(),
        sentiment=sentiment,
        asof_join=InMemoryAsofJoinAdapter(),
        assembler=assembler,
        quality_gate_config=gate_config,
    )


def _seed_store(n: int = _N) -> FakeMedallionStore:
    """`FakeMedallionStore` com candles + fundamentals + news vazia para AAPL."""
    store = FakeMedallionStore()
    store.write(layer="bronze", table="candle", rows=_candle_rows(n))
    store.write(layer="bronze", table="fundamental", rows=_fundamental_rows())
    return store


def test_happy_path_returns_frozen_result_with_hash_and_counts() -> None:
    """A2/I7 — result frozen com n_rows/n_features/feature_set_hash corretos."""
    store = _seed_store()
    assembler = InMemoryDatasetAssembler()
    use_case = _make_use_case(store=store, assembler=assembler)

    result = use_case.execute(BuildDatasetRequest(asset=_ASSET))

    assert isinstance(result, BuildDatasetResult)
    assert result.asset == _ASSET
    assert result.n_rows == _N - 1  # drop da 1ª linha (alvo backward)
    assert result.n_features == len(list_feature_specs())
    assert result.feature_set_hash == feature_set_hash()
    assert result.start == date(2024, 1, 2)  # 1ª linha cai
    assert result.end == date(2024, 1, 10)
    # persistência delegada ao assembler.
    assert assembler.persisted == [_ASSET]


def test_assembler_receives_aligned_inputs_from_all_four_families() -> None:
    """O assembler recebe candles/indicadores/sentimento/as-of alinhados por grade."""
    store = _seed_store()
    assembler = InMemoryDatasetAssembler()
    use_case = _make_use_case(store=store, assembler=assembler)

    use_case.execute(BuildDatasetRequest(asset=_ASSET))

    inputs = assembler.last_inputs
    assert inputs is not None
    assert len(inputs.candles) == _N
    assert len(inputs.indicators) == _N  # 1 indicador-row por barra (3.1)
    assert len(inputs.asof_rows) == _N  # 1 linha as-of por dia da grade (3.3)
    assert len(inputs.grid_days) == _N
    # sentimento agregado por dia: o fake escora todos os artigos (aqui news vazia → 0).
    assert all("fundamentals_effective_date" in row for row in inputs.asof_rows)


def test_fewer_than_two_candles_raises_c1() -> None:
    """C1 — menos de 2 candles levanta `ValueError` (alvo indefinível)."""
    store = FakeMedallionStore()
    store.write(layer="bronze", table="candle", rows=_candle_rows(1))
    store.write(layer="bronze", table="fundamental", rows=_fundamental_rows())
    use_case = _make_use_case(store=store, assembler=InMemoryDatasetAssembler())

    with pytest.raises(ValueError, match="not enough rows to compute target_return"):
        use_case.execute(BuildDatasetRequest(asset=_ASSET))


def test_quality_gate_error_propagates() -> None:
    """Propagação — gate com cobertura mínima impossível levanta `DatasetQualityError`.

    Exercita o ramo de COBERTURA TEMPORAL (C6), não o de NaN-ratio — o fake emite
    features finitas; a reprovação por missing tem teste próprio (#72).
    """
    store = _seed_store()
    use_case = _make_use_case(
        store=store,
        assembler=InMemoryDatasetAssembler(),
        gate_config=DatasetQualityGateConfig(
            max_nan_ratio_per_feature=0.0, min_temporal_coverage_days=10_000
        ),
    )

    with pytest.raises(DatasetQualityError, match="Temporal coverage insufficient"):
        use_case.execute(BuildDatasetRequest(asset=_ASSET))


def test_window_filter_narrows_candles() -> None:
    """A janela `[start, end]` filtra os candles antes da montagem."""
    store = _seed_store()
    assembler = InMemoryDatasetAssembler()
    use_case = _make_use_case(store=store, assembler=assembler)

    result = use_case.execute(
        BuildDatasetRequest(asset=_ASSET, start=date(2024, 1, 3), end=date(2024, 1, 7))
    )

    # 5 dias na janela (3,4,5,6,7) → drop da 1ª → 4 linhas.
    assert result.n_rows == 4  # noqa: PLR2004
    assert result.start == date(2024, 1, 4)
    assert result.end == date(2024, 1, 7)


# -- #72: gate ARMADO reprovando pelo caminho wireado (BuildDataset + fake com None) --


def test_quality_gate_rejects_missing_above_threshold_and_blocks_persist() -> None:
    """#72 — missing pós-warmup acima do limiar ergue `DatasetQualityError` via use case.

    `sentiment_score` (warmup nominal 0) com 1 `None` INTERIOR (linha 4) em 9 linhas
    retidas → ratio 0.1111 > 0.02. O erro nomeia feature e ratio, e `persist` NÃO é
    chamado: o gate roda ANTES da persistência. Antes da #72 este ramo era inalcançável
    (fake só `0.0` e limiar `1.0`). Interior, não à esquerda: `None` na linha 0 de uma
    feature de warmup 0 é warmup subdeclarado — checagem absoluta (d), #83.
    """
    store = _seed_store()
    assembler = InMemoryDatasetAssembler(missing_rows={"sentiment_score": {4}})
    use_case = _make_use_case(
        store=store,
        assembler=assembler,
        gate_config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.02),
    )

    with pytest.raises(
        DatasetQualityError, match=r"NaN-ratio above 0\.02.*sentiment_score=0\.1111"
    ):
        use_case.execute(BuildDatasetRequest(asset=_ASSET))
    assert assembler.persisted == []


@pytest.mark.parametrize(
    "threshold",
    [
        pytest.param(0.2, id="below-threshold"),
        pytest.param(1.0, id="explicitly-disarmed"),
    ],
)
def test_quality_gate_passes_same_missing_when_within_threshold_control(threshold: float) -> None:
    """Controle #72 — o MESMO missing (0.1111) passa com limiar acima dele ou `1.0`.

    Prova que a reprovação do teste anterior vem do limiar, não do fake: com 0.2 o
    ratio 0.1111 cabe; com `1.0` (desarme explícito) nunca reprova — o defeito original,
    agora só alcançável por declaração.
    """
    store = _seed_store()
    assembler = InMemoryDatasetAssembler(missing_rows={"sentiment_score": {4}})
    use_case = _make_use_case(
        store=store,
        assembler=assembler,
        gate_config=DatasetQualityGateConfig(max_nan_ratio_per_feature=threshold),
    )

    result = use_case.execute(BuildDatasetRequest(asset=_ASSET))

    assert result.n_rows == _N - 1
    assert assembler.persisted == [_ASSET]


def test_quality_gate_flags_feature_whose_effective_warmup_exceeds_nominal() -> None:
    """#83 — 1º finito além do `warmup_count` nominal é acusado pela checagem absoluta (d).

    Modela a geometria que a #72 mediu no `DatasetAssembler` real (`trend_regime`:
    nominal 63 vs efetivo 112 — `ema_50` em warmup + shift(1) + rolling(63)) como um
    excesso de 49 linhas sobre o nominal ATUAL do registry, e prova que o gate a acusa
    pela checagem absoluta — nomeando nominal e efetivo — MESMO com o ratio desarmado
    (`1.0`), que é o instrumento que o #80 apontou como errado para este defeito (o
    ratio depende de N; o excesso não). `persist` NÃO é chamado.
    """
    n = 200
    nominal = get_feature_spec("trend_regime").warmup_count
    effective = nominal + 49
    store = _seed_store(n)
    assembler = InMemoryDatasetAssembler(effective_warmup={"trend_regime": effective})
    use_case = _make_use_case(
        store=store,
        assembler=assembler,
        gate_config=DatasetQualityGateConfig(max_nan_ratio_per_feature=1.0),
        n=n,
    )

    with pytest.raises(
        DatasetQualityError,
        match=rf"Effective warmup exceeds.*trend_regime: first finite at row {effective}"
        rf" > warmup_count {nominal}",
    ):
        use_case.execute(BuildDatasetRequest(asset=_ASSET))
    assert assembler.persisted == []


def test_quality_gate_passes_when_effective_warmup_matches_nominal_control() -> None:
    """Controle #72/#83 — mesma fixture (200 candles) sem excesso de warmup → passa a 0.0.

    O fake emite `None` exatamente no warmup NOMINAL de cada feature (geometria
    default); a checagem absoluta (d) passa (`1º finito == nominal`) e o ratio mede 0
    em todas → nada a acusar, mesmo com o limiar mais estrito. Isola a causa do teste
    anterior no excesso.
    """
    n = 200
    store = _seed_store(n)
    assembler = InMemoryDatasetAssembler()
    use_case = _make_use_case(store=store, assembler=assembler, gate_config=_STRICT_GATE, n=n)

    result = use_case.execute(BuildDatasetRequest(asset=_ASSET))

    assert result.n_rows == n - 1
    assert assembler.persisted == [_ASSET]
