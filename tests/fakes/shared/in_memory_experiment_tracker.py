"""Fake in-memory do port `ExperimentTracker` — NÃO um mock.

`FakeExperimentTracker` aplica a MESMA semântica observável do adapter real
(`MlflowTracker`): mantém runs num dict keyed por `run_id`, gera `run_id` via
`uuid4().hex` quando não fornecido, REABRE o mesmo run ao receber um `run_id` já
registrado (idempotência por `run_id`, I2), recusa um `run_id` fornecido mas
inexistente (C3, `LookupError` — o id é atribuído pelo backend, não pelo
chamador, espelhando o `mlflow`), exige run ativo para
`log_*`/`set_tags`/`log_artifact`/`end_run` (C2, levantando `RuntimeError` — o
mesmo TIPO observável que o adapter real re-levanta do `mlflow`) e propaga erro
de I/O em `log_artifact` com path inexistente (C4, espelhando o real).

Guarda o estado mínimo de cada run (params/metrics/tags/artifacts) para que o
fake produza COMPORTAMENTO real e estável, não asserts de chamada. A paridade
fake↔real é provada pelo contract test
(`tests/contract/shared/test_experiment_tracker_contract.py`), parametrizado
sobre `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass
class _RunState:
    """Estado in-memory de um run (acumulado entre reaberturas)."""

    run_id: str
    run_name: str | None = None
    params: dict[str, object] = field(default_factory=dict)
    # métricas acumuladas por (nome, step) — step None vira chave própria.
    metrics: dict[tuple[str, int | None], float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)


class FakeExperimentTracker:
    """Implementação in-memory determinística do contrato `ExperimentTracker`."""

    def __init__(self) -> None:
        self._runs: dict[str, _RunState] = {}
        self._active_run_id: str | None = None

    # -- contrato ------------------------------------------------------------

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
        """Abre/reabre um run e o torna ativo; retorna o `run_id` (ver port).

        `run_id is None` cria um run novo com id gerado (`uuid4().hex`). Um
        `run_id` fornecido REABRE o run existente (I2); fornecer um `run_id`
        ainda não registrado é erro (C3) — espelha o `mlflow`, em que o id é
        atribuído pelo backend e não pelo chamador (levanta `LookupError`, o
        mesmo tipo observável que o adapter real).
        """
        if run_id is None:
            resolved_id = uuid4().hex
            self._runs[resolved_id] = _RunState(run_id=resolved_id, run_name=run_name)
            self._active_run_id = resolved_id
            return resolved_id
        run = self._runs.get(run_id)
        if run is None:
            raise LookupError(f"Run with id={run_id} not found")
        if run_name is not None:
            # reabertura nomeada: atualiza o nome sem duplicar o run (I2).
            run.run_name = run_name
        self._active_run_id = run_id
        return run_id

    def log_params(self, params: Mapping[str, object]) -> None:
        """Registra params no run ativo (C2)."""
        self._active_run().params.update(params)

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        """Registra métricas no run ativo, por `step` (C2)."""
        run = self._active_run()
        for name, value in metrics.items():
            run.metrics[name, step] = value

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Define tags no run ativo (C2)."""
        self._active_run().tags.update(tags)

    def log_artifact(self, path: str) -> None:
        """Registra artefato no run ativo; path inexistente propaga erro (C2/C4)."""
        run = self._active_run()
        if not Path(path).exists():
            raise FileNotFoundError(path)
        run.artifacts.append(path)

    def end_run(self) -> None:
        """Encerra o run ativo (C2)."""
        self._active_run()
        self._active_run_id = None

    # -- helpers internos ----------------------------------------------------

    def _active_run(self) -> _RunState:
        """Retorna o run ativo ou levanta `RuntimeError` se não houver (C2)."""
        if self._active_run_id is None:
            raise RuntimeError("no active run")
        return self._runs[self._active_run_id]
