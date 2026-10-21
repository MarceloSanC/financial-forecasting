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
from tests.unit.features.evaluation._conformal_parameters import conformal_parameters
from tests.unit.features.evaluation._preregistration_payload import (
    TEST_FINGERPRINT,
    r1_payload,
    r2_payload,
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
        "conformal_parameters": None,
        "h3_parameters": None,
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


# --- Stage 7.2 Task 16: bloco `[conformal]` na derivação única ----------------------


@pytest.mark.unit
def test_r0_and_r1_derive_no_conformal_parameters() -> None:
    assert _COMMAND.parameters.conformal_parameters is None
    r1 = Preregistration.from_mapping(r1_payload())
    assert (
        refresh_command_from(r1, "test_plan-r1-0123456789ab").parameters.conformal_parameters
        is None
    )


@pytest.mark.unit
def test_plan_with_block_derives_the_block() -> None:
    r2 = Preregistration.from_mapping(r2_payload())
    parameters = refresh_command_from(r2, "test_plan-r2-0123456789ab").parameters
    assert parameters.conformal_parameters == conformal_parameters()
    assert parameters.conformal_parameters is r2.conformal


# --- Stage 7.3 Task 27: bloco `[h3]` na derivação única ------------------------------------


@pytest.mark.unit
def test_r0_to_r2_derive_no_h3_parameters() -> None:
    from tests.unit.features.evaluation._preregistration_payload import (  # noqa: PLC0415
        r2_payload,
    )

    assert _COMMAND.parameters.h3_parameters is None
    for payload, ref in ((r1_payload(), "r1"), (r2_payload(), "r2")):
        plan = Preregistration.from_mapping(payload)
        command = refresh_command_from(plan, f"test_plan-{ref}-0123456789ab")
        assert command.parameters.h3_parameters is None


@pytest.mark.unit
def test_plan_with_h3_derives_the_block() -> None:
    from tests.unit.features.evaluation._h3_parameters import h3_parameters  # noqa: PLC0415
    from tests.unit.features.evaluation._preregistration_payload import (  # noqa: PLC0415
        r3_payload,
    )

    r3 = Preregistration.from_mapping(r3_payload())
    parameters = refresh_command_from(r3, "test_plan-r3-0123456789ab").parameters
    assert parameters.h3_parameters == h3_parameters()
    assert parameters.h3_parameters is r3.h3
    assert parameters.conformal_parameters is r3.conformal
