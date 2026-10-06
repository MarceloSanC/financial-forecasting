"""Unit test do `refresh_command_from` (Stage 6.5, A3, I6; ADR 6.5.0004 item 3).

Cada campo do `RefreshGoldCommand` sai do plano (parametrizado), a partição é
`(asset, cohort_id)`, os `RefreshParameters` inteiros vêm do plano e da referência, as
tuplas derivadas têm ordem fixa e o comando do scorecard não tem partição.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from tests.unit.features.evaluation._preregistration_payload import (
    TEST_FINGERPRINT,
    valid_payload,
)
from tests.unit.features.evaluation._profile_parameters import (
    profile_block,
    profile_parameters,
)

_PLAN = Preregistration.from_mapping(valid_payload())
_REF = "test_plan-r0-0123456789ab"
_COMMAND = refresh_command_from(_PLAN, _REF)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("asset", "AAPL"),
        ("parent_sweep_id", "test_cohort-r0-0123456789ab"),
        ("horizons", (1, 7)),
        ("window_deficits", dict.fromkeys(_PLAN.models, 0)),
        ("dataset_fingerprint", TEST_FINGERPRINT),
    ],
)
def test_command_field_from_plan(field: str, expected: object) -> None:
    assert getattr(_COMMAND, field) == expected


@pytest.mark.unit
def test_command_field_from_plan_follows_changes() -> None:
    payload = valid_payload()
    payload["asset"] = "MSFT"
    payload["window_deficits"] = {**payload["window_deficits"], "gbm_quantile": 3}  # type: ignore[dict-item]

    command = refresh_command_from(Preregistration.from_mapping(payload), _REF)

    assert command.asset == "MSFT"
    assert command.window_deficits["gbm_quantile"] == 3  # noqa: PLR2004


@pytest.mark.unit
def test_command_partition_from_cohort() -> None:
    assert _COMMAND.partition == GoldPartition("AAPL", _PLAN.cohort.cohort_id)


@pytest.mark.unit
def test_command_parameters_from_plan() -> None:
    parameters = _COMMAND.parameters

    assert parameters.as_mapping() == {
        "preregistration_ref": _REF,
        "degeneracy_tolerance": 1e-12,
        "band_levels": [0.95, 0.975],
        "min_violations": 2,
        "candidate": "tft_quantile",
        "dm_alpha": 0.05,
        "dm_variance_estimators": ["rectangular", "bartlett"],
        "mcs_alpha": 0.1,
        "mcs_reps": 1000,
        "mcs_seed": 127,
        "mcs_schemes": ["stationary", "moving_block"],
        "monte_carlo_draws": 999,
        "monte_carlo_seed": 128,
        "mcs_block_sensitivities": ["h", "sqrt_T"],
        "profile_parameters": None,
    }


@pytest.mark.unit
def test_command_tuple_order() -> None:
    parameters = _COMMAND.parameters

    assert parameters.band_levels == (0.95, 0.975)
    assert parameters.dm_variance_estimators == (
        DmVarianceEstimator.RECTANGULAR,
        DmVarianceEstimator.BARTLETT,
    )
    assert parameters.mcs_schemes == (BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK)
    with_bands = valid_payload()
    with_bands["h1_gate"]["profile_band_level"] = 0.975  # type: ignore[index]
    assert refresh_command_from(
        Preregistration.from_mapping(with_bands), _REF
    ).parameters.band_levels == (0.975,)


@pytest.mark.unit
def test_scorecard_command_without_partition() -> None:
    fields = {field.name for field in dataclasses.fields(BuildConfirmatoryScorecardCommand)}

    assert fields == {"name", "revision", "preregistration_ref"}
    command = BuildConfirmatoryScorecardCommand(
        name="test_plan", revision=0, preregistration_ref=_REF
    )
    assert command.revision == 0
    for bad, message in (
        ({"revision": -1}, "revision must be an int >= 0"),
        ({"revision": True}, "revision must be an int >= 0"),
        ({"name": ""}, "name must be a non-empty str"),
        ({"preregistration_ref": ""}, "preregistration_ref must be a non-empty str"),
    ):
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(command, **bad)  # type: ignore[arg-type]


@pytest.mark.unit
def test_profile_parameters_from_the_plan() -> None:
    """Stage 6.6 (F8a): MC, blocos e regras de perfil saem do plano; r0 -> sem regras."""
    parameters = _COMMAND.parameters
    assert (parameters.monte_carlo_draws, parameters.monte_carlo_seed) == (
        _PLAN.monte_carlo.draws,
        _PLAN.monte_carlo.seed,
    )
    assert parameters.mcs_block_sensitivities == _PLAN.mcs.block_sensitivities
    assert parameters.profile_parameters is None
    amended = Preregistration.from_mapping(
        {
            **valid_payload(),
            "revision": 1,
            "amends": _REF,
            "justification": "blinded profile rules",
            "blind_status": "blinded",
            "profile_parameters": profile_block(),
        }
    )
    assert refresh_command_from(
        amended, "test_plan-r1-0123456789ab"
    ).parameters.profile_parameters == (profile_parameters())
