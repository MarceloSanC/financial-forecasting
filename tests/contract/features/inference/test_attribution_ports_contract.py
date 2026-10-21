"""Contrato dos ports do consumidor da atribuição do `inference` (Stage 7.3, Task 16; CA9).

Duas pernas por port, tipadas pelo Protocol DO INFERENCE (o mypy prova a conformidade):

- `CheckpointAttributionPredictor`: `InMemoryCheckpointAttributionPredictor` /
  `PredictTftAttributionFromCheckpoints` sobre o cohort sintético da 7.1 com os fakes do
  modeling e uma partição de referência SINTÉTICA (a mesma nas duas pernas, diferente da
  registry real). O fake é configurado com o que o real devolve no mesmo cohort;
- `PermutedPredictionPersister`: `InMemoryPermutedPredictionPersister` /
  `PersistPermutedPredictions` sobre o `ParquetAnalyticsRepository` em `tmp_path`;
- `VsnWeightPersister`: `InMemoryVsnWeightPersister` / `PersistVsnWeights` sobre o
  mesmo `ParquetAnalyticsRepository` (ida e volta e filtro por `run_id`, C4-4).

O `check_port_coverage.py` é cego a slice: `test_real_repo_attribution_ports_resolve`
(arquitetura) amarra cada `("inference", nome)` a esta suíte.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
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
from financial_forecasting.shared.application.exceptions import (
    ApplicationError,
    DuplicateKeyError,
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


def _permuted_command(
    entries: list[PermutedDecisionEntry], run_id: str = "r" * 64
) -> PersistPermutedPredictionsCommand:
    return PersistPermutedPredictionsCommand(
        run_id=run_id,
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


def _vsn_command(run_id: str = "r" * 64) -> PersistVsnWeightsCommand:
    return PersistVsnWeightsCommand(
        run_id=run_id,
        model_version="tft_quantile",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=1,
        dataset_timestamps=_TIMESTAMPS,
        variable_families={"close": "price", "day_of_week": "none"},
        decisions=[VsnDecisionEntry(d, {"close": 0.7, "day_of_week": 0.3}) for d in (2, 3)],
    )


def _entries() -> list[PermutedDecisionEntry]:
    last = len(_TIMESTAMPS) - 1
    return [
        PermutedDecisionEntry(family, k, decision, _forecasts())
        for family, k in (("none", 0), ("price", 1), ("sentiment", 2))
        for decision in (2, last - 1)
    ]


_PERMUTED_KEY = (
    "run_id",
    "permuted_family",
    "permutation_index",
    "decision_idx",
    "horizon",
    "quantile_level",
)
_VSN_KEY = ("run_id", "decision_idx", "variable", "family")
Keys = Callable[[str | None], set[tuple[Any, ...]]]


@dataclass(frozen=True)
class _PersisterLeg:
    permuted: PermutedPredictionPersister
    vsn: VsnWeightPersister
    permuted_keys_of: Keys
    vsn_keys_of: Keys

    def permuted_keys(self) -> set[tuple[Any, ...]]:
        return self.permuted_keys_of(None)

    def vsn_keys(self) -> set[tuple[Any, ...]]:
        return self.vsn_keys_of(None)


@pytest.fixture(params=["fake", "real"])
def persister_leg(request: pytest.FixtureRequest, tmp_path: Path) -> _PersisterLeg:
    """Perna real: os use cases sobre o `ParquetAnalyticsRepository` em `tmp_path` (C4-4)."""
    if request.param == "fake":
        permuted_fake = InMemoryPermutedPredictionPersister()
        vsn_fake = InMemoryVsnWeightPersister()
        return _PersisterLeg(
            permuted=permuted_fake,
            vsn=vsn_fake,
            permuted_keys_of=lambda run: {k for k in permuted_fake.keys if run in (None, k[0])},
            vsn_keys_of=lambda run: {k for k in vsn_fake.keys if run in (None, k[0])},
        )
    repo = ParquetAnalyticsRepository(data_root=tmp_path, clock=FakeClock())

    def read(table: str, columns: tuple[str, ...], run: str | None) -> set[tuple[Any, ...]]:
        filters: dict[str, object] = {"asset": "AAPL"}
        if run is not None:
            filters["run_id"] = run  # filtro por partição (run_id particiona as duas tabelas)
        rows = repo.read(layer="silver", table=table, filters=filters)
        return {tuple(row[c] for c in columns) for row in rows}

    return _PersisterLeg(
        permuted=PersistPermutedPredictions(repository=repo),
        vsn=PersistVsnWeights(repository=repo),
        permuted_keys_of=lambda run: read("fact_permuted_predictions", _PERMUTED_KEY, run),
        vsn_keys_of=lambda run: read("fact_vsn_weights", _VSN_KEY, run),
    )


def test_permuted_round_trip_filtered_by_run(persister_leg: _PersisterLeg) -> None:
    """C4-4: dois runs gravados; a leitura de um run devolve só as linhas dele."""
    for run in ("a" * 64, "b" * 64):
        persister_leg.permuted(_permuted_command(_entries(), run_id=run))
    only_a = persister_leg.permuted_keys_of("a" * 64)
    assert only_a
    assert {key[0] for key in only_a} == {"a" * 64}
    assert len(persister_leg.permuted_keys()) == 2 * len(only_a)


def test_vsn_round_trip_filtered_by_run(persister_leg: _PersisterLeg) -> None:
    """C4-4: dois runs gravados; a leitura de um run devolve só os pesos dele."""
    for run in ("a" * 64, "b" * 64):
        persister_leg.vsn(_vsn_command(run))
    only_b = persister_leg.vsn_keys_of("b" * 64)
    assert {key[0] for key in only_b} == {"b" * 64}
    assert len(only_b) == 4  # noqa: PLR2004 — 2 decisões x 2 variáveis
    assert len(persister_leg.vsn_keys()) == 2 * len(only_b)


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


# -- recusas do real que o fake reusa (TA-12) ------------------------------------------


def test_vsn_variable_without_family_refused(persister_leg: _PersisterLeg) -> None:
    orphan = dataclasses.replace(_vsn_command(), variable_families={"close": "price"})
    with pytest.raises(ValueError, match="no declared family"):
        persister_leg.vsn(orphan)
    assert persister_leg.vsn_keys() == set()


def test_permuted_family_outside_the_vocabulary_refused(persister_leg: _PersisterLeg) -> None:
    entries = [PermutedDecisionEntry("volatility", 1, 2, _forecasts())]
    with pytest.raises(Exception, match=r"permuted_family|volatility"):
        persister_leg.permuted(_permuted_command(entries))
    assert persister_leg.permuted_keys() == set()


def test_same_run_written_twice_raises_duplicate_key(persister_leg: _PersisterLeg) -> None:
    persister_leg.permuted(_permuted_command(_entries()))
    written = persister_leg.permuted_keys()
    with pytest.raises(DuplicateKeyError):
        persister_leg.permuted(_permuted_command(_entries()))
    assert persister_leg.permuted_keys() == written
