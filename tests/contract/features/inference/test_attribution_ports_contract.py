"""Contrato dos ports do consumidor da atribuição do `inference` (Stage 7.3, Task 16; CA9).

Duas pernas por port, tipadas pelo Protocol DO INFERENCE (o mypy prova a conformidade):

- `CheckpointAttributionPredictor`: `InMemoryCheckpointAttributionPredictor` /
  `PredictTftAttributionFromCheckpoints` sobre o cohort sintético da 7.1 com os fakes do
  modeling e uma partição de referência SINTÉTICA (a mesma nas duas pernas, diferente da
  registry real). O fake é configurado com o que o real devolve no mesmo cohort;
- `PermutedPredictionPersister`: `InMemoryPermutedPredictionPersister` /
  `PersistPermutedPredictions` sobre o `FakeAnalyticsRepository`;
- `VsnWeightPersister`: `InMemoryVsnWeightPersister` / `PersistVsnWeights` sobre o
  `FakeAnalyticsRepository`.

O `check_port_coverage.py` é cego a slice: `test_real_repo_attribution_ports_resolve`
(arquitetura) amarra cada `("inference", nome)` a esta suíte.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PermutedDecisionEntry,
    PersistPermutedPredictions,
    PersistPermutedPredictionsCommand,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeights,
    PersistVsnWeightsCommand,
    VsnDecisionEntry,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.application.ports.out.checkpoint_attribution_predictor import (  # noqa: E501
    CheckpointAttributionPredictor,
)
from financial_forecasting.features.inference.application.ports.out.permuted_prediction_persister import (  # noqa: E501
    PermutedPredictionPersister,
)
from financial_forecasting.features.inference.application.ports.out.vsn_weight_persister import (
    VsnWeightPersister,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    PredictTftAttributionCommand,
    PredictTftAttributionFromCheckpoints,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.inference.in_memory_checkpoint_attribution_predictor import (
    InMemoryCheckpointAttributionPredictor,
)
from tests.fakes.features.inference.in_memory_permuted_prediction_persister import (
    InMemoryPermutedPredictionPersister,
)
from tests.fakes.features.inference.in_memory_vsn_weight_persister import (
    InMemoryVsnWeightPersister,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application.test_predict_tft_attribution_from_checkpoints import (
    _REGISTRY,
    _donors,
    _use_case,
)
from tests.unit.features.modeling.application.test_predict_tft_from_checkpoints import (
    _SEED,
    _Setup,
)

pytestmark = pytest.mark.contract

_TIMESTAMPS = tuple(f"2024-03-{day:02d}T00:00:00+00:00" for day in range(4, 14))
_LEVELS = (0.1, 0.5, 0.9)


# -- predictor -----------------------------------------------------------------------


@dataclass(frozen=True)
class _PredictorLeg:
    predictor: CheckpointAttributionPredictor
    setup: _Setup

    def command(self, **overrides: object) -> PredictTftAttributionCommand:
        fields: dict[str, object] = {
            "spec": self.setup.spec,
            "seed": _SEED,
            "allowed": self.setup.allowed,
            "num_threads": 2,
            "donors_by_fold": _donors(self.setup),
            "family_partition": _REGISTRY,
        }
        fields.update(overrides)
        return PredictTftAttributionCommand(**fields)  # type: ignore[arg-type]


@pytest.fixture(params=["fake", "real"])
def predictor_leg(request: pytest.FixtureRequest, tmp_path: Path) -> _PredictorLeg:
    setup = _Setup(tmp_path)
    supplier = _use_case(setup)
    assert isinstance(supplier, PredictTftAttributionFromCheckpoints)
    real: CheckpointAttributionPredictor = supplier
    if request.param == "real":
        return _PredictorLeg(predictor=real, setup=setup)
    recorded = supplier(_PredictorLeg(predictor=real, setup=setup).command())
    fake: CheckpointAttributionPredictor = InMemoryCheckpointAttributionPredictor(
        registry_partition=_REGISTRY, results={_SEED: recorded}
    )
    return _PredictorLeg(predictor=fake, setup=setup)


def test_predictor_identity_and_permuted_keys(predictor_leg: _PredictorLeg) -> None:
    result = predictor_leg.predictor(predictor_leg.command())
    assert [run.run_id for run in result.runs] == [run.run_id for run in predictor_leg.setup.runs]
    for run in result.runs:
        assert set(run.permuted) == {(family, k) for family in _REGISTRY for k in (1, 2)}
        assert set(run.identity) <= set(run.test_decisions)
        assert set(run.encoder_weights) == set(run.test_decisions)


def test_predictor_refuses_non_permutation_donors(predictor_leg: _PredictorLeg) -> None:
    donors = _donors(predictor_leg.setup)
    first = min(donors)
    n = len(donors[first][0])
    donors[first] = ((0,) * n, donors[first][1])
    with pytest.raises(ValueError, match="permutation"):
        predictor_leg.predictor(predictor_leg.command(donors_by_fold=donors))


def test_predictor_refuses_partition_different_from_its_registry(
    predictor_leg: _PredictorLeg,
) -> None:
    moved = {**_REGISTRY, "price": _REGISTRY["price"][:1]}
    with pytest.raises(ApplicationError, match="registry"):
        predictor_leg.predictor(predictor_leg.command(family_partition=moved))


# -- persisters ------------------------------------------------------------------------


def _forecasts() -> dict[int, QuantileForecast]:
    return {
        h: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1, 0.2, 0.3)) for h in (1, 2)
    }


def _permuted_command(entries: list[PermutedDecisionEntry]) -> PersistPermutedPredictionsCommand:
    return PersistPermutedPredictionsCommand(
        run_id="r" * 64,
        model_version="tft_quantile",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=1,
        permutation_seed=130,
        permutation_algorithm="fisher_yates_random_random_v1",
        partition_hash="p" * 64,
        dataset_timestamps=_TIMESTAMPS,
        entries=entries,
    )


def _entries() -> list[PermutedDecisionEntry]:
    last = len(_TIMESTAMPS) - 1
    return [
        PermutedDecisionEntry(family, k, decision, _forecasts())
        for family, k in (("none", 0), ("price", 1), ("sentiment", 2))
        for decision in (2, last - 1)
    ]


@dataclass(frozen=True)
class _PersisterLeg:
    permuted: PermutedPredictionPersister
    vsn: VsnWeightPersister
    permuted_keys: Callable[[], set[tuple[Any, ...]]]
    vsn_keys: Callable[[], set[tuple[Any, ...]]]


@pytest.fixture(params=["fake", "real"])
def persister_leg(request: pytest.FixtureRequest) -> _PersisterLeg:
    if request.param == "fake":
        permuted_fake = InMemoryPermutedPredictionPersister()
        vsn_fake = InMemoryVsnWeightPersister()
        return _PersisterLeg(
            permuted=permuted_fake,
            vsn=vsn_fake,
            permuted_keys=lambda: set(permuted_fake.keys),
            vsn_keys=lambda: set(vsn_fake.keys),
        )
    repo = FakeAnalyticsRepository(clock=FakeClock())

    def read(table: str, columns: tuple[str, ...]) -> set[tuple[Any, ...]]:
        rows = repo.read(layer="silver", table=table, filters={"asset": "AAPL"})
        return {tuple(row[c] for c in columns) for row in rows}

    return _PersisterLeg(
        permuted=PersistPermutedPredictions(repository=repo),
        vsn=PersistVsnWeights(repository=repo),
        permuted_keys=lambda: read(
            "fact_permuted_predictions",
            (
                "run_id",
                "permuted_family",
                "permutation_index",
                "decision_idx",
                "horizon",
                "quantile_level",
            ),
        ),
        vsn_keys=lambda: read("fact_vsn_weights", ("run_id", "decision_idx", "variable", "family")),
    )


def test_persisters_write_one_run_and_read_back(persister_leg: _PersisterLeg) -> None:
    last = len(_TIMESTAMPS) - 1
    result = persister_leg.permuted(_permuted_command(_entries()))
    expected = {
        ("r" * 64, family, k, decision, h, level)
        for family, k in (("none", 0), ("price", 1), ("sentiment", 2))
        for decision in (2, last - 1)
        for h in (1, 2)
        if decision + h <= last
        for level in _LEVELS
    }
    assert persister_leg.permuted_keys() == expected
    assert result.rows_written == len(expected)
    assert result.rows_skipped == 3 * len(_LEVELS)

    families = {"close": "price", "day_of_week": "none"}
    vsn = persister_leg.vsn(
        PersistVsnWeightsCommand(
            run_id="r" * 64,
            model_version="tft_quantile",
            asset="AAPL",
            feature_set_name="fs_all",
            schema_version=1,
            dataset_timestamps=_TIMESTAMPS,
            variable_families=families,
            decisions=[VsnDecisionEntry(d, {"close": 0.7, "day_of_week": 0.3}) for d in (2, 3)],
        )
    )
    assert vsn.rows_written == 4  # noqa: PLR2004
    assert persister_leg.vsn_keys() == {
        ("r" * 64, d, variable, family) for d in (2, 3) for variable, family in families.items()
    }


@pytest.mark.parametrize(("family", "k"), [("none", 1), ("price", 0)])
def test_persisters_refuse_identity_not_none_zero(
    persister_leg: _PersisterLeg, family: str, k: int
) -> None:
    with pytest.raises(ValueError, match=r"permutation_index|identity"):
        persister_leg.permuted(
            _permuted_command([PermutedDecisionEntry(family, k, 2, _forecasts())])
        )
    assert persister_leg.permuted_keys() == set()
