"""Fake in-memory do port `IndicatorCalculator` — NÃO um mock (concept 3.1 A5).

`FakeIndicatorCalculator` é um fake COMPORTAMENTAL determinístico (stdlib-only): para
cada `Candle` (ordenado por `timestamp`, espelhando o I9 do adapter real) devolve uma
`Mapping[str, float]` com EXATAMENTE as chaves de `INDICATOR_SPECS`. Honra a MESMA
FORMA do adapter real para passar o MESMO contract test parametrizado do port
(paridade fake↔real, concept 3.1 A6/Task 05):

- `candle_range`/`candle_body` são REAIS e causais (`high - low`, `|close - open|`) —
  derivados ponto-a-ponto da própria barra (`same_timestamp_ohlc_derived`).
- Os indicadores trailing (`rsi_14`/`macd`/`macd_signal`/`ema_*`/`volatility_20d`)
  são placeholders FINITOS e DETERMINÍSTICOS pós-warmup (derivados do `close` e do
  índice da barra) e `NaN` durante o warmup declarado (I6) — o suficiente para um
  consumidor exercitar o contrato sem `pandas`. O fake NÃO calcula a fórmula canônica
  (isso é responsabilidade do adapter real, validado pela fixture-oráculo).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato agnóstico de
`pandas`/`pandas_ta_classic`: importa SÓ stdlib + a entity `Candle` e o registry de
domínio `INDICATOR_SPECS`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

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
        rows: list[Mapping[str, float]] = []
        for index, candle in enumerate(ordered):
            row: dict[str, float] = {}
            for name, spec in INDICATOR_SPECS.items():
                if spec.anti_leakage_tag == _OHLC_TAG:
                    row[name] = self._ohlc_derived(name, candle)
                elif index < spec.warmup:
                    # `NaN` legítimo durante o warmup declarado (I6).
                    row[name] = math.nan
                else:
                    # placeholder finito e determinístico pós-warmup (forma do contrato).
                    row[name] = float(candle.close) + index * 1e-3
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
