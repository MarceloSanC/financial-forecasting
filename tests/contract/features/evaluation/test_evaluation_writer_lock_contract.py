"""Contract test do port `EvaluationWriterLock` — fake e `JsonCohortProgressLedger` (D8).

Prova (concept 8.1 D8) que as duas pernas têm o mesmo lock de escritor único: adquirir e
liberar; segunda aquisição com o lock detido → `ApplicationError`; `break_stale=True`
toma um lock órfão (deixado por outro dono). O real é o ledger da 5.5, por duck typing;
as fixtures são TIPADAS pelo Protocol do `evaluation`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pytest

from financial_forecasting.features.evaluation.application.ports.out.evaluation_writer_lock import (
    EvaluationWriterLock,
)
from financial_forecasting.features.modeling.adapters.out.filesystem.json_cohort_progress_ledger import (  # noqa: E501
    JsonCohortProgressLedger,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.evaluation.in_memory_evaluation_writer_lock import (
    InMemoryEvaluationWriterLock,
)

pytestmark = pytest.mark.contract


class Harness(Protocol):
    lock: EvaluationWriterLock

    def orphan(self) -> None: ...


class _FakeHarness:
    def __init__(self, _root: Path) -> None:
        self._fake = InMemoryEvaluationWriterLock()
        self.lock: EvaluationWriterLock = self._fake

    def orphan(self) -> None:
        self._fake.hold_by_other()


class _RealHarness:
    def __init__(self, root: Path) -> None:
        self._root = root
        self.lock: EvaluationWriterLock = JsonCohortProgressLedger(
            artifacts_root=root / "artifacts", data_root=root / "data"
        )

    def orphan(self) -> None:
        # outro processo adquiriu e caiu sem liberar
        JsonCohortProgressLedger(
            artifacts_root=self._root / "artifacts", data_root=self._root / "data"
        ).acquire_writer()


HARNESSES: dict[str, Callable[[Path], Harness]] = {"fake": _FakeHarness, "real": _RealHarness}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    return HARNESSES[request.param](tmp_path)


def test_acquire_then_release(harness: Harness) -> None:
    harness.lock.acquire_writer()
    harness.lock.release_writer()
    harness.lock.release_writer()  # idempotente

    harness.lock.acquire_writer()
    harness.lock.release_writer()


def test_second_acquire_raises_application_error(harness: Harness) -> None:
    harness.lock.acquire_writer()

    with pytest.raises(ApplicationError):
        harness.lock.acquire_writer()
    harness.lock.release_writer()


def test_break_stale_takes_an_orphan_lock(harness: Harness) -> None:
    harness.orphan()
    with pytest.raises(ApplicationError):
        harness.lock.acquire_writer()

    harness.lock.acquire_writer(break_stale=True)
    harness.lock.release_writer()
    harness.lock.acquire_writer()
    harness.lock.release_writer()
