"""Unit test de `CohortSpec.production_round` (Stage 8.4, Task 01 / CA5).

Prova: o modelo de produção (todos os campos de congelamento menos a impressão
digital do dado) vira um spec congelado com a impressão digital da rodada e os
demais campos iguais; o `cohort_id` muda com o dado; modelo já com impressão
digital, modelo incompleto e impressão digital malformada são recusados.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from tests.unit.features.modeling.application.test_cohort_spec import _spec

_HASHER = CanonicalJsonHasher()
_FP_A = "b" * 64
_FP_B = "c" * 64


def _model() -> CohortSpec:
    return replace(_spec(), name="aapl_production", dataset_fingerprint=None)


def _cohort_id(spec: CohortSpec) -> str:
    return spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))


def test_round_spec_is_the_model_frozen_with_the_round_fingerprint() -> None:
    model = _model()
    assert not model.is_frozen()

    round_spec = model.production_round(_FP_A)

    assert round_spec.is_frozen()
    assert round_spec.dataset_fingerprint == _FP_A
    for field in fields(CohortSpec):
        if field.name != "dataset_fingerprint":
            assert getattr(round_spec, field.name) == getattr(model, field.name), field.name


def test_cohort_id_changes_with_the_data() -> None:
    model = _model()

    first = _cohort_id(model.production_round(_FP_A))
    second = _cohort_id(model.production_round(_FP_B))

    assert first != second
    assert first.startswith("aapl_production-r0-")
    assert _cohort_id(model.production_round(_FP_A)) == first


def test_model_already_frozen_is_refused() -> None:
    with pytest.raises(ValueError, match="already declares a dataset_fingerprint"):
        _spec(dataset_fingerprint=_FP_A).production_round(_FP_B)


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"tft_params": None}, "tft_params"),
        ({"gbm_params": None}, "gbm_params"),
        ({"provenance": None}, "provenance"),
        ({"seeds": ()}, "seeds"),
    ],
)
def test_incomplete_model_is_refused_naming_the_field(
    change: dict[str, object], named: str
) -> None:
    model = replace(_model(), **change)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=named):
        model.production_round(_FP_A)


def test_model_without_n_trials_is_refused() -> None:
    model = _model()
    model = replace(model, sweep=replace(model.sweep, n_trials=None))

    with pytest.raises(ValueError, match=r"sweep\.n_trials"):
        model.production_round(_FP_A)


@pytest.mark.parametrize("bad", ["", "B" * 64, "b" * 63, "g" * 64, 64])
def test_malformed_fingerprint_is_refused(bad: object) -> None:
    with pytest.raises(ValueError, match="dataset_fingerprint"):
        _model().production_round(bad)  # type: ignore[arg-type]


def test_require_production_model_accepts_the_model_and_refuses_a_frozen_spec() -> None:
    _model().require_production_model()

    with pytest.raises(ValueError, match="already declares a dataset_fingerprint"):
        _spec(dataset_fingerprint=_FP_A).require_production_model()
