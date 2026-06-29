"""Contract test do port `MedallionStore` — paridade Fake ↔ ParquetMedallionStore.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (invariantes I2/I7, casos C1/C2/C4, critérios A5/A6): round-
trip de write/read, append-only entre writes, **colisão de PK lógica →
`DuplicateKeyError`** (C1) sem `overwrite` e substituição com `overwrite=True`
(I2), filtro por `asset` retornando só o asset pedido (I7), `read` de dataset/
asset inexistente devolvendo vazio (C4) e `(layer, table)` fora do registry →
erro de aplicação (C2).

Na Task 05 a fixture parametriza só o fake; a Task 07 adiciona `_build_real`
(`ParquetMedallionStore(tmp_path)`) para rodar o MESMO contrato sobre
`[fake, real]` — a estrutura já está pronta. As linhas de exemplo usam os dtypes
exatos do bronze (concept §9): `timestamp`/`published_at`/`fiscal_date_end` UTC,
OHLC `float32`, `volume` `int64`, fundamentals `float64` — para que o adapter
real (que valida com `pandera`) aceite os mesmos dados que o fake.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
    Row,
)
from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_F32 = np.float32
_VOLUME = 1_000_000
_TWO_ROWS = 2


def _candle_row(asset: str, ts: datetime, close: float) -> Row:
    return {
        "asset": asset,
        "timestamp": ts,
        "open": _F32(close - 1.0),
        "high": _F32(close + 1.0),
        "low": _F32(close - 2.0),
        "close": _F32(close),
        "volume": _VOLUME,
    }


def _build_fake(_tmp_path: Path) -> MedallionStore:
    return FakeMedallionStore()


# `_build_real` é adicionado na Task 07 (ParquetMedallionStore). Até lá, só fake.
_FACTORIES: list[Callable[[Path], MedallionStore]] = [_build_fake]
_IDS = ["fake"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> MedallionStore:
    """Parametriza o contrato sobre o fake (e o adapter real a partir da Task 07)."""
    factory: Callable[[Path], MedallionStore] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_write_then_read_round_trip(store: MedallionStore) -> None:
    """Round-trip: o que foi gravado é lido de volta (filtrando pelo asset)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["asset"] == "AAPL"
    assert rows[0]["volume"] == _VOLUME


@pytest.mark.contract
def test_write_is_append_only_across_calls(store: MedallionStore) -> None:
    """I2: dois writes de PKs distintas acumulam (append-only)."""
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 2, tzinfo=UTC), 100.0)],
    )
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 3, tzinfo=UTC), 101.0)],
    )

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(rows) == _TWO_ROWS


@pytest.mark.contract
def test_duplicate_logical_pk_raises_without_overwrite(store: MedallionStore) -> None:
    """C1: re-gravar a MESMA PK lógica sem `overwrite` levanta DuplicateKeyError."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])

    with pytest.raises(DuplicateKeyError):
        store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 999.0)])


@pytest.mark.contract
def test_overwrite_replaces_colliding_rows(store: MedallionStore) -> None:
    """I2: `overwrite=True` substitui as linhas colididas (mesma PK, novo valor)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])

    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", ts, 200.0)],
        overwrite=True,
    )

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})
    assert len(rows) == 1
    assert float(rows[0]["close"]) == pytest.approx(200.0)


@pytest.mark.contract
def test_read_filters_by_asset(store: MedallionStore) -> None:
    """I7: `read({"asset": A})` num dataset com dois assets devolve só A."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])
    store.write(layer="bronze", table="candle", rows=[_candle_row("MSFT", ts, 300.0)])

    aapl = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(aapl) == 1
    assert all(r["asset"] == "AAPL" for r in aapl)


@pytest.mark.contract
def test_read_missing_dataset_returns_empty(store: MedallionStore) -> None:
    """C4: `read` de dataset ainda não gravado devolve sequência vazia."""
    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert list(rows) == []


@pytest.mark.contract
def test_read_missing_asset_returns_empty(store: MedallionStore) -> None:
    """C4: filtro por um `asset` sem dados devolve vazio (não erro)."""
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 2, tzinfo=UTC), 100.0)],
    )

    rows = store.read(layer="bronze", table="candle", filters={"asset": "NVDA"})

    assert list(rows) == []


@pytest.mark.contract
def test_unknown_layer_table_raises(store: MedallionStore) -> None:
    """C2: `(layer, table)` fora do registry é erro de aplicação."""
    with pytest.raises(ApplicationError):
        store.write(layer="bronze", table="unknown_table", rows=[])

    with pytest.raises(ApplicationError):
        store.read(layer="silver", table="candle", filters={"asset": "AAPL"})


@pytest.mark.contract
def test_news_round_trip_with_string_columns(store: MedallionStore) -> None:
    """Round-trip de uma tabela com PK distinta (news: asset_id/article_id)."""
    row: Row = {
        "asset_id": "AAPL",
        "article_id": "a-1",
        "published_at": datetime(2024, 3, 1, tzinfo=UTC),
        "headline": "h",
        "summary": "s",
        "source": "src",
        "url": "http://x",
        "language": "en",
    }
    store.write(layer="bronze", table="news", rows=[row])

    rows = store.read(layer="bronze", table="news", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["article_id"] == "a-1"
