"""Contract test do `DatasetAssembler` (Task 03) — validadores anti-leakage.

Cobre concept 3.5 I2/I3/I4/I7 / C2/C3:

- happy path: monta um dataset sintético sem leakage; ordem de colunas = registry.
- I2/C2: injeta divergência sintética numa feature derivada → `AntiLeakageError`
  nomeando-a (re-derivação via oráculo puro `DerivedFeatures`).
- I2 (issue #32): a metade INDICADORES do oráculo — parametrizada em
  `[fake-indicators, pandas-ta-indicators]`, porque com placeholders a extensão seria
  inverificável e só o adapter real impõe a fronteira `float32` que a tolerância de
  1 ulp existe para atravessar: happy path nas duas pernas; deslocamento de UMA barra
  em `ema_50` → erro nomeando o indicador; valor fabricado no warmup do oráculo → erro;
  faltante pós-warmup declarado → erro; perturbação de 4 ulp32 → erro, 0.4 ulp → passa.
- I3/C3: `fundamentals_effective_date > day` → `AntiLeakageError` (guarda as-of).
- I4: invariante causal — anexar uma barra futura não muda o prefixo das features.
- regimes/flags em `float64` (D2 / ADR 3.5.0002).

Usa o `FakeIndicatorCalculator` (3.1) para os indicadores (fórmula canônica em
`float64`, mascarada ao warmup nominal) e dados OHLCV sintéticos determinísticos; os
testes da #32 rodam também com o `PandasTaIndicatorCalculator`. Não depende de
DuckDB/FinBERT.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pandera.pandas as pa
import pyarrow.parquet as pq
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas import (
    dataset_assembler as assembler_module,
)
from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.adapters.out.parquet.schemas.dataset_schema import (  # noqa: E501
    DATASET_TFT_SCHEMA,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
)
from financial_forecasting.features.feature_engineering.application.ports.out.indicator_calculator import (  # noqa: E501
    IndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
    IndicatorSpec,
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


def _build_inputs(
    *,
    effective_offset_days: int = 30,
    indicator_calculator: IndicatorCalculator | None = None,
) -> DatasetAssemblyInputs:
    """Monta os insumos sintéticos completos para o assembler."""
    candles = _candles()
    calculator = indicator_calculator or FakeIndicatorCalculator()
    indicators = calculator.calculate("AAPL", candles)
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


def test_assembled_frame_conforms_to_pandera_schema() -> None:
    """C7/A5 — o frame REAL montado satisfaz `DATASET_TFT_SCHEMA` (não só um frame
    hand-built conforme). Fecha o gap: antes a validação pandera nunca tocava a saída
    do assembler, mascarando divergências de dtype (asset_id object, flags float64).
    """
    assembler = DatasetAssembler()
    assembler.assemble(_build_inputs())
    frame = assembler._assembled["AAPL"]
    # Não levanta — o assembler já validou em `assemble`; re-validar prova a paridade.
    DATASET_TFT_SCHEMA.validate(frame)


def test_assembled_storage_dtypes_match_oracle_contract() -> None:
    """C7/A5 — dtypes de armazenamento batem o contrato físico/oráculo: asset_id
    `string`, news_volume/has_news/volume_spike_flag `int64` (sem NaN nas retidas).
    """
    assembler = DatasetAssembler()
    assembler.assemble(_build_inputs())
    frame = assembler._assembled["AAPL"]
    assert str(frame["asset_id"].dtype) == "string"
    for col in ("news_volume", "has_news", "volume_spike_flag"):
        assert str(frame[col].dtype) == "int64", col


def test_assemble_rejects_frame_violating_schema() -> None:
    """C7 (mutation guard) — se a montagem produzisse um dtype fora do contrato, o
    schema pandera invocado DENTRO de `assemble` rejeita antes de reter/persistir.

    Corrompe `target_return` para `string` após a montagem, antes da validação,
    provando que o branch de validação de schema NÃO é dead-code (inverter/pular a
    validação faria este teste falhar).
    """
    assembler = DatasetAssembler()
    inputs = _build_inputs()
    real_finalize = assembler._finalize_storage_dtypes

    def corrupt_dtype(frame: object) -> object:
        out = real_finalize(frame)  # type: ignore[arg-type]
        out["target_return"] = out["target_return"].astype("string")  # type: ignore[index]
        return out

    assembler._finalize_storage_dtypes = corrupt_dtype  # type: ignore[method-assign]

    with pytest.raises(pa.errors.SchemaError):
        assembler.assemble(inputs)
    # Frame corrompido NÃO foi retido (validação barrou antes do `self._assembled[...]`).
    assert "AAPL" not in assembler._assembled


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


# -- #32: metade INDICADORES do oráculo anti-leakage (fake e pandas-ta real) --------

_INDICATOR_CALCULATORS: dict[str, type[IndicatorCalculator]] = {
    "fake-indicators": FakeIndicatorCalculator,
    "pandas-ta-indicators": PandasTaIndicatorCalculator,
}
_PROBE_ROW = 150  # pós-warmup de todo indicador comparado (ema_50 = 50, rsi = 14)
_FLOAT32_ULP_EXPONENT_OFFSET = 24


def _float32_ulp(value: float) -> float:
    """Um ulp de float32 na magnitude de `value` (mesma conta do validador)."""
    return 2.0 ** (math.frexp(abs(value))[1] - _FLOAT32_ULP_EXPONENT_OFFSET)


def _assembler_with_indicator_patch(
    patch: object,
) -> DatasetAssembler:
    """Assembler cujo `_attach_indicators` aplica `patch(frame)` DEPOIS de anexar.

    Corrompe a coluna já anexada (o que o validador enxerga), não o insumo — isola a
    prova no validador, não no calculador.
    """
    assembler = DatasetAssembler()
    real_attach = assembler._attach_indicators

    def attach(frame: object, indicators: object) -> None:
        real_attach(frame, indicators)  # type: ignore[arg-type]
        patch(frame)  # type: ignore[operator]

    assembler._attach_indicators = attach  # type: ignore[method-assign]
    return assembler


@pytest.fixture(params=sorted(_INDICATOR_CALCULATORS))
def indicator_inputs(request: pytest.FixtureRequest) -> DatasetAssemblyInputs:
    """Insumos com indicadores do fake (float64) ou do pandas-ta real (float32)."""
    return _build_inputs(indicator_calculator=_INDICATOR_CALCULATORS[str(request.param)]())


def test_indicator_half_of_the_oracle_passes_the_real_assembler(
    indicator_inputs: DatasetAssemblyInputs,
) -> None:
    """Happy path #32 — os 11 indicadores batem com `indicator_formulas` nas duas pernas.

    Com o pandas-ta real é o fio que faltava (comentário 2 da #32): a fronteira
    `float32` do port cruza o validador dentro de 1 ulp; com o fake, a fórmula canônica
    em float64 bate exato.
    """
    result = DatasetAssembler().assemble(indicator_inputs)

    assert result.n_rows == _N - 1


def test_one_bar_shift_in_an_indicator_column_raises_naming_it(
    indicator_inputs: DatasetAssemblyInputs,
) -> None:
    """#32 — `ema_50` deslocada UMA barra (a classe do ADR 4.3.0001) → erro nomeando-a.

    Um `ema_50` correto na fórmula e deslocado de uma barra na montagem passava nos
    dois testes existentes (3.1 valida a fórmula isolada; 3.5 não conferia indicador).
    """

    def shift_ema_50(frame: object) -> None:
        frame["ema_50"] = frame["ema_50"].shift(1)  # type: ignore[index]

    with pytest.raises(AntiLeakageError, match=r"indicator 'ema_50'"):
        _assembler_with_indicator_patch(shift_ema_50).assemble(indicator_inputs)


def test_fabricated_value_inside_oracle_warmup_raises(
    indicator_inputs: DatasetAssemblyInputs,
) -> None:
    """#32 — valor finito onde o oráculo não tem (`ema_200` na linha 5) é fabricado → erro."""

    def fabricate(frame: object) -> None:
        frame.loc[5, "ema_200"] = 123.0  # type: ignore[attr-defined]

    with pytest.raises(AntiLeakageError, match=r"'ema_200' has a value at row 5 where"):
        _assembler_with_indicator_patch(fabricate).assemble(indicator_inputs)


def test_missing_value_after_declared_warmup_raises(
    indicator_inputs: DatasetAssemblyInputs,
) -> None:
    """#32 — `NaN` pós-warmup declarado onde o oráculo é finito é valor perdido → erro."""

    def drop_one(frame: object) -> None:
        frame.loc[_PROBE_ROW, "ema_50"] = math.nan  # type: ignore[attr-defined]

    with pytest.raises(
        AntiLeakageError, match=rf"'ema_50' missing at row {_PROBE_ROW} after its declared"
    ):
        _assembler_with_indicator_patch(drop_one).assemble(indicator_inputs)


@pytest.mark.parametrize(
    ("ulps", "should_raise"),
    [
        pytest.param(4.0, True, id="4-ulp32-raises"),
        pytest.param(0.4, False, id="0.4-ulp32-passes"),
    ],
)
def test_tolerance_is_one_ulp_of_float32(
    indicator_inputs: DatasetAssemblyInputs, ulps: float, should_raise: bool
) -> None:
    """#32 — a tolerância é 1 ulp de float32: +4 ulp reprova, +0.4 ulp passa.

    Fixa que o validador distingue "fórmula certa com dtype float32 no meio" (0.5 ulp
    de quantização) de qualquer outra coisa — as tolerâncias `rel=1e-4`/`abs=1e-3` dos
    testes da 3.1 são 4-5 ordens de grandeza acima disso.
    """

    def perturb(frame: object) -> None:
        value = float(frame.loc[_PROBE_ROW, "ema_50"])  # type: ignore[attr-defined]
        frame.loc[_PROBE_ROW, "ema_50"] = value + ulps * _float32_ulp(value)  # type: ignore[attr-defined]

    assembler = _assembler_with_indicator_patch(perturb)
    if should_raise:
        with pytest.raises(AntiLeakageError, match=r"'ema_50' diverges .*tolerance=1 ulp float32"):
            assembler.assemble(indicator_inputs)
    else:
        assembler.assemble(indicator_inputs)


def test_registry_indicator_without_pure_oracle_is_refused_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#32 — indicador novo no registry SEM oráculo puro ergue, em vez de passar sem conferir.

    É a guarda contra o falso verde de segunda ordem que a #32 existe para matar: o
    validador só é honesto se cobre TODO o registry; um `IndicatorSpec` que o oráculo não
    reproduz precisa reprovar o build, não ser ignorado. Substitui o registry visto pelo
    módulo do assembler por um com uma chave extra (o `MappingProxyType` real é imutável).
    """
    extra = IndicatorSpec(
        name="obv_probe",
        family="volume",
        source_cols=("close", "volume"),
        warmup=1,
        anti_leakage_tag="trailing_window_causal",
    )
    monkeypatch.setattr(
        assembler_module, "INDICATOR_SPECS", {**INDICATOR_SPECS, "obv_probe": extra}
    )

    with pytest.raises(AntiLeakageError, match=r"no pure oracle for indicators \['obv_probe'\]"):
        DatasetAssembler().assemble(_build_inputs())
