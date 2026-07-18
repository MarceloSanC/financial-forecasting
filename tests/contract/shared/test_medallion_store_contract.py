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

Stage 5.2 (Task 04, concept 5.2 D3): o par **read-only**
`("processed", "dataset_tft")` entra no MESMO contrato — round-trip de leitura
filtrada por `asset`, asset/dataset inexistente → vazio (C4), `write` no par →
`ApplicationError` (read-only), normalização NaN → None e a disciplina de
filtro do par: `asset=None` ≡ filtro ausente (união), valor de `asset` fora de
`^[A-Za-z0-9._-]+$` ergue `ValueError` antes de interpolar no glob/SQL e chave
de filtro ≠ `asset` ergue (nunca ignora silenciosamente) — com o real semeado
gravando o Parquet direto no `tmp_path` (layout físico da 3.5:
`processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet`) e o fake semeado
pelo helper `seed_read_only` (fora do port). Os casos bronze pré-existentes
seguem intactos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
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
_YEAR_2024 = 2024


def pd_year(value: object) -> int:
    """Extrai o ano de um timestamp (datetime/pd.Timestamp), agnóstico de impl."""
    assert isinstance(value, datetime)  # pd.Timestamp é subclasse de datetime
    return value.year


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


def _news_row(asset_id: str, article_id: str, ts: datetime) -> Row:
    return {
        "asset_id": asset_id,
        "article_id": article_id,
        "published_at": ts,
        "headline": "h",
        "summary": "s",
        "source": "src",
        "url": "http://x",
        "language": "en",
    }


def _fundamental_row(asset_id: str, ts: datetime) -> Row:
    return {
        "asset_id": asset_id,
        "report_type": "quarterly",
        "fiscal_date_end": ts,
        "reported_date": ts,
        "revenue": 1.0,
        "net_income": 2.0,
        "operating_cash_flow": 3.0,
        "total_shareholder_equity": 4.0,
        "total_liabilities": 5.0,
        "source": "src",
    }


def _build_fake(_tmp_path: Path) -> MedallionStore:
    return FakeMedallionStore()


def _build_real(tmp_path: Path) -> MedallionStore:
    return ParquetMedallionStore(tmp_path)


# Mesmo contrato sobre fake e real (paridade fake↔real, I6/ADR 0.0.0021).
_FACTORIES: list[Callable[[Path], MedallionStore]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> MedallionStore:
    """Parametriza o contrato sobre o fake (e o adapter real a partir da Task 07)."""
    factory: Callable[[Path], MedallionStore] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_write_then_read_round_trip(store: MedallionStore) -> None:
    """Round-trip: o que foi gravado é lido de volta (filtrando pelo asset)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    written = _candle_row("AAPL", ts, 100.0)
    store.write(layer="bronze", table="candle", rows=[written])

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(rows) == 1
    # Conjunto EXATO de chaves = schema escrito (sem coluna fantasma de partição):
    # fecha I6 (paridade fake↔real) e a fidelidade de schema do read (A5/A6).
    assert set(rows[0]) == set(written)
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
def test_write_empty_rows_is_noop(store: MedallionStore) -> None:
    """`write` de uma lista vazia (tabela conhecida) é no-op, não grava nada."""
    store.write(layer="bronze", table="candle", rows=[])

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})
    assert list(rows) == []


@pytest.mark.contract
def test_read_filters_by_year(store: MedallionStore) -> None:
    """I7: `read({"asset": A, "year": Y})` devolve só as linhas do ano Y."""
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2023, 6, 1, tzinfo=UTC), 90.0)],
    )
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 6, 1, tzinfo=UTC), 100.0)],
    )

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL", "year": 2024})

    assert len(rows) == 1
    assert pd_year(rows[0]["timestamp"]) == _YEAR_2024


@pytest.mark.contract
def test_news_round_trip_with_string_columns(store: MedallionStore) -> None:
    """Round-trip de uma tabela com PK distinta (news: asset_id/article_id).

    A coluna lógica é `asset_id`, mas a partição em disco é `asset`: o read NÃO
    pode devolver um `asset` fantasma. O assert de conjunto EXATO de chaves fecha
    o buraco de I6 (paridade fake↔real) que o teste antigo (só `len`/`article_id`)
    deixava passar.
    """
    written = _news_row("AAPL", "a-1", datetime(2024, 3, 1, tzinfo=UTC))
    store.write(layer="bronze", table="news", rows=[written])

    rows = store.read(layer="bronze", table="news", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert set(rows[0]) == set(written)  # sem `asset` fantasma
    assert rows[0]["article_id"] == "a-1"


@pytest.mark.contract
def test_fundamental_round_trip_no_phantom_partition(store: MedallionStore) -> None:
    """Round-trip de fundamental (coluna lógica `asset_id`, partição `asset`).

    Igual a news: o read não pode reintroduzir a coluna de partição `asset`, que
    não pertence ao schema fundamental. Assert de conjunto EXATO de chaves em
    [fake, real] (I6/A5/A6).
    """
    written = _fundamental_row("AAPL", datetime(2024, 3, 31, tzinfo=UTC))
    store.write(layer="bronze", table="fundamental", rows=[written])

    rows = store.read(layer="bronze", table="fundamental", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert set(rows[0]) == set(written)  # sem `asset` fantasma
    assert rows[0]["report_type"] == "quarterly"


# -----------------------------------------------------------------------------
# Par read-only ("processed", "dataset_tft") — Stage 5.2 Task 04 (concept D3).
# -----------------------------------------------------------------------------

_PROCESSED_LAYER = "processed"
_DATASET_TFT = "dataset_tft"


def _dataset_row(asset: str, ts: datetime, target_return: float, rsi: float | None) -> Row:
    """Linha mínima do dataset TFT (3.5): timestamp UTC + target + feature nullable."""
    return {
        "timestamp": ts,
        "asset_id": asset,
        "rsi_14": rsi,
        "target_return": target_return,
    }


def _seed_dataset_tft(
    store: MedallionStore, tmp_path: Path, asset: str, rows: Sequence[Row]
) -> None:
    """Semeia o par read-only FORA do port (write no par é proibido).

    Fake: helper `seed_read_only` (in-memory). Real: grava o Parquet direto no
    `tmp_path` espelhando o layout físico da 3.5
    (`processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet`).
    """
    if isinstance(store, FakeMedallionStore):
        store.seed_read_only(layer=_PROCESSED_LAYER, table=_DATASET_TFT, asset=asset, rows=rows)
        return
    target_dir = tmp_path / _PROCESSED_LAYER / _DATASET_TFT / asset
    target_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([dict(r) for r in rows])
    frame.to_parquet(target_dir / f"{_DATASET_TFT}_{asset}.parquet", index=False)


@pytest.mark.contract
def test_dataset_tft_read_filters_by_asset(store: MedallionStore, tmp_path: Path) -> None:
    """Round-trip de leitura do par read-only filtrada por `asset` (D3)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, 55.0)])
    _seed_dataset_tft(store, tmp_path, "MSFT", [_dataset_row("MSFT", ts, -0.02, 45.0)])

    rows = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["asset_id"] == "AAPL"
    assert float(str(rows[0]["target_return"])) == pytest.approx(0.01)
    timestamp = rows[0]["timestamp"]
    assert isinstance(timestamp, datetime)  # pd.Timestamp é subclasse de datetime
    assert timestamp.tzinfo is not None  # tz-aware UTC (premissa do RunBaselines)


