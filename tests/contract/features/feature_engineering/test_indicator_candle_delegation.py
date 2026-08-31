"""Contract test da delegação de `candle_range`/`candle_body` ao domínio (issue #67).

A #67 move a FÓRMULA das duas candle para `derived_features.py`; o adapter
`PandasTaIndicatorCalculator` passa a CHAMAR o domínio, mantendo o `astype("float32")`
(invariante I4 de `IndicatorSpec`). O contrato desta mudança é **valor bit-idêntico**:
nada no dataset pode mudar.

Por isso este módulo NÃO usa `pytest.approx` em lugar nenhum. Tolerância é exatamente
a cegueira que deixou o defeito original passar: os testes de contrato existentes
comparam candle com `rel=1e-4`/`abs=1e-3`, quatro a cinco ordens de grandeza acima da
quantização float32 (~5e-8) que a #65 vai tratar. Aqui a comparação é `==` sobre o
float e sobre o padrão de BITS (`struct.pack`), contra um baseline que reproduz
verbatim a implementação pré-#67.

Três frentes:

1. **Paridade bit-idêntica** — adapter atual == baseline pré-#67, bit a bit.
2. **Anti-vacuidade** — a fixture DISCRIMINA float32 de float64 (se os preços fossem
   exatamente representáveis em float32, a frente 1 passaria vazia).
3. **Delegação real** — trocar a função de domínio MUDA a saída do adapter, provando
   que ele chama o domínio em vez de reimplementar a fórmula.
"""

from __future__ import annotations

