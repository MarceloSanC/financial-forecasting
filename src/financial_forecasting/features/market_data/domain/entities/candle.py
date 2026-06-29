"""Entity `Candle` — barra OHLCV diária de um ativo (domínio puro, stdlib-only).

`Candle` é a entity de domínio do bounded context `market_data`: identidade
lógica `(asset, timestamp)` (mesma PK lógica da bronze `candle`, Stage 2.1) e
invariantes OHLC FORTES validadas na construção (`__post_init__`). Endurece o old
(`financial-time-series-forecasting/src/entities/candle.py`), que só checava
`close>0`/`volume>=0` — aqui as relações OHLC canônicas são obrigatórias.

Domínio puro: importa SÓ `dataclasses` + `datetime` (stdlib). Sem
`pandas`/`pyarrow`/`pydantic` — o gate `import-linter` `hexagonal-layers`/
`domain-purity` reprova qualquer vazamento (concept 2.2 I8).

Invariantes (concept 2.2 §5, levantadas como `ValueError` em violação):

- **I1 — OHLC consistente.** `high >= max(open, close)`, `low <= min(open, close)`,
  `high >= low`.
- **I2 — Não-negatividade OHLCV.** `open/high/low/close/volume >= 0`.
- **I3 — Sem nulos.** Nenhum campo é `None` (frozen não impede `None`).
- **I4 — Timestamp tz-aware.** `timestamp.tzinfo` não pode ser `None` (naive →
  `ValueError`). A NORMALIZAÇÃO a `00:00 UTC` é feita na fronteira do adapter
  (Tasks 05/06), não aqui — a entity exige apenas tz-aware.
- **I5 — Identidade `(asset, timestamp)`.** `asset` é parte da identidade; a
  invariante de coleção "sem duplicados" (I6) é do agregado/`MedallionStore`, não
  desta entity (concept 2.2 D5).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Barra OHLCV diária imutável com invariantes OHLC fortes (concept 2.2 §5).

    Identidade lógica: `(asset, timestamp)`. `timestamp` é tz-aware (UTC no
    pipeline; no diário, normalizado a `00:00 UTC` pelo adapter que constrói a
    `Candle`). Construir uma `Candle` que viole qualquer invariante levanta
    `ValueError` antes de qualquer escrita (concept 2.2 C1).
    """

    asset: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self) -> None:
        self._require_no_nulls()
        self._require_tz_aware()
        self._require_non_negative()
        self._require_ohlc_consistent()

    # -- invariantes ---------------------------------------------------------

    def _require_no_nulls(self) -> None:
        """I3 — nenhum campo `None` (frozen dataclass não impede `None`)."""
        for name in ("asset", "timestamp", "open", "high", "low", "close", "volume"):
            if getattr(self, name) is None:
                raise ValueError(f"Candle field {name!r} must not be None")

    def _require_tz_aware(self) -> None:
        """I4 — `timestamp` tz-aware (naive → `ValueError`)."""
        if self.timestamp.tzinfo is None:
            raise ValueError("Candle.timestamp must be timezone-aware (UTC enforced)")

    def _require_non_negative(self) -> None:
        """I2 — todos os OHLCV `>= 0`."""
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"Candle field {name!r} must be non-negative, got {value!r}")

    def _require_ohlc_consistent(self) -> None:
        """I1 — relações OHLC canônicas fortes."""
        if self.high < self.low:
            raise ValueError(f"Candle high ({self.high}) must be >= low ({self.low})")
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"Candle high ({self.high}) must be >= max(open, close) "
                f"({max(self.open, self.close)})"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"Candle low ({self.low}) must be <= min(open, close) "
                f"({min(self.open, self.close)})"
            )
