"""Fake in-memory do port `CandleFetcher` — NÃO um mock (concept 2.2 A4).

`FakeCandleFetcher` é um fake COMPORTAMENTAL determinístico (stdlib-only): devolve
uma `list[Candle]` pré-carregada, filtrando pelo intervalo `[start, end]` e
aplicando a MESMA semântica de fronteira do adapter real (`start`/`end` tz-aware,
`start <= end` → `ValueError`). Não asserta chamadas — produz comportamento real
e estável, para passar o MESMO contract test parametrizado do port que o
`ParquetRawCandleFetcher` (paridade fake↔real, concept 2.2 I14).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato
agnóstico de `pandas`/`pyarrow`: só `datetime` + a entity `Candle`.
"""

from __future__ import annotations

from datetime import datetime

from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware


class FakeCandleFetcher:
    """Implementação in-memory determinística do contrato `CandleFetcher`."""

    def __init__(self, candles: list[Candle] | None = None) -> None:
        # Cópia defensiva: o fake não compartilha estado mutável com o chamador.
        self._candles: list[Candle] = list(candles or [])

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        """Devolve os candles pré-carregados de `symbol` no intervalo `[start, end]`.

        Aplica a fronteira do contrato (concept 2.2 C5): `start`/`end` tz-aware e
        `start <= end`. Filtra por `asset == symbol` e por `start <= ts <= end`.
        """
        require_tz_aware(start, "start")
        require_tz_aware(end, "end")
        if start > end:
            raise ValueError("start must be <= end")

        return [
            candle
            for candle in self._candles
            if candle.asset == symbol and start <= candle.timestamp <= end
        ]
