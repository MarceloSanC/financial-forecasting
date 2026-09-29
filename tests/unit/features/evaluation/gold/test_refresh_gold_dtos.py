"""Testes dos DTOs do refresh do gold (Stage 6.4 Task 07; A7, C2, C3, I17)."""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldInputs,
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshGoldCommand,
    RefreshParameters,
    RefreshStatus,
    failed_checks_of,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)

_PREREG = "prereg-test-0001"  # literal declarado até a 6.5 fornecer o hash congelado
_VALID: dict[str, object] = {
    "preregistration_ref": _PREREG,
    "degeneracy_tolerance": 1e-9,
    "band_levels": (0.95, 0.975),
    "min_violations": 5,
    "candidate": "tft",
    "dm_alpha": 0.05,
    "dm_variance_estimators": (DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT),
    "mcs_alpha": 0.10,
    "mcs_reps": 1000,
    "mcs_seed": 20260929,
    "mcs_schemes": (BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK),
}
_PARAMETERS = RefreshParameters(**_VALID)  # type: ignore[arg-type]
_NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _parameters(**changes: object) -> RefreshParameters:
    return RefreshParameters(**{**_VALID, **changes})  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("missing", sorted(_VALID))
def test_parameters_no_default(missing: str) -> None:
    """Todo campo é obrigatório e keyword: faltar um → `TypeError`."""
    kwargs = {k: v for k, v in _VALID.items() if k != missing}
    with pytest.raises(TypeError, match=missing):
        RefreshParameters(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RefreshParameters(*_VALID.values())  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"degeneracy_tolerance": -1.0}, "degeneracy_tolerance must be", id="tol"),
        pytest.param({"degeneracy_tolerance": math.nan}, "degeneracy_tolerance must", id="nan"),
        pytest.param({"band_levels": (0.95, 1.0)}, "band_level must be in (0, 1)", id="band"),
        pytest.param({"band_levels": (True,)}, "band_level must be a finite", id="band-bool"),
        pytest.param({"min_violations": -1}, "min_violations must be an int >= 0", id="minv"),
        pytest.param({"min_violations": True}, "min_violations must be", id="minv-bool"),
        pytest.param({"dm_alpha": 0.0}, "alpha must be a finite number in", id="dm-alpha"),
        pytest.param({"mcs_alpha": 1.5}, "alpha must be a finite number in", id="mcs-alpha"),
        pytest.param({"mcs_reps": 999}, "reps must be >= 1000", id="reps-floor"),
        pytest.param({"mcs_reps": True}, "reps must be an int >= 1", id="reps-bool"),
        pytest.param({"mcs_reps": 1000.0}, "reps must be an int >= 1", id="reps-float"),
        pytest.param({"mcs_seed": -1}, "seed must be an int >= 0", id="seed"),
        pytest.param({"mcs_seed": True}, "seed must be an int >= 0", id="seed-bool"),
        pytest.param({"candidate": ""}, "candidate must be a non-empty str", id="candidate"),
        pytest.param(
            {"dm_variance_estimators": ("rectangular",)}, "DmVarianceEstimator", id="estimator"
        ),
        pytest.param({"mcs_schemes": ("stationary",)}, "BootstrapScheme", id="scheme"),
    ],
)
def test_parameters_owner_messages(changes: dict[str, object], message: str) -> None:
    """Cada campo inválido ergue pela mensagem do validador DONO (C2; ADR 6.4.0006)."""
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        _parameters(**changes)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["band_levels", "dm_variance_estimators", "mcs_schemes"])
def test_tuple_empty_or_repeated(name: str) -> None:
    value = _VALID[name]
    assert isinstance(value, tuple)
    with pytest.raises(ValueError, match=f"{name} must be a non-empty tuple"):
        _parameters(**{name: ()})
    with pytest.raises(ValueError, match=f"{name} must be a non-empty tuple"):
        _parameters(**{name: list(value)})
    with pytest.raises(ValueError, match=f"{name} must not repeat"):
        _parameters(**{name: (value[0], value[0])})


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", None, 7])
def test_preregistration_ref_required(value: object) -> None:
    with pytest.raises(ValueError, match="preregistration_ref must be a non-empty str"):
        _parameters(preregistration_ref=value)


def _command(**changes: object) -> RefreshGoldCommand:
    kwargs: dict[str, object] = {
        "asset": "AAPL",
        "parent_sweep_id": "sweep-01",
        "horizons": (1, 7),
        "window_deficits": {"tft": 3},
        "parameters": _PARAMETERS,
    }
    kwargs.update(changes)
    return RefreshGoldCommand(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        pytest.param({"asset": "AA/PL"}, "asset", id="asset-slash"),
        pytest.param({"asset": "AA PL"}, "asset", id="asset-space"),
        pytest.param({"asset": "AAPL\n"}, "asset", id="asset-newline"),
        pytest.param({"parent_sweep_id": "../x"}, "parent_sweep_id", id="sweep-dots-slash"),
        pytest.param({"parent_sweep_id": ""}, "parent_sweep_id", id="sweep-empty"),
    ],
)
def test_identifier_rule(changes: dict[str, object], field: str) -> None:
    """C3: o comando constrói a partição e ergue pela regra única de identificador."""
    with pytest.raises(ValueError, match=f"^{field} must match"):
        _command(**changes)
    command = _command()
    assert command.partition == GoldPartition("AAPL", "sweep-01")


