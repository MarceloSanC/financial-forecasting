"""Contract test do port `AnalyticsRepository` — paridade Fake ↔ adapter real.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (concept 4.2 §5/§6, critérios A2/A5/A6/A7/A8/A9): round-trip
write/read por tabela, **colisão de PK lógica → `DuplicateKeyError`** em fato
append-only sem flag (C1), `allow_upsert=True` substituindo só as colididas (C5),
`dim_run` fazendo upsert por `update_policy` mesmo sem flag (I3), `(layer, table)`
fora do registry → `ApplicationError` (C2), `read` de tabela/asset inexistente →
vazio (C4), round-trip `parent_sweep_id=None` → `None` (A8/C6), filtro por `asset`
(I8) e `created_at_utc` de `dim_run` determinístico via `FakeClock` (A6).

Na Task 03 a fixture parametriza só o fake; a Task 06 adiciona `_build_real`
(`ParquetAnalyticsRepository(data_root=tmp_path, clock=FakeClock(...))`) para rodar
o MESMO contrato sobre `[fake, real]` — a estrutura já está pronta (espelha
`tests/contract/shared/test_medallion_store_contract.py`). As linhas de exemplo
usam os dtypes exatos dos schemas `pandera` silver (4.1): hashes/timestamps `str`,
`schema_version`/`horizon`/`seed`/`year` `int`, `quantile_level`/`value_*`/métricas
`float` — para que o adapter real (que valida com `pandera`) aceite os mesmos dados
que o fake.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
    AnalyticsRepository,
    Row,
)
from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)

if TYPE_CHECKING:
    from pathlib import Path

_SILVER = "silver"
_DIM_RUN_SCHEMA_VERSION = 1
_FACT_OOS_SCHEMA_VERSION = 1
_FIXED_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
_TWO_ROWS = 2


class FakeClock:
    """Clock determinístico (timestamp fixo) para `created_at_utc` no contract."""

    def __init__(self, now: datetime = _FIXED_NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


# -- row factories (dtypes exatos dos schemas silver 4.1) --------------------


def _dim_run_row(
    run_id: str,
    *,
    asset: str = "AAPL",
    parent_sweep_id: str | None = "sweep-1",
    model_version: str = "tft_v1",
) -> Row:
    """Linha de `dim_run` SEM `created_at_utc` (o repo preenche write-time, I5)."""
    return {
        "schema_version": _DIM_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "asset": asset,
        "parent_sweep_id": parent_sweep_id,
        "feature_set_name": "fs_all",
        "config_signature": "cfg-hash",
        "split_fingerprint": "split-hash",
        "fold": "fold-0",
        "seed": 42,
        "model_version": model_version,
    }


def _fact_oos_row(
    run_id: str,
    *,
    quantile_level: float = 0.5,
    asset: str = "AAPL",
    value_raw: float = 0.01,
) -> Row:
    return {
        "schema_version": _FACT_OOS_SCHEMA_VERSION,
        "run_id": run_id,
        "model_version": "tft_v1",
        "asset": asset,
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


def _build_fake(_tmp_path: Path) -> AnalyticsRepository:
    return FakeAnalyticsRepository(clock=FakeClock())


# Mesmo contrato sobre fake (e o adapter real a partir da Task 06; I9/ADR 0.0.0021).
_FACTORIES: list[Callable[[Path], AnalyticsRepository]] = [_build_fake]
_IDS = ["fake"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def repo(request: pytest.FixtureRequest, tmp_path: Path) -> AnalyticsRepository:
    """Parametriza o contrato sobre o fake (e o adapter real a partir da Task 06)."""
    factory: Callable[[Path], AnalyticsRepository] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_dim_run_round_trip(repo: AnalyticsRepository) -> None:
    """Round-trip de `dim_run`: o que foi gravado é lido de volta (filtra asset)."""
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-1")])

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["asset"] == "AAPL"


@pytest.mark.contract
def test_fact_oos_round_trip(repo: AnalyticsRepository) -> None:
    """Round-trip de `fact_oos_predictions` (partição asset/feature_set_name/year)."""
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row("run-1")])

    rows = repo.read(layer=_SILVER, table="fact_oos_predictions", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert float(rows[0]["quantile_level"]) == pytest.approx(0.5)


@pytest.mark.contract
def test_append_only_pk_collision_raises_without_flag(repo: AnalyticsRepository) -> None:
    """C1: re-gravar a MESMA PK lógica num fato append-only sem flag → DuplicateKeyError."""
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row("run-1")])

    with pytest.raises(DuplicateKeyError):
        repo.write(
            layer=_SILVER,
            table="fact_oos_predictions",
            rows=[_fact_oos_row("run-1", value_raw=0.99)],
        )


@pytest.mark.contract
def test_allow_upsert_replaces_only_collided(repo: AnalyticsRepository) -> None:
    """C5: `allow_upsert=True` substitui só as colididas; as demais permanecem."""
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[
            _fact_oos_row("run-1", quantile_level=0.1),
            _fact_oos_row("run-1", quantile_level=0.9),
        ],
    )

    # Upsert só da quantile_level=0.1 (novo value_raw); a 0.9 permanece intacta.
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row("run-1", quantile_level=0.1, value_raw=0.5)],
        allow_upsert=True,
    )

    rows = repo.read(layer=_SILVER, table="fact_oos_predictions", filters={"asset": "AAPL"})
    assert len(rows) == _TWO_ROWS
    by_q = {float(r["quantile_level"]): float(r["value_raw"]) for r in rows}
    assert by_q[0.1] == pytest.approx(0.5)  # substituída
    assert by_q[0.9] == pytest.approx(0.01)  # intacta


@pytest.mark.contract
def test_dim_run_upserts_by_policy_without_flag(repo: AnalyticsRepository) -> None:
    """I3: `dim_run` faz upsert por `update_policy` mesmo sem `allow_upsert`."""
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-1", model_version="v1")])

    # Mesma PK (run_id), sem flag: dim_run substitui por política (não levanta).
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-1", model_version="v2")])

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})
    assert len(rows) == 1
    assert rows[0]["model_version"] == "v2"


@pytest.mark.contract
def test_unknown_layer_table_raises(repo: AnalyticsRepository) -> None:
    """C2: `(layer, table)` fora do registry é erro de aplicação (write e read)."""
    with pytest.raises(ApplicationError):
        repo.write(layer=_SILVER, table="unknown_table", rows=[])

    with pytest.raises(ApplicationError):
        repo.read(layer="bronze", table="dim_run", filters={"asset": "AAPL"})


@pytest.mark.contract
def test_read_missing_returns_empty(repo: AnalyticsRepository) -> None:
    """C4: `read` de tabela não gravada ou `asset` sem dados → sequência vazia."""
    assert list(repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})) == []

    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-1")])
    assert list(repo.read(layer=_SILVER, table="dim_run", filters={"asset": "NVDA"})) == []


@pytest.mark.contract
def test_parent_sweep_id_none_round_trip(repo: AnalyticsRepository) -> None:
    """A8/C6: `parent_sweep_id=None` é gravado e lido de volta como `None`."""
    repo.write(
        layer=_SILVER,
        table="dim_run",
        rows=[_dim_run_row("run-1", parent_sweep_id=None)],
    )

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["parent_sweep_id"] is None


@pytest.mark.contract
def test_read_filters_by_asset(repo: AnalyticsRepository) -> None:
    """I8: `read({"asset": A})` num dataset com dois assets devolve só A."""
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-aapl", asset="AAPL")])
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-msft", asset="MSFT")])

    aapl = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(aapl) == 1
    assert all(r["asset"] == "AAPL" for r in aapl)


@pytest.mark.contract
def test_dim_run_created_at_utc_is_deterministic(repo: AnalyticsRepository) -> None:
    """A6: `dim_run` ganha `created_at_utc` write-time determinístico (FakeClock)."""
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("run-1")])

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["created_at_utc"] == _FIXED_NOW.isoformat()
