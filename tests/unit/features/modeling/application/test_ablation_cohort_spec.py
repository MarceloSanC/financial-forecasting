"""`AblationCohortSpec` (Stage 7.3, Task 05; CA3 parte VO, I3, I5, C1; ADR 7.3.0003 item 1)."""

from __future__ import annotations

import re
from dataclasses import replace
from hashlib import sha256
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    ABLATION_FEATURE_SET_NAME,
    AblationCohortSpec,
    AblationConfiguration,
    AblationDeclarationError,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

pytestmark = pytest.mark.unit


def _hex(label: str) -> str:
    return sha256(label.encode()).hexdigest()


_PARTITION = {
    "price": ("open", "close"),
    "technical": ("rsi_14",),
    "sentiment": ("sent_mean", "sent_std"),
    "fundamental": ("pe_ratio",),
}


def _configurations() -> tuple[AblationConfiguration, ...]:
    return tuple(
        AblationConfiguration.of(name, feature_set_hash=_hex(name))
        for name in ABLATION_CONFIGURATIONS
    )


def _spec(**overrides: Any) -> AblationCohortSpec:  # noqa: ANN401
    fields: dict[str, Any] = {
        "name": "aapl_ablation",
        "revision": 0,
        "base_cohort_file": "config/cohorts/aapl_confirmatory.toml",
        "base_cohort_id": "aapl_confirmatory-r0-0123456789ab",
        "base_cohort_hash": _hex("base"),
        "feature_set_name": ABLATION_FEATURE_SET_NAME,
        "configurations": _configurations(),
        "family_partition": _PARTITION,
        "seeds": (),
        "device": "rocm",
        "torch_build": None,
    }
    fields.update(overrides)
    return AblationCohortSpec(**fields)


def _hash(spec: AblationCohortSpec) -> str:
    return CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload()).value


def test_five_configurations_in_fixed_order() -> None:
    assert ABLATION_CONFIGURATIONS == (
        "full",
        "minus_price",
        "minus_technical",
        "minus_sentiment",
        "minus_fundamental",
    )
    assert tuple(c.name for c in _spec().configurations) == ABLATION_CONFIGURATIONS


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("full", None),
        ("minus_price", "price"),
        ("minus_technical", "technical"),
        ("minus_sentiment", "sentiment"),
        ("minus_fundamental", "fundamental"),
    ],
)
def test_configuration_identity_derived_from_the_name(name: str, family: str | None) -> None:
    configuration = AblationConfiguration.of(name, feature_set_hash=_hex(name))
    assert configuration.excluded_family == family
    assert configuration.model_version == f"tft_quantile_loco_{name}"
    # um model_version único para todas mataria a identidade por configuração
    with pytest.raises(ValueError, match="model_version"):
        AblationConfiguration(
            name=name,
            excluded_family=family,
            model_version="tft_quantile_loco",
            feature_set_hash=_hex(name),
        )
    with pytest.raises(ValueError, match="excluded_family"):
        AblationConfiguration(
            name=name,
            excluded_family="price" if family != "price" else "technical",
            model_version=f"tft_quantile_loco_{name}",
            feature_set_hash=_hex(name),
        )


@pytest.mark.parametrize(
    "configurations",
    [
        pytest.param(_configurations()[:4], id="missing"),
        pytest.param((*_configurations()[:4], _configurations()[0]), id="repeated"),
        pytest.param(tuple(reversed(_configurations())), id="other-order"),
    ],
)
def test_missing_repeated_or_unknown_configuration_refused(
    configurations: tuple[AblationConfiguration, ...],
) -> None:
    with pytest.raises(ValueError, match="configurations must be exactly"):
        _spec(configurations=configurations)
    with pytest.raises(ValueError, match="configuration must be one of"):
        AblationConfiguration.of("minus_volatility", feature_set_hash=_hex("x"))


@pytest.mark.parametrize("seeds", [(1, 1), (0, 1), (-2,), (True,), (1.0,)], ids=repr)
def test_repeated_or_non_positive_seed_refused(seeds: tuple[object, ...]) -> None:
    with pytest.raises(ValueError, match="seeds"):
        _spec(seeds=seeds)


@pytest.mark.parametrize(
    "partition",
    [
        pytest.param({**_PARTITION, "sentiment": ("sent_mean", "open")}, id="overlap"),
        pytest.param({k: v for k, v in _PARTITION.items() if k != "fundamental"}, id="missing"),
        pytest.param({**_PARTITION, "volatility": ("atr",)}, id="extra"),
        pytest.param({**_PARTITION, "technical": ()}, id="empty-family"),
    ],
)
def test_partition_overlap_or_missing_family_refused(partition: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="family_partition"):
        _spec(family_partition=partition)


@pytest.mark.parametrize(
    ("seeds", "torch_build", "frozen"),
    [
        ((), None, False),
        ((1, 2), None, False),
        ((), "2.13.0+rocm6.4", False),
        ((1, 2), "2.13.0+rocm6.4", True),
    ],
)
def test_is_frozen_requires_seeds_and_torch_build(
    seeds: tuple[int, ...], torch_build: str | None, frozen: bool
) -> None:
    assert _spec(seeds=seeds, torch_build=torch_build).is_frozen() is frozen


_CHANGES: dict[str, Any] = {
    "name": "other_ablation",
    "revision": 1,
    "base_cohort_file": "config/cohorts/other.toml",
    "base_cohort_id": "aapl_confirmatory-r1-000000000000",
    "base_cohort_hash": _hex("other-base"),
    "configurations": tuple(
        AblationConfiguration.of(name, feature_set_hash=_hex("x" + name))
        for name in ABLATION_CONFIGURATIONS
    ),
    "family_partition": {**_PARTITION, "price": ("open",), "technical": ("rsi_14", "close")},
    "seeds": (1,),
    "device": "cpu",
    "torch_build": "2.13.0+rocm6.4",
}


@pytest.mark.parametrize("field", sorted(_CHANGES))
def test_every_field_changes_the_hash(field: str) -> None:
    assert _hash(_spec(**{field: _CHANGES[field]})) != _hash(_spec())


@pytest.mark.parametrize("name", ["fs_all", "fs_other", ""])
def test_feature_set_name_other_than_the_ablation_partition_refused(name: str) -> None:
    """C2-1: com `fs_all`, as linhas LOCO cairiam na partição confirmatória (I3)."""
    with pytest.raises(ValueError, match="feature_set_name"):
        _spec(feature_set_name=name)


def test_cohort_id_pattern() -> None:
    spec = _spec(revision=3)
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    cohort_id = spec.cohort_id(cohort_hash)
    assert re.fullmatch(r"aapl_ablation-r3-[0-9a-f]{12}", cohort_id)
    assert cohort_id.endswith(cohort_hash.value[:12])


def test_with_freeze_sets_seeds_and_build_only() -> None:
    draft = _spec()
    frozen = draft.with_freeze(seeds=[1, 2, 3], torch_build="2.13.0+rocm6.4")
    assert frozen.seeds == (1, 2, 3)
    assert frozen.torch_build == "2.13.0+rocm6.4"
    assert frozen.is_frozen()
    assert replace(frozen, seeds=(), torch_build=None) == draft
    assert not draft.is_frozen()


def test_declaration_error_is_an_application_error() -> None:
    assert issubclass(AblationDeclarationError, ApplicationError)