import math
import struct
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.pandas_ta.pandas_ta_indicator_calculator import (  # noqa: E501
    PandasTaIndicatorCalculator,
    _from_domain,
)
from financial_forecasting.features.feature_engineering.domain.services import (
    derived_features as df_,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

_ASSET = "AAPL"
_N_BARS = 300

# Valores presentes usados na travessia de fronteira `_from_domain` (evita magic values).
_PRESENT_LOW = 1.5
_PRESENT_HIGH = 2.5


def _candles(n: int = _N_BARS) -> list[Candle]:
    """Barras determinísticas com preços NÃO exatamente representáveis em float32.

    Os offsets quebrados (`1.0891`/`1.0313`/`0.2137`/`0.1873`) são deliberados: garantem
    que `high - low` e `|close - open|` em float64 divirjam do float32 do port, dando
    dentes ao teste de paridade (ver `test_fixture_discriminates_float32_from_float64`).

    As barras ALTERNAM alta e baixa (`close > open` nas pares, `close < open` nas ímpares).
    Sem a alternância, o `abs()` de `candle_body` ficaria sem cobertura no nível do
    contrato: uma fixture só de alta mantém `close - open` positivo e deixa a remoção do
    `abs()` passar despercebida pelo gate de paridade.
    """
    base = datetime(2020, 1, 1, tzinfo=UTC)
    out: list[Candle] = []
    for i in range(n):
        close = 187.4432 + math.sin(i / 7.0) * 5.0 + i * 0.05
        # par = barra de alta (abre abaixo); ímpar = barra de baixa (abre acima).
        open_ = close - 0.2137 if i % 2 == 0 else close + 0.1873
        out.append(
            Candle(
                asset=_ASSET,
                timestamp=base + timedelta(days=i),
                open=open_,
                high=close + 1.0891,
                low=close - 1.0313,
                close=close,
                volume=1_000_000 + i * 1000,
            )
        )
    return out


def _baseline_candle_columns(candles: list[Candle]) -> tuple[list[float], list[float]]:
    """Reproduz VERBATIM a implementação pré-#67 (aritmética inline no adapter).

    Espelha `_to_sorted_frame` + as duas linhas removidas de `_compute_indicators`
    (`frame["high"] - frame["low"]` / `(frame["close"] - frame["open"]).abs()`) + o
    `astype("float32")` final. É o "antes" do teste antes/depois.
    """
    frame = pd.DataFrame(
        {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    ).sort_values("timestamp")
    frame = frame.reset_index(drop=True)

    out = pd.DataFrame(index=frame.index)
    out["candle_range"] = frame["high"] - frame["low"]
    out["candle_body"] = (frame["close"] - frame["open"]).abs()
    out = out.astype("float32")
    return (
        [float(v) for v in out["candle_range"]],
        [float(v) for v in out["candle_body"]],
    )


def _bits(value: float) -> bytes:
    """Padrão de bits IEEE-754 do float — igualdade mais estrita que `==`.

    Distingue `+0.0` de `-0.0`, que `==` considera iguais. Usado para deixar a
    intenção do gate inequívoca: nada mudou, nem no último bit.
    """
    return struct.pack("<d", value)


@pytest.mark.contract
def test_candle_columns_are_bit_identical_to_pre_refactor_baseline() -> None:
    """GATE #67 — adapter atual == implementação pré-refactor, BIT A BIT (sem tolerância)."""
    candles = _candles()
    rows = PandasTaIndicatorCalculator().calculate(_ASSET, candles)
    baseline_range, baseline_body = _baseline_candle_columns(candles)

    assert len(rows) == len(candles)
    for index, row in enumerate(rows):
        assert _bits(row["candle_range"]) == _bits(baseline_range[index]), (
            f"candle_range divergiu na barra {index}: "
            f"{row['candle_range']!r} != {baseline_range[index]!r}"
        )
        assert _bits(row["candle_body"]) == _bits(baseline_body[index]), (
            f"candle_body divergiu na barra {index}: "
            f"{row['candle_body']!r} != {baseline_body[index]!r}"
        )


@pytest.mark.contract
def test_fixture_discriminates_float32_from_float64() -> None:
    """ANTI-VACUIDADE — a fixture detectaria uma regressão para float64.

    Se os preços fossem exatamente representáveis em float32, o teste de paridade
    passaria sem provar nada. Aqui afirmamos que o valor float64 exato DIFERE do que
    o port entrega em toda barra — é justamente essa lacuna (~5e-8, acima do `_ATOL`
    de 1e-9 do validador anti-vazamento) que a #65 vai fechar ao adotar float64.
    """
    candles = _candles()
    rows = PandasTaIndicatorCalculator().calculate(_ASSET, candles)

    divergent = sum(
        1
        for candle, row in zip(candles, rows, strict=True)
        if row["candle_range"] != candle.high - candle.low
    )
    assert divergent == len(candles), (
        "a fixture perdeu o poder de discriminação: os preços viraram exatamente "
        "representáveis em float32, e o gate de paridade passou a ser vazio"
    )


@pytest.mark.contract
def test_fixture_covers_both_bullish_and_bearish_bars() -> None:
    """ANTI-VACUIDADE do `abs()` — a fixture tem barra de alta E de baixa.

    `candle_body` é `|close - open|`. Numa fixture só de alta, `close - open` já é
    positivo e remover o `abs()` não mudaria valor nenhum — o gate de paridade passaria
    verde sobre um adapter quebrado.
    """
    candles = _candles()
    assert any(c.close > c.open for c in candles), "faltam barras de alta"
    assert any(c.close < c.open for c in candles), "faltam barras de baixa"


@pytest.mark.contract
def test_adapter_delegates_to_domain_instead_of_reimplementing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD #67 — nenhuma reimplementação da fórmula sobra no adapter.

    Prova comportamental (não `grep`): substituindo as funções de DOMÍNIO, a saída do
    adapter muda. Se ele ainda calculasse `high - low` inline, o sentinela não apareceria.
    """
    sentinel_range = 7.5
    sentinel_body = 2.25
    monkeypatch.setattr(df_, "candle_range", lambda high, low: tuple(sentinel_range for _ in high))
    monkeypatch.setattr(
        df_, "candle_body", lambda open_, close: tuple(sentinel_body for _ in open_)
    )

    rows = PandasTaIndicatorCalculator().calculate(_ASSET, _candles(30))

    assert [row["candle_range"] for row in rows] == [sentinel_range] * 30
    assert [row["candle_body"] for row in rows] == [sentinel_body] * 30


@pytest.mark.contract
def test_missing_ohlc_becomes_nan_column_not_none() -> None:
    """Fronteira `_from_domain`: `None` do domínio vira `NaN` na coluna (paridade pandas).

    O domínio devolve `None` para faltante; a coluna pandas precisa de `NaN`, que é o
    que a subtração de `Series` propagaria antes da #67. Sem essa tradução, a coluna
    viraria `object` e a coerção a `float32` quebraria.
    """
    first, missing, last = _PRESENT_LOW, None, _PRESENT_HIGH
    translated = _from_domain((first, missing, last))
    assert math.isnan(translated[1])
    # os valores presentes atravessam intactos (o `NaN` não contamina a série).
    assert translated[0] == _PRESENT_LOW
    assert translated[2] == _PRESENT_HIGH
