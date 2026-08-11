"""Unit — rastreamento do run no `TrainTft` (I12) e absorção da falha (C8).

Prova, com o fake do `ExperimentTracker` (1.5):

- **A8:** um `start_run`/`end_run` por fold — inclusive o `end_run`, sem o qual
  o run fica ativo e o fold seguinte esbarra em "run já ativo" no backend real;
  params, métricas por época, tags e `log_artifact` com caminho existente;
- **ordem obrigatória (I12/C8):** rastrear DEPOIS de persistir. O teste observa
  o entrelaçamento com um tracker espião que lê o repositório no momento do
  `start_run` — sem isso a ordem seria invisível às asserções, porque a
  absorção da falha torna as duas ordens indistinguíveis pelo estado final;
- **C8:** tracker que ergue não derruba a execução — nem na abertura nem no
  meio —, o resultado volta com `tracking_run_id` vazio, as linhas persistidas
  permanecem e o run é fechado mesmo no caminho de erro.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.unit.features.modeling.application.test_train_tft import _build, _command

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
        FakeAnalyticsRepository,
    )

pytestmark = pytest.mark.unit

_N_FOLDS = 2
_EXPECTED_MODEL_VERSION = "tft_quantile"
_EXPECTED_PHASE = "confirmatory_ready"
_FACT_TABLE = "fact_oos_predictions"


class _ExplodingTracker:
    """Tracker que falha logo na abertura do run (C8)."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.end_calls = 0

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
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

    def end_run(self) -> None:
        self.end_calls += 1


class _LateExplodingTracker(_ExplodingTracker):
    """Falha só ao registrar o artefato — depois de params/métricas/tags.

    Cobre a metade de C8 que o caso anterior não alcança: a falha NO MEIO do
    rastreamento também precisa ser absorvida, e o run precisa ser fechado.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logged_artifact = False

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
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


class _RepositoryProbingTracker:
    """Espião que fotografa o repositório no instante do `start_run`.

    É o único jeito de a ordem "persistir -> rastrear" virar comportamento
    observável: comparando o estado final, as duas ordens são idênticas.
    """

    def __init__(self) -> None:
        # Atribuído após a construção do use case (ovo e galinha: o tracker
        # entra no construtor, e o repositório nasce lá dentro).
        self.repository: FakeAnalyticsRepository | None = None
        self.rows_at_start: list[int] = []

    def start_run(self, *, run_name: str | None = None, run_id: str | None = None) -> str:
        assert self.repository is not None
        self.rows_at_start.append(
            len(self.repository.read(layer="silver", table=_FACT_TABLE))
        )
        return f"tracking-{len(self.rows_at_start)}"

    def log_params(self, params: Mapping[str, object]) -> None:
        return None

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        return None

    def set_tags(self, tags: Mapping[str, str]) -> None:
        return None

    def log_artifact(self, path: str) -> None:
        return None

    def end_run(self) -> None:
        return None


class TestRunIsTracked:
    def test_one_run_per_fold_with_params_metrics_tags_and_artifact(
        self, tmp_path: Path
    ) -> None:
        use_case, _, _, tracker = _build(tmp_path)

        result = use_case(_command())

        assert len(result.runs) == _N_FOLDS
        assert all(summary.tracking_run_id for summary in result.runs)
        for summary in result.runs:
            run = tracker._runs[summary.tracking_run_id]
            assert run.params["run_id"] == summary.run_id
            assert run.tags["model_version"] == _EXPECTED_MODEL_VERSION
            assert run.tags["phase"] == _EXPECTED_PHASE
            assert run.tags["fold"] == str(summary.fold_index)
            assert [str(path) for path in run.artifacts] == [summary.artifact_path]
            assert ("best_val_loss", None) in run.metrics

    def test_every_run_is_closed(self, tmp_path: Path) -> None:
        """Sem `end_run`, o fold seguinte esbarra em "run já ativo" no real."""
        use_case, _, _, tracker = _build(tmp_path)

        use_case(_command())

        assert tracker._active_run_id is None
        assert len(tracker._runs) == _N_FOLDS

    def test_logged_artifact_exists_on_disk(self, tmp_path: Path) -> None:
        """Asserção sobre o que o TRACKER recebeu, não sobre o fake do trainer."""
        from pathlib import Path as _Path  # noqa: PLC0415

        use_case, _, _, tracker = _build(tmp_path)

        result = use_case(_command())

        for summary in result.runs:
            run = tracker._runs[summary.tracking_run_id]
            assert _Path(run.artifacts[0]).is_file()

    def test_validation_loss_is_logged_once_per_epoch(self, tmp_path: Path) -> None:
        """Uma métrica por época, indexada por `step` (histórico de I6/D11).

        Sem o `step`, as épocas se sobrescreveriam e o histórico que prova
        `best_epoch == argmin` viraria um único ponto.
        """
        use_case, _, _, tracker = _build(tmp_path)

        result = use_case(_command())

        run = tracker._runs[result.runs[0].tracking_run_id]
        steps = sorted(step for (name, step) in run.metrics if name == "val_loss")
        assert steps == list(range(len(steps)))
        assert len(steps) > 1


class TestPersistBeforeTrack:
    def test_predictions_are_already_persisted_when_the_run_opens(
        self, tmp_path: Path
    ) -> None:
        """A ordem é o que torna a absorção de C8 segura — e aqui ela é observada."""
        probing = _RepositoryProbingTracker()
        use_case, repo, _, _ = _build(tmp_path, tracker=probing)
        probing.repository = repo

        use_case(_command())

        assert len(probing.rows_at_start) == _N_FOLDS
        # No 1º `start_run` as linhas do 1º fold JÁ existem; no 2º, as dos dois.
        # Rastrear antes de persistir zeraria a primeira e igualaria as duas.
        assert probing.rows_at_start[0] > 0
        assert probing.rows_at_start[1] > probing.rows_at_start[0]


class TestTrackerFailureIsAbsorbed:
    """C8 — observabilidade não derruba resultado já persistido."""

    def test_failure_at_start_leaves_predictions_intact(self, tmp_path: Path) -> None:
        tracker = _ExplodingTracker()
        use_case, repo, _, _ = _build(tmp_path, tracker=tracker)

        result = use_case(_command())

        assert tracker.start_calls == _N_FOLDS
        assert all(summary.tracking_run_id == "" for summary in result.runs)
        assert all(summary.rows_written > 0 for summary in result.runs)
        assert repo.read(layer="silver", table=_FACT_TABLE)

    def test_failure_midway_is_absorbed_and_the_run_is_closed(
        self, tmp_path: Path
    ) -> None:
        tracker = _LateExplodingTracker()
        use_case, repo, _, _ = _build(tmp_path, tracker=tracker)

        result = use_case(_command())

        assert tracker.logged_artifact
        assert tracker.end_calls == _N_FOLDS  # fechado mesmo no caminho de erro
        assert all(summary.tracking_run_id == "" for summary in result.runs)
        assert len(repo.read(layer="silver", table="dim_run")) == _N_FOLDS
