"""Contrato dos ports espelho do `inference` (Stage 7.1, Task 08).

Os quatro ports têm a forma de um port já existente de outro slice e reaproveitam
o fake e o real dele (technical 7.1 §1). Cada fixture é TIPADA PELO PROTOCOL DO
INFERENCE — é o mypy sobre estas fixtures que prova que fake e real satisfazem o
port do consumidor. O `check_port_coverage.py` indexa fakes por nome de classe e
é vácuo para homônimos (§1); o teste do gate amarra esta suíte a cada um.

- `RuntimeEnvironmentProbe`: `InMemoryRuntimeEnvironmentProbe` /
  `GitRuntimeEnvironmentProbe` sobre um repositório git descartável;
- `PredictionPersister`: `InMemoryPredictionPersister` / `PersistPredictions`
  sobre o silver Parquet em `tmp_path`;
- `SilverTableReader`: `FakeSilverTableReader` / `ParquetAnalyticsRepository`;
- `CohortLedger`: `InMemoryCohortLedger` / `JsonCohortProgressLedger`.

Exclusivo da perna real, por construção: a colisão de PK do persister — o
`InMemoryPredictionPersister` não guarda linhas (conta as resolvíveis), então só o
`PersistPredictions` sobre o silver pode provar que `DuplicateKeyError` propaga.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.application.ports.out.cohort_ledger import (
    CohortLedger,
)
from financial_forecasting.features.inference.application.ports.out.prediction_persister import (
    PredictionPersister,
)
from financial_forecasting.features.inference.application.ports.out.runtime_environment_probe import (  # noqa: E501
    RuntimeEnvironmentProbe,
)
from financial_forecasting.features.inference.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.modeling.adapters.out.filesystem.json_cohort_progress_ledger import (  # noqa: E501
    JsonCohortProgressLedger,
)
from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import (  # noqa: E501
    GitRuntimeEnvironmentProbe,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    THREADS_KEY,
)
from financial_forecasting.shared.application.exceptions import (
    ApplicationError,
    DuplicateKeyError,
)
from tests.fakes.features.evaluation.fake_silver_table_reader import FakeSilverTableReader
from tests.fakes.features.inference.in_memory_cohort_ledger import InMemoryCohortLedger
from tests.fakes.features.modeling.in_memory_prediction_persister import (
    InMemoryPredictionPersister,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock

pytestmark = pytest.mark.contract

_COHORT_FILE = "config/cohorts/test.toml"
_COHORT = "aapl_confirmatory-r0-abcdef123456"
_LEVELS = (0.1, 0.5, 0.9)
_TIMESTAMPS = tuple(f"2024-01-{day:02d}T00:00:00+00:00" for day in range(2, 12))


# -- RuntimeEnvironmentProbe ----------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for rel, text in {
        "src/pkg/m.py": "x = 1\n",
        "uv.lock": "lock\n",
        _COHORT_FILE: "n = 1\n",
    }.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture(params=["fake", "real"])
def probe(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> RuntimeEnvironmentProbe:
    if request.param == "fake":
        return InMemoryRuntimeEnvironmentProbe()
    # O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo do teste é outro.
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(variable, raising=False)
    return GitRuntimeEnvironmentProbe(
        repo_root=_repo(tmp_path), cohort_file=_COHORT_FILE, device="cpu"
    )


def test_probe_snapshot_has_code_dirty_and_threads_keys(probe: RuntimeEnvironmentProbe) -> None:
    snapshot = probe.snapshot()

    assert snapshot[DIRTY_KEY] in {"true", "false"}
    # o valor é texto nas duas pernas (o real grava `torch.get_num_threads()`)
    assert isinstance(snapshot[THREADS_KEY], str)
    assert snapshot[THREADS_KEY]


# -- PredictionPersister --------------------------------------------------------------


def _calib_command(decision_idx: int) -> PersistPredictionsCommand:
    return PersistPredictionsCommand(
        run_id="r" * 64,
        split="calib",
        model_version="tft_quantile",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=1,
        decision_idx=decision_idx,
        dataset_timestamps=_TIMESTAMPS,
        forecasts={
            h: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.02, -0.01, 0.03))
            for h in (1, 2)
        },
    )


def _real_repository(tmp_path: Path) -> ParquetAnalyticsRepository:
    return ParquetAnalyticsRepository(data_root=tmp_path, clock=FakeClock())


@pytest.fixture(params=["fake", "real"])
def persister(request: pytest.FixtureRequest, tmp_path: Path) -> PredictionPersister:
    if request.param == "fake":
        return InMemoryPredictionPersister()
    return PersistPredictions(repository=_real_repository(tmp_path))


def test_persister_writes_a_calib_decision_atomically(persister: PredictionPersister) -> None:
    result = persister(_calib_command(decision_idx=3))

    assert (result.rows_written, result.rows_skipped) == (2 * len(_LEVELS), 0)


def test_persister_writes_the_calib_rows_with_split_and_guardrail(tmp_path: Path) -> None:
    """Só real: as linhas gravadas são de calib, raw e guardrail na mesma linha."""
    repository = _real_repository(tmp_path)
    PersistPredictions(repository=repository)(_calib_command(decision_idx=3))

    rows = repository.read(layer="silver", table="fact_oos_predictions", filters={"asset": "AAPL"})
    assert len(rows) == 2 * len(_LEVELS)
    assert {row["split"] for row in rows} == {"calib"}
    assert {row["guardrail_applied"] for row in rows} == {1}  # grade cruzada → rearranjada


def test_persister_collision_propagates(tmp_path: Path) -> None:
    """Só real (ver módulo): a mesma decisão de calib gravada duas vezes colide."""
    persister: PredictionPersister = PersistPredictions(repository=_real_repository(tmp_path))
    persister(_calib_command(decision_idx=3))

    with pytest.raises(DuplicateKeyError):
        persister(_calib_command(decision_idx=3))


# -- SilverTableReader -------------------------------------------------------------------


def _dim_run(run_id: str, sweep: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": "AAPL",
        "parent_sweep_id": sweep,
        "feature_set_name": "fs_all",
        "config_signature": "sig",
        "split_fingerprint": "split",
        "fold": "0",
        "seed": 11,
        "model_version": "tft_quantile",
    }


def _fact(run_id: str, split: str, level: float) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": "tft_quantile",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "split": split,
        "horizon": 1,
        "decision_idx": 3,
        "timestamp_utc": "2024-01-05T00:00:00+00:00",
        "target_timestamp_utc": "2024-01-08T00:00:00+00:00",
        "quantile_level": level,
        "value_raw": 0.01,
        "value_guardrail": 0.01,
        "guardrail_applied": 0,
        "year": 2024,
    }


_RUNS = [_dim_run("run-a", _COHORT), _dim_run("run-b", "other-cohort")]
_FACTS = [_fact("run-a", "test", 0.5), _fact("run-a", "calib", 0.5), _fact("run-a", "calib", 0.9)]


@pytest.fixture(params=["fake", "real"])
def reader(request: pytest.FixtureRequest, tmp_path: Path) -> SilverTableReader:
    if request.param == "fake":
        return FakeSilverTableReader({"dim_run": _RUNS, "fact_oos_predictions": _FACTS})
    repository = _real_repository(tmp_path)
    repository.write(layer="silver", table="dim_run", rows=_RUNS)
    repository.write(layer="silver", table="fact_oos_predictions", rows=_FACTS)
    return repository


def _rows(rows: Sequence[Mapping[str, object]], *keys: str) -> list[tuple[object, ...]]:
    return sorted(tuple(row[key] for key in keys) for row in rows)


def test_reader_returns_dim_run_and_calib_facts_of_the_partition(reader: SilverTableReader) -> None:
    runs = reader.read(
        layer="silver", table="dim_run", filters={"asset": "AAPL", "parent_sweep_id": _COHORT}
    )
    facts = reader.read(
        layer="silver",
        table="fact_oos_predictions",
        filters={"asset": "AAPL", "feature_set_name": "fs_all"},
    )

    assert [row["run_id"] for row in runs if row["parent_sweep_id"] == _COHORT] == ["run-a"]
    assert _rows(facts, "run_id", "split", "quantile_level") == [
        ("run-a", "calib", 0.5),
        ("run-a", "calib", 0.9),
        ("run-a", "test", 0.5),
    ]


# -- CohortLedger --------------------------------------------------------------------------


@dataclass(frozen=True)
class _LedgerLeg:
    open: Callable[[], CohortLedger]
    record_environment: Callable[[str, Mapping[str, str]], None]


@pytest.fixture(params=["fake", "real"])
def ledger_leg(request: pytest.FixtureRequest, tmp_path: Path) -> _LedgerLeg:
    if request.param == "fake":
        fake = InMemoryCohortLedger()
        return _LedgerLeg(
            open=lambda: fake,
            record_environment=lambda cohort, env: fake.record_environment(
                cohort, env, started_at="2026-10-06T00:00:00+00:00"
            ),
        )

    def open_real() -> JsonCohortProgressLedger:
        return JsonCohortProgressLedger(
            artifacts_root=tmp_path / "artifacts", data_root=tmp_path / "data"
        )

    return _LedgerLeg(
        open=open_real,
        record_environment=lambda cohort, env: open_real().record_environment(
            cohort, env, started_at="2026-10-06T00:00:00+00:00"
        ),
    )


def test_ledger_second_writer_is_refused(ledger_leg: _LedgerLeg) -> None:
    ledger_leg.open().acquire_writer()

    with pytest.raises(ApplicationError):
        ledger_leg.open().acquire_writer()


def test_ledger_break_stale_releases(ledger_leg: _LedgerLeg) -> None:
    ledger_leg.open().acquire_writer()
    taker = ledger_leg.open()

    taker.acquire_writer(break_stale=True)
    taker.release_writer()

    ledger_leg.open().acquire_writer()


def test_ledger_environment_none_then_recorded(ledger_leg: _LedgerLeg) -> None:
    environment = {"torch": "2.13.0+cpu", THREADS_KEY: "6", DIRTY_KEY: "false"}
    assert ledger_leg.open().environment(_COHORT) is None

    ledger_leg.record_environment(_COHORT, environment)

    assert dict(ledger_leg.open().environment(_COHORT) or {}) == environment
