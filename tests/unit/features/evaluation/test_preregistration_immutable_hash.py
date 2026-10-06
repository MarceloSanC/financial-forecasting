"""Unit test da imutabilidade do pré-registro pelo hash (Stage 6.5, A1, I2, I3).

Com o dublê que recusa float (`FloatRefusingHasher`; o gate de pureza proíbe o
`CanonicalJsonHasher` aqui): toda folha do payload canônico muda o hash —
calculado direto sobre o payload trocado, **sem** `from_mapping`, porque várias
folhas só têm um valor válido (Checkpoint B r1, T-F2); 1e-12 x 1e-11 diferem;
`0` x `0.0` num campo float são o mesmo plano (a coerção é do VO do plano); a
referência é `<name>-r<rev>-<hash12>`. O comportamento contra o hasher real
(arredondamento) está em `tests/unit/shared/domain/value_objects/test_preregistration_hash.py`.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    leaf_paths,
    leaf_value,
    valid_payload,
    with_leaf,
)

_HASH12 = 12


def _digest(payload: dict[str, object]) -> PreregistrationHash:
    return PreregistrationHash.compute(hasher=FloatRefusingHasher(), payload=payload)


def _plan_digest(payload: dict[str, object]) -> PreregistrationHash:
    return _digest(Preregistration.from_mapping(payload).as_payload())


def _alternative(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value * 1.5 if value else 1.0
    if isinstance(value, str):
        return value + "_x"
    raise TypeError(f"unexpected leaf {value!r}")


_BASE_PAYLOAD = Preregistration.from_mapping(valid_payload()).as_payload()


@pytest.mark.unit
@pytest.mark.parametrize("path", leaf_paths(_BASE_PAYLOAD))
def test_every_leaf_changes_hash(path: str) -> None:
    changed = with_leaf(_BASE_PAYLOAD, path, _alternative(leaf_value(_BASE_PAYLOAD, path)))

    assert changed != _BASE_PAYLOAD
    assert _digest(changed) != _digest(_BASE_PAYLOAD)


@pytest.mark.unit
def test_leaf_paths_cover_payload() -> None:
    paths = leaf_paths(_BASE_PAYLOAD)

    assert paths == leaf_paths(valid_payload())
    assert "dm.alpha" in paths
    assert "horizons[1]" in paths
    assert "h1_gate.power_scenarios[0].lower_rate" in paths


@pytest.mark.unit
def test_tolerance_exponents_differ() -> None:
    tight = with_leaf(valid_payload(), "h1_gate.degeneracy_tolerance", 1e-12)
    loose = with_leaf(valid_payload(), "h1_gate.degeneracy_tolerance", 1e-11)

    assert _plan_digest(tight) != _plan_digest(loose)


@pytest.mark.unit
def test_zero_int_float_same_hash() -> None:
    as_int = with_leaf(valid_payload(), "h1_gate.degeneracy_tolerance", 0)
    as_float = with_leaf(valid_payload(), "h1_gate.degeneracy_tolerance", 0.0)

    assert _plan_digest(as_int) == _plan_digest(as_float)
    assert _plan_digest(as_int) != _plan_digest(valid_payload())


@pytest.mark.unit
def test_hasher_never_sees_float() -> None:
    with pytest.raises(AssertionError, match="received a float"):
        FloatRefusingHasher().hash_mapping({"x": [1.5]})

    digest = _plan_digest(valid_payload())

    assert len(digest.value) == 64  # noqa: PLR2004 — sha256 hex


@pytest.mark.unit
def test_reference_uses_hash12() -> None:
    plan = Preregistration.from_mapping(valid_payload())
    digest = _digest(plan.as_payload())

    assert plan.reference(digest) == "test_plan-r0-" + digest.value[:_HASH12]
    r1 = Preregistration.from_mapping(
        {
            **valid_payload(),
            "revision": 1,
            "amends": plan.reference(digest),
            "justification": "blinded fix",
            "blind_status": "blinded",
        }
    )
    r1_digest = _digest(r1.as_payload())
    assert r1.reference(r1_digest) == f"test_plan-r1-{r1_digest.value[:_HASH12]}"


_BLOCK_PAYLOAD = Preregistration.from_mapping(
    {
        **valid_payload(),
        "revision": 1,
        "amends": "test_plan-r0-0123456789ab",
        "justification": "blinded profile rules",
        "blind_status": "blinded",
        "profile_parameters": {
            "subset_multiplicity": "none_raw_p_descriptive_v1",
            "partial_degeneracy_pairs": "symmetric_and_adjacent_non_degenerate_rows_v1",
            "mcs_block_sensitivity_scheme": "primary_scheme",
            "stationarity": {
                "acf_max_lag": "min_floor_10_log10_T_T_minus_1",
                "break_test": "cusum_mean_dm_primary_variance_kolmogorov_v1",
                "break_alpha": 0.05,
            },
        },
    }
).as_payload()


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", [p for p in leaf_paths(_BLOCK_PAYLOAD) if p.startswith("profile_parameters")]
)
def test_every_profile_parameter_leaf_changes_hash(path: str) -> None:
    """Stage 6.6 Task 08: toda folha do bloco `profile_parameters` entra no hash."""
    changed = with_leaf(_BLOCK_PAYLOAD, path, _alternative(leaf_value(_BLOCK_PAYLOAD, path)))
    assert _digest(changed) != _digest(_BLOCK_PAYLOAD)


@pytest.mark.unit
def test_the_block_changes_the_hash_and_its_absence_keeps_r0() -> None:
    without_block = {k: v for k, v in _BLOCK_PAYLOAD.items() if k != "profile_parameters"}
    assert _digest(_BLOCK_PAYLOAD) != _digest(without_block)
    assert "profile_parameters" not in _BASE_PAYLOAD
