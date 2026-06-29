"""Unit test do `ParquetAnalyticsRepository.write` + mapper `RunRecord -> row`.

Cobre (concept 4.2 A2/A3/A4/A5/A6, C1/C2/C3/C5, I2/I3/I4/I7): despacho por
`(layer, table)` e `(layer, table)` fora do registry → `ApplicationError` (C2);
`pandera` ANTES do disco (dtype divergente → `SchemaError`, nenhum arquivo
escrito) (C3/I4); partição Hive literal em 1..3 níveis — `fact_failures`
`asset=` (1 nível), `dim_run` `asset=/parent_sweep_id=` (2), `fact_oos_predictions`
`asset=/feature_set_name=/year=` (3) — sem derivar ano de âncora (I2/A4); colisão
de PK lógica sem flag → `DuplicateKeyError` (C1); `allow_upsert=True` substitui só
as colididas (C5); `dim_run` upsert por `update_policy` sem flag (I3); o mapper
preenche `created_at_utc` via `FakeClock` determinístico (A6/I5).

A leitura de volta usa `pandas.read_parquet` direto (não o `read` do adapter, que
só chega na task-05) — este é um unit test do `write`, não do round-trip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors

from financial_forecasting.features.analytics_store.adapters.out.parquet.mappers.run_record_mapper import (  # noqa: E501
    run_record_to_row,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)
from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)

_SILVER = "silver"
_FIXED_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
_TWO_ROWS = 2


class FakeClock:
    """Clock determinístico (timestamp fixo)."""

    def __init__(self, now: datetime = _FIXED_NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _repo(tmp_path: Path) -> ParquetAnalyticsRepository:
    return ParquetAnalyticsRepository(data_root=tmp_path, clock=FakeClock())


def _run_record(run_id: str = "run-1", *, parent_sweep_id: str | None = "sweep-1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        asset="AAPL",
        parent_sweep_id=parent_sweep_id,
        feature_set_name="fs_all",
        config_signature="cfg-hash",
        split_fingerprint="split-hash",
        fold="fold-0",
        seed=42,
        model_version="tft_v1",
        schema_version=1,
    )


def _fact_oos_row(
    run_id: str = "run-1", *, quantile_level: float = 0.5, value_raw: float = 0.01
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": "tft_v1",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "split": "test",
        "horizon": 1,
        "decision_idx": 0,
        "timestamp_utc": "2024-01-02T00:00:00+00:00",
        "target_timestamp_utc": "2024-01-03T00:00:00+00:00",
        "quantile_level": quantile_level,
        "value_raw": value_raw,
        "value_guardrail": value_raw,
        "guardrail_applied": 0,
        "year": 2024,
    }


def _fact_failures_row(run_id: str = "run-1") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": "AAPL",
        "failed_at_utc": "2024-01-02T00:00:00+00:00",
        "stage": "train",
        "error_type": "ValueError",
        "error_message": "boom",
        "trace_hash": "abc123",
        "traceback_excerpt": None,
    }


# -- mapper ------------------------------------------------------------------


def test_mapper_fills_created_at_utc_via_clock() -> None:
    """A6/I5: o mapper injeta `created_at_utc` do `Clock` (ISO UTC), não do VO."""
    row = run_record_to_row(_run_record(), clock=FakeClock())

    assert row["created_at_utc"] == _FIXED_NOW.isoformat()
    assert row["run_id"] == "run-1"
    assert "created_at_utc" not in {f for f in RunRecord.__dataclass_fields__}


# -- dispatch ----------------------------------------------------------------


def test_write_does_not_clobber_existing_created_at_utc(tmp_path: Path) -> None:
    """I5 (idempotência): `dim_run` com `created_at_utc` já presente NÃO é sobrescrito.

    Mutação-guarda: o `_fill_write_time` só preenche quando a coluna falta
    (`is None`); se preenchesse sempre (remover o guard / inverter `is None`), um
    `created_at_utc` produzido upstream (ex.: pelo mapper) seria clobberado pelo
    `clock.now()`. Os demais testes usam um valor IGUAL ao do clock, então não
    distinguem; aqui o valor pré-existente é DIFERENTE do `FakeClock`.
    """
    repo = _repo(tmp_path)
    preexisting = "2000-01-01T00:00:00+00:00"  # != _FIXED_NOW
    row = run_record_to_row(_run_record(), clock=FakeClock())
    row["created_at_utc"] = preexisting

    repo.write(layer=_SILVER, table="dim_run", rows=[row])

    path = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=sweep-1"
        / "dim_run.parquet"
    )
    df = pd.read_parquet(path)
    assert df.iloc[0]["created_at_utc"] == preexisting


def test_collision_message_carries_pk_columns_and_path(tmp_path: Path) -> None:
    """C1 (diagnóstico): a `DuplicateKeyError` cita `pk_columns`, `collisions` e `path`.

    Mutação-guarda: a mensagem diagnóstica é parte do contrato C1; sem este
    assert, alterar/esvaziar a mensagem passaria silenciosamente.
    """
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    with pytest.raises(DuplicateKeyError) as excinfo:
        repo.write(
            layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(value_raw=0.99)]
        )

    message = str(excinfo.value)
    assert "pk_columns=" in message
    assert "collisions=" in message
    assert "path=" in message
    assert "run_id" in message  # nome de coluna da PK lógica


def test_unknown_layer_table_raises(tmp_path: Path) -> None:
    """C2: `(layer, table)` fora do `SILVER_REGISTRY` → `ApplicationError`."""
    repo = _repo(tmp_path)
    with pytest.raises(ApplicationError):
        repo.write(layer=_SILVER, table="nope", rows=[_fact_oos_row()])
    with pytest.raises(ApplicationError):
        repo.write(layer="bronze", table="dim_run", rows=[])


def test_empty_rows_is_noop(tmp_path: Path) -> None:
    """`write` de lista vazia (tabela conhecida) é no-op."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[])
    assert not any(tmp_path.rglob("*.parquet"))


