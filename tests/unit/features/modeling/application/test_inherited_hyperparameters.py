"""Unit test do parâmetro `inherited_hyperparameters` (Stage 8.4, Task 02 / CA5).

A rodada de produção usa os hiperparâmetros dos sweeps do confirmatório sobre dado
novo (ADR 8.4.0001 item 6). Prova: por padrão, sweeps sobre outro dado seguem
recusados; com `True`, só essa igualdade é dispensada — impressão digital
observada ≠ declarada, `feature_set_hash`, device, `pipeline_version` e a
proveniência ausente continuam recusados —, e o use case corre as unidades.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortDeclarationMismatchError,
    DatasetMismatchError,
    RunConfirmatoryCohort,
    RunConfirmatoryCohortCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application import test_cohort_tft_helpers as helpers
from tests.unit.features.modeling.application import test_run_confirmatory_cohort as runner

_OTHER_DATA = "0" * 64


def _swept_on_other_data(spec: CohortSpec) -> CohortSpec:
    assert spec.provenance is not None
    return replace(spec, provenance=replace(spec.provenance, dataset_fingerprint=_OTHER_DATA))


# -- check_cohort_declarations --------------------------------------------------------


def test_default_still_refuses_sweeps_on_other_data() -> None:
    with pytest.raises(CohortDeclarationMismatchError, match="sweeps ran on a different dataset"):
        helpers._check(_swept_on_other_data(helpers._spec()))


def test_inherited_accepts_sweeps_on_other_data() -> None:
    grid = helpers._check(_swept_on_other_data(helpers._spec()), inherited_hyperparameters=True)

    assert len(grid.timestamps) == helpers._N_SESSIONS


@pytest.mark.parametrize(
    ("spec_overrides", "check_overrides", "error", "message"),
    [
        ({"dataset_fingerprint": "0" * 64}, {}, DatasetMismatchError, "materialized data changed"),
        ({}, {"observed_feature_set_hash": "e" * 64}, CohortDeclarationMismatchError, "registry"),
        ({}, {"pipeline_version": "other"}, CohortDeclarationMismatchError, "pipeline_version"),
        ({"device": "rocm"}, {}, CohortDeclarationMismatchError, "device"),
        ({"provenance": None}, {}, CohortDeclarationMismatchError, "no sweep provenance"),
    ],
    ids=["fingerprint", "feature_set_hash", "pipeline_version", "device", "no-provenance"],
)
def test_inherited_keeps_every_other_refusal(
    spec_overrides: dict[str, object],
    check_overrides: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    spec = _swept_on_other_data(helpers._spec())
    spec = replace(spec, **spec_overrides)  # type: ignore[arg-type]

    with pytest.raises(error, match=message):
        helpers._check(spec, inherited_hyperparameters=True, **check_overrides)


# -- RunConfirmatoryCohort -------------------------------------------------------------


def _use_case(harness: runner._Harness, *, inherited: bool) -> RunConfirmatoryCohort:
    return RunConfirmatoryCohort(
        store=runner._store(),
        hasher=runner._HASHER,
        clock=FakeClock(),
        ledger=harness.ledger,
        run_index=harness.index,
        probe=InMemoryRuntimeEnvironmentProbe(),
        run_baselines=harness._baselines,
        train_gbm=harness._gbm,
        train_tft=harness._tft,
        modeling_columns=modeling_columns(),
        observed_feature_set_hash=runner._FEATURE_SET_HASH,
        pipeline_version=PIPELINE_VERSION,
        schema_version=1,
        supported_device="cpu",
        inherited_hyperparameters=inherited,
    )


def test_use_case_default_refuses_sweeps_on_other_data_before_training() -> None:
    harness = runner._Harness()
    spec = _swept_on_other_data(runner._spec())

    with pytest.raises(CohortDeclarationMismatchError, match="sweeps ran on a different dataset"):
        _use_case(harness, inherited=False)(RunConfirmatoryCohortCommand(spec=spec))

    assert harness.calls == []
    assert harness.ledger.acquire_count == 1
    assert not harness.ledger.is_locked


def test_use_case_with_inherited_hyperparameters_runs_every_unit() -> None:
    harness = runner._Harness()
    spec = _swept_on_other_data(runner._spec())

    result = _use_case(harness, inherited=True)(RunConfirmatoryCohortCommand(spec=spec))

    assert [unit for unit, _ in harness.calls] == ["baselines", "gbm", "tft:seed=11", "tft:seed=22"]
    assert [outcome.status for outcome in result.outcomes] == ["ran"] * 4
    assert result.cohort_id == runner._cohort_id(spec)
