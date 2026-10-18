"""Prova de geometria do calib sobre o cohort real, ativada por ambiente (Stage 7.2 Task 21).

Concept 7.2 D8, I12 e C7. Por run TFT do cohort:

- o `SplitFingerprint` recomposto é igual ao `dim_run.split_fingerprint`;
- as decisões de calib no silver são as do `FoldSplit.calib` (h+1 e h+7);
- o calib não cruza o `early_stop`;
- todo `target_timestamp_utc` do calib vem antes do `test[0]`;
- o manifesto da inferência tem as `len(seeds) x n_folds` entradas `completed`.

Os folds saem do `cohort_tft_folds` (a mesma função do `ResolveTftCheckpoints`), com
o splitter do composition root, sobre as sessões da grade. A grade é montada pelo
`build_training_grid` com as features do painel do TFT. O splitter não é
reimplementado. O `cohort_id` vem do `CohortHash` do spec, nunca de um literal.

Cegamento (I12): a leitura é por `pyarrow` com `columns=` explícito. As três tuplas
de colunas não têm `value_*` nem `target_return`, então nenhuma previsão nem
realizado é lido. Nada é escrito no `data_root` lido, e nenhum `gold/` é criado.

O teste real é pulado sem `FF_REAL_COHORT_DATA_ROOT`. Se a variável aponta para um
caminho inexistente, ele falha em vez de pular. Os testes sintéticos rodam sempre.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from financial_forecasting import cli
from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    cohort_tft_folds,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    TFT_MODEL_VERSION,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.features.modeling.domain.value_objects.fold_split import FoldSplit
from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from financial_forecasting.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.integration

cohort_file: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_file")

_ENV = "FF_REAL_COHORT_DATA_ROOT"
_REPO = Path(__file__).resolve().parents[4]
_SPEC_FILE = _REPO / "config" / "cohorts" / "aapl_confirmatory.toml"
_CALIB = "calib"
_COMPLETED = "completed"

# As únicas colunas lidas (I12): identidade e partição do run, tempo e split das linhas.
_DIM_RUN_COLUMNS = ("run_id", "model_version", "seed", "fold", "split_fingerprint")
_FACT_COLUMNS = ("run_id", "split", "horizon", "timestamp_utc", "target_timestamp_utc")
# A grade: o timestamp e as features do painel do TFT, sem o `target_return`. As features
# entram porque o `build_training_grid` corta o prefixo sem valor por elas (o painel).
_GRID_FEATURES = (*unknown_feature_names(), *known_feature_names())
_GRID_COLUMNS = ("timestamp", *_GRID_FEATURES)


# --- a prova -----------------------------------------------------------------------------


def _day(value: object) -> str:
    """O dia ISO de um timestamp (string ISO ou `datetime`): a unidade do `FoldSplit`."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def _read(paths: list[Path], columns: tuple[str, ...]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(paths):
        rows.extend(pq.ParquetFile(path).read(columns=list(columns)).to_pylist())
    return rows


@dataclass(frozen=True)
class _Geometry:
    """O resultado da prova: os problemas achados e a linha-resumo."""

    problems: tuple[str, ...]
    summary: str


def _sessions(root: Path, asset: str) -> tuple[date, ...]:
    dataset = root / "processed" / "dataset_tft" / asset / f"dataset_tft_{asset}.parquet"
    rows = _read([dataset], _GRID_COLUMNS)
    return build_training_grid(rows, columns=_GRID_FEATURES).sessions()


def _manifest_problems(root: Path, cohort_id: str, expected: int) -> list[str]:
    path = root / "inference" / cohort_id / "manifest.json"
    if not path.is_file():
        return [f"manifest {path} is missing"]
    runs = json.loads(path.read_text(encoding="utf-8")).get("runs", {})
    completed = sum(1 for entry in runs.values() if entry.get("status") == _COMPLETED)
    if completed != expected:
        return [f"manifest has {completed} completed entries, expected {expected}"]
    return []


