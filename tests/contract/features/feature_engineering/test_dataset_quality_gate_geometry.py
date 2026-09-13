"""Contract test #72/#83 — geometria warmup nominal vs efetivo no frame REAL montado.

Fixa que o `warmup_count` declarado no registry cobre o warmup EFETIVO de CADA feature
quando o `DatasetQualityGate` recebe `feature_rows` do `DatasetAssembler` real (pandas
+ oráculo `DerivedFeatures`) sobre candles sintéticos determinísticos — e, por
consequência, que o gate mais estrito possível (ratio 0.0 + checagem absoluta (d))
PASSA no frame real. Parametrizado nos DOIS calculadores de indicadores: o
`FakeIndicatorCalculator` (NaN durante o warmup NOMINAL de cada indicador — a
geometria em que a conta do registry é exata) e o `PandasTaIndicatorCalculator` real
(a geometria de produção — a única que importa para o dataset AAPL).

Medido (300 candles → 299 linhas pós-drop), antes e depois da #83:

- `volatility_regime`: 1º finito na linha 82 nos dois calculadores (`volatility_20d`
  warmup 20 + shift(1) + rolling(63), menos o drop da 1ª linha). Nominal era 63
  (excesso +19); hoje 82.
- `trend_regime`: 1º finito na linha 112 com o fake (`ema_50` warmup nominal 50 +
  shift(1) + rolling(63), idem) e **111** com o pandas-ta real — `ta.ema(length=50)`
  semeia com SMA em `length-1` e fica finita uma barra ANTES do warmup nominal do
  indicador. Nominal era 63 (excesso +49); hoje 112, cota superior das duas geometrias.
- TODAS as outras 53 features: 1º finito `<=` nominal (a maioria a `-1`, pelo drop da
  1ª linha; `vol_of_vol` — o exemplo da #72 — já declarava 40 e mede 38).

Os dois excessos eram **débito de declaração do registry** (finding #72), tolerado pelo
limiar 0.02 no tamanho do piloto (0.0048/0.0124) por dependência de N — e é por isso
que a #83 levou a checagem para dentro do gate como ABSOLUTA (linhas, não ratio). A
sentinela `_KNOWN_EXCESS_WARMUP` está VAZIA desde a reconciliação: qualquer feature
que volte a subdeclarar o warmup reaparece aqui com o excesso medido.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
    DatasetAssemblyResult,
)
from financial_forecasting.features.feature_engineering.application.ports.out.indicator_calculator import (  # noqa: E501
    IndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityGate,
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    get_feature_spec,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

pytestmark = pytest.mark.contract

_N = 300  # > maior warmup (252 YoY): toda feature tem linhas pós-warmup avaliáveis
# Excesso MEDIDO de warmup efetivo sobre o nominal, por feature (linhas). Sentinela do
# finding #72 — VAZIA desde a reconciliação do registry (#83): era
# `{"volatility_regime": 19, "trend_regime": 49}`.
_KNOWN_EXCESS_WARMUP: dict[str, int] = {}
# Geometria medida no frame real, por calculador de indicadores (#83). O registry
# declara a cota superior (82/112); o pandas-ta real mede `trend_regime` em 111 porque
# `ta.ema(length=50)` fica finita em `length-1` (semente SMA), 1 barra antes do nominal.
_MEASURED_FIRST_FINITE: dict[str, dict[str, int]] = {
    "fake-indicators": {"volatility_regime": 82, "trend_regime": 112},
    "pandas-ta-indicators": {"volatility_regime": 82, "trend_regime": 111},
}
_INDICATOR_CALCULATORS: dict[str, type[IndicatorCalculator]] = {
    "fake-indicators": FakeIndicatorCalculator,
    "pandas-ta-indicators": PandasTaIndicatorCalculator,
}


def _synthetic_inputs(
    indicator_calculator: IndicatorCalculator, n: int = _N
) -> DatasetAssemblyInputs:
    """Insumos sintéticos determinísticos (mesma forma dos contract tests do assembler)."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for i in range(n):
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
    indicators = indicator_calculator.calculate("AAPL", candles)
    days: list[date] = [c.timestamp.date() for c in candles]
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
        daily_sentiment=[],  # sem sentimento → fillna(0.0) (paridade old)
        asof_rows=asof_rows,
        grid_days=days,
    )