@pytest.mark.unit
def test_command_horizons() -> None:
    with pytest.raises(ValueError, match="horizons must be a non-empty tuple"):
        _command(horizons=())
    with pytest.raises(ValueError, match="horizons must not repeat"):
        _command(horizons=(1, 1))
    with pytest.raises(ValueError, match="window_deficits must be a Mapping"):
        _command(window_deficits=[("tft", 3)])
    with pytest.raises(ValueError, match="parameters must be RefreshParameters"):
        _command(parameters=_VALID)
    deficits = {"tft": 3}
    command = _command(window_deficits=deficits)
    deficits["tft"] = 99
    assert command.window_deficits == {"tft": 3}


def _row(model: str | None, seed: int | None, value: float = 0.5) -> dict[str, object]:
    return {"model": model, "seed": seed, "value": value, "asset": "AAPL"}


@pytest.mark.unit
def test_table_key_order() -> None:
    """Estritamente ordenadas pela chave, `None` antes de qualquer valor; sem repetir."""
    rows = (_row(None, None), _row("a", None), _row("a", 1), _row("a", 2), _row("b", 0))
    table = GoldTable("gold_x", ("model", "seed"), rows)
    assert [(r["model"], r["seed"]) for r in table.rows] == [
        (None, None),
        ("a", None),
        ("a", 1),
        ("a", 2),
        ("b", 0),
    ]
    with pytest.raises(ValueError, match="strictly increasing by key"):
        GoldTable("gold_x", ("model", "seed"), (rows[1], rows[0]))
    with pytest.raises(ValueError, match="strictly increasing by key"):
        GoldTable("gold_x", ("model", "seed"), (rows[2], rows[2]))
    with pytest.raises(ValueError, match="mix types"):
        GoldTable("gold_x", ("seed",), (_row("a", 1), {**_row("a", 1), "seed": "x"}))
    with pytest.raises(ValueError, match="key columns"):
        GoldTable("gold_x", ("horizon",), rows[:1])
    with pytest.raises(ValueError, match="key must be a non-empty tuple"):
        GoldTable("gold_x", (), rows[:1])