def _fold_problems(
    run_id: str,
    fold: FoldSplit,
    fingerprint: object,
    calib: list[dict[str, object]],
    horizons: tuple[int, ...],
) -> list[str]:
    problems: list[str] = []
    if fingerprint != fold.fingerprint.value:
        problems.append(f"{run_id}: split_fingerprint differs from the recomposed FoldSplit")
    expected = set(fold.calib)
    early_stop = set(fold.early_stop)
    for horizon in horizons:
        decisions = {_day(row["timestamp_utc"]) for row in calib if row["horizon"] == horizon}
        if decisions != expected:
            extra, missing = sorted(decisions - expected), sorted(expected - decisions)
            problems.append(
                f"{run_id} h={horizon}: calib decisions != FoldSplit.calib "
                f"(extra {extra[:3]}, missing {missing[:3]})"
            )
        if decisions & early_stop:
            problems.append(f"{run_id} h={horizon}: calib intersects early_stop")
    late = sorted(
        {d for d in (_day(r["target_timestamp_utc"]) for r in calib) if d >= fold.test[0]}
    )
    if late:
        problems.append(f"{run_id}: calib targets at or after test[0] {fold.test[0]}: {late[:3]}")
    return problems


def check_geometry(root: Path, spec: CohortSpec, splitter: WalkForwardSplitter) -> _Geometry:
    """A prova de D8 sobre um `data_root`: só tempo, partições, fingerprints e manifesto."""
    hasher = CanonicalJsonHasher()
    cohort_id = spec.cohort_id(CohortHash.compute(hasher=hasher, payload=spec.hash_payload()))
    asset = spec.asset_id
    dim_run = [
        row
        for row in _read(
            list(
                (
                    root / "silver" / "dim_run" / f"asset={asset}" / f"parent_sweep_id={cohort_id}"
                ).glob("*.parquet")
            ),
            _DIM_RUN_COLUMNS,
        )
        if row["model_version"] == TFT_MODEL_VERSION
    ]
    facts_dir = root / "silver" / "fact_oos_predictions" / f"asset={asset}"
    facts_dir /= f"feature_set_name={spec.feature_set_name}"
    calib_by_run: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in _read(list(facts_dir.glob("year=*/*.parquet")), _FACT_COLUMNS):
        if row["split"] == _CALIB:
            calib_by_run[str(row["run_id"])].append(row)
    sessions = _sessions(root, asset)
    problems: list[str] = []
    by_unit = {(row["seed"], str(row["fold"])): row for row in dim_run}
    checked = 0
    for seed in spec.seeds:
        _, _, _, folds = cohort_tft_folds(
            spec, seed=seed, panel_sessions=sessions, splitter=splitter, hasher=hasher
        )
        for fold in folds:
            run = by_unit.get((seed, str(fold.fold_index)))
            if run is None:
                problems.append(f"seed {seed} fold {fold.fold_index}: no TFT run in dim_run")
                continue
            run_id = str(run["run_id"])
            calib = calib_by_run.pop(run_id, [])
            problems += _fold_problems(run_id, fold, run["split_fingerprint"], calib, spec.horizons)
            checked += 1
    if calib_by_run:
        problems.append(f"calib rows of runs outside the cohort folds: {sorted(calib_by_run)[:3]}")
    expected = len(spec.seeds) * spec.geometry.n_folds
    problems += _manifest_problems(root, cohort_id, expected)
    summary = (
        f"geometry cohort={cohort_id} runs_checked={checked}/{expected} "
        f"horizons={list(spec.horizons)} calib_size={spec.geometry.calib_size} "
        f"problems={len(problems)}"
    )
    return _Geometry(problems=tuple(problems), summary=summary)


# --- raiz sintética ---------------------------------------------------------------------

_ASSET = "AAPL"
_FIRST = date(2019, 1, 2)
_N_SESSIONS = 320