@pytest.fixture(scope="module", params=sorted(_INDICATOR_CALCULATORS))
def indicator_leg(request: pytest.FixtureRequest) -> str:
    """Perna do calculador de indicadores: fake (warmup nominal) ou pandas-ta (produção)."""
    return str(request.param)


@pytest.fixture(scope="module")
def assembled(indicator_leg: str) -> DatasetAssemblyResult:
    """Frame real montado UMA vez por perna (pandas + oráculo puro das derivadas)."""
    calculator = _INDICATOR_CALCULATORS[indicator_leg]()
    return DatasetAssembler().assemble(_synthetic_inputs(calculator))


def _first_finite_index(result: DatasetAssemblyResult, col: str) -> int:
    """Índice (pós-drop) da 1ª linha com valor não-faltante de `col`; -1 se nunca."""
    for index, row in enumerate(result.feature_rows):
        if row.get(col) is not None:
            return index
    return -1


def test_only_known_features_have_effective_warmup_beyond_nominal(
    assembled: DatasetAssemblyResult,
) -> None:
    """Geometria — NENHUMA feature tem 1º finito além do nominal (sentinela vazia, #83).

    Para cada feature do registry mede o 1º índice finito no frame real e compara com
    `warmup_count`. Excessos positivos devem ser EXATAMENTE os da sentinela (hoje
    nenhum); qualquer feature com excesso — ou nunca finita em 299 linhas — reprova (o
    registry passou a subdeclarar um warmup).
    """
    excess: dict[str, int] = {}
    for col in assembled.feature_columns:
        first = _first_finite_index(assembled, col)
        assert first >= 0, f"{col}: nunca finita em {assembled.n_rows} linhas"
        nominal = get_feature_spec(col).warmup_count
        if first > nominal:
            excess[col] = first - nominal

    assert excess == _KNOWN_EXCESS_WARMUP


@pytest.mark.parametrize("name", ["volatility_regime", "trend_regime"])
def test_regime_first_finite_is_the_measured_one_and_declared_is_its_upper_bound(
    assembled: DatasetAssemblyResult, indicator_leg: str, name: str
) -> None:
    """#83 — 1º finito medido por perna (82/112 fake; 82/111 pandas-ta) e declarado = cota.

    Igualdade por perna fixa a geometria (não só `<=`, que o teste anterior garante):
    uma mudança de janela, de insumo ou do adapter de indicadores muda o número e
    obriga a rever a declaração. O declarado é o MÁXIMO entre as pernas — com o fake os
    insumos ficam finitos exatamente no warmup nominal (`ema_50` = 50) e a conta
    `input + 1 + 62 - 1` é exata; o pandas-ta real fica 1 barra à frente em `ema_50`,
    e essa folga é do indicador (declara 50, entrega em 49), não do regime.
    """
    measured = _MEASURED_FIRST_FINITE[indicator_leg][name]
    declared = get_feature_spec(name).warmup_count

    assert _first_finite_index(assembled, name) == measured
    assert declared == max(leg[name] for leg in _MEASURED_FIRST_FINITE.values())
    assert measured <= declared


def test_strictest_gate_passes_the_real_frame(assembled: DatasetAssemblyResult) -> None:
    """O gate mais estrito (ratio 0.0 + checagem absoluta (d)) PASSA no frame real (#83).

    Antes da #83 este frame reprovava a 0.0 nomeando `trend_regime` (0.2076) e
    `volatility_regime` (0.0805); com o registry reconciliado, o gate desconta o warmup
    certo de cada feature e não há missing interior a acusar. É a forma positiva da
    sentinela: se alguma feature voltar a subdeclarar, (d) reprova aqui com nominal e
    efetivo na mensagem.
    """
    DatasetQualityGate().validate(
        timestamps=list(assembled.timestamps),
        rows=list(assembled.feature_rows),
        feature_cols=list(assembled.feature_columns),
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )
