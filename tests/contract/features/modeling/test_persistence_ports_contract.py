"""Contrato `[fake, real]` dos ports `PredictionPersister` e `RunRecordPersister` (#68).

Os dois ports são definidos em `modeling/application/ports/out/` e satisfeitos por
duck-typing pelos use cases do `analytics_store` (`PersistPredictions`,
`PersistRunRecord`) — a perna "real" aqui é o use case real sobre o
`FakeAnalyticsRepository` (o dublê certo fica na fronteira de I/O; nada de disco).
A mesma suíte roda nas duas pernas e assevera o MESMO oráculo, o que verifica a
paridade transitivamente (correção registrada na issue #62):

`PredictionPersister`:
- (a) janela completa: `rows_written == n_horizontes x n_níveis`, `rows_skipped == 0`;
- (b) janela incompleta num horizonte: esse horizonte inteiro é pulado
  (`rows_skipped == n_níveis`), os demais gravados — sem `y_true` fabricado;
- (c) `horizon < 1` / `decision_idx < 0` erguem `ValueError` nas duas pernas (a regra
  é do domain service `MultiHorizonPredictionPersister`, casa única);
- (d) o resultado expõe exatamente o que o port promete (`rows_written`, `rows_skipped`).

`RunRecordPersister`:
- (e) um record → `rows_written == 1`; regravar o mesmo `run_id` não ergue (upsert)
  e a última versão prevalece — lida do repositório (real) ou do fake.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecord,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)
from financial_forecasting.features.modeling.application.ports.out.prediction_persister import (
    PredictionPersister,
)
from financial_forecasting.features.modeling.application.ports.out.run_record_persister import (
    RunRecordPersister,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_prediction_persister import (
    InMemoryPredictionPersister,
)
from tests.fakes.features.modeling.in_memory_run_record_persister import (
    InMemoryRunRecordPersister,
)

_LEVELS = (0.1, 0.5, 0.9)
_TIMESTAMPS = tuple(f"2025-01-{day:02d}T00:00:00+00:00" for day in (2, 3, 6, 7, 8))
_LAST_IDX = len(_TIMESTAMPS) - 1


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


def _forecast(shift: float = 0.0) -> QuantileForecast:
    return QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1 + shift, 0.5, 0.9))


def _command(*, decision_idx: int, horizons: tuple[int, ...]) -> PersistPredictionsCommand:
    return PersistPredictionsCommand(
        run_id="a" * 64,
        split="test",
        model_version="tft_v1",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=1,
        decision_idx=decision_idx,
        dataset_timestamps=_TIMESTAMPS,
        forecasts={horizon: _forecast() for horizon in horizons},
    )


def _record(**overrides: object) -> RunRecord:
    fields: dict[str, object] = {
        "run_id": "b" * 64,
        "asset": "AAPL",
        "parent_sweep_id": None,
        "feature_set_name": "fs_all",
        "config_signature": "c" * 64,
        "split_fingerprint": "d" * 64,
        "fold": "0",
        "seed": None,
        "model_version": "v1",
        "schema_version": 1,
    }
    fields.update(overrides)
    return RunRecord(**fields)  # type: ignore[arg-type]


# -- PredictionPersister -----------------------------------------------------------


@pytest.fixture(params=["fake", "real"])
def prediction_persister(request: pytest.FixtureRequest) -> PredictionPersister:
    if request.param == "fake":
        return InMemoryPredictionPersister()
    return PersistPredictions(repository=FakeAnalyticsRepository(clock=_FakeClock()))


def test_complete_windows_count_one_row_per_horizon_and_level(
    prediction_persister: PredictionPersister,
) -> None:
    result = prediction_persister(_command(decision_idx=0, horizons=(1, 2)))

    assert (result.rows_written, result.rows_skipped) == (2 * len(_LEVELS), 0)


def test_incomplete_window_skips_that_horizon_entirely(
    prediction_persister: PredictionPersister,
) -> None:
    """decision no penúltimo índice: h=1 cabe, h=2 não → 3 gravadas, 3 puladas."""
    result = prediction_persister(_command(decision_idx=_LAST_IDX - 1, horizons=(1, 2)))

    assert (result.rows_written, result.rows_skipped) == (len(_LEVELS), len(_LEVELS))


@pytest.mark.parametrize(
    "decision_idx, horizons",
    [pytest.param(-1, (1,), id="decision-negativa"), pytest.param(0, (0,), id="horizonte-zero")],
)
def test_invalid_geometry_raises_in_both_legs(
    prediction_persister: PredictionPersister, decision_idx: int, horizons: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError, match="must be >="):
        prediction_persister(_command(decision_idx=decision_idx, horizons=horizons))


# -- RunRecordPersister -----------------------------------------------------------


@pytest.fixture(params=["fake", "real"])
def run_record_leg(
    request: pytest.FixtureRequest,
) -> tuple[RunRecordPersister, Callable[[str], str]]:
    """`(persister, model_version_of(run_id))` — a leitura de volta é própria de cada perna."""
    if request.param == "fake":
        fake = InMemoryRunRecordPersister()
        return fake, lambda run_id: fake.records[run_id].model_version
    repo = FakeAnalyticsRepository(clock=_FakeClock())

    def read_back(run_id: str) -> str:
        [row] = [r for r in repo.read(layer="silver", table="dim_run") if r["run_id"] == run_id]
        return str(row["model_version"])

    return PersistRunRecord(repository=repo), read_back


def test_one_record_written_and_rerun_replaces_it(
    run_record_leg: tuple[RunRecordPersister, Callable[[str], str]],
) -> None:
    persister, model_version_of = run_record_leg

    first = persister(_record(model_version="v1"))
    second = persister(_record(model_version="v2"))

    assert (first.rows_written, second.rows_written) == (1, 1)
    assert model_version_of("b" * 64) == "v2"
