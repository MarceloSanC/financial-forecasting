"""Contrato do port `RuntimeEnvironmentProbe` (Stage 5.5, A4 / I5).

Nas duas pernas (a `real` entra na Task 23): a foto traz todas as
`REQUIRED_KEYS` como texto e `code_dirty` é `"true"`/`"false"`; duas fotos do
mesmo estado são iguais.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    REQUIRED_KEYS,
    RuntimeEnvironmentProbe,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)


@pytest.fixture(params=["fake"])
def probe(request: pytest.FixtureRequest) -> RuntimeEnvironmentProbe:
    if request.param == "fake":
        return InMemoryRuntimeEnvironmentProbe()
    raise AssertionError(request.param)  # pragma: no cover


@pytest.mark.contract
def test_snapshot_has_every_required_key_as_text(probe: RuntimeEnvironmentProbe) -> None:
    snapshot = probe.snapshot()

    assert set(REQUIRED_KEYS) <= set(snapshot)
    assert all(isinstance(value, str) and value for value in snapshot.values())
    assert snapshot[DIRTY_KEY] in {"true", "false"}


@pytest.mark.contract
def test_two_snapshots_of_the_same_state_are_equal(probe: RuntimeEnvironmentProbe) -> None:
    assert probe.snapshot() == probe.snapshot()
