"""Contract test do port `ExperimentTracker` — paridade Fake ↔ MlflowTracker.

Um ÚNICO contrato parametrizado sobre `[FakeExperimentTracker, MlflowTracker]`
prova que ambas as implementações honram a MESMA semântica observável
(invariantes I2/I3, critérios A3/A4): start/end de run, log de
params/metrics(step)/tags/artifact, erro de estado sem run ativo (C2) e
**idempotência por `run_id`** (I2: reabrir o mesmo `run_id` não cria run novo).

O `MlflowTracker` recebe `tracking_uri = sqlite:///<tmp_path>/mlruns.db` para
isolar cada execução (D4) — sem servidor, sem rede. A idempotência é verificada
pela IDENTIDADE do `run_id` (start_run(run_id=r) devolve r e um log subsequente
no run reaberto não falha nem exige novo run), mantendo o contrato AGNÓSTICO da
API de cada backend (ver technical 1.5 §7 [decision]). O fake levanta
`RuntimeError` em operação sem run ativo; o adapter re-levanta o erro do
`mlflow` como o mesmo `RuntimeError` — o `pytest.raises(RuntimeError)` casa em
ambos.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

import pytest

from financial_forecasting.shared.adapters.out.mlflow.mlflow_tracker import MlflowTracker
from financial_forecasting.shared.application.ports.out.experiment_tracker import (
    ExperimentTracker,
)
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker

_EXPECTED_ACCURACY = 0.95
_FIRST_LOSS = 0.5
_SECOND_LOSS = 0.4


def _build_fake(_tmp_path: Path) -> ExperimentTracker:
    return FakeExperimentTracker()


def _build_real(tmp_path: Path) -> ExperimentTracker:
    return MlflowTracker(tracking_uri=f"sqlite:///{tmp_path}/mlruns.db")


@pytest.fixture(params=[_build_fake, _build_real], ids=["fake", "real"])
def tracker(request: pytest.FixtureRequest, tmp_path: Path) -> ExperimentTracker:
    """Parametriza o contrato sobre o fake e o adapter real (isolado em tmp_path)."""
    factory: Callable[[Path], ExperimentTracker] = request.param
    impl = factory(tmp_path)
    yield impl
    # Garante que nenhum run ativo do mlflow vaza entre parametrizações.
    with contextlib.suppress(RuntimeError):
        impl.end_run()


@pytest.mark.contract
def test_start_run_returns_run_id(tracker: ExperimentTracker) -> None:
    """start_run devolve um run_id não-vazio e o torna ativo."""
    run_id = tracker.start_run(run_name="contract-run")

    assert isinstance(run_id, str)
    assert run_id


@pytest.mark.contract
def test_log_params_on_active_run(tracker: ExperimentTracker) -> None:
    """log_params no run ativo não levanta."""
    tracker.start_run(run_name="params")

    tracker.log_params({"lr": 0.01, "model": "tft", "layers": 3})

    tracker.end_run()


@pytest.mark.contract
def test_log_metrics_with_step_on_active_run(tracker: ExperimentTracker) -> None:
    """log_metrics com step no run ativo não levanta (duas chamadas por step)."""
    tracker.start_run(run_name="metrics")

    tracker.log_metrics({"loss": _FIRST_LOSS}, step=0)
    tracker.log_metrics({"loss": _SECOND_LOSS, "accuracy": _EXPECTED_ACCURACY}, step=1)

    tracker.end_run()


@pytest.mark.contract
def test_set_tags_on_active_run(tracker: ExperimentTracker) -> None:
    """set_tags no run ativo não levanta."""
    tracker.start_run(run_name="tags")

    tracker.set_tags({"phase": "exploratory", "asset": "AAPL"})

    tracker.end_run()


@pytest.mark.contract
def test_log_artifact_on_active_run(tracker: ExperimentTracker, tmp_path: Path) -> None:
    """log_artifact com arquivo real no run ativo não levanta."""
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello", encoding="utf-8")

    tracker.start_run(run_name="artifact")
    tracker.log_artifact(str(artifact))
    tracker.end_run()


@pytest.mark.contract
def test_log_params_without_active_run_raises(tracker: ExperimentTracker) -> None:
    """C2: log_params sem run ativo levanta RuntimeError (mesmo tipo em ambos)."""
    with pytest.raises(RuntimeError):
        tracker.log_params({"lr": 0.01})


@pytest.mark.contract
def test_log_metrics_without_active_run_raises(tracker: ExperimentTracker) -> None:
    """C2: log_metrics sem run ativo levanta RuntimeError."""
    with pytest.raises(RuntimeError):
        tracker.log_metrics({"loss": _FIRST_LOSS})


@pytest.mark.contract
def test_set_tags_without_active_run_raises(tracker: ExperimentTracker) -> None:
    """C2: set_tags sem run ativo levanta RuntimeError."""
    with pytest.raises(RuntimeError):
        tracker.set_tags({"phase": "x"})


@pytest.mark.contract
def test_end_run_without_active_run_raises(tracker: ExperimentTracker) -> None:
    """C2: end_run sem run ativo levanta RuntimeError."""
    with pytest.raises(RuntimeError):
        tracker.end_run()


@pytest.mark.contract
def test_idempotent_resume_by_run_id(tracker: ExperimentTracker) -> None:
    """I2: reabrir o mesmo run_id resume o run (mesmo id), sem duplicar.

    Verificação agnóstica de backend: capturo o run_id, encerro o run, reabro
    por aquele run_id e exijo que (a) o id devolvido seja o MESMO e (b) um log
    no run reaberto não falhe (prova que há run ativo, ou seja, foi resumido —
    não foi criado um run vazio nem deixado sem run).
    """
    original_id = tracker.start_run(run_name="resume")
    tracker.end_run()

    resumed_id = tracker.start_run(run_id=original_id)

    assert resumed_id == original_id
    tracker.log_metrics({"loss": _SECOND_LOSS}, step=2)
    tracker.end_run()
