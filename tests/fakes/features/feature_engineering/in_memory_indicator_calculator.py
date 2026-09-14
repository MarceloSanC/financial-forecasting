"""Fake in-memory do port `IndicatorCalculator` — NÃO um mock (concept 3.1 A5).

`FakeIndicatorCalculator` é um fake COMPORTAMENTAL determinístico (stdlib-only): para
cada `Candle` (ordenado por `timestamp`, espelhando o I9 do adapter real) devolve uma
`Mapping[str, float]` com EXATAMENTE as chaves de `INDICATOR_SPECS`. Honra a MESMA
FORMA do adapter real para passar o MESMO contract test parametrizado do port
(paridade fake↔real, concept 3.1 A6/Task 05):

- `candle_range`/`candle_body` são REAIS e causais (`high - low`, `|close - open|`) —
  derivados ponto-a-ponto da própria barra (`same_timestamp_ohlc_derived`).
- Os indicadores trailing (`rsi_14`/`macd`/`macd_signal`/`ema_*`/`volatility_20d`)
  são a FÓRMULA CANÔNICA calculada pelo oráculo puro de domínio
  (`indicator_formulas`, issue #32) em `float64`, com `NaN` nas primeiras `warmup`
  barras DECLARADAS de cada spec (I6 — o fake mascara ao warmup NOMINAL; o adapter
  real fica finito no warmup EFETIVO da lib, uma barra antes em `ema_N`/`rsi_14`).
  Antes da #32 eram placeholders (`close + índice*1e-3`) — o que tornava
  inverificável a extensão do validador anti-leakage do `DatasetAssembler` aos
  indicadores: o placeholder reprovaria na primeira comparação, então todo teste
  que alimenta o assembler com este fake exige a fórmula verdadeira.

O fake NÃO coage a `float32` (a fronteira de dtype é do adapter real, #67) — é a
diferença legítima entre as pernas, e é exatamente o que o validador do assembler
tolera (1 ulp de `float32`).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato agnóstico de
`pandas`/`pandas_ta_classic`: importa SÓ stdlib + a entity `Candle`, o registry de
domínio `INDICATOR_SPECS` e o oráculo `indicator_formulas`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from financial_forecasting.features.feature_engineering.domain.services import (
    indicator_formulas as f,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

# Tags do registry (evita comparar strings literais espalhadas).
_OHLC_TAG = "same_timestamp_ohlc_derived"


class FakeIndicatorCalculator:
    """Implementação in-memory determinística do contrato `IndicatorCalculator`.

    `calculate` ordena por `timestamp` (espelha o I9 do real) e devolve uma linha por
    barra com as chaves de `INDICATOR_SPECS`. Sequência vazia → lista vazia (C5).
    """

    def calculate(self, asset: str, candles: Sequence[Candle]) -> Sequence[Mapping[str, float]]:
        """Devolve uma `Mapping` por candle (ordenado por timestamp) com as chaves do registry."""
        ordered = sorted(candles, key=lambda c: c.timestamp)
        trailing = f.trailing_indicators([float(c.close) for c in ordered])
        rows: list[Mapping[str, float]] = []
        for index, candle in enumerate(ordered):
            row: dict[str, float] = {}
            for name, spec in INDICATOR_SPECS.items():
                if spec.anti_leakage_tag == _OHLC_TAG:
                    row[name] = self._ohlc_derived(name, candle)
                    continue
                value = trailing[name][index]
                # `NaN` legítimo durante o warmup DECLARADO (I6) — também onde o
                # oráculo ainda não tem valor (série curta).
                row[name] = math.nan if index < spec.warmup or value is None else value
            rows.append(row)
        return rows

    @staticmethod
    def _ohlc_derived(name: str, candle: Candle) -> float:
        """`candle_range`/`candle_body` reais e causais (mesma fórmula do adapter)."""
        if name == "candle_range":
            return float(candle.high - candle.low)
        if name == "candle_body":
            return float(abs(candle.close - candle.open))
        raise ValueError(f"Unexpected ohlc-derived indicator name: {name!r}")
