"""Port-out `IndicatorCalculator` (`Protocol`) — cálculo de indicadores técnicos.

`IndicatorCalculator` é o port secundário (driven) do bounded context
`feature_engineering`: abstrai O CÁLCULO dos indicadores técnicos a partir de uma
sequência de `Candle`. A `application` (consumidor futuro 3.5 `build_dataset`)
depende SÓ deste `Protocol` estrutural; o adapter concreto
(`PandasTaIndicatorCalculator`) o satisfaz por duck-typing (NÃO herda da
`application`, ao contrário da ABC do old `interfaces/technical_indicator_calculator.py`).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `MedallionStore` (2.1), `ExperimentTracker` (1.5) e `CandleFetcher`
(2.2). Importa a entity `Candle` do `domain` de `market_data` em runtime — a
`application` pode importar `domain`, inclusive de outro BC (LAYOUT §3/§7; concept
3.1 §7 D3).

I5 — o port NÃO vaza pandas/DataFrame: a fronteira troca
`Sequence[Candle]` → `Sequence[Mapping[str, float]]` (uma `Mapping` por barra). Os
nomes de coluna do pandas-ta (`MACD_12_26_9`/`MACDs_12_26_9`) NUNCA cruzam a
fronteira — ficam internos ao adapter. NUNCA importa
`adapters`/`pandas`/`pyarrow`/`pandas_ta_classic` (inward-only; `store-no-storage-leak`
estendido ao BC na Task 08; concept 3.1 I5/I11/I12).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from financial_forecasting.features.market_data.domain.entities.candle import Candle


class IndicatorCalculator(Protocol):
    """Contrato de cálculo de indicadores técnicos, agnóstico de biblioteca.

    Semântica garantida por qualquer implementação (concept 3.1 §4 D3):

    - **Alinhamento 1-barra → 1-linha:** devolve uma `Mapping[str, float]` por
      `Candle` de entrada, na ORDEM TEMPORAL após ordenação por `timestamp` (a
      ordenação é responsabilidade do adapter; concept 3.1 I9).
    - **Chaves = nomes de `INDICATOR_SPECS`:** cada `Mapping` carrega exatamente as
      colunas do registry de domínio (validação de set completo no adapter; I8/C2).
    - **Valores `float`:** materializados em `float32` pelo adapter (I4); na fronteira
      do port trafegam como `float` Python.
    - **`NaN` só no warmup:** `NaN` é tolerado APENAS durante o warmup declarado de
      cada indicador (efetivo para `volatility_20d`); pós-warmup os valores são
      finitos (I6). Sequência vazia → saída vazia (C5).
    """

    def calculate(self, asset: str, candles: Sequence[Candle]) -> Sequence[Mapping[str, float]]:
        """Calcula os indicadores de `asset` para cada `Candle`, alinhado por barra."""
        ...
