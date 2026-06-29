"""Port compartilhado: ExperimentTracker.

Abstrai o tracking de experimentos (runs com params/metrics/tags/artifacts)
usado pelo treino e pelos sweeps (a Stage 5.4 `TrainTft` consome este port).
A camada `application` depende APENAS deste `Protocol` estrutural, com tipos
primitivos/`Mapping` — NUNCA tipos do `mlflow`: o tracker é trocável, testável
por um fake in-memory e validado por contract test (paridade fake↔real, mesma
postura da Stage 1.4 / ADR 0.0.0021). A tradução para a API concreta (`mlflow`)
vive só no adapter `MlflowTracker` (`shared/adapters/out/mlflow/`).

Semântica garantida por qualquer implementação deste contrato:

- **Idempotência por `run_id` (I2).** `start_run` retorna o `run_id` do run
  ativo. Quando recebe um `run_id` já existente, REABRE/atualiza o mesmo run em
  vez de criar outro (no-op de criação) — registrar o mesmo `run_id` duas vezes
  não duplica. Herdado da semântica `dim_run`/dedup do repo antigo
  (`upsert_dim_run`), agora como contrato e não detalhe de Parquet.
- **Run ativo exigido (C2).** `log_params`/`log_metrics`/`set_tags`/
  `log_artifact`/`end_run` operam sobre o run ATIVO; chamá-los sem um
  `start_run` prévio é caso de erro de estado (o adapter propaga o "no active
  run" do `mlflow`; o fake levanta o mesmo tipo de erro observável —
  `RuntimeError`).
- **`run_id` inexistente no backend (C3).** `start_run(run_id=...)` com um id
  ainda não registrado abre um run NOVO identificado por aquele id (não é erro);
  a idempotência é sobre não duplicar ao reabrir, não sobre exigir
  pré-existência.
- **`log_artifact` com path inexistente (C4).** Propaga o erro de I/O da
  implementação subjacente (não silencia).

Ver ADR docs/adr/1_5_0002-experiment-tracker-port-shape.md (forma do port) e
docs/adr/1_5_0001-mlflow-sqlite-local-tracking.md (backend).
"""

from collections.abc import Mapping
from typing import Protocol


class ExperimentTracker(Protocol):
    """Contrato de tracking de experimentos (run-based), sem vazar `mlflow`."""

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
        """Abre (ou REABRE) um run e o torna o run ativo; retorna o `run_id`.

        Com `run_id` de um run já existente, reabre o MESMO run em vez de criar
        outro (idempotência por `run_id`, I2). Com `run_id` inexistente, abre um
        run novo com aquele id (C3). `run_name` nomeia um run novo. Retorna o
        `run_id` (string) do run ativo.
        """
        ...

    def log_params(self, params: Mapping[str, object]) -> None:
        """Registra parâmetros (valores heterogêneos) no run ativo.

        Exige run ativo (C2). O adapter serializa os valores para o backend.
        """
        ...

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        """Registra métricas (float) no run ativo, opcionalmente por `step`.

        Exige run ativo (C2). `step` carrega a dimensão de passo de treino.
        """
        ...

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Define tags (string) no run ativo. Exige run ativo (C2)."""
        ...

    def log_artifact(self, path: str) -> None:
        """Registra um artefato a partir de um path de arquivo no run ativo.

        Exige run ativo (C2); path inexistente propaga erro de I/O (C4).
        """
        ...

    def end_run(self) -> None:
        """Encerra o run ativo. Exige run ativo (C2)."""
        ...
