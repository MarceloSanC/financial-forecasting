"""Unit — rastreamento do run no `TrainTft` (I12) e absorção da falha (C8).

Prova, com o fake do `ExperimentTracker` (1.5):

- **A8:** um `start_run`/`end_run` por fold; params, métricas por época e da
  melhor época, tags (`model_version`/`phase`/`fold`) e `log_artifact` com
  caminho EXISTENTE em disco;
- **C8:** tracker que ergue **não** derruba a execução — o resultado volta com
  `tracking_run_id` vazio e as linhas persistidas permanecem. A ordem
  (persistir, depois rastrear) é o que torna essa absorção segura, e o teste a
  verifica pelo efeito: com o tracker quebrado, o parquet continua completo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.unit.features.modeling.application.test_train_tft import (
    _build,
    _command,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = pytest.mark.unit

_N_FOLDS = 2
_EXPECTED_MODEL_VERSION = "tft_quantile"
_EXPECTED_PHASE = "confirmatory_ready"


class _ExplodingTracker:
    """Tracker que falha logo na abertura do run (C8)."""

    def __init__(self) -> None:
        self.start_calls = 0

    def start_run(
        self, *, run_name: str | None = None, run_id: str | None = None
    ) -> str:
        self.start_calls += 1
        msg = "tracking backend unreachable"
        raise RuntimeError(msg)

    def log_params(self, params: Mapping[str, object]) -> None:  # pragma: no cover
        raise AssertionError

    def log_metrics(
        self, metrics: Mapping[str, float], step: int | None = None
    ) -> None:  # pragma: no cover
        raise AssertionError

    def set_tags(self, tags: Mapping[str, str]) -> None:  # pragma: no cover
        raise AssertionError

    def log_artifact(self, path: str) -> None:  # pragma: no cover
        raise AssertionError

    def end_run(self) -> None:  # pragma: no cover
        raise AssertionError


class _LateExplodingTracker(_ExplodingTracker):
    """Falha só ao registrar o artefato — depois de params/métricas/tags.

    Cobre a metade de C8 que o caso anterior não alcança: a falha no MEIO do
    rastreamento também precisa ser absorvida, não só a de abertura.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logged_artifact = False

    def start_run(
        self, *, run_name: str | None = None, run_id: str | None = None
    ) -> str:
        self.start_calls += 1
        return f"tracking-{self.start_calls}"

    def log_params(self, params: Mapping[str, object]) -> None:
        return None

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        return None

    def set_tags(self, tags: Mapping[str, str]) -> None:
        return None

    def log_artifact(self, path: str) -> None:
        self.logged_artifact = True
        msg = "artifact store unreachable"
        raise OSError(msg)


def _tracker_of(use_case: Any) -> Any:  # noqa: ANN401 — acesso ao fake injetado
    return use_case._tracker


class TestRunIsTracked:
    def test_one_run_per_fold_with_params_metrics_tags_and_artifact(
        self, tmp_path: Path
    ) -> None:
        use_case, _, _ = _build(tmp_path)
        tracker = _tracker_of(use_case)

        result = use_case(_command())

        assert len(result.runs) == _N_FOLDS
        assert all(summary.tracking_run_id for summary in result.runs)
        for summary in result.runs:
            run = tracker._runs[summary.tracking_run_id]
            assert run.params["run_id"] == summary.run_id
            assert run.tags["model_version"] == _EXPECTED_MODEL_VERSION
            assert run.tags["phase"] == _EXPECTED_PHASE
            assert run.tags["fold"] == str(summary.fold_index)
            assert run.artifacts == [summary.artifact_path]
            assert ("best_val_loss", None) in run.metrics

    def test_validation_loss_is_logged_once_per_epoch(self, tmp_path: Path) -> None:
        """Uma métrica por época, indexada por `step` (histórico de I6/D11).

        Sem o `step`, as épocas se sobrescreveriam e o histórico que prova
        `best_epoch == argmin` viraria um único ponto.
        """
        use_case, _, _ = _build(tmp_path)
        tracker = _tracker_of(use_case)

        result = use_case(_command())

        run = tracker._runs[result.runs[0].tracking_run_id]
        steps = sorted(step for (name, step) in run.metrics if name == "val_loss")
        assert steps == list(range(len(steps)))
        assert len(steps) > 1

    def test_artifact_path_logged_exists_on_disk(self, tmp_path: Path) -> None:
        """O fake do tracker valida existência — é o que fecha o item do DoD."""
        from pathlib import Path as _Path  # noqa: PLC0415

        use_case, _, _ = _build(tmp_path)

        result = use_case(_command())

        assert all(_Path(summary.artifact_path).is_file() for summary in result.runs)


class TestTrackerFailureIsAbsorbed:
    """C8 — observabilidade não derruba resultado já persistido."""

    def test_failure_at_start_leaves_predictions_intact(self, tmp_path: Path) -> None:
        use_case, repo, _ = _build(tmp_path)
        use_case._tracker = _ExplodingTracker()

        result = use_case(_command())

        assert all(summary.tracking_run_id == "" for summary in result.runs)
        assert all(summary.rows_written > 0 for summary in result.runs)
        assert repo.read(layer="silver", table="fact_oos_predictions")

    def test_failure_midway_is_absorbed_too(self, tmp_path: Path) -> None:
        use_case, repo, _ = _build(tmp_path)
        tracker = _LateExplodingTracker()
        use_case._tracker = tracker

        result = use_case(_command())

        assert tracker.logged_artifact
        assert all(summary.tracking_run_id == "" for summary in result.runs)
        assert len(repo.read(layer="silver", table="dim_run")) == _N_FOLDS
