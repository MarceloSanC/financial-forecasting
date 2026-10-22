"""Contract test do port `SilverTableReader` — fake e `ParquetAnalyticsRepository` (ADR 6.4.0004).

Prova (concept 6.4 A8, D3) que as duas pernas entregam a mesma leitura: filtro de
partição aplicado; chave fora da partição ignorada (superconjunto, o consumidor
pós-filtra); partição ausente → vazio; tabela desconhecida → `ApplicationError`; tipos
preservados (`guardrail_applied` `int`, `seed` `None`/`int`). As linhas são gravadas
nas duas pernas — na real, `dim_run` num único lote misto de `seed` `None`/`int`
(issue #119). Sem `skipif`.

Stage 8.1 (ADR 8.1.0002 item 2b): `columns` declara o tipo e a nulabilidade de toda
coluna das quatro tabelas que o refresh lê; o fake tem de devolver exatamente o mesmo
que o real (é o que prova o espelho).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.evaluation.fake_silver_table_reader import FakeSilverTableReader
from tests.fakes.shared.in_memory_clock import FakeClock

Row = Mapping[str, object]
_SILVER = "silver"


def _run(run_id: str, *, sweep: str, seed: int | None, fold: str = "f0") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": "AAPL",
        "parent_sweep_id": sweep,
        "feature_set_name": "fs-core",
        "config_signature": "sig",
        "split_fingerprint": "split",
        "fold": fold,
        "seed": seed,
        "model_version": "tft",
    }


def _fact(run_id: str, *, level: float, applied: int, fs: str = "fs-core") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": "tft",
        "asset": "AAPL",
        "feature_set_name": fs,
        "split": "test",
        "horizon": 1,
        "decision_idx": 3,
        "timestamp_utc": "2024-01-05T00:00:00+00:00",
        "target_timestamp_utc": "2024-01-08T00:00:00+00:00",
        "quantile_level": level,
        "value_raw": 0.01 * level,
        "value_guardrail": 0.01 * level,
        "guardrail_applied": applied,
        "year": 2024,
    }


_RUNS = [
    _run("run-a", sweep="sweep-01", seed=None),
    _run("run-b", sweep="sweep-01", seed=1),
    _run("run-c", sweep="sweep-02", seed=2),
]
_FACTS = [
    _fact("run-a", level=0.25, applied=0),
    _fact("run-b", level=0.75, applied=1),
    _fact("run-c", level=0.5, applied=0, fs="fs-other"),
]


def _fake(_root: Path) -> SilverTableReader:
    return FakeSilverTableReader({"dim_run": _RUNS, "fact_oos_predictions": _FACTS})


def _real(root: Path) -> SilverTableReader:
    repo = ParquetAnalyticsRepository(data_root=root, clock=FakeClock())
    repo.write(layer=_SILVER, table="dim_run", rows=_RUNS)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=_FACTS)
    return repo


READERS: dict[str, Callable[[Path], SilverTableReader]] = {"fake": _fake, "real": _real}


@pytest.fixture(params=list(READERS), ids=list(READERS))
def reader(request: pytest.FixtureRequest, tmp_path: Path) -> SilverTableReader:
    return READERS[request.param](tmp_path)


def _ids(rows: Sequence[Row]) -> list[object]:
    return sorted(str(row["run_id"]) for row in rows)


@pytest.mark.contract
def test_partition_filter_applied(reader: SilverTableReader) -> None:
    runs = reader.read(
        layer=_SILVER, table="dim_run", filters={"asset": "AAPL", "parent_sweep_id": "sweep-01"}
    )
    assert _ids(runs) == ["run-a", "run-b"]
    facts = reader.read(
        layer=_SILVER,
        table="fact_oos_predictions",
        filters={"asset": "AAPL", "feature_set_name": "fs-other"},
    )
    assert _ids(facts) == ["run-c"]


@pytest.mark.contract
def test_non_partition_superset(reader: SilverTableReader) -> None:
    """Chave fora da partição é ignorada: o resultado é superconjunto."""
    rows = reader.read(
        layer=_SILVER,
        table="dim_run",
        filters={"asset": "AAPL", "parent_sweep_id": "sweep-01", "run_id": "run-a"},
    )
    assert _ids(rows) == ["run-a", "run-b"]


@pytest.mark.contract
def test_absent_partition_empty(reader: SilverTableReader) -> None:
    assert list(reader.read(layer=_SILVER, table="dim_run", filters={"asset": "MSFT"})) == []
    assert (
        list(
            reader.read(
                layer=_SILVER,
                table="fact_oos_predictions",
                filters={"asset": "AAPL", "feature_set_name": "fs-missing"},
            )
        )
        == []
    )


@pytest.mark.contract
def test_unknown_table_raises(reader: SilverTableReader) -> None:
    with pytest.raises(ApplicationError, match="Unknown silver"):
        reader.read(layer=_SILVER, table="gold_nothing", filters={"asset": "AAPL"})


@pytest.mark.contract
def test_values_round_trip(reader: SilverTableReader) -> None:
    runs = {
        row["run_id"]: row
        for row in reader.read(
            layer=_SILVER,
            table="dim_run",
            filters={"asset": "AAPL", "parent_sweep_id": "sweep-01"},
        )
    }
    assert runs["run-a"]["seed"] is None
    assert type(runs["run-b"]["seed"]) is int
    assert runs["run-b"]["seed"] == 1
    assert runs["run-a"]["fold"] == "f0"
    facts = {
        row["run_id"]: row
        for row in reader.read(
            layer=_SILVER,
            table="fact_oos_predictions",
            filters={"asset": "AAPL", "feature_set_name": "fs-core"},
        )
    }
    for run_id, expected in (("run-a", 0), ("run-b", 1)):
        assert type(facts[run_id]["guardrail_applied"]) is int
        assert facts[run_id]["guardrail_applied"] == expected
    assert facts["run-b"]["quantile_level"] == 0.75  # noqa: PLR2004 — o nível gravado
    assert facts["run-a"]["target_timestamp_utc"] == "2024-01-08T00:00:00+00:00"


_REFRESH_TABLES = (
    "dim_run",
    "fact_oos_predictions",
    "fact_permuted_predictions",
    "fact_vsn_weights",
)
_FACT_TABLES = _REFRESH_TABLES[1:]
_KINDS = {"int", "float", "str", "bool"}


@pytest.mark.contract
def test_columns_declares_every_schema_column_with_kind_and_nullability(
    reader: SilverTableReader,
) -> None:
    declared = {table: reader.columns(layer=_SILVER, table=table) for table in _REFRESH_TABLES}

    for columns in declared.values():
        assert columns
        assert {kind for kind, _ in columns.values()} <= _KINDS
        assert all(type(nullable) is bool for _, nullable in columns.values())
    assert declared["dim_run"]["seed"] == ("int", True)
    assert declared["dim_run"]["parent_sweep_id"] == ("str", True)
    assert "created_at_utc" in declared["dim_run"]
    for table in _FACT_TABLES:
        assert declared[table]["year"] == ("int", False)
    assert declared["fact_oos_predictions"]["quantile_level"] == ("float", False)
    assert declared["fact_permuted_predictions"]["quantile_level"] == ("float", False)
    assert declared["fact_vsn_weights"]["weight"] == ("float", False)


@pytest.mark.contract
@pytest.mark.parametrize("table", _REFRESH_TABLES)
def test_fake_columns_equal_real_columns(table: str, tmp_path: Path) -> None:
    fake = _fake(tmp_path).columns(layer=_SILVER, table=table)
    real = _real(tmp_path).columns(layer=_SILVER, table=table)

    assert dict(fake) == dict(real)


@pytest.mark.contract
def test_columns_of_unknown_table_raises_application_error(reader: SilverTableReader) -> None:
    with pytest.raises(ApplicationError, match="Unknown silver"):
        reader.columns(layer=_SILVER, table="gold_nothing")
