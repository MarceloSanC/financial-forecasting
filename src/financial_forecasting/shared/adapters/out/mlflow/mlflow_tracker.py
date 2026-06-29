"""Adapter MlflowTracker — implementação concreta do port `ExperimentTracker`.

Único lugar do projeto que importa `mlflow` (invariante I4; `check_layout.py` +
`import-linter` são o gate). Traduz a superfície mínima do port
(`shared/application/ports/out/experiment_tracker.py`) para a API do `mlflow`,
com backend SQLite local vindo de `Settings.mlflow_tracking_uri` (ADR 1.5.0001).

Semântica preservada (contract-testada em paridade com o fake, ADR 0.0.0021):

- **Idempotência por `run_id` (I2).** `start_run(run_id=...)` resume o run
  existente via `mlflow.start_run(run_id=...)` em vez de criar um novo — não
  duplica. Sem `run_id`, abre um run novo (id gerado pelo `mlflow`).
- **Run ativo exigido (C2).** `log_*`/`set_tags`/`log_artifact`/`end_run` sem
  `start_run` prévio levantam `RuntimeError` — o MESMO tipo observável que o
  fake (`FakeExperimentTracker`), para o contract test ser satisfeito por ambos
  sem conhecer a API do `mlflow`. O adapter checa `mlflow.active_run()` ANTES de
  delegar e levanta `RuntimeError` quando não há run ativo (em vez de deixar o
  `mlflow` abrir um run implícito).
- **`log_artifact` com path inexistente (C4).** Propaga o erro de I/O.

`mlflow` mantém o run ativo num contexto global de thread; o adapter não guarda
estado de run próprio (a fonte da verdade do run ativo é o `mlflow`).
"""

from __future__ import annotations

from collections.abc import Mapping

import mlflow
from mlflow.exceptions import MlflowException

_NO_ACTIVE_RUN = "no active run"


class MlflowTracker:
    """Implementação do contrato `ExperimentTracker` sobre `mlflow`."""

    def __init__(self, tracking_uri: str) -> None:
        self._tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)

    # -- contrato ------------------------------------------------------------

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
        """Abre/reabre um run e o torna ativo; retorna o `run_id` (ver port).

        Aponta o tracking_uri (idempotente) e delega a `mlflow.start_run`, que
        resume o run quando `run_id` é de um run EXISTENTE (I2) ou cria um novo
        (id gerado pelo backend) quando `run_id is None`.

        `run_id` fornecido mas inexistente no backend é caso de erro (C3): o
        `mlflow` levanta `MlflowException` ("Run ... not found") — o id de um run
        é atribuído pelo backend, não pelo chamador. O adapter re-levanta como
        `LookupError` (o MESMO tipo observável que o fake) para o contract test
        provar a paridade sem conhecer a API do `mlflow`.
        """
        mlflow.set_tracking_uri(self._tracking_uri)
        try:
            active = mlflow.start_run(run_id=run_id, run_name=run_name)
        except MlflowException as exc:
            raise LookupError(str(exc)) from exc
        return str(active.info.run_id)

    def log_params(self, params: Mapping[str, object]) -> None:
        """Registra params no run ativo (C2)."""
        self._require_active_run()
        mlflow.log_params(dict(params))

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        """Registra métricas no run ativo, por `step` (C2)."""
        self._require_active_run()
        mlflow.log_metrics(dict(metrics), step=step)

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Define tags no run ativo (C2)."""
        self._require_active_run()
        mlflow.set_tags(dict(tags))

    def log_artifact(self, path: str) -> None:
        """Registra artefato no run ativo; path inexistente propaga erro (C2/C4)."""
        self._require_active_run()
        mlflow.log_artifact(path)

    def end_run(self) -> None:
        """Encerra o run ativo (C2)."""
        self._require_active_run()
        mlflow.end_run()

    # -- helpers internos ----------------------------------------------------

    @staticmethod
    def _require_active_run() -> None:
        """Levanta `RuntimeError` se não houver run ativo (C2).

        `mlflow.active_run()` retorna `None` quando não há run ativo. Checar
        ANTES de delegar (a) garante o MESMO tipo de erro observável que o fake
        (`RuntimeError`) para o contract test ser satisfeito por ambos sem
        conhecer a API do `mlflow` e (b) evita o comportamento implícito do
        `mlflow` de abrir um run novo em algumas chamadas sem run ativo.
        """
        if mlflow.active_run() is None:
            raise RuntimeError(_NO_ACTIVE_RUN)
