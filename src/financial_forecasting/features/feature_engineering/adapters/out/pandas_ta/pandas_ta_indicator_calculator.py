"""Adapter `PandasTaIndicatorCalculator` — cálculo real via `pandas-ta-classic`.

ÚNICA casa de `pandas`/`pandas_ta_classic` no bounded context `feature_engineering`
(I12). Satisfaz o port `IndicatorCalculator` por duck-typing (NÃO herda da
`application`). Converte `Sequence[Candle]` → `DataFrame` ordenado por `timestamp`
(`.sort_values`, I9 — base da causalidade I2 e do alinhamento linha-a-barra), calcula
os indicadores do registry de domínio `INDICATOR_SPECS`, coage cada coluna a `float32`
(I4) e devolve `Sequence[Mapping[str, float]]` — os nomes de coluna do pandas-ta
(`RSI_14`/`MACD_12_26_9`/`MACDs_12_26_9`/`EMA_N`) NUNCA cruzam a fronteira (mapeados
para os nomes de `INDICATOR_SPECS`).

Fórmulas (concept 3.1 §4 / A6, validadas pela fixture-oráculo Task 06):
- `rsi_14` = `ta.rsi(close, length=14)` (smoothing de Wilder/RMA, não SMA).
- `macd`/`macd_signal` = `ta.macd(close)` lendo `MACD_12_26_9`/`MACDs_12_26_9`
  (defaults 12/26/9 = EMA12-EMA26 e signal = EMA9(MACD)).
- `ema_10/50/100/200` = `ta.ema(close, length=N)` (recursiva, alpha=2/(N+1)).
- `volatility_20d` = `close.pct_change().rolling(20).std()` (cálculo manual).
- `candle_range`/`candle_body` = DELEGADOS ao domínio
  (`derived_features.candle_range`/`candle_body`) — a fórmula não é reimplementada aqui.

Repartição de responsabilidade nas duas de candle (issue #67): o DOMÍNIO é dono da
FÓRMULA (`high - low`, `|close - open|` — aritmética pura, testável, portável) e este
ADAPTER é dono da FRONTEIRA DE DTYPE (o `astype("float32")` que o invariante I4 de
`IndicatorSpec` exige do port). É a repartição do Humble Object: o adapter fica com a
parte não-portável e cede a testável. Antes da #67 a aritmética morava inline aqui, sem
nenhuma chamada de biblioteca com conteúdo — código de domínio em infraestrutura.

I8/C2 — antes de devolver, valida que produziu EXATAMENTE as colunas de
`INDICATOR_SPECS` (`set(produzidas) == set(registry)`); divergência → erro explícito
(endurece o `RuntimeError("Missing technical indicators")` do old para igualdade de
conjunto). Sequência vazia → saída vazia (C5).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import pandas as pd
import pandas_ta_classic as ta

from financial_forecasting.features.feature_engineering.domain.services import (
    derived_features as df_,
)
from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle

# Janela do retorno realizado (volatility_20d): std rolling de pct_change.
_VOLATILITY_WINDOW = 20
# Comprimentos das EMAs (concept 3.1 §4).
_EMA_LENGTHS = (10, 50, 100, 200)
# Comprimento do RSI.
_RSI_LENGTH = 14
# Nomes de coluna do pandas-ta para o MACD (defaults 12/26/9). Internos ao adapter.
_MACD_LINE_COL = "MACD_12_26_9"
_MACD_SIGNAL_COL = "MACDs_12_26_9"


class PandasTaIndicatorCalculator:
    """Implementação real do contrato `IndicatorCalculator` sobre `pandas-ta-classic`."""

    def calculate(self, asset: str, candles: Sequence[Candle]) -> Sequence[Mapping[str, float]]:
        """Calcula os indicadores de `asset` para cada `Candle`, alinhado por barra (I9)."""
        if not candles:
            return []

        frame = self._to_sorted_frame(candles)
        indicators = self._compute_indicators(frame)
        self._require_complete_set(indicators)
        return self._to_rows(indicators)

    # -- pipeline ------------------------------------------------------------

    @staticmethod
    def _to_sorted_frame(candles: Sequence[Candle]) -> pd.DataFrame:
        """`Candle` → `DataFrame` ordenado por `timestamp` (I9), index reiniciado."""
        frame = pd.DataFrame(
            {
                "timestamp": [c.timestamp for c in candles],
                "open": [c.open for c in candles],
                "high": [c.high for c in candles],
                "low": [c.low for c in candles],
                "close": [c.close for c in candles],
                "volume": [c.volume for c in candles],
            }
        )
        return frame.sort_values("timestamp").reset_index(drop=True)

    def _compute_indicators(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Calcula os indicadores e coage cada coluna a `float32` (I4)."""
        close = frame["close"]
        out = pd.DataFrame(index=frame.index)

        out["rsi_14"] = ta.rsi(close, length=_RSI_LENGTH)

        macd = ta.macd(close)
        out["macd"] = macd[_MACD_LINE_COL]
        out["macd_signal"] = macd[_MACD_SIGNAL_COL]

        for length in _EMA_LENGTHS:
            out[f"ema_{length}"] = ta.ema(close, length=length)

        out["volatility_20d"] = close.pct_change().rolling(_VOLATILITY_WINDOW).std()

        # Candle (#67): a fórmula vem do domínio; aqui só a travessia da fronteira.
        out["candle_range"] = _from_domain(
            df_.candle_range(frame["high"].tolist(), frame["low"].tolist())
        )
        out["candle_body"] = _from_domain(
            df_.candle_body(frame["open"].tolist(), frame["close"].tolist())
        )

        return out.astype("float32")

    @staticmethod
    def _require_complete_set(indicators: pd.DataFrame) -> None:
        """I8/C2 — produziu EXATAMENTE as colunas de `INDICATOR_SPECS`, senão erro."""
        produced = set(indicators.columns)
        expected = set(INDICATOR_SPECS)
        if produced != expected:
            missing = expected - produced
            extra = produced - expected
            raise RuntimeError(
                "Technical indicator set mismatch vs INDICATOR_SPECS: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )

    @staticmethod
    def _to_rows(indicators: pd.DataFrame) -> list[Mapping[str, float]]:
        """`DataFrame` `float32` → uma `Mapping[str, float]` por barra (ordem preservada)."""
        names = list(INDICATOR_SPECS)
        return [{name: float(row[name]) for name in names} for _, row in indicators.iterrows()]


def _from_domain(values: df_.OutSeq) -> list[float]:
    """`OutSeq` do domínio → `list[float]`, traduzindo `None` (faltante) para `NaN`.

    Travessia de fronteira: o domínio fala `None` para faltante, a coluna pandas fala
    `NaN` — mesma semântica que a subtração de `Series` propagaria. A coerção a
    `float32` (I4) é aplicada depois, no `astype` de `_compute_indicators`.
    """
    return [math.nan if value is None else value for value in values]