@pytest.mark.unit
def test_table_columns_uniform() -> None:
    with pytest.raises(ValueError, match="columns"):
        GoldTable("gold_x", ("model",), (_row("a", 1), {"model": "b", "seed": 1}))
    with pytest.raises(ValueError, match="unsupported values"):
        GoldTable("gold_x", ("model",), (_row("a", 1, math.nan),))
    with pytest.raises(ValueError, match="unsupported values"):
        GoldTable("gold_x", ("model",), ({**_row("a", 1), "value": (1, 2)},))
    with pytest.raises(ValueError, match="must be a Mapping"):
        GoldTable("gold_x", ("model",), (("a", 1),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="rows must be a tuple"):
        GoldTable("gold_x", ("model",), [_row("a", 1)])  # type: ignore[arg-type]
    source = _row("a", 1)
    table = GoldTable("gold_x", ("model",), (source,))
    source["value"] = 9.0
    assert table.rows[0]["value"] == _row("a", 1)["value"]
    assert table.columns == ("asset", "model", "seed", "value")
    assert GoldTable("gold_empty", ("model",), ()).columns == ()


def _manifest(**changes: object) -> GoldManifest:
    kwargs: dict[str, object] = {
        "status": RefreshStatus.COMPLETED,
        "partition": GoldPartition("AAPL", "sweep-01"),
        "rows_by_table": {"gold_quality_checks": 4, "gold_dm_results": 2},
        "parameters": _PARAMETERS,
        "horizons": (1, 7),
        "window_deficits": {"tft": 3},
        "dataset_fingerprint": DatasetFingerprint(value="ab" * 32),
        "realized_sessions": 250,
        "realized_returns_fsum": 0.125,
        "realized_first_timestamp": "2024-01-02T00:00:00+00:00",
        "realized_last_timestamp": "2024-12-31T00:00:00+00:00",
        "n_runs": 6,
        "build_order": ("quality_checks", "dm_results"),
        "started_at": _NOW,
        "finished_at": _NOW,
    }
    kwargs.update(changes)
    return GoldManifest(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_manifest_mapping() -> None:
    mapping = _manifest().as_mapping()
    decoded = json.loads(json.dumps(mapping, sort_keys=True))
    assert decoded == mapping
    assert mapping["preregistration_ref"] == _PREREG
    assert mapping["parameters"]["preregistration_ref"] == _PREREG  # type: ignore[index]
    assert mapping["status"] == "COMPLETED"
    assert mapping["parameters"]["mcs_schemes"] == ["stationary", "moving_block"]  # type: ignore[index]
    assert mapping["started_at"] == _NOW.isoformat()
    assert (mapping["asset"], mapping["parent_sweep_id"]) == ("AAPL", "sweep-01")
    for changes, message in (
        ({"status": "COMPLETED"}, "status must be a RefreshStatus"),
        ({"rows_by_table": {"t": -1}}, "must be an int >= 0"),
        ({"n_runs": True}, "n_runs must be an int >= 0"),
        ({"started_at": datetime(2026, 9, 29)}, "timezone-aware"),
        ({"window_deficits": [("tft", 3)]}, "window_deficits must be a Mapping"),
        ({"started_at": datetime(2026, 9, 29, 13, 0, tzinfo=UTC)}, "is after finished_at"),
        ({"dataset_fingerprint": "ab" * 32}, "must be a DatasetFingerprint"),
        ({"realized_returns_fsum": math.inf}, "realized_returns_fsum must be a finite"),
        ({"realized_returns_fsum": None}, "realized_returns_fsum must be a finite"),
        ({"horizons": [1, 7]}, "horizons must be a tuple"),
        ({"build_order": ["quality_checks"]}, "build_order must be a tuple"),
    ):
        with pytest.raises(ValueError, match=message):
            _manifest(**changes)


def _result(severity: CheckSeverity, outcome: CheckOutcome, check: str) -> QualityCheckResult:
    return QualityCheckResult(
        check=check,
        severity=severity,
        outcome=outcome,
        kind="k",
        horizon=1,
        model="tft",
        seed=None,
        occurrences=2,
        value=None,
        detail="first",
    )


@pytest.mark.unit
def test_failed_checks_of_results() -> None:
    results = (
        _result(CheckSeverity.ERROR, CheckOutcome.PASS, "a"),
        _result(CheckSeverity.ERROR, CheckOutcome.FAIL, "b"),
        _result(CheckSeverity.WARN, CheckOutcome.REPORTED, "c"),
        _result(CheckSeverity.ERROR, CheckOutcome.SKIPPED, "d"),
        _result(CheckSeverity.ERROR, CheckOutcome.FAIL, "e"),
    )
    assert failed_checks_of(results) == (
        FailedCheck("b", "k", 1, "tft", None, 2, "first"),
        FailedCheck("e", "k", 1, "tft", None, 2, "first"),
    )
    assert failed_checks_of(results[:1]) == ()


@pytest.mark.unit
def test_parameters_as_mapping() -> None:
    assert _PARAMETERS.as_mapping()["mcs_reps"] == _VALID["mcs_reps"]
    assert dataclasses.replace(_PARAMETERS) == _PARAMETERS


@pytest.mark.unit
def test_gold_inputs_status_coherence() -> None:
    partition = GoldPartition("AAPL", "sweep-01")
    failing = (_result(CheckSeverity.ERROR, CheckOutcome.FAIL, "alignment_check"),)
    blocked = GoldInputs(
        partition=partition,
        parameters=_PARAMETERS,
        status=RefreshStatus.BLOCKED,
        check_results=failing,
        horizon_reports=(),
        mcs_reports=(),
        block_estimates={},
    )
    assert blocked.preregistration_ref == _PREREG
    with pytest.raises(ValueError, match="BLOCKED generation has no"):
        dataclasses.replace(blocked, mcs_reports=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="COMPLETED generation cannot"):
        dataclasses.replace(blocked, status=RefreshStatus.COMPLETED)
    with pytest.raises(ValueError, match="BLOCKED generation needs a blocking"):
        dataclasses.replace(
            blocked,
            check_results=(_result(CheckSeverity.WARN, CheckOutcome.REPORTED, "degeneracy"),),
        )
    completed = dataclasses.replace(blocked, status=RefreshStatus.COMPLETED, check_results=())
    assert completed.status is RefreshStatus.COMPLETED
    with pytest.raises(ValueError, match="status must be a RefreshStatus"):
        dataclasses.replace(blocked, status="BLOCKED")
    with pytest.raises(ValueError, match="block_estimates must be a Mapping"):
        dataclasses.replace(blocked, block_estimates=[])


@pytest.mark.unit
def test_table_key_order_sorted_by_key() -> None:
    """`sorted_by_key` ordena pela mesma regra (None primeiro) e deixa a validação falar."""
    rows = [_row("b", 0), _row("a", 2), _row(None, None), _row("a", None)]
    table = GoldTable.sorted_by_key("gold_x", ("model", "seed"), rows)
    assert [(r["model"], r["seed"]) for r in table.rows] == [
        (None, None),
        ("a", None),
        ("a", 2),
        ("b", 0),
    ]
    with pytest.raises(ValueError, match="key columns"):
        GoldTable.sorted_by_key("gold_x", ("horizon",), rows)
    with pytest.raises(ValueError, match="mix types"):
        GoldTable.sorted_by_key("gold_x", ("seed",), [_row("a", 1), {**_row("a", 1), "seed": "x"}])
