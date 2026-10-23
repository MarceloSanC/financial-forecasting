"""Testes do `SilverContentAccumulator` e do DTO `SilverContent` (Stage 8.1 Task 03).

Critérios A2 (lógica de unidades e de quem muda o quê, com tipos do fake) e I6. Com o
`FloatRefusingHasher` (dublê stdlib do `Hasher`, sem fake por desenho — issue #70; o gate
de pureza proíbe importar o adapter real): além do hash, prova que nenhum `float` cru
chega ao hasher. O comportamento contra o `CanonicalJsonHasher` real fica na integração.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    REALIZED_TABLE,
    SilverContent,
    unit_key,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    REALIZED_COLUMNS,
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    SilverContentHash,
)
from tests.fakes.features.evaluation.fake_silver_table_reader import SILVER_COLUMNS
from tests.unit.features.evaluation._preregistration_payload import FloatRefusingHasher

_OOS = "fact_oos_predictions"
_SWEEP = "aapl_confirmatory-r0"
_ASSET = "AAPL"
_HEX = "a" * 64
_REALIZED = RealizedReturns(
    timestamps=("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00"),
    returns=(0.0125, -0.003),
)


def _dim_run(run_id: str, *, seed: int | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": _ASSET,
        "parent_sweep_id": _SWEEP,
        "feature_set_name": "fs-core",
        "config_signature": "sig",
        "split_fingerprint": "split",
        "fold": "0",
        "seed": seed,
        "model_version": "tft",
        "created_at_utc": "2026-10-22T00:00:00+00:00",
    }


def _fact(run_id: str, *, year: int, level: float = 0.5) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": "tft",
        "asset": _ASSET,
        "feature_set_name": "fs-core",
        "split": "test",
        "horizon": 1,
        "decision_idx": year - 2000,
        "timestamp_utc": f"{year}-01-05T00:00:00+00:00",
        "target_timestamp_utc": f"{year}-01-08T00:00:00+00:00",
        "quantile_level": level,
        "value_raw": 0.01 * level,
        "value_guardrail": 0.01 * level,
        "guardrail_applied": 0,
        "year": year,
    }


_DIM_RUNS = [_dim_run("run-a", seed=1), _dim_run("run-b", seed=None)]
_FACTS = [
    _fact("run-a", year=2023),
    _fact("run-a", year=2023, level=0.25),
    _fact("run-a", year=2024),
    _fact("run-b", year=2024),
]


def _accumulator() -> SilverContentAccumulator:
    return SilverContentAccumulator(hasher=FloatRefusingHasher())


def _content(
    *,
    dim_runs: list[dict[str, object]] = _DIM_RUNS,
    facts: list[dict[str, object]] = _FACTS,
    realized: RealizedReturns = _REALIZED,
) -> SilverContent:
    accumulator = _accumulator()
    accumulator.add_dim_run(
        columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=_SWEEP, rows=dim_runs
    )
    accumulator.add_facts(table=_OOS, columns=SILVER_COLUMNS[_OOS], rows=facts)
    accumulator.add_realized(asset=_ASSET, realized=realized)
    return accumulator.result()


@pytest.mark.unit
def test_year_taken_from_row_one_pass_equals_per_year_passes() -> None:
    per_year = _accumulator()
    per_year.add_dim_run(columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=_SWEEP, rows=_DIM_RUNS)
    for year in (2024, 2023):
        per_year.add_facts(
            table=_OOS,
            columns=SILVER_COLUMNS[_OOS],
            rows=[row for row in _FACTS if row["year"] == year],
        )
    per_year.add_realized(asset=_ASSET, realized=_REALIZED)

    assert per_year.result() == _content()


@pytest.mark.unit
def test_same_unit_in_two_reads_raises() -> None:
    accumulator = _accumulator()
    accumulator.add_facts(table=_OOS, columns=SILVER_COLUMNS[_OOS], rows=_FACTS[:1])
    with pytest.raises(ValueError, match=r"fact_oos_predictions\|run-a\|2023"):
        accumulator.add_facts(table=_OOS, columns=SILVER_COLUMNS[_OOS], rows=_FACTS[1:2])

    accumulator.add_dim_run(
        columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=_SWEEP, rows=_DIM_RUNS
    )
    with pytest.raises(ValueError, match="already read"):
        accumulator.add_dim_run(columns=SILVER_COLUMNS["dim_run"], parent_sweep_id=_SWEEP, rows=[])


@pytest.mark.unit
def test_tables_and_units_keys_format() -> None:
    content = _content()

    assert set(content.units) == {
        f"dim_run|{_SWEEP}",
        "fact_oos_predictions|run-a|2023",
        "fact_oos_predictions|run-a|2024",
        "fact_oos_predictions|run-b|2024",
        f"realized|{_ASSET}",
    }
    assert set(content.tables) == {"dim_run", _OOS, REALIZED_TABLE}
    assert unit_key(_OOS, "run-a", 2023) == "fact_oos_predictions|run-a|2023"


@pytest.mark.unit
def test_changing_one_row_changes_only_its_unit_its_table_and_total() -> None:
    base = _content()
    facts = [dict(row) for row in _FACTS]
    facts[2]["value_raw"] = 0.123
    changed = _content(facts=facts)

    changed_units = {key for key in base.units if base.units[key] != changed.units[key]}
    changed_tables = {key for key in base.tables if base.tables[key] != changed.tables[key]}
    assert changed_units == {"fact_oos_predictions|run-a|2024"}
    assert changed_tables == {_OOS}
    assert changed.digest != base.digest


@pytest.mark.unit
def test_realized_unit_uses_declared_str_and_float_kinds() -> None:
    expected = SilverContentHash.of_unit(
        hasher=FloatRefusingHasher(),
        table=REALIZED_TABLE,
        columns={"timestamp": ("str", False), "target_return": ("float", False)},
        rows=[
            {"timestamp": timestamp, "target_return": value}
            for timestamp, value in zip(_REALIZED.timestamps, _REALIZED.returns, strict=True)
        ],
    )

    assert dict(REALIZED_COLUMNS) == {
        "timestamp": ("str", False),
        "target_return": ("float", False),
    }
    assert _content().units[f"realized|{_ASSET}"] == expected.value
    # Float exato: um retorno que o arredondamento a 10 casas igualaria muda a unidade.
    nudged = RealizedReturns(
        timestamps=_REALIZED.timestamps, returns=(0.0125 + 1e-12, _REALIZED.returns[1])
    )
    assert _content(realized=nudged).units[f"realized|{_ASSET}"] != expected.value


@pytest.mark.unit
def test_silver_content_round_trip_and_rejects_bad_hex_or_missing_key() -> None:
    content = _content()
    mapping = content.as_mapping()

    assert SilverContent.from_mapping(mapping) == content
    assert list(mapping) == ["digest", "tables", "units"]
    with pytest.raises(ValueError, match="misses the keys"):
        SilverContent.from_mapping({"digest": _HEX, "tables": {}})
    with pytest.raises(ValueError, match="unknown keys"):
        SilverContent.from_mapping({**mapping, "extra": 1})
    with pytest.raises(ValueError, match="sha256 hex"):
        SilverContent.from_mapping({**mapping, "digest": "A" * 64})
    with pytest.raises(ValueError, match="sha256 hex"):
        SilverContent(digest=_HEX, tables={"dim_run": "xyz"}, units={})
    with pytest.raises(ValueError, match="sha256 hex"):
        SilverContent(digest=_HEX, tables={}, units={"dim_run|s": _HEX[:-1]})


@pytest.mark.unit
@pytest.mark.parametrize(
    "row",
    [
        pytest.param({k: v for k, v in _FACTS[0].items() if k != "run_id"}, id="no-run-id"),
        pytest.param({**_FACTS[0], "run_id": ""}, id="empty-run-id"),
        pytest.param({k: v for k, v in _FACTS[0].items() if k != "year"}, id="no-year"),
        pytest.param({**_FACTS[0], "year": 2023.0}, id="float-year"),
        pytest.param({**_FACTS[0], "year": "2023"}, id="str-year"),
        pytest.param({**_FACTS[0], "year": True}, id="bool-year"),
    ],
)
def test_row_without_run_id_or_int_year_raises(row: Mapping[str, object]) -> None:
    with pytest.raises(ValueError, match=r"run_id|int year"):
        _accumulator().add_facts(table=_OOS, columns=SILVER_COLUMNS[_OOS], rows=[row])


@pytest.mark.unit
def test_created_at_utc_declared_in_dim_run_does_not_change_units() -> None:
    """O `dim_run` declara `created_at_utc` (fake e real): proveniência fica fora do hash."""
    rewritten = [{**row, "created_at_utc": "2030-01-01T00:00:00+00:00"} for row in _DIM_RUNS]

    assert "created_at_utc" in SILVER_COLUMNS["dim_run"]
    assert _content(dim_runs=rewritten) == _content()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("parts", "message"),
    [
        pytest.param((), "at least one part", id="no-parts"),
        pytest.param(("dim_run", True), "must be str or int", id="bool-part"),
        pytest.param(("dim_run", 1.5), "must be str or int", id="float-part"),
        pytest.param(("dim_run", None), "must be str or int", id="none-part"),
        pytest.param(("dim_run", ""), "non-empty and free of", id="empty-part"),
        pytest.param(("dim_run", "a|b"), "non-empty and free of", id="separator-part"),
    ],
)
def test_unit_key_rejects_bad_parts(parts: tuple[object, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        unit_key(*parts)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"tables": ["dim_run"]}, "tables must be a Mapping, got list", id="tables"),
        pytest.param({"units": "dim_run|s"}, "units must be a Mapping, got str", id="units"),
        pytest.param({"tables": {"": _HEX}}, "tables keys must be non-empty str", id="empty"),
        pytest.param({"units": {1: _HEX}}, "units keys must be non-empty str", id="int-key"),
        pytest.param({"digest": 1}, "digest must be a str", id="digest-int"),
    ],
)
def test_silver_content_from_mapping_rejects_bad_values(
    changes: dict[str, object], message: str
) -> None:
    mapping = {**_content().as_mapping(), **changes}

    with pytest.raises(ValueError, match=message):
        SilverContent.from_mapping(mapping)


@pytest.mark.unit
def test_silver_content_from_mapping_rejects_non_mapping_and_freezes_sorted() -> None:
    with pytest.raises(ValueError, match="silver_content must be a Mapping, got list"):
        SilverContent.from_mapping([("digest", _HEX)])  # type: ignore[arg-type]

    content = SilverContent(digest=_HEX, tables={"b": _HEX, "a": _HEX}, units={})
    assert list(content.tables) == ["a", "b"]
    with pytest.raises(TypeError):
        content.tables["c"] = _HEX  # type: ignore[index]