# -- pandera antes do disco --------------------------------------------------


def test_pandera_rejects_before_disk(tmp_path: Path) -> None:
    """C3/I4: dtype divergente → `SchemaError` e nenhum arquivo escrito."""
    repo = _repo(tmp_path)
    bad = _fact_oos_row()
    bad["quantile_level"] = "not-a-float"  # deveria ser float64

    with pytest.raises(SchemaError):
        repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[bad])

    assert not any(tmp_path.rglob("*.parquet"))


def test_pandera_rejects_extra_column(tmp_path: Path) -> None:
    """C3/I4: coluna extra (strict=True) → `SchemaError`, sem arquivo."""
    repo = _repo(tmp_path)
    bad = _fact_oos_row()
    bad["ghost"] = 1

    # `strict=True` levanta `SchemaErrors` (coleta de erros), não `SchemaError`.
    with pytest.raises(SchemaErrors):
        repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[bad])
    assert not any(tmp_path.rglob("*.parquet"))


# -- partição literal 1..3 níveis --------------------------------------------


def test_partition_three_levels_fact_oos(tmp_path: Path) -> None:
    """A4/I2: `fact_oos_predictions` particiona por asset/feature_set_name/year."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    expected = (
        tmp_path
        / "silver"
        / "fact_oos_predictions"
        / "asset=AAPL"
        / "feature_set_name=fs_all"
        / "year=2024"
        / "fact_oos_predictions.parquet"
    )
    assert expected.exists()


def test_partition_two_levels_dim_run(tmp_path: Path) -> None:
    """A4/I2: `dim_run` particiona por asset/parent_sweep_id."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER, table="dim_run", rows=[run_record_to_row(_run_record(), clock=FakeClock())]
    )

    expected = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=sweep-1"
        / "dim_run.parquet"
    )
    assert expected.exists()


def test_partition_one_level_fact_failures(tmp_path: Path) -> None:
    """A4/I2: `fact_failures` particiona só por asset (1 nível)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_failures", rows=[_fact_failures_row()])

    expected = tmp_path / "silver" / "fact_failures" / "asset=AAPL" / "fact_failures.parquet"
    assert expected.exists()


def test_parent_sweep_id_none_uses_sentinel(tmp_path: Path) -> None:
    """C6: `parent_sweep_id=None` grava sob `parent_sweep_id=__none__`."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER,
        table="dim_run",
        rows=[run_record_to_row(_run_record(parent_sweep_id=None), clock=FakeClock())],
    )

    expected = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=__none__"
        / "dim_run.parquet"
    )
    assert expected.exists()


# -- append-only / upsert ----------------------------------------------------


def test_collision_without_flag_raises(tmp_path: Path) -> None:
    """C1: colisão de PK lógica em fato append-only sem flag → DuplicateKeyError."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    with pytest.raises(DuplicateKeyError):
        repo.write(
            layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(value_raw=0.99)]
        )


def test_allow_upsert_replaces_only_collided(tmp_path: Path) -> None:
    """C5: `allow_upsert=True` substitui só a colidida; a outra permanece."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row(quantile_level=0.1), _fact_oos_row(quantile_level=0.9)],
    )
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row(quantile_level=0.1, value_raw=0.5)],
        allow_upsert=True,
    )

    path = (
        tmp_path
        / "silver"
        / "fact_oos_predictions"
        / "asset=AAPL"
        / "feature_set_name=fs_all"
        / "year=2024"
        / "fact_oos_predictions.parquet"
    )
    df = pd.read_parquet(path)
    assert len(df) == _TWO_ROWS
    by_q = dict(zip(df["quantile_level"], df["value_raw"], strict=True))
    assert by_q[0.1] == pytest.approx(0.5)
    assert by_q[0.9] == pytest.approx(0.01)


def test_append_only_distinct_pks_accumulate(tmp_path: Path) -> None:
    """I3: dois writes de PKs distintas no mesmo fato acumulam (append-only)."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.1)]
    )
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.9)]
    )

    path = (
        tmp_path
        / "silver"
        / "fact_oos_predictions"
        / "asset=AAPL"
        / "feature_set_name=fs_all"
        / "year=2024"
        / "fact_oos_predictions.parquet"
    )
    assert len(pd.read_parquet(path)) == _TWO_ROWS


def test_dim_run_upserts_by_policy_without_flag(tmp_path: Path) -> None:
    """I3: `dim_run` faz upsert por `update_policy` mesmo sem `allow_upsert`."""
    repo = _repo(tmp_path)
    row_v1 = run_record_to_row(_run_record(), clock=FakeClock())
    repo.write(layer=_SILVER, table="dim_run", rows=[{**row_v1, "model_version": "v1"}])
    repo.write(layer=_SILVER, table="dim_run", rows=[{**row_v1, "model_version": "v2"}])

    path = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=sweep-1"
        / "dim_run.parquet"
    )
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert df.iloc[0]["model_version"] == "v2"
