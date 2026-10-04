"""E2E do refresh do gold sobre silver sintético, pelo `RefreshGold` wirado (Stage 6.4 Task 12).

Um único `data_root` (fixture de módulo, padrão do `test_run_baselines.py`): silver
sintético gravado pelo `ParquetAnalyticsRepository` real (`dim_run` um run por
chamada — #119) e o dataset `processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet`
com `timestamp` e todas as colunas de `modeling_columns()` (5.5), com um prefixo de
aquecimento de `_WARMUP` linhas com NaN numa feature; o silver indexa o `decision_idx`
na grade APARADA (ADR 6.4.0009) e o comando leva o fingerprint da grade calculado pela
função da 5.5 (`grid_fingerprint`, o oráculo). O `RefreshGold` vem de
`wire_dependencies` (caminho de produção: `ArchMcs` real atrás do proxy lazy,
`ParquetGoldStore`, cinco builders). Cenário: horizontes 1 e 2; `tft_quantile`
(candidato) com seeds 0 e 1 e prefixo 2 sessões atrás (déficit declarado 3);
`gbm_quantile`; `baseline_naive` pontual (grade toda igual); 2 folds; grade
(0,05; 0,25; 0,5; 0,75; 0,95); ~60 pontos de teste por série.

Sequência: (0) refresh de um cohort **B** (outro `parent_sweep_id`, mesmo ativo) e
cópia dos bytes do seu `current/`; (1) refresh do cohort **A** → `COMPLETED`; (2)
rerun **sem apagar**; (3) o arquivo da partição de fatos é reescrito sem as linhas de
um alvo interior de um run do GBM (lacuna interior) e o refresh dá `BLOCKED`.
Revisão de execução (Task 15): (2b) depois do (2), o cohort A com fingerprint
divergente ergue `GridFingerprintMismatchError` e o `current/` fica byte-igual; (4)
depois do (3), um cohort **C** com o mesmo silver mas `decision_idx` no dataset
INTEIRO (índice da grade + `_WARMUP`) dá `BLOCKED` com `decision_index_mismatch`.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    refresh_gold as refresh_gold_module,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    GridFingerprintMismatchError,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.unit.features.evaluation.gold._cohort_factory import (
    Cohort,
    make_cohort,
    replace_records,
    targets_of,
)

pytestmark = pytest.mark.integration

_ASSET = "AAPL"
_SWEEP_A = "sweep-a"
_SWEEP_B = "sweep-b"
_SWEEP_C = "sweep-c"
_WARMUP = 5  # P: linhas de aquecimento (NaN numa feature) que a grade da 5.5 apara
_SILVER = "silver"
_CANDIDATE = "tft_quantile"
_GBM = "gbm_quantile"
_NAIVE = "baseline_naive"
_LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
_SEEDS: Mapping[str, tuple[int | None, ...]] = {_NAIVE: (None,), _GBM: (None,), _CANDIDATE: (0, 1)}
_N_SESSIONS = 70
_PREREG = "prereg-e2e-6.4"  # literal declarado até a 6.5 fornecer o hash congelado
_POINT = 0.0005
_TABLES = (
    "gold_quality_checks",
    "gold_calibration_table",
    "gold_dm_results",
    "gold_mcs_results",
    "gold_metrics_by_run",
)
_K = len(_SEEDS)
_ESTIMATORS = (DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT)
_SCHEMES = (BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK)
_HORIZONS = (1, 2)
_PARAMETERS = RefreshParameters(
    preregistration_ref=_PREREG,
    degeneracy_tolerance=1e-9,
    band_levels=(0.95, 0.975),
    min_violations=5,
    candidate=_CANDIDATE,
    dm_alpha=0.05,
    dm_variance_estimators=_ESTIMATORS,
    mcs_alpha=0.10,
    mcs_reps=1000,
    mcs_seed=20260929,
    mcs_schemes=_SCHEMES,
)

Rows = list[tuple[object, ...]]


def _cohort() -> Cohort:
    cohort = make_cohort(
        seeds=_SEEDS, levels=_LEVELS, n_sessions=_N_SESSIONS, prefixes={_CANDIDATE: 2}
    )
    return replace_records(
        cohort,
        lambda r: r.model == _NAIVE,
        lambda r: dataclasses.replace(r, value_raw=_POINT, value_guardrail=_POINT),
    )


def _write_silver(
    deps: ApplicationDependencies,
    cohort: Cohort,
    *,
    sweep: str,
    prefix: str,
    index_offset: int = 0,
) -> None:
    repo = deps.analytics_repository
    for run in cohort.runs:  # um write por run (#119)
        repo.write(
            layer=_SILVER,
            table="dim_run",
            rows=[
                {
                    "schema_version": 1,
                    "run_id": prefix + run.run_id,
                    "asset": _ASSET,
                    "parent_sweep_id": sweep,
                    "feature_set_name": run.feature_set_name,
                    "config_signature": run.config_signature,
                    "split_fingerprint": "split-e2e",
                    "fold": run.fold,
                    "seed": run.seed,
                    "model_version": run.model,
                }
            ],
        )
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[
            {
                "schema_version": 1,
                "run_id": prefix + record.run_id,
                "model_version": record.model,
                "asset": _ASSET,
                "feature_set_name": "fs-core",
                "split": record.split,
                "horizon": record.horizon,
                "decision_idx": record.decision_idx + index_offset,
                "timestamp_utc": record.decision_timestamp,
                "target_timestamp_utc": record.target_timestamp,
                "quantile_level": record.quantile_level,
                "value_raw": record.value_raw,
                "value_guardrail": record.value_guardrail,
                "guardrail_applied": int(record.guardrail_applied),
                "year": int(record.target_timestamp[:4]),
            }
            for record in cohort.records
        ],
    )


def _dataset_rows(cohort: Cohort) -> list[dict[str, object]]:
    """Linhas do dataset: `_WARMUP` de aquecimento (NaN na 1ª feature) + as sessões."""
    realized = cohort.realized
    columns = modeling_columns()
    features = [name for name in columns if name != "target_return"]
    first = datetime.fromisoformat(realized.timestamps[0])
    stamps = [first - timedelta(days=_WARMUP - i) for i in range(_WARMUP)]
    stamps += [datetime.fromisoformat(ts) for ts in realized.timestamps]
    returns = [0.0] * _WARMUP + list(realized.returns)
    rows: list[dict[str, object]] = []
    for i, (stamp, target) in enumerate(zip(stamps, returns, strict=True)):
        row: dict[str, object] = {"timestamp": stamp, "asset_id": _ASSET, "target_return": target}
        for j, name in enumerate(features):
            row[name] = math.nan if (i < _WARMUP and j == 0) else math.sin(i + 1.5 * j)
        rows.append(row)
    return rows


def _write_dataset(data_root: Path, rows: list[dict[str, object]]) -> None:
    target = data_root / "processed" / "dataset_tft" / _ASSET
    target.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target / f"dataset_tft_{_ASSET}.parquet", index=False)


def _oracle_fingerprint(rows: list[dict[str, object]]) -> str:
    """O fingerprint da grade pela função da 5.5 (o oráculo do e2e)."""
    grid = build_training_grid(rows, columns=modeling_columns())
    return grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=_ASSET)


def _drop_interior_gbm_target(data_root: Path, cohort: Cohort) -> str:
    """Reescreve a partição de fatos sem um alvo interior de um run do GBM (cohort A)."""
    target = targets_of(cohort, _GBM, None, 1)[20]
    run_id = next(
        r.run_id
        for r in cohort.records
        if (r.model, r.horizon, r.target_timestamp) == (_GBM, 1, target)
    )
    files = sorted((data_root / _SILVER / "fact_oos_predictions").rglob("*.parquet"))
    assert files
    for path in files:
        table = pq.ParquetFile(path).read()
        rows = [
            row
            for row in table.to_pylist()
            if not (row["run_id"] == run_id and row["target_timestamp_utc"] == target)
        ]
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    return target


def _command(sweep: str, fingerprint: str) -> RefreshGoldCommand:
    return RefreshGoldCommand(
        asset=_ASSET,
        parent_sweep_id=sweep,
        horizons=_HORIZONS,
        window_deficits={_CANDIDATE: 3},
        parameters=_PARAMETERS,
        dataset_fingerprint=fingerprint,
    )


@dataclass(frozen=True)
class _Generation:
    result: RefreshGoldResult
    manifest: dict[str, object]
    tables: dict[str, Rows]
    columns: dict[str, list[str]]
    counts: dict[str, int]
    files: tuple[str, ...]

    def column(self, table: str, name: str) -> list[object]:
        index = self.columns[table].index(name)
        return [row[index] for row in self.tables[table]]


def _current(deps: ApplicationDependencies, sweep: str) -> Path:
    return deps.refresh_gold._gold_store.current_dir(GoldPartition(_ASSET, sweep))  # type: ignore[attr-defined]


def _snapshot(deps: ApplicationDependencies, sweep: str, result: RefreshGoldResult) -> _Generation:
    current = _current(deps, sweep)
    manifest = json.loads((current / "MANIFEST.json").read_text(encoding="utf-8"))
    tables: dict[str, Rows] = {}
    columns: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    connection = duckdb.connect()
    for name in manifest["rows_by_table"]:
        path = str(current / f"{name}.parquet")
        cursor = connection.execute(
            "SELECT * FROM read_parquet(?, hive_partitioning = false)", [path]
        )
        columns[name] = [column[0] for column in cursor.description]
        tables[name] = cursor.fetchall()
        counts[name] = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?, hive_partitioning = false)", [path]
        ).fetchone()[0]  # type: ignore[index]
    return _Generation(
        result=result,
        manifest=manifest,
        tables=tables,
        columns=columns,
        counts=counts,
        files=tuple(sorted(p.name for p in current.iterdir())),
    )


def _bytes(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


class _StepCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@dataclass(frozen=True)
class _Scenario:
    deps: ApplicationDependencies
    cohort_b_before: dict[str, bytes]
    cohort_b_after: dict[str, bytes]
    completed: _Generation
    rerun: _Generation
    blocked: _Generation
    delegate_loaded_after_step_1: bool
    step_1_logs: tuple[str, ...]
    gap_target: str
    oracle_fingerprint: str
    first_grid_timestamp: str
    mismatch_error: str
    current_before_mismatch: dict[str, bytes]
    current_after_mismatch: dict[str, bytes]
    full_index: _Generation


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    data_root = tmp_path_factory.mktemp("e2e-refresh-gold")
    cohort = _cohort()
    deps = wire_dependencies(
        settings=Settings(
            _env_file=None,
            data_root=data_root,
            mlflow_tracking_uri=f"sqlite:///{data_root}/mlruns.db",
        )
    )
    _write_silver(deps, cohort, sweep=_SWEEP_A, prefix="")
    _write_silver(deps, cohort, sweep=_SWEEP_B, prefix="b-")
    _write_silver(deps, cohort, sweep=_SWEEP_C, prefix="c-", index_offset=_WARMUP)
    rows = _dataset_rows(cohort)
    _write_dataset(data_root, rows)
    oracle = _oracle_fingerprint(rows)
    refresh = deps.refresh_gold

    result_b = refresh(_command(_SWEEP_B, oracle))  # (0)
    assert result_b.status is RefreshStatus.COMPLETED
    cohort_b_before = _bytes(_current(deps, _SWEEP_B))

    capture = _StepCapture()
    logger = logging.getLogger(refresh_gold_module.__name__)
    logger.addHandler(capture)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        completed = _snapshot(deps, _SWEEP_A, refresh(_command(_SWEEP_A, oracle)))  # (1)
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)
    loaded = refresh._mcs_backend._delegate is not None  # type: ignore[attr-defined]
    rerun = _snapshot(deps, _SWEEP_A, refresh(_command(_SWEEP_A, oracle)))  # (2)
    before_mismatch = _bytes(_current(deps, _SWEEP_A))
    with pytest.raises(GridFingerprintMismatchError) as raised:  # (2b)
        refresh(_command(_SWEEP_A, "0" * 64))
    after_mismatch = _bytes(_current(deps, _SWEEP_A))
    gap = _drop_interior_gbm_target(data_root, cohort)  # (3)
    blocked = _snapshot(deps, _SWEEP_A, refresh(_command(_SWEEP_A, oracle)))
    full_index = _snapshot(deps, _SWEEP_C, refresh(_command(_SWEEP_C, oracle)))  # (4)
    return _Scenario(
        deps=deps,
        cohort_b_before=cohort_b_before,
        cohort_b_after=_bytes(_current(deps, _SWEEP_B)),
        completed=completed,
        rerun=rerun,
        blocked=blocked,
        delegate_loaded_after_step_1=loaded,
        step_1_logs=tuple(capture.messages),
        gap_target=gap,
        oracle_fingerprint=oracle,
        first_grid_timestamp=rows[_WARMUP]["timestamp"].isoformat(),  # type: ignore[attr-defined]
        mismatch_error=str(raised.value),
        current_before_mismatch=before_mismatch,
        current_after_mismatch=after_mismatch,
        full_index=full_index,
    )


def _same(left: Rows, right: Rows) -> bool:
    """Igualdade célula a célula com NaN = NaN."""
    if len(left) != len(right):
        return False
    for row_l, row_r in zip(left, right, strict=True):
        for a, b in zip(row_l, row_r, strict=True):
            both_nan = (
                isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b)
            )
            if a != b and not both_nan:
                return False
    return True


def test_e2e_wired_lazy_backend_loaded(scenario: _Scenario) -> None:
    """O `RefreshGold` de `wire_dependencies` carregou o `ArchMcs` só depois de usá-lo."""
    assert scenario.delegate_loaded_after_step_1
    steps = [m for m in scenario.step_1_logs if " step=" in m]
    assert any("step=mcs " in m for m in steps)
    assert scenario.step_1_logs[-1].startswith("refresh_gold status=COMPLETED")


def test_e2e_completed_five_tables(scenario: _Scenario) -> None:
    generation = scenario.completed
    assert generation.result.status is RefreshStatus.COMPLETED
    assert generation.manifest["status"] == "COMPLETED"
    assert generation.manifest["preregistration_ref"] == _PREREG
    assert sorted(generation.manifest["rows_by_table"]) == sorted(_TABLES)  # type: ignore[arg-type]
    assert generation.files == tuple(sorted(("MANIFEST.json", *(f"{t}.parquet" for t in _TABLES))))
    assert all(generation.tables[name] for name in _TABLES)


def test_e2e_duckdb_counts(scenario: _Scenario) -> None:
    generation = scenario.completed
    assert generation.counts == generation.manifest["rows_by_table"]
    assert generation.counts == dict(generation.result.rows_by_table)
    assert generation.counts["gold_dm_results"] == (_K - 1) * len(_ESTIMATORS) * len(_HORIZONS)
    assert generation.counts["gold_mcs_results"] == _K * len(_SCHEMES) * len(_HORIZONS)
    assert set(generation.column("gold_mcs_results", "reps")) == {_PARAMETERS.mcs_reps}
    assert set(generation.column("gold_mcs_results", "seed")) == {_PARAMETERS.mcs_seed}
    for name in ("p_value", "adjusted_p_value", "rejected"):
        assert None not in generation.column("gold_dm_results", name)
    assert None not in generation.column("gold_mcs_results", "mcs_p_value")


def test_e2e_rerun_identical(scenario: _Scenario) -> None:
    """Rerun sem apagar: toda linha das cinco tabelas idêntica (NaN = NaN) — I16."""
    assert scenario.rerun.result == scenario.completed.result
    assert set(scenario.rerun.tables) == set(scenario.completed.tables)
    for name, rows in scenario.completed.tables.items():
        assert _same(rows, scenario.rerun.tables[name]), name


def test_e2e_manifest_same_but_timestamps(scenario: _Scenario) -> None:
    first, second = scenario.completed.manifest, scenario.rerun.manifest
    changed = {key for key in first if first[key] != second[key]}
    assert changed <= {"started_at", "finished_at"}
    assert set(first) == set(second)


def test_e2e_blocked_replaces(scenario: _Scenario) -> None:
    """Lacuna interior no silver → `BLOCKED`: só `gold_quality_checks` + manifesto."""
    generation = scenario.blocked
    assert generation.result.status is RefreshStatus.BLOCKED
    assert generation.manifest["status"] == "BLOCKED"
    assert generation.files == ("MANIFEST.json", "gold_quality_checks.parquet")
    failed = {(f.check, f.kind, f.model) for f in generation.result.failed_checks}
    assert ("alignment_check", "interior_gap", _GBM) in failed
    connection = duckdb.connect()
    path = str(_current(scenario.deps, _SWEEP_A) / "gold_quality_checks.parquet")
    outcomes = connection.execute(
        "SELECT outcome, horizon FROM read_parquet(?, hive_partitioning = false) "
        'WHERE "check" = ? AND kind = ? AND model = ?',
        [path, "alignment_check", "interior_gap", _GBM],
    ).fetchall()
    # o alvo removido é o mesmo nos dois horizontes do run: uma lacuna por horizonte
    assert sorted(outcomes) == [("fail", 1), ("fail", 2)]


def test_e2e_other_cohort_untouched(scenario: _Scenario) -> None:
    assert scenario.cohort_b_after == scenario.cohort_b_before
    assert "MANIFEST.json" in scenario.cohort_b_before


def test_e2e_warmup_prefix_completed(scenario: _Scenario) -> None:
    """Dataset com aquecimento e silver na grade aparada → COMPLETED (ADR 6.4.0009)."""
    generation = scenario.completed
    assert generation.result.status is RefreshStatus.COMPLETED
    assert generation.manifest["grid_trimmed_prefix"] == _WARMUP
    realized = generation.manifest["realized"]
    assert realized["first_timestamp"] == scenario.first_grid_timestamp  # type: ignore[index]
    assert realized["n_sessions"] == _N_SESSIONS  # type: ignore[index]
    # a proveniência publicada carrega o prefixo e o fingerprint que o use case passou
    # ao contexto dos checks (não só ao manifesto)
    checks = generation.column("gold_quality_checks", "check")
    details = generation.column("gold_quality_checks", "detail")
    [provenance] = [d for c, d in zip(checks, details, strict=True) if c == "realized_provenance"]
    assert f"grid_trimmed_prefix={_WARMUP};" in str(provenance)
    assert f"dataset_fingerprint={scenario.oracle_fingerprint};" in str(provenance)


def test_e2e_fingerprint_equals_modeling(scenario: _Scenario) -> None:
    """O fingerprint do manifesto é o `grid_fingerprint` da 5.5 sobre o mesmo dataset."""
    assert scenario.completed.manifest["dataset_fingerprint"] == scenario.oracle_fingerprint
    assert scenario.rerun.manifest["dataset_fingerprint"] == scenario.oracle_fingerprint


def test_e2e_fingerprint_mismatch_raises(scenario: _Scenario) -> None:
    """Fingerprint divergente ergue (C10) e o `current/` fica byte-igual ao do (2)."""
    assert "C10" in scenario.mismatch_error
    assert scenario.current_after_mismatch == scenario.current_before_mismatch


def test_e2e_full_index_silver_blocked(scenario: _Scenario) -> None:
    """Silver indexado no dataset INTEIRO (grade + P) → BLOCKED `decision_index_mismatch`."""
    generation = scenario.full_index
    assert generation.result.status is RefreshStatus.BLOCKED
    assert generation.files == ("MANIFEST.json", "gold_quality_checks.parquet")
    kinds = {(f.check, f.kind) for f in generation.result.failed_checks}
    assert ("alignment_check", "decision_index_mismatch") in kinds
