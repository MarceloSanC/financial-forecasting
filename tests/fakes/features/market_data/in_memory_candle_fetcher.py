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
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.asset_id import AssetId


class FakeCandleFetcher:
    """Implementação in-memory determinística do contrato `CandleFetcher`.

    `simulate_source_failure`: quando informado, o fake ergue o tipo do contrato para
    "origem indisponível" (`ApplicationError`) com essa mensagem no MESMO ponto em que
    o adapter real toca a origem — DEPOIS da validação da entrada (issue #69). É o
    que permite ao contract test provar que fake e real falham com o mesmo tipo.
    """

    def __init__(
        self,
        candles: list[Candle] | None = None,
        *,
        simulate_source_failure: str | None = None,
    ) -> None:
        # Cópia defensiva: o fake não compartilha estado mutável com o chamador.
        self._candles: list[Candle] = list(candles or [])
        self._simulate_source_failure = simulate_source_failure

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        """Devolve os candles pré-carregados de `symbol` no intervalo `[start, end]`.

        Aplica a fronteira do contrato (concept 2.2 C5): `start`/`end` tz-aware e
        `start <= end`. Filtra por `asset == symbol` e por `start <= ts <= end`.
        """
        require_tz_aware(start, "start")
        require_tz_aware(end, "end")
        if start > end:
            raise ValueError("start must be <= end")

        asset = AssetId.parse(symbol).value  # mesma identidade canônica do real (#69 c)
        if self._simulate_source_failure is not None:
            raise ApplicationError(self._simulate_source_failure) from ConnectionError(
                "simulated source failure"
            )
        return [
            candle
            for candle in self._candles
            if candle.asset == asset and start <= candle.timestamp <= end
        ]