def _spec() -> CohortSpec:
    """Duas seeds, dois folds, h em {1, 7}; o spec congelado (só o que os folds leem)."""
    tft_base = TftTrainingParams(
        seed=0,
        max_encoder_length=10,
        hidden_size=4,
        attention_head_size=1,
        hidden_continuous_size=2,
        max_epochs=1,
        patience=1,
        batch_size=32,
    )
    return CohortSpec(
        name="geometry-synthetic",
        revision=0,
        asset_id=_ASSET,
        feature_set_name="fs-geometry",
        feature_set_hash=feature_set_hash(),
        pipeline_version=PIPELINE_VERSION,
        horizons=(1, 7),
        quantile_levels=(0.1, 0.5, 0.9),
        geometry=CohortGeometry(n_folds=2, test_size=20, val_size=20, calib_size=16, embargo=1),
        device="cpu",
        seeds=(11, 12),
        sweep=SweepPlan(
            tft_space=(SearchDimension(name="dropout", low=0.0, high=0.2, kind="float"),),
            tft_base_params=tft_base,
            gbm_space=(SearchDimension(name="num_leaves", low=4, high=16, kind="int"),),
            gbm_base_params=GbmTrainingParams(seed=7, num_boost_round_max=20),
            n_trials=1,
            sampler_seed=2026,
        ),
        tft_params=replace(tft_base, dropout=0.1),
        gbm_params=None,
        baseline_specs=BaselineSpec.canonical_five(historical_quantiles_window=20),
        provenance=None,
        dataset_fingerprint=None,
    )


def _calendar_sessions() -> tuple[date, ...]:
    window = ExchangeCalendarsProvider().sessions(start=_FIRST, end=date(2020, 12, 31))
    return window.sessions[:_N_SESSIONS]


def _write_dataset(root: Path, sessions: tuple[date, ...]) -> None:
    names = {*modeling_columns(), *_GRID_FEATURES}
    rows = [
        {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _ASSET,
            **{name: math.sin(i + 0.7 * j) for j, name in enumerate(sorted(names))},
        }
        for i, day in enumerate(sessions)
    ]
    target = root / "processed" / "dataset_tft" / _ASSET
    target.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target / f"dataset_tft_{_ASSET}.parquet", index=False)


def _iso(day: str) -> str:
    return f"{day}T00:00:00+00:00"


