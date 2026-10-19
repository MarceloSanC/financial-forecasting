"""Unit do `PredictTftAttributionFromCheckpoints` (Stage 7.3, Task 12; CA9, I8, C1, C5).

Mesmo oráculo da 7.1 (`_frozen_tft_cohort` com o `InMemoryTftCheckpointPredictor`, um
checkpoint registrado por run), via o `_Setup` de `test_predict_tft_from_checkpoints.py`.
A partição de referência é SINTÉTICA e diferente da real (outras features, outros
tamanhos), para que a guarda "partição ≠ registry" não passe por coincidência com a
registry de produção.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    FamilyFeatureKnownError,
    TftAttributionPrediction,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    FamilyPartitionMismatchError,
    PredictTftAttributionCommand,
    PredictTftAttributionFromCheckpoints,
    PredictTftAttributionResult,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    UnknownRunError,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    registry_family_partition,
    unknown_feature_names,
)
from tests.fakes.features.modeling.in_memory_tft_checkpoint_predictor import (
    InMemoryTftCheckpointPredictor,
)
from tests.unit.features.modeling.application import _frozen_tft_cohort as cohort
from tests.unit.features.modeling.application.test_predict_tft_from_checkpoints import (
    _SEED,
    _indices,
    _Setup,
)

pytestmark = pytest.mark.unit

_UNKNOWN = unknown_feature_names()
# Sintética: features reais, mas famílias de outros tamanhos (2, 1, 3, 1).
_REGISTRY: dict[str, tuple[str, ...]] = {
    "price": _UNKNOWN[0:2],
    "technical": _UNKNOWN[2:3],
    "sentiment": _UNKNOWN[3:6],
    "fundamental": _UNKNOWN[6:7],
}
_K_P = 2


def _emitting_test_decisions(setup: _Setup, fold: Any) -> tuple[int, ...]:  # noqa: ANN401
    last = len(cohort.sessions()) - 1
    return tuple(d for d in sorted(_indices(fold.test)) if d + min(cohort.HORIZONS) <= last)


def _donors(setup: _Setup) -> dict[int, tuple[tuple[int, ...], ...]]:
    donors = {}
    for fold in setup.folds():
        n = len(_emitting_test_decisions(setup, fold))
        donors[fold.fold_index] = (tuple(reversed(range(n))), (*range(1, n), 0))
    return donors


def _use_case(setup: _Setup, **overrides: object) -> PredictTftAttributionFromCheckpoints:
    arguments: dict[str, object] = {
        "store": cohort.store(),
        "hasher": cohort.HASHER,
        "splitter": cohort.splitter(),
        "locator": setup.locator,
        "predictor": setup.predictor,
        "artifacts_root": setup.artifacts_root,
        "modeling_columns": modeling_columns(),
        "observed_feature_set_hash": cohort.FEATURE_SET_HASH,
        "pipeline_version": PIPELINE_VERSION,
        "supported_device": "cpu",
        "registry_partition": _REGISTRY,
    }
    arguments.update(overrides)
    return PredictTftAttributionFromCheckpoints(**arguments)  # type: ignore[arg-type]


def _predict(setup: _Setup, **command: object) -> PredictTftAttributionResult:
    fields: dict[str, object] = {
        "spec": setup.spec,
        "seed": _SEED,
        "allowed": setup.allowed,
        "num_threads": 3,
        "donors_by_fold": _donors(setup),
        "family_partition": _REGISTRY,
    }
    fields.update(command)
    return _use_case(setup)(PredictTftAttributionCommand(**fields))  # type: ignore[arg-type]


def _attribution_calls(setup: _Setup) -> list[dict[str, Any]]:
    return [c for c in setup.predictor.calls if c.get("method") == "attribution"]


def test_run_ids_equal_what_train_tft_records(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    result = _predict(setup)
    assert [run.run_id for run in result.runs] == [run.run_id for run in setup.runs]
    assert [run.fold_index for run in result.runs] == [run.fold_index for run in setup.runs]
    assert result.cohort_id == cohort.cohort_id(setup.spec)


@pytest.mark.parametrize(
    "mutation",
    ["not-a-permutation", "missing-fold", "different-k-p", "wrong-length"],
)
def test_donors_must_be_k_p_permutations_of_the_fold_test_positions(
    tmp_path: Path, mutation: str
) -> None:
    setup = _Setup(tmp_path)
    donors = _donors(setup)
    first = min(donors)
    n = len(donors[first][0])
    if mutation == "not-a-permutation":
        donors[first] = ((0,) * n, donors[first][1])
    elif mutation == "missing-fold":
        del donors[first]
    elif mutation == "different-k-p":
        donors[first] = donors[first][:1]
    else:
        donors[first] = (tuple(range(n + 1)), tuple(range(n + 1)))
    with pytest.raises(ValueError, match=r"C1|permutation"):
        _predict(setup, donors_by_fold=donors)
    assert _attribution_calls(setup) == []


def test_partition_different_from_registry_refused_before_predicting(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    moved = {**_REGISTRY, "price": _REGISTRY["price"][:1], "technical": (_UNKNOWN[1], _UNKNOWN[2])}
    for partition in (moved, registry_family_partition()):
        with pytest.raises(FamilyPartitionMismatchError, match="registry"):
            _predict(setup, family_partition=partition)
    assert _attribution_calls(setup) == []


def test_family_column_known_in_the_panel_raises_before_predicting(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    known = known_feature_names()[0]
    registry = {**_REGISTRY, "technical": (known,)}
    use_case = _use_case(setup, registry_partition=registry)
    command = PredictTftAttributionCommand(
        spec=setup.spec,
        seed=_SEED,
        allowed=setup.allowed,
        num_threads=3,
        donors_by_fold=_donors(setup),
        family_partition=registry,
    )
    with pytest.raises(FamilyFeatureKnownError, match=known):
        use_case(command)
    assert _attribution_calls(setup) == []


class _KnownFamilyPredictor(InMemoryTftCheckpointPredictor):
    def predict_attribution_from_checkpoint(self, **kwargs: Any) -> TftAttributionPrediction:  # noqa: ANN401
        raise FamilyFeatureKnownError("checkpoint says the family is known (C5)")


def test_adapter_family_known_error_propagates(tmp_path: Path) -> None:
    setup = _Setup(tmp_path, predictor=_KnownFamilyPredictor())
    with pytest.raises(FamilyFeatureKnownError, match="checkpoint says"):
        _predict(setup)


def test_run_outside_allowlist_raises(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    allowed = dict(setup.allowed)
    allowed.pop(setup.runs[0].run_id)
    with pytest.raises(UnknownRunError):
        _predict(setup, allowed=allowed)
    assert _attribution_calls(setup) == []


def test_donor_positions_map_to_sorted_test_decisions(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    result = _predict(setup)
    calls = _attribution_calls(setup)
    for fold, run, call in zip(setup.folds(), result.runs, calls, strict=True):
        expected = _emitting_test_decisions(setup, fold)
        assert run.test_decisions == expected
        assert call["decision_indices"] == expected
        assert call["donors"] == _donors(setup)[fold.fold_index]
        # o fake devolve, na permutada, a grade da decisão doadora
        donors = _donors(setup)[fold.fold_index][0]
        compared = 0
        for position, decision in enumerate(expected):
            donor = expected[donors[position]]
            for horizon, grid in run.permuted[("price", 1)].get(decision, {}).items():
                if horizon in run.identity.get(donor, {}):
                    assert grid == run.identity[donor][horizon]
                    compared += 1
        assert compared > 0


def test_result_carries_family_columns_and_normalizer(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    result = _predict(setup)
    for run in result.runs:
        assert run.family_columns == _REGISTRY
        assert run.normalizer_center == pytest.approx(0.25 + run.fold_index)
        assert run.normalizer_scale == pytest.approx(0.5 + run.fold_index)
        assert set(run.permuted) == {(f, k) for f in _REGISTRY for k in range(1, _K_P + 1)}
        assert set(run.encoder_weights) == set(run.test_decisions)
        assert run.checkpoint_sha256 == setup.allowed[run.run_id]
    assert result.settings["num_threads"] == "3"
    assert result.seed == _SEED


class _LeakingAttributionPredictor(InMemoryTftCheckpointPredictor):
    def predict_attribution_from_checkpoint(self, **kwargs: Any) -> TftAttributionPrediction:  # noqa: ANN401
        result = super().predict_attribution_from_checkpoint(**kwargs)
        extra = max(kwargs["decision_indices"]) + 1
        permuted = dict(result.permuted)
        key = next(iter(permuted))
        permuted[key] = {**permuted[key], extra: {1: (0.0, 0.0, 0.0)}}
        return TftAttributionPrediction(
            identity=result.identity,
            permuted=permuted,
            encoder_weights=result.encoder_weights,
            normalizer_center=result.normalizer_center,
            normalizer_scale=result.normalizer_scale,
            settings=result.settings,
        )


def test_emission_outside_request_raises(tmp_path: Path) -> None:
    setup = _Setup(tmp_path, predictor=_LeakingAttributionPredictor())
    with pytest.raises(ValueError, match="outside the requested test range"):
        _predict(setup)
