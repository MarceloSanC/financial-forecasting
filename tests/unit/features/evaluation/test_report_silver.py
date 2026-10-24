"""Leitura do silver das figuras conferida por unidade (Stage 8.3, Task 05; A4, I2).

O "julgado" é o `SilverContent` de um `SilverContentAccumulator` alimentado com as
mesmas linhas, como o refresh faz, mais as unidades de pares que a 8.3 não lê (runs da
ablação; `fact_permuted_predictions`/`fact_vsn_weights` do mesmo `run_id` do candidato).
O `Hasher` não tem fake por desenho (#70): um dublê local mínimo (sha256 do `repr`).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    ReportSourceMismatchError,
    SilverContentMismatchError,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    GridFingerprintMismatchError,
)
from financial_forecasting.features.evaluation.application.use_cases.report_silver import (
    VerifiedSilver,
    _check_units,
    read_verified_silver,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from tests.fakes.features.evaluation.fake_silver_table_reader import (
    SILVER_COLUMNS,
    FakeSilverTableReader,
)
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader

_ASSET = "AAPL"
_SWEEP = "cohort-r0"
_PARTITION = GoldPartition(asset=_ASSET, parent_sweep_id=_SWEEP)
_GRID_COLUMNS = ("feat_a", "target_return")
_SESSIONS = 6
_FIRST = datetime(2024, 1, 2, tzinfo=UTC)

Row = dict[str, object]


class _Sha256Hasher:
    """Dublê mínimo do `Hasher` (sem fake por desenho, #70): sha256 do `repr` ordenado."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        return sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()

    def hash_text(self, text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()


_HASHER = _Sha256Hasher()


def _session(index: int) -> str:
    return (_FIRST + timedelta(days=index)).isoformat()


def _run(run_id: str, model: str, seed: int | None, fold: str, feature_set: str) -> Row:
    return {
        "run_id": run_id,
        "asset": _ASSET,
        "parent_sweep_id": _SWEEP,
        "feature_set_name": feature_set,
        "config_signature": f"cfg-{model}",
        "fold": fold,
        "seed": seed,
        "model_version": model,
    }


def _fact(run: Row, *, split: str, decision: int, level: float, value: float) -> Row:
    return {
        "run_id": run["run_id"],
        "model_version": run["model_version"],
        "asset": _ASSET,
        "feature_set_name": run["feature_set_name"],
        "split": split,
        "horizon": 1,
        "decision_idx": decision,
        "timestamp_utc": _session(decision),
        "target_timestamp_utc": _session(decision + 1),
        "quantile_level": level,
        "value_raw": value,
        "value_guardrail": value,
        "guardrail_applied": 0,
        "year": 2024,
    }


def _world() -> dict[str, list[Row]]:
    runs = [
        _run("run-tft-1", "tft_quantile", 1, "0", "fs-core"),
        _run("run-tft-2", "tft_quantile", 2, "0", "fs-core"),
        _run("run-zero", "baseline_zero_return", None, "0", "fs-base"),
    ]
    facts = [
        _fact(run, split=split, decision=decision, level=level, value=level - 0.5 + decision / 10)
        for run in runs
        for split, decision in (("calib", 0), ("test", 2), ("test", 3))
        for level in (0.1, 0.5, 0.9)
    ]
    # outro cohort no mesmo feature_set (e outro ativo): filtrados antes do hash
    stranger = _run("run-other", "tft_quantile", 1, "0", "fs-core")
    stranger["parent_sweep_id"] = "other-cohort"
    facts.append(_fact(stranger, split="test", decision=2, level=0.5, value=9.0))
    foreign = _fact(runs[0], split="test", decision=4, level=0.5, value=7.0)
    foreign["asset"] = "MSFT"
    facts.append(foreign)
    return {"dim_run": [*runs, stranger], "fact_oos_predictions": facts}


def _dataset(returns: list[float] | None = None) -> list[Row]:
    values = returns or [0.01 * (index + 1) for index in range(_SESSIONS)]
    return [
        {"timestamp": _FIRST + timedelta(days=index), "feat_a": 1.0, "target_return": value}
        for index, value in enumerate(values)
    ]


def _fingerprint(dataset: list[Row]) -> str:
    grid = build_training_grid(dataset, columns=_GRID_COLUMNS)
    return grid_fingerprint(grid, hasher=_HASHER, asset_id=_ASSET)


def _judged(
    world: dict[str, list[Row]], dataset: list[Row], *, extra: Mapping[str, str] | None = None
) -> SilverContent:
    """O que o refresh julgado registrou: as mesmas linhas pós-filtradas + pares não lidos."""
    accumulator = SilverContentAccumulator(hasher=_HASHER)
    cohort_runs = [r for r in world["dim_run"] if r["parent_sweep_id"] == _SWEEP]
    run_ids = {r["run_id"] for r in cohort_runs}
    accumulator.add_dim_run(
        columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=_SWEEP, rows=cohort_runs
    )
    accumulator.add_facts(
        table="fact_oos_predictions",
        columns=SILVER_COLUMNS["fact_oos_predictions"],
        rows=[
            row
            for row in world["fact_oos_predictions"]
            if row["run_id"] in run_ids and row["asset"] == _ASSET
        ],
    )
    grid = build_training_grid(dataset, columns=_GRID_COLUMNS)
    accumulator.add_realized(
        asset=_ASSET,
        realized=RealizedReturns(
            timestamps=grid.timestamps_iso(), returns=grid.column("target_return")
        ),
    )
    content = accumulator.result()
    units = {**content.units, **(extra or {})}
    return SilverContent(digest=content.digest, tables=content.tables, units=units)


def _read(
    world: dict[str, list[Row]],
    *,
    judged: SilverContent,
    dataset: list[Row] | None = None,
    fingerprint: str | None = None,
) -> VerifiedSilver:
    data = _dataset() if dataset is None else dataset
    return read_verified_silver(
        silver_reader=FakeSilverTableReader(world),
        grid_reader=FakeTrainingGridReader({_ASSET: data}, columns=_GRID_COLUMNS, hasher=_HASHER),
        hasher=_HASHER,
        partition=_PARTITION,
        expected_fingerprint=_fingerprint(data) if fingerprint is None else fingerprint,
        judged=judged,
    )


def _mismatch_keys(
    world: dict[str, list[Row]], judged: SilverContent, **kwargs: object
) -> tuple[str, ...]:
    with pytest.raises(SilverContentMismatchError) as caught:
        _read(world, judged=judged, **kwargs)  # type: ignore[arg-type]
    return caught.value.keys


@pytest.mark.unit
def test_identical_silver_passes_and_returns_runs_records_realized() -> None:
    world = _world()
    verified = _read(world, judged=_judged(world, _dataset()))
    assert [run.run_id for run in verified.runs] == ["run-tft-1", "run-tft-2", "run-zero"]
    records = verified.records
    assert len(records) == 27  # noqa: PLR2004 — 3 runs, 3 decisões, 3 níveis
    assert {r.split for r in records} == {"calib", "test"}
    assert all(r.run_id != "run-other" and r.decision_idx != 4 for r in records)  # noqa: PLR2004
    assert verified.realized.returns[0] == 0.01  # noqa: PLR2004
    assert set(verified.units) == {
        "dim_run|cohort-r0",
        "fact_oos_predictions|run-tft-1|2024",
        "fact_oos_predictions|run-tft-2|2024",
        "fact_oos_predictions|run-zero|2024",
        "realized|AAPL",
    }


@pytest.mark.unit
def test_altered_test_row_raises_with_unit_key() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    altered = copy.deepcopy(world)
    altered["fact_oos_predictions"][4]["value_guardrail"] = 123.0  # run-tft-1, test
    assert altered["fact_oos_predictions"][4]["split"] == "test"
    assert _mismatch_keys(altered, judged) == ("fact_oos_predictions|run-tft-1|2024",)


@pytest.mark.unit
def test_altered_calib_row_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    altered = copy.deepcopy(world)
    row = next(
        r
        for r in altered["fact_oos_predictions"]
        if r["run_id"] == "run-tft-2" and r["split"] == "calib"
    )
    row["value_raw"] = -1.0
    assert _mismatch_keys(altered, judged) == ("fact_oos_predictions|run-tft-2|2024",)


@pytest.mark.unit
def test_missing_unit_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    missing = copy.deepcopy(world)
    missing["fact_oos_predictions"] = [
        r for r in missing["fact_oos_predictions"] if r["run_id"] != "run-zero"
    ]
    assert _mismatch_keys(missing, judged) == ("fact_oos_predictions|run-zero|2024",)


@pytest.mark.unit
def test_extra_unit_read_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    extra = copy.deepcopy(world)
    late = _fact(extra["dim_run"][0], split="test", decision=3, level=0.5, value=0.2)
    late["year"] = 2025
    extra["fact_oos_predictions"].append(late)
    assert _mismatch_keys(extra, judged) == ("fact_oos_predictions|run-tft-1|2025",)


@pytest.mark.unit
def test_altered_realized_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    other = _dataset([0.5] * _SESSIONS)
    assert _mismatch_keys(world, judged, dataset=other) == ("realized|AAPL",)


@pytest.mark.unit
def test_altered_dim_run_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    altered = copy.deepcopy(world)
    altered["dim_run"][2]["config_signature"] = "cfg-changed"
    assert _mismatch_keys(altered, judged) == ("dim_run|cohort-r0",)


@pytest.mark.unit
def test_ablation_units_only_in_judged_pass() -> None:
    world = _world()
    judged = _judged(
        world,
        _dataset(),
        extra={
            "dim_run|ablation-r0": "ab" * 32,
            "fact_oos_predictions|run-loco-11|2024": "cd" * 32,
        },
    )
    assert _read(world, judged=judged).runs


@pytest.mark.unit
def test_permuted_and_vsn_units_of_candidate_run_id_only_in_judged_pass() -> None:
    world = _world()
    judged = _judged(
        world,
        _dataset(),
        extra={
            "fact_permuted_predictions|run-tft-1|2024": "ef" * 32,
            "fact_vsn_weights|run-tft-1|2024": "01" * 32,
        },
    )
    verified = _read(world, judged=judged)
    assert "fact_vsn_weights|run-tft-1|2024" not in verified.units


@pytest.mark.unit
def test_rows_of_other_asset_or_run_are_filtered_before_hashing() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    noisy = copy.deepcopy(world)
    noisy["fact_oos_predictions"].append(
        {**_fact(noisy["dim_run"][3], split="test", decision=3, level=0.9, value=5.0)}
    )
    verified = _read(noisy, judged=judged)
    assert all(r.run_id != "run-other" for r in verified.records)


@pytest.mark.unit
def test_grid_fingerprint_other_than_plan_raises() -> None:
    world = _world()
    with pytest.raises(GridFingerprintMismatchError, match="fingerprint"):
        _read(world, judged=_judged(world, _dataset()), fingerprint="0" * 64)


@pytest.mark.unit
def test_cohort_without_dim_run_raises() -> None:
    world = _world()
    judged = _judged(world, _dataset())
    world["dim_run"] = []
    with pytest.raises(ReportSourceMismatchError, match="dim_run"):
        _read(world, judged=judged)


@pytest.mark.unit
def test_error_message_has_keys_not_values() -> None:
    judged = {
        "dim_run|c": "a" * 64,
        "realized|AAPL": "b" * 64,
        "fact_oos_predictions|r|2024": "c" * 64,
    }
    read = {"dim_run|c": "d" * 64, "realized|AAPL": "b" * 64}
    with pytest.raises(SilverContentMismatchError) as caught:
        _check_units(judged, read, run_ids=frozenset({"r"}), parent_sweep_id="c", asset="AAPL")
    message = str(caught.value)
    assert caught.value.keys == ("dim_run|c", "fact_oos_predictions|r|2024")
    assert "a" * 64 not in message and "d" * 64 not in message and "c" * 64 not in message