def _write_root(
    root: Path, spec: CohortSpec, splitter: WalkForwardSplitter, plant: str | None = None
) -> None:
    """Raiz consistente com os folds do spec; `plant` estraga um ponto (um caso do C7)."""
    sessions = _calendar_sessions()
    _write_dataset(root, sessions)
    hasher = CanonicalJsonHasher()
    cohort_id = spec.cohort_id(CohortHash.compute(hasher=hasher, payload=spec.hash_payload()))
    index = {day.isoformat(): i for i, day in enumerate(sessions)}
    runs: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    manifest: dict[str, object] = {}
    for seed in spec.seeds:
        _, _, _, folds = cohort_tft_folds(
            spec, seed=seed, panel_sessions=sessions, splitter=splitter, hasher=hasher
        )
        for fold in folds:
            run_id = f"{cohort_id}-tft-s{seed}-f{fold.fold_index}"
            first = (seed, fold.fold_index) == (spec.seeds[0], 0)
            fingerprint = fold.fingerprint.value
            if first and plant == "fingerprint":
                fingerprint = "0" * 64
            runs.append(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "asset": _ASSET,
                    "parent_sweep_id": cohort_id,
                    "feature_set_name": spec.feature_set_name,
                    "config_signature": "sig-tft",
                    "split_fingerprint": fingerprint,
                    "fold": str(fold.fold_index),
                    "seed": seed,
                    "model_version": TFT_MODEL_VERSION,
                }
            )
            decisions = list(fold.calib)
            if first and plant == "outside_calib":
                decisions[0] = fold.train[-1]
            if first and plant == "early_stop":
                decisions[0] = fold.early_stop[-1]
            for horizon in spec.horizons:
                for position, decision in enumerate(decisions):
                    target = sessions[index[decision] + horizon].isoformat()
                    if first and plant == "late_target" and position == len(decisions) - 1:
                        target = fold.test[0]
                    facts.extend(
                        {
                            "schema_version": 1,
                            "run_id": run_id,
                            "model_version": TFT_MODEL_VERSION,
                            "asset": _ASSET,
                            "feature_set_name": spec.feature_set_name,
                            "split": _CALIB,
                            "horizon": horizon,
                            "decision_idx": index[decision],
                            "timestamp_utc": _iso(decision),
                            "target_timestamp_utc": _iso(target),
                            "quantile_level": level,
                            "value_raw": 0.0,
                            "value_guardrail": 0.0,
                            "guardrail_applied": 0,
                            "year": int(target[:4]),
                        }
                        for level in spec.quantile_levels
                    )
            status = "started" if first and plant == "manifest" else _COMPLETED
            manifest[run_id] = {"status": status}
    repository = ParquetAnalyticsRepository(data_root=root, clock=SystemClock())
    repository.write(layer="silver", table="dim_run", rows=runs)
    repository.write(layer="silver", table="fact_oos_predictions", rows=facts)
    folder = root / "inference" / cohort_id
    folder.mkdir(parents=True)
    document = {"cohort_id": cohort_id, "runs": manifest}
    (folder / "manifest.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture(scope="module")
def splitter(tmp_path_factory: pytest.TempPathFactory) -> WalkForwardSplitter:
    """O splitter do composition root (o calendário real da janela ampla)."""
    root = tmp_path_factory.mktemp("geometry-wiring")
    deps = wire_dependencies(settings=Settings(_env_file=None, data_root=root / "data"))
    wired: WalkForwardSplitter = deps.run_baselines._splitter
    return wired


# --- testes ------------------------------------------------------------------------------


def test_requested_columns_exclude_values_and_target() -> None:
    for columns in (_DIM_RUN_COLUMNS, _FACT_COLUMNS, _GRID_COLUMNS):
        assert not [c for c in columns if c.startswith("value_") or c == "target_return"]
    assert "target_return" not in _GRID_FEATURES


def test_checks_pass_on_a_consistent_synthetic_root(
    tmp_path: Path, splitter: WalkForwardSplitter
) -> None:
    spec = _spec()
    _write_root(tmp_path, spec, splitter)
    result = check_geometry(tmp_path, spec, splitter)
    assert result.problems == ()
    assert "runs_checked=4/4" in result.summary
    assert not (tmp_path / "gold").exists()


@pytest.mark.parametrize(
    ("plant", "expected"),
    [
        ("fingerprint", "split_fingerprint differs"),
        ("outside_calib", "calib decisions != FoldSplit.calib"),
        ("early_stop", "calib intersects early_stop"),
        ("late_target", "calib targets at or after test[0]"),
        ("manifest", "manifest has 3 completed entries, expected 4"),
    ],
)
def test_checks_fail_on_a_planted_violation(
    tmp_path: Path, splitter: WalkForwardSplitter, plant: str, expected: str
) -> None:
    spec = _spec()
    _write_root(tmp_path, spec, splitter, plant)
    problems = check_geometry(tmp_path, spec, splitter).problems
    assert any(expected in problem for problem in problems), problems


def test_real_cohort_calib_geometry(splitter: WalkForwardSplitter) -> None:
    """Etapa G (CA10): pulado sem a variável; caminho inexistente falha."""
    value = os.environ.get(_ENV)
    if not value:
        pytest.skip(f"{_ENV} is not set (Etapa G runs it over the real cohort, read-only)")
    root = Path(value)
    assert root.is_dir(), f"{_ENV}={value!r} is not an existing directory"
    spec = cohort_file.load(_SPEC_FILE)
    result = check_geometry(root, spec, splitter)
    print(result.summary)  # a linha-resumo da Etapa G
    assert result.problems == (), result.problems


def test_real_cohort_with_missing_root_fails_instead_of_skipping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, splitter: WalkForwardSplitter
) -> None:
    monkeypatch.setenv(_ENV, str(tmp_path / "missing"))
    with pytest.raises(AssertionError, match="is not an existing directory"):
        test_real_cohort_calib_geometry(splitter)


def test_the_real_spec_file_is_frozen_with_the_geometry_the_check_reads() -> None:
    spec = cohort_file.load(_SPEC_FILE)
    assert spec.is_frozen()
    assert spec.tft_params is not None
    assert set(spec.horizons) == {1, 7}