@pytest.mark.contract
def test_dataset_tft_read_without_filter_returns_all_assets(
    store: MedallionStore, tmp_path: Path
) -> None:
    """Sem `filters`, o par read-only devolve a união dos assets semeados."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, 55.0)])
    _seed_dataset_tft(store, tmp_path, "MSFT", [_dataset_row("MSFT", ts, -0.02, 45.0)])

    rows = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT)

    assert {r["asset_id"] for r in rows} == {"AAPL", "MSFT"}


@pytest.mark.contract
def test_dataset_tft_read_asset_none_is_absent_filter(
    store: MedallionStore, tmp_path: Path
) -> None:
    """`filters={"asset": None}` equivale a filtro ausente → união (paridade fake↔real)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, 55.0)])
    _seed_dataset_tft(store, tmp_path, "MSFT", [_dataset_row("MSFT", ts, -0.02, 45.0)])

    rows = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": None})

    assert {r["asset_id"] for r in rows} == {"AAPL", "MSFT"}


@pytest.mark.contract
@pytest.mark.parametrize("bad_asset", ["../evil", "AAPL/2024", "AA PL", "*"])
def test_dataset_tft_invalid_asset_filter_value_raises(
    store: MedallionStore, bad_asset: str
) -> None:
    """Valor de `asset` fora de `^[A-Za-z0-9._-]+$` ergue ANTES de interpolar."""
    with pytest.raises(ValueError, match="asset"):
        store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": bad_asset})


@pytest.mark.contract
def test_dataset_tft_unsupported_filter_key_raises(
    store: MedallionStore, tmp_path: Path
) -> None:
    """Filtro não suportado (chave ≠ `asset`) no par read-only ergue, não ignora."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, 55.0)])

    with pytest.raises(ValueError, match="year"):
        store.read(
            layer=_PROCESSED_LAYER,
            table=_DATASET_TFT,
            filters={"asset": "AAPL", "year": 2024},
        )


@pytest.mark.contract
def test_dataset_tft_read_missing_dataset_and_asset_return_empty(
    store: MedallionStore, tmp_path: Path
) -> None:
    """C4: dataset ainda não semeado (e depois asset inexistente) devolvem vazio."""
    empty = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": "AAPL"})
    assert list(empty) == []

    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, 55.0)])

    rows = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": "NVDA"})
    assert list(rows) == []


@pytest.mark.contract
def test_dataset_tft_write_raises_read_only(store: MedallionStore) -> None:
    """`write` no par read-only ergue `ApplicationError` nas duas implementações."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)

    with pytest.raises(ApplicationError, match="read-only"):
        store.write(
            layer=_PROCESSED_LAYER,
            table=_DATASET_TFT,
            rows=[_dataset_row("AAPL", ts, 0.01, 55.0)],
        )


@pytest.mark.contract
def test_dataset_tft_read_normalizes_nan_to_none(store: MedallionStore, tmp_path: Path) -> None:
    """Valor faltante numa coluna de feature volta como `None` (paridade fake↔real)."""
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    _seed_dataset_tft(store, tmp_path, "AAPL", [_dataset_row("AAPL", ts, 0.01, None)])

    rows = store.read(layer=_PROCESSED_LAYER, table=_DATASET_TFT, filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["rsi_14"] is None
