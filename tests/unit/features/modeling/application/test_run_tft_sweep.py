"""Unit — `RunTftSweep`: isolamento estrutural (A10) e laço ask-and-tell.

O critério central desta Task é **A10**, e ele é ESTRUTURAL: o teste inspeciona
a assinatura do construtor. Uma asserção do tipo "o fake do repositório não
recebeu escritas" seria vácua se o repositório nunca fosse injetado — que é
exatamente o desenho. Por isso a prova primária é a ausência da dependência, e
as demais (fit-only, zero escritas pelo store, rótulo de fase) vêm depois.
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
    RunTftSweep,
    RunTftSweepCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.features.modeling.in_memory_hyperparameter_search import (
    InMemoryHyperparameterSearch,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_hasher import FakeHasher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

_FRIDAY = 4
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_SEED = 11
_N_TRIALS = 3
_EXPECTED_PHASE = "exploratory"
_FORBIDDEN_PORTS = ("persist_predictions", "analytics_repository")

_SCOPE = ScopeSpec(
    asset_id="TEST", feature_set_name="fs_test", max_horizon=2, cohort_id="cohort-h2"
)
_SPACE = (
    SearchDimension(name="hidden_size", low=4, high=32, kind="int"),
    SearchDimension(name="dropout", low=0.0, high=0.5, kind="float"),
)
_FEATURE_NAMES = unknown_feature_names() + known_feature_names()
# Histórico determinístico do `InMemoryTftTrainer` com `max_epochs=3`
# (decrescente e com a última pior, para o argmin ser interior).
_FAKE_HISTORY = (1.0, 0.9, 2.0)
_BASE_ENCODER_LENGTH = 12
_BASE_MAX_EPOCHS = 3


class _WritingStore(FakeMedallionStore):
    """Conta leituras e escritas — A10 assere que a varredura não grava."""

    def __init__(self) -> None:
        super().__init__()
        self.write_calls = 0
        self.read_calls = 0

    def write(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.write_calls += 1
        return super().write(**kwargs)

    def read(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.read_calls += 1
        return super().read(**kwargs)


def _weekday_sessions(count: int, *, start: date = date(2021, 1, 4)) -> tuple[date, ...]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


_SESSIONS = _weekday_sessions(_N_SESSIONS)


def _dataset_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(_SESSIONS):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": idx / 1000.0,
        }
        for position, name in enumerate(_FEATURE_NAMES):
            row[name] = float(idx) + (position + 1) / 100.0
        rows.append(row)
    return rows


def _seeded_store() -> _WritingStore:
    store = _WritingStore()
    store.seed_read_only(
        layer="processed",
        table="dataset_tft",
        asset=_SCOPE.asset_id,
        rows=_dataset_rows(),
    )
    return store


def _command(**overrides: object) -> RunTftSweepCommand:
    base: dict[str, object] = {
        "scope": _SCOPE,
        "base_params": TftTrainingParams(
            seed=_SEED,
            max_encoder_length=_BASE_ENCODER_LENGTH,
            max_epochs=_BASE_MAX_EPOCHS,
        ),
        "space": _SPACE,
        "n_trials": _N_TRIALS,
        "seed": _SEED,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "n_folds": 2,
        "test_size": 3,
        "val_size": 5,
        "calib_size": 5,
        "embargo": 1,
    }
    base.update(overrides)
    return RunTftSweepCommand(**base)  # type: ignore[arg-type]


def _build(
    tmp_path: Path, trainer: InMemoryTftTrainer | None = None
) -> tuple[RunTftSweep, _WritingStore, InMemoryTftTrainer, FakeExperimentTracker]:
    store = _seeded_store()
    resolved_trainer = trainer if trainer is not None else InMemoryTftTrainer()
    tracker = FakeExperimentTracker()
    use_case = RunTftSweep(
        store=store,
        splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
        trainer=resolved_trainer,
        search=InMemoryHyperparameterSearch(),
        tracker=tracker,
        hasher=FakeHasher(),
        artifacts_root=tmp_path / "artifacts",
    )
    return use_case, store, resolved_trainer, tracker


class TestStructuralIsolation:
    """A10 — a prova primária é a AUSÊNCIA da dependência."""

    @pytest.mark.parametrize("port", _FORBIDDEN_PORTS)
    def test_no_result_persistence_port_in_the_constructor(self, port: str) -> None:
        """Se alguém injetar uma dessas portas, gravar em silver vira possível.

        Uma asserção "o fake não recebeu escritas" não substituiria isto: ela
        seria vácua justamente porque a porta não existe.
        """
        parameters = inspect.signature(RunTftSweep.__init__).parameters

        assert port not in parameters

    def test_the_store_receives_no_writes(self, tmp_path: Path) -> None:
        """O `MedallionStore` expõe `write` genérico — aqui só se lê."""
        use_case, store, _, _ = _build(tmp_path)

        use_case(_command())

        assert store.write_calls == 0


class TestFitOnlyMode:
    def test_trainer_is_always_called_without_test_decisions(
        self, tmp_path: Path
    ) -> None:
        """Nenhuma predição out-of-sample é sequer PRODUZIDA na exploração."""
        use_case, _, trainer, _ = _build(tmp_path)

        use_case(_command())

        assert len(trainer.calls) == _N_TRIALS
        for call in trainer.calls:
            assert call["test_decision_indices"] == ()

    def test_no_artifact_is_written(self, tmp_path: Path) -> None:
        use_case, _, _, _ = _build(tmp_path)

        use_case(_command())

        assert not (tmp_path / "artifacts").exists()


class TestAskTellLoop:
    def test_one_trial_per_requested_iteration(self, tmp_path: Path) -> None:
        use_case, _, _, _ = _build(tmp_path)

        result = use_case(_command())

        assert len(result.trials) == _N_TRIALS
        assert [trial.trial_number for trial in result.trials] == list(range(_N_TRIALS))

    def test_objective_is_the_minimum_validation_loss(self, tmp_path: Path) -> None:
        """O objetivo NUNCA vem de `calib` ou `test` — só da perda de validação.

        O fake produz um histórico determinístico, então o objetivo informado ao
        estudo tem de ser exatamente o mínimo dele. Se alguém trocasse a fonte
        (pela última época, por exemplo), este número mudaria.
        """
        use_case, _, _, _ = _build(tmp_path)

        result = use_case(_command())

        expected = min(_FAKE_HISTORY)
        assert all(
            trial.objective_value == pytest.approx(expected) for trial in result.trials
        )

    def test_integer_dimension_is_recast_before_building_params(
        self, tmp_path: Path
    ) -> None:
        """Sem reconverter, `hidden_size=16.0` passaria e quebraria na lib."""
        use_case, _, trainer, _ = _build(tmp_path)

        use_case(_command())

        for call in trainer.calls:
            assert isinstance(call["params"].hidden_size, int)
            assert not isinstance(call["params"].hidden_size, bool)

    def test_best_params_come_from_the_best_trial(self, tmp_path: Path) -> None:
        use_case, _, _, _ = _build(tmp_path)

        result = use_case(_command())

        best = next(
            trial for trial in result.trials if trial.trial_number == result.best_trial_number
        )
        assert result.best_params.hidden_size == round(best.values["hidden_size"])
        assert result.best_params.dropout == pytest.approx(best.values["dropout"])

    def test_frozen_base_params_are_preserved(self, tmp_path: Path) -> None:
        """O que não está no espaço mantém o valor pré-registrado."""
        use_case, _, trainer, _ = _build(tmp_path)

        use_case(_command())

        for call in trainer.calls:
            assert call["params"].seed == _SEED
            assert call["params"].max_encoder_length == _BASE_ENCODER_LENGTH


class TestExploratoryLabel:
    def test_every_run_is_tagged_exploratory(self, tmp_path: Path) -> None:
        """Segunda camada de I14 — a primeira é a ausência da porta."""
        use_case, _, _, tracker = _build(tmp_path)

        use_case(_command())

        runs = list(tracker._runs.values())
        assert len(runs) == _N_TRIALS
        assert all(run.tags["phase"] == _EXPECTED_PHASE for run in runs)


class TestErrorCases:
    @pytest.mark.parametrize("n_trials", [0, -1])
    def test_non_positive_trial_count_raises(self, tmp_path: Path, n_trials: int) -> None:
        use_case, store, _, _ = _build(tmp_path)

        with pytest.raises(ValueError, match="C9"):
            use_case(_command(n_trials=n_trials))

        assert store.read_calls == 0  # ergueu antes de qualquer I/O

    def test_empty_space_raises(self, tmp_path: Path) -> None:
        use_case, _, _, _ = _build(tmp_path)

        with pytest.raises(ValueError, match="space"):
            use_case(_command(space=()))

    def test_all_trials_failing_raises(self, tmp_path: Path) -> None:
        class _AlwaysFailing(InMemoryTftTrainer):
            def train_and_predict(self, **kwargs: Any) -> Any:  # noqa: ANN401
                super().train_and_predict(**kwargs)
                msg = "combinação inviável"
                raise ValueError(msg)

        use_case, _, _, _ = _build(tmp_path, trainer=_AlwaysFailing())

        with pytest.raises(ValueError, match="C9"):
            use_case(_command())
