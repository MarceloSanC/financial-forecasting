"""Contract test #32 — paridade `PandasTaIndicatorCalculator` ↔ `indicator_formulas` a 1 ulp32.

O oráculo puro (`domain/services/indicator_formulas.py`) reproduz `pandas-ta-classic`
na MESMA ordem de operações; a única diferença legítima entre as duas saídas é a
fronteira de dtype do port (`float32`, I4 da 3.1). Por isso a tolerância aqui NÃO é
`rel=1e-4`/`abs=1e-3` (as dos testes de fórmula canônica da 3.1 — quatro a cinco
ordens de grandeza acima da quantização, o que a #32 apontou como cego a um
deslocamento de barra num indicador trailing), e sim **1 ulp de `float32` do valor
do oráculo**: `|adapter - oráculo| <= ulp32(oráculo)`. A quantização a `float32`
custa no máximo 0.5 ulp; qualquer diferença de fórmula, de semente ou de alinhamento
custa ordens de grandeza mais.

Duas séries: sintética (senoidal com tendência, 300 barras) e um passeio aleatório
geométrico de 4000 barras com semente fixa (tamanho do piloto AAPL) — nas duas, TODOS
os 11 indicadores (os 9 trailing + `candle_range`/`candle_body`) batem em 100% das
posições comparáveis, e o padrão de `NaN` do adapter coincide com o `None` do oráculo
posição a posição.

Guardas de anti-vacuidade: (a) o teste compara milhares de posições (não só o fim da
série); (b) um deslocamento de UMA barra no oráculo reprova; (c) a igualdade
`float32(oráculo) == adapter` também vale bit a bit — o que documenta que a tolerância
de 1 ulp é folga contra dependência de versão da lib, não um afrouxamento.
"""

from __future__ import annotations

import math
import random
import struct
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
)
from financial_forecasting.features.feature_engineering.domain.services import (
    derived_features as df_,
)
from financial_forecasting.features.feature_engineering.domain.services import (
    indicator_formulas as f,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

pytestmark = pytest.mark.contract

_BASE_TS = datetime(2015, 1, 1, tzinfo=UTC)
_N_SYNTHETIC = 300
_N_RANDOM_WALK = 4000
_RANDOM_WALK_SEED = 0
_MIN_COMPARED_FRACTION = 0.9  # ≥ 90% das posições pós-warmup são comparadas (anti-vacuidade)


def _ulp32(value: float) -> float:
    """Um ulp de `float32` na magnitude de `value` (`2^(e-24)` com `frexp`), piso subnormal."""
    if value == 0.0:
        return 2.0**-149
    return max(2.0 ** (math.frexp(abs(value))[1] - 24), 2.0**-149)


def _float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]  # type: ignore[no-any-return]


def _candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            asset="AAPL",
            timestamp=_BASE_TS + timedelta(days=i),
            open=close - 0.3,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000 + i,
        )
        for i, close in enumerate(closes)
    ]


def _synthetic_closes() -> list[float]:
    return [100.0 + math.sin(i / 9.0) * 4.0 + i * 0.04 for i in range(_N_SYNTHETIC)]


def _random_walk_closes() -> list[float]:
    rng = random.Random(_RANDOM_WALK_SEED)
    closes = [100.0]
    for _ in range(_N_RANDOM_WALK - 1):
        closes.append(closes[-1] * math.exp(rng.gauss(0.0004, 0.02)))
    return closes


def _oracle(candles: list[Candle]) -> dict[str, tuple[float | None, ...]]:
    """Os 11 indicadores do registry pelo oráculo puro (mesmas chaves de `INDICATOR_SPECS`)."""
    closes = [c.close for c in candles]
    return {
        **f.trailing_indicators(closes),
        "candle_range": df_.candle_range([c.high for c in candles], [c.low for c in candles]),
        "candle_body": df_.candle_body([c.open for c in candles], [c.close for c in candles]),
    }


@pytest.fixture(scope="module", params=["synthetic-300", "random-walk-4000"])
def series(request: pytest.FixtureRequest) -> tuple[list[Candle], list[dict[str, float]]]:
    closes = _synthetic_closes() if request.param == "synthetic-300" else _random_walk_closes()
    candles = _candles(closes)
    rows = [dict(row) for row in PandasTaIndicatorCalculator().calculate("AAPL", candles)]
    return candles, rows


@pytest.mark.parametrize("name", sorted(INDICATOR_SPECS))
def test_adapter_matches_pure_oracle_within_one_ulp32_everywhere(
    series: tuple[list[Candle], list[dict[str, float]]], name: str
) -> None:
    """Cada indicador: `NaN` ⇔ `None` posição a posição e `|adapter - oráculo| <= 1 ulp32`."""
    candles, rows = series
    expected = _oracle(candles)[name]
    compared = 0
    for index, (row, oracle_value) in enumerate(zip(rows, expected, strict=True)):
        built = row[name]
        if oracle_value is None:
            assert math.isnan(built), f"{name}[{index}]: adapter finito onde o oráculo é None"
            continue
        assert not math.isnan(built), f"{name}[{index}]: adapter NaN onde o oráculo é finito"
        assert abs(built - oracle_value) <= _ulp32(oracle_value), (
            f"{name}[{index}]: adapter={built!r} oráculo={oracle_value!r}"
        )
        compared += 1
    warmup = INDICATOR_SPECS[name].warmup
    assert compared >= _MIN_COMPARED_FRACTION * (len(rows) - warmup)


@pytest.mark.parametrize("name", sorted(INDICATOR_SPECS))
def test_adapter_equals_the_float32_rounding_of_the_oracle_bit_for_bit(
    series: tuple[list[Candle], list[dict[str, float]]], name: str
) -> None:
    """Mais forte que 1 ulp: `float32(oráculo) == adapter` em TODAS as posições comparáveis.

    Documenta que a tolerância de 1 ulp do teste anterior (e do validador do
    `DatasetAssembler`) é folga contra dependência de versão da lib, não afrouxamento:
    hoje a paridade é bit a bit.
    """
    candles, rows = series
    expected = _oracle(candles)[name]
    mismatches = [
        index
        for index, (row, oracle_value) in enumerate(zip(rows, expected, strict=True))
        if oracle_value is not None and _float32(oracle_value) != row[name]
    ]
    assert mismatches == []


def test_one_bar_shift_in_the_oracle_breaks_parity_control(
    series: tuple[list[Candle], list[dict[str, float]]],
) -> None:
    """Controle — o oráculo deslocado UMA barra reprova em (quase) toda posição.

    Prova que a tolerância de 1 ulp32 discrimina a classe de bug que a #32 persegue
    (ADR 4.3.0001: indexação deslocada num indicador trailing) — o deslocamento custa
    ordens de grandeza acima da quantização em todas as séries e indicadores.
    """
    candles, rows = series
    oracle = _oracle(candles)
    for name in ("ema_10", "ema_50", "rsi_14", "volatility_20d", "macd"):
        shifted = (None, *oracle[name][:-1])
        violations = sum(
            1
            for row, oracle_value in zip(rows, shifted, strict=True)
            if oracle_value is not None
            and not math.isnan(row[name])
            and abs(row[name] - oracle_value) > _ulp32(oracle_value)
        )
        comparable = sum(
            1
            for row, oracle_value in zip(rows, shifted, strict=True)
            if oracle_value is not None and not math.isnan(row[name])
        )
        assert violations >= _MIN_COMPARED_FRACTION * comparable, name
