"""Cenário sintético da API de inferência para os e2e da Stage 7.4 (Checkpoint C3-2).

Silver sintético (10 seeds, folds "0" e "1", teste e calib sobrepostos, um
`gbm_quantile` no mesmo cohort), gravado pelo `ParquetAnalyticsRepository` real; gold
publicado pelo `ParquetGoldStore` real a partir das fábricas de `_serving_gold_rows`; e as
`Settings` com `data_root = tmp_path` e o arquivo de cohort real só como configuração (o
`cohort_id` sai do mesmo leitor + hasher da composition root). Nenhum dado real é lido.
Valores diádicos: os literais esperados pelos testes são exatos. Usado pelo e2e da API e
pelo gate de deep learning em subprocesso.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.evaluation._serving_gold_rows import (
    complete_rows,
    correction_row,
    generation,
)

REPO = Path(__file__).resolve().parents[4]
COHORT_FILE = REPO / "config" / "cohorts" / "aapl_confirmatory.toml"
ASSET = "AAPL"
FS = "fs_all"
LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
OFFSETS = (-0.0625, -0.03125, -0.015625, 0.0, 0.0078125, 0.03125, 0.0625)
SEEDS = tuple(range(1, 11))
CALIB_ONLY = date(2024, 3, 8)
TEST_0 = [date(2024, 3, d) for d in (11, 12, 13, 14, 15)]
CALIB_1 = [date(2024, 3, 14), date(2024, 3, 15)]
TEST_1 = [date(2024, 3, d) for d in (18, 19, 20, 21, 22)]
LAST = date(2024, 3, 22)  # só h+1
H7 = 7


def _cohort_id() -> str:
    cohort_file = importlib.import_module(
        "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
    )
    spec = cohort_file.load(COHORT_FILE)
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    cohort_id: str = spec.cohort_id(cohort_hash)
    return cohort_id


COHORT = _cohort_id()


def _ts(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _grid(seed: int, fold: int, horizon: int) -> tuple[float, ...]:
    base = seed / 512 + horizon / 4096 + fold / 8192
    return tuple(base + offset for offset in OFFSETS)


def _facts(
    run: tuple[str, int, int], split: str, day: date, horizon: int
) -> list[dict[str, object]]:
    run_id, seed, fold = run
    model = "gbm_quantile" if run_id.startswith("gbm") else "tft_quantile"
    return [
        {
            "schema_version": 1,
            "run_id": run_id,
            "model_version": model,
            "asset": ASSET,
            "feature_set_name": FS,
            "split": split,
            "horizon": horizon,
            "decision_idx": 0,
            "timestamp_utc": _ts(day),
            "target_timestamp_utc": _ts(day + timedelta(days=horizon)),
            "quantile_level": level,
            "value_raw": value,
            "value_guardrail": value,
            "guardrail_applied": 0,
            "year": day.year,
        }
        for level, value in zip(LEVELS, _grid(seed, fold, horizon), strict=True)
    ]


def _dim(run_id: str, seed: int, fold: int, model: str = "tft_quantile") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": ASSET,
        "parent_sweep_id": COHORT,
        "feature_set_name": FS,
        "config_signature": "sig",
        "split_fingerprint": "split",
        "fold": str(fold),
        "seed": seed,
        "model_version": model,
    }


def write_silver(root: Path) -> None:
    dims = [_dim(f"f{fold}s{seed}", seed, fold) for fold in (0, 1) for seed in SEEDS]
    dims.append(_dim("gbm0", 1, 0, model="gbm_quantile"))
    facts: list[dict[str, object]] = []
    for seed in SEEDS:
        for horizon in (1, H7):
            facts += _facts((f"f0s{seed}", seed, 0), "calib", CALIB_ONLY, horizon)
            for day in TEST_0:
                facts += _facts((f"f0s{seed}", seed, 0), "test", day, horizon)
            for day in CALIB_1:
                facts += _facts((f"f1s{seed}", seed, 1), "calib", day, horizon)
            for day in TEST_1:
                if not (horizon == H7 and day == LAST):
                    facts += _facts((f"f1s{seed}", seed, 1), "test", day, horizon)
    for day in TEST_0:
        facts += _facts(("gbm0", 1, 0), "test", day, 1)
    repository = ParquetAnalyticsRepository(data_root=root, clock=FakeClock())
    repository.write(layer="silver", table="dim_run", rows=dims)
    repository.write(layer="silver", table="fact_oos_predictions", rows=facts)


def _inner_pair(tail: str, correction: float) -> dict[str, object]:
    row = correction_row("0", 1, tail, correction=correction)
    return {
        **row,
        "lower_level": 0.25,
        "upper_level": 0.75,
        "tail_level": 0.25 if tail == "lower" else 0.75,
    }


def publish(
    root: Path,
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    parameters: RefreshParameters | None = None,
) -> Path:
    rows = complete_rows()
    rows[GOLD_CONFORMAL_CORRECTIONS.name] += [
        _inner_pair("lower", 0.001953125),
        _inner_pair("upper", 0.0009765625),
        # fold "1", seed 1, h+1, par (0.1, 0.9): Q_lo = 2^-4, Q_hi = 2^-5 (C2-6)
        correction_row("1", 1, "lower", correction=0.0625),
        correction_row("1", 1, "upper", correction=0.03125),
    ]
    tables, manifest = generation(status, rows=rows, parameters=parameters)
    partition = GoldPartition(ASSET, COHORT)
    tables = [
        GoldTable.sorted_by_key(t.name, t.key, [{**r, "parent_sweep_id": COHORT} for r in t.rows])
        for t in tables
    ]
    store = ParquetGoldStore(root)
    store.publish(
        partition=partition, tables=tables, manifest=replace(manifest, partition=partition)
    )
    current: Path = store.current_dir(partition)
    return current


def settings(root: Path, cohort_file: Path | None = COHORT_FILE) -> Settings:
    return Settings(
        _env_file=None,
        data_root=root,
        artifacts_root=root / "artifacts",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
        serving_cohort_file=cohort_file,
    )
