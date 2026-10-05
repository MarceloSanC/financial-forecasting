"""Contract test do port `TrainingGridReader` — fake e `ReadTrainingGrid` (ADR 6.4.0009).

Prova (concept 6.4 A8, C4) que as duas pernas entregam a mesma grade de treino: o
prefixo sem valor aparado e reportado (`trimmed_prefix`), linhas em ordem
cronológica, valor ausente depois do prefixo → `InteriorMissingValuesError`, ativo
ausente ou sem linha utilizável → `NoUsableRowsError`, cada leitura só vê o seu
ativo, e o fingerprint devolvido é o do dono (`grid_fingerprint`) sobre a grade
devolvida — o mesmo valor nas duas pernas (issue #128). Perna `real`:
`ReadTrainingGrid` sobre o `ParquetMedallionStore` com o dataset
gravado por `pandas` no layout do par read-only
(`processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet`); perna `fake`: as
mesmas linhas no `FakeTrainingGridReader`. Sem `skipif`. `_COLUMNS` são declaradas
aqui (o contrato é da leitura, não do registry).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from financial_forecasting.features.evaluation.application.ports.out.training_grid_reader import (
    TrainingGridReader,
)
from financial_forecasting.features.modeling.application.use_cases.read_training_grid import (
    ReadTrainingGrid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
    NoUsableRowsError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader

Row = dict[str, object]
_COLUMNS = ("feat_a", "feat_b", "target_return")
_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)
_PREFIX = 3
_N = 12


def _rows(asset: str, *, prefix: int = _PREFIX, offset: float = 0.0) -> list[Row]:
    rows: list[Row] = []
    for i in range(_N):
        rows.append(
            {
                "timestamp": _EPOCH + timedelta(days=i),
                "asset_id": asset,
                "feat_a": math.nan if i < prefix else offset + i / 10,
                "feat_b": offset + 2.0 * i,
                "target_return": offset + (i % 4) / 100,
            }
        )
    return rows


def _shuffled(rows: Sequence[Row]) -> list[Row]:
    return [rows[i] for i in (5, 0, 11, 2, 7, 1, 9, 3, 10, 4, 8, 6)]


def _interior(asset: str) -> list[Row]:
    rows = _rows(asset)
    rows[7] = {**rows[7], "feat_b": math.nan}
    return rows


def _all_invalid(asset: str) -> list[Row]:
    return _rows(asset, prefix=_N)


_DATA: Mapping[str, list[Row]] = {
    "AAPL": _shuffled(_rows("AAPL")),
    "MSFT": _rows("MSFT", prefix=0, offset=100.0),
    "BADI": _interior("BADI"),
    "NONE": _all_invalid("NONE"),
}


def _fake(_root: Path) -> TrainingGridReader:
    return FakeTrainingGridReader(_DATA, columns=_COLUMNS, hasher=CanonicalJsonHasher())


def _real(root: Path) -> TrainingGridReader:
    for asset, rows in _DATA.items():
        target = root / "processed" / "dataset_tft" / asset
        target.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(target / f"dataset_tft_{asset}.parquet", index=False)
    return ReadTrainingGrid(
        store=ParquetMedallionStore(data_root=root), columns=_COLUMNS, hasher=CanonicalJsonHasher()
    )


READERS: dict[str, Callable[[Path], TrainingGridReader]] = {"fake": _fake, "real": _real}


@pytest.fixture(params=list(READERS), ids=list(READERS))
def reader(request: pytest.FixtureRequest, tmp_path: Path) -> TrainingGridReader:
    return READERS[request.param](tmp_path)


@pytest.mark.contract
def test_grid_trimmed_prefix_reported(reader: TrainingGridReader) -> None:
    grid, _ = reader(asset_id="AAPL")
    assert grid.trimmed_prefix == _PREFIX
    assert grid.timestamps_iso()[0] == (_EPOCH + timedelta(days=_PREFIX)).isoformat()
    assert len(grid.timestamps) == _N - _PREFIX
    assert grid.column("feat_a")[0] == pytest.approx(_PREFIX / 10)
    assert set(grid.columns) == set(_COLUMNS)


@pytest.mark.contract
def test_grid_rows_chronological(reader: TrainingGridReader) -> None:
    """Linhas gravadas fora de ordem saem em ordem cronológica, valores alinhados."""
    grid, _ = reader(asset_id="AAPL")
    stamps = grid.timestamps_iso()
    assert list(stamps) == sorted(stamps)
    assert grid.column("feat_b") == tuple(2.0 * i for i in range(_PREFIX, _N))


@pytest.mark.contract
def test_grid_interior_missing_raises(reader: TrainingGridReader) -> None:
    with pytest.raises(InteriorMissingValuesError):
        reader(asset_id="BADI")


@pytest.mark.contract
@pytest.mark.parametrize("asset", ["NONE", "ZZZZ"])
def test_grid_no_usable_rows_raises(reader: TrainingGridReader, asset: str) -> None:
    """Toda linha inválida ou ativo ausente → `NoUsableRowsError`."""
    with pytest.raises(NoUsableRowsError):
        reader(asset_id=asset)


@pytest.mark.contract
def test_grid_asset_partition_only(reader: TrainingGridReader) -> None:
    """Dois ativos no mesmo `data_root`: cada leitura só vê o seu."""
    msft, _ = reader(asset_id="MSFT")
    aapl, _ = reader(asset_id="AAPL")
    assert msft.trimmed_prefix == 0
    assert len(msft.timestamps) == _N
    assert min(msft.column("feat_b")) >= 100.0  # noqa: PLR2004 — o offset do MSFT
    assert max(aapl.column("feat_b")) < 100.0  # noqa: PLR2004 — nenhuma linha do MSFT


def _oracle_fingerprint(asset: str) -> DatasetContentFingerprint:
    """O valor esperado: a função do dono sobre a grade montada das mesmas linhas."""
    grid = build_training_grid(_DATA[asset], columns=_COLUMNS)
    return DatasetContentFingerprint(
        grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=asset)
    )


@pytest.mark.contract
@pytest.mark.parametrize("asset", ["AAPL", "MSFT"])
def test_fingerprint_is_the_owner_value_of_the_returned_grid(
    reader: TrainingGridReader, asset: str
) -> None:
    """O fingerprint vem do dono, sobre a grade devolvida — igual nas duas pernas (#128)."""
    grid, fingerprint = reader(asset_id=asset)
    assert isinstance(fingerprint, DatasetContentFingerprint)
    assert fingerprint == _oracle_fingerprint(asset)
    assert fingerprint.value == grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=asset)


@pytest.mark.contract
def test_fingerprint_distinguishes_assets(reader: TrainingGridReader) -> None:
    """Grades diferentes, fingerprints diferentes (o valor não é constante)."""
    _, msft = reader(asset_id="MSFT")
    _, aapl = reader(asset_id="AAPL")
    assert msft != aapl
