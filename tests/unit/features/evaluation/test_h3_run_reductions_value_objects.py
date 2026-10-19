"""Unit dos registros e reduções por run da atribuição (Stage 7.3, Task 23; I19).

Cinco VOs frozen stdlib: `PermutedForecastRecord`, `VsnWeightRecord`, `PermutedRunLosses`,
`AblationRunLosses` (com `merge_ablation_parts`) e `VsnRunWeights` (com
`reduce_vsn_run`). Todos sintéticos.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.ablation_run_losses import (
    AblationMergeError,
    AblationRunLosses,
    AblationRunPart,
    OverlappingAblationPartsError,
    merge_ablation_parts,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_forecast_record import (  # noqa: E501
    PermutedForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    PermutedRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_run_weights import (
    VsnRunWeights,
    reduce_vsn_run,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_weight_record import (
    VsnWeightRecord,
)

pytestmark = pytest.mark.unit

_HASH = "c3" * 32
_T = ("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00", "2024-01-04T00:00:00+00:00")


def _permuted_record(**changes: Any) -> PermutedForecastRecord:  # noqa: ANN401
    fields: dict[str, Any] = {
        "run_id": "run-a",
        "model": "tft_quantile",
        "seed": 1,
        "fold_index": 0,
        "permuted_family": "price",
        "permutation_index": 3,
        "permutation_seed": 130,
        "permutation_algorithm": "fisher_yates_random_random_v1",
        "partition_hash": _HASH,
        "horizon": 1,
        "decision_idx": 10,
        "decision_timestamp": _T[0],
        "target_timestamp": _T[1],
        "quantile_level": 0.5,
        "value_raw": 0.01,
        "value_guardrail": 0.01,
        "guardrail_applied": False,
    }
    fields.update(changes)
    return PermutedForecastRecord(**fields)


def _vsn_record(**changes: Any) -> VsnWeightRecord:  # noqa: ANN401
    fields: dict[str, Any] = {
        "run_id": "run-a",
        "model": "tft_quantile",
        "seed": 1,
        "fold_index": 0,
        "decision_idx": 10,
        "decision_timestamp": _T[0],
        "variable": "rsi_14",
        "family": "technical",
        "weight": 0.25,
    }
    fields.update(changes)
    return VsnWeightRecord(**fields)


def _permuted_losses(**changes: Any) -> PermutedRunLosses:  # noqa: ANN401
    fields: dict[str, Any] = {
        "run_id": "run-a",
        "seed": 1,
        "fold_index": 0,
        "permutation_seed": 130,
        "permutation_algorithm": "fisher_yates_random_random_v1",
        "partition_hash": _HASH,
        "decision_timestamps": _T,
        "identity": {1: (0.1, 0.2, 0.3), 7: (0.4, 0.5, 0.6)},
        "permuted": {("price", 1, 1): (0.2, 0.2, 0.2), ("price", 1, 7): (0.5, 0.5, 0.5)},
    }
    fields.update(changes)
    return PermutedRunLosses(**fields)


def _ablation(decisions: tuple[str, ...], losses: tuple[float, ...], **changes: Any) -> Any:  # noqa: ANN401
    fields: dict[str, Any] = {
        "run_id": "run-b",
        "model_version": "tft_quantile_loco_minus_price",
        "seed": 1,
        "fold_index": 0,
        "decision_timestamps": decisions,
        "losses": {1: losses, 7: tuple(2 * loss for loss in losses)},
    }
    fields.update(changes)
    return AblationRunLosses(**fields)


# --- registros ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "index", "valid"),
    [
        ("none", 0, True),
        ("price", 1, True),
        ("none", 1, False),
        ("price", 0, False),
    ],
)
def test_permuted_record_none_iff_index_zero(family: str, index: int, valid: bool) -> None:
    if valid:
        assert _permuted_record(permuted_family=family, permutation_index=index)
        return
    with pytest.raises(ValueError, match="permuted_family 'none' iff permutation_index 0"):
        _permuted_record(permuted_family=family, permutation_index=index)


@pytest.mark.parametrize("family", ["volatility", "Price", "", None])
def test_permuted_record_family_vocabulary(family: object) -> None:
    with pytest.raises(ValueError, match="permuted_family must be one of"):
        _permuted_record(permuted_family=family)
    with pytest.raises(ValueError, match="family must be one of"):
        _vsn_record(family=family)


def test_vsn_record_accepts_the_none_family() -> None:
    assert _vsn_record(variable="relative_time_idx", family="none").family == "none"


# --- reduções -----------------------------------------------------------------------


def test_run_losses_lengths_match_decisions() -> None:
    with pytest.raises(ValueError, match=r"identity\[7\] has 2 losses for 3 decisions"):
        _permuted_losses(identity={1: (0.1, 0.2, 0.3), 7: (0.4, 0.5)})
    with pytest.raises(ValueError, match=r"permuted\['price', 1, 1\] has 4 losses for 3"):
        _permuted_losses(permuted={("price", 1, 1): (0.1, 0.2, 0.3, 0.4)})
    with pytest.raises(ValueError, match=r"losses\[1\] has 2 losses for 3 decisions"):
        _ablation(_T, (0.1, 0.2))


@pytest.mark.parametrize(
    "decisions", [(_T[1], _T[0], _T[2]), (_T[0], _T[0], _T[1]), ()], ids=["order", "dup", "empty"]
)
def test_run_losses_decisions_strictly_increasing(decisions: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="decision_timestamps"):
        _permuted_losses(
            decision_timestamps=decisions,
            identity={1: (0.1,) * len(decisions)},
            permuted={("price", 1, 1): (0.1,) * len(decisions)},
        )
    with pytest.raises(ValueError, match="decision_timestamps"):
        _ablation(decisions, (0.1,) * len(decisions))


def test_permuted_losses_keys_are_checked() -> None:
    with pytest.raises(ValueError, match="permuted family must be one of"):
        _permuted_losses(permuted={("none", 1, 1): (0.1, 0.2, 0.3)})
    with pytest.raises(ValueError, match="k must be an int >= 1"):
        _permuted_losses(permuted={("price", 0, 1): (0.1, 0.2, 0.3)})
    with pytest.raises(ValueError, match="is not an identity horizon"):
        _permuted_losses(permuted={("price", 1, 30): (0.1, 0.2, 0.3)})


def test_reduce_vsn_run_groups_by_decision() -> None:
    records = [
        _vsn_record(decision_timestamp=t, decision_idx=i, variable=v, weight=w)
        for i, t in enumerate(_T[:2])
        for v, w in (("rsi_14", 0.25), ("log_return", 0.75))
    ]

    reduced = reduce_vsn_run(records)

    assert reduced.run_id == "run-a"
    assert (reduced.seed, reduced.fold_index) == (1, 0)
    assert list(reduced.weights) == list(_T[:2])
    assert dict(reduced.weights[_T[0]]) == {"log_return": 0.75, "rsi_14": 0.25}


def test_reduce_vsn_run_refuses_duplicate_variable() -> None:
    with pytest.raises(ValueError, match="variable 'rsi_14' twice at decision"):
        reduce_vsn_run([_vsn_record(), _vsn_record(weight=0.5)])
    with pytest.raises(ValueError, match="reduce_vsn_run takes one run"):
        reduce_vsn_run([_vsn_record(), _vsn_record(run_id="run-z", variable="macd")])
    with pytest.raises(ValueError, match="other decisions have"):
        reduce_vsn_run([_vsn_record(), _vsn_record(decision_timestamp=_T[1], variable="macd")])


def _part(losses: dict[int, dict[str, float]], **changes: Any) -> AblationRunPart:  # noqa: ANN401
    fields: dict[str, Any] = {
        "run_id": "run-b",
        "model_version": "tft_quantile_loco_minus_price",
        "seed": 1,
        "fold_index": 0,
        "losses": losses,
    }
    fields.update(changes)
    return AblationRunPart(**fields)


def test_ablation_losses_merge_disjoint_parts() -> None:
    december = _part({1: {_T[0]: 0.1}, 7: {_T[0]: 0.2}})
    january = _part({1: {_T[1]: 0.2, _T[2]: 0.3}, 7: {_T[1]: 0.4, _T[2]: 0.6}})

    merged = merge_ablation_parts([january, december])

    assert merged.decision_timestamps == _T
    assert merged.losses[1] == (0.1, 0.2, 0.3)
    assert merged.losses[7] == (0.2, 0.4, 0.6)


def test_a_part_with_only_h1_merges_by_horizon_then_intersects() -> None:
    """C6-1: a cauda de janeiro só com h+1 entra no h+1 e sai na interseção."""
    december = _part({1: {_T[0]: 0.1, _T[1]: 0.2}, 7: {_T[0]: 0.2, _T[1]: 0.4}})
    january = _part({1: {_T[2]: 0.3}})

    merged = merge_ablation_parts([december, january])

    assert merged.decision_timestamps == _T[:2]
    assert merged.losses == {1: (0.1, 0.2), 7: (0.2, 0.4)}
    with pytest.raises(AblationMergeError, match="no decision has every horizon"):
        merge_ablation_parts([_part({1: {_T[0]: 0.1}, 7: {_T[1]: 0.2}})])


def test_overlapping_parts_refused() -> None:
    with pytest.raises(OverlappingAblationPartsError, match="is in two parts"):
        merge_ablation_parts([_part({1: {_T[0]: 0.1}}), _part({1: {_T[0]: 0.2}})])
    with pytest.raises(AblationMergeError, match="different runs"):
        merge_ablation_parts([_part({1: {_T[0]: 0.1}}), _part({1: {_T[1]: 0.2}}, seed=2)])
    with pytest.raises(ValueError, match="at least one part"):
        merge_ablation_parts([])


@pytest.mark.parametrize(
    ("build", "field", "value"),
    [
        (_permuted_record, "partition_hash", "XYZ"),
        (_permuted_record, "quantile_level", 1),
        (_permuted_record, "guardrail_applied", 0),
        (_vsn_record, "weight", 1.5),
        (_vsn_record, "seed", -1),
        (_permuted_losses, "identity", {}),
        (_permuted_losses, "partition_hash", "c3"),
        (_permuted_losses, "permuted", {("price", 1, 1): (0.1, float("nan"), 0.3)}),
        (lambda **c: _ablation(_T, (0.1, 0.2, 0.3), **c), "model_version", ""),
        (lambda **c: _ablation(_T, (0.1, 0.2, 0.3), **c), "losses", {0: (0.1, 0.2, 0.3)}),
        (lambda **c: _part({1: {_T[0]: 0.1}}, **c), "losses", {1: {}}),
        (lambda **c: _part({1: {_T[0]: 0.1}}, **c), "losses", {1: {_T[0]: float("nan")}}),
    ],
)
def test_raw_construction_refused(build: Any, field: str, value: object) -> None:  # noqa: ANN401
    """O construtor direto com a invariante violada ergue `ValueError` (os cinco VOs)."""
    valid = build()
    with pytest.raises(ValueError, match=field.split("_", maxsplit=1)[0]):
        dataclasses.replace(valid, **{field: value})


def test_raw_construction_of_vsn_run_weights_refused() -> None:
    valid = VsnRunWeights(
        run_id="run-a", seed=1, fold_index=0, weights={_T[0]: {"rsi_14": 0.5, "macd": 0.5}}
    )
    for weights in ({}, {_T[0]: {}}, {_T[0]: {"rsi_14": 2.0}}, {_T[0]: {"rsi_14": 1}}):
        with pytest.raises(ValueError, match="weights"):
            dataclasses.replace(valid, weights=weights)
