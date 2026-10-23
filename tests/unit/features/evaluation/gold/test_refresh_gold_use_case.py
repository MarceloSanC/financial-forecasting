"""Testes do use case `RefreshGold` com fakes (Stage 6.4 Task 11).

Critérios A1, A3, A4, A6, A7; invariantes I11-I16; casos C1-C7.

Silver e dataset sintéticos saem da fábrica `make_cohort` (`gold/_cohort_factory.py`)
convertida para as linhas do schema silver (`dim_run`, `fact_oos_predictions`) e do
dataset de treino: um prefixo de aquecimento de `_WARMUP` linhas com NaN numa feature
antes das sessões do cohort, então a grade aparada (`build_training_grid`, 5.5) começa
na sessão 0 do cohort — a origem do `decision_idx` do silver (ADR 6.4.0009).
Colaboradores: `FakeSilverTableReader`, `FakeTrainingGridReader` (espiado), `FakeClock`,
`FakeMcsBackend` (espiado), `InMemoryGoldStore` e `FakeGoldBuilder`s no grafo do
concept. O `Hasher` não tem fake por desenho (#70): o teste declara um dublê local
mínimo (`_StubHasher`) só para o `DatasetContentFingerprint`.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldInputs,
    GoldTable,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
    unit_key,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    refresh_gold as refresh_gold_module,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    silver_content_accumulator as accumulator_module,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    GridFingerprintMismatchError,
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.services import (
    dm_profiles,
    profile_reports,
)
from financial_forecasting.features.evaluation.domain.services.conformal_assembly import (
    ConformalAssembly,
    ConformalAssemblyResult,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import SampleKind
from financial_forecasting.features.evaluation.domain.services.joint_contribution import (
    JOINT_BLOCK_NEEDS_BOTH,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    ModelConfidenceSet,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    is_constant,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AssembledCohort,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    MIN_BLOCK_LENGTH_OBS,
    BootstrapIndices,
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    ConformalParameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3Parameters,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformalCommand,
    CalibrateConformalResult,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import NoUsableRowsError
from financial_forecasting.features.modeling.domain.services.training_grid import (
    TrainingGrid,
    build_training_grid,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    SilverContentHash,
)
from tests.fakes.features.evaluation.fake_conformal_calibration import FakeConformalCalibration
from tests.fakes.features.evaluation.fake_gold_builder import FakeGoldBuilder
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.fakes.features.evaluation.fake_silver_table_reader import (
    SILVER_PARTITIONS,
    FakeSilverTableReader,
)
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._preregistration_payload import FloatRefusingHasher
from tests.unit.features.evaluation._profile_parameters import profile_parameters
from tests.unit.features.evaluation.gold._cohort_factory import (
    Cohort,
    at_point,
    drop_records,
    make_cohort,
    replace_records,
    targets_of,
    with_ablation,
    with_calib,
    with_permuted,
    with_vsn,
)

_ASSET = "AAPL"
_SWEEP = "sweep-01"
_PREREG = "prereg-test-0001"  # literal declarado até a 6.5 fornecer o hash congelado
_BLOCK = 2.5
_HORIZONS = (1, 2)
_QUALITY = "quality_checks"
_CONFIRMATORY = ("metrics_by_run", "calibration_table", "dm_results", "mcs_results")
_PARAMETERS = RefreshParameters(
    preregistration_ref=_PREREG,
    degeneracy_tolerance=1e-9,
    band_levels=(0.95, 0.975),
    min_violations=5,
    candidate="tft",
    dm_alpha=0.05,
    dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT),
    mcs_alpha=0.10,
    mcs_reps=1500,  # ≠ MIN_MCS_REPS: o repasse de `reps` é distinguível do piso (A2)
    mcs_seed=20260929,
    mcs_schemes=(BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK),
    monte_carlo_draws=19,  # pequeno: o Monte Carlo roda em todo refresh de teste
    monte_carlo_seed=128,
    mcs_block_sensitivities=("h", "sqrt_T"),
    profile_parameters=None,
    conformal_parameters=None,
    h3_parameters=None,
)
_R1_PARAMETERS = dataclasses.replace(_PARAMETERS, profile_parameters=profile_parameters())
_WARMUP = 3  # linhas de aquecimento com NaN numa feature, aparadas pela grade
_GRID_COLUMNS = ("feat_a", "target_return")
_EXPECTED_STEPS = (
    "read_runs",
    "read_facts",
    "read_realized",
    "assemble",
    "preconditions",
    "checks",
    "reports",
    "mcs",
    "profiles",
    "mcs_blocks",
    "build",
    "publish",
)


class _StubHasher:
    """Dublê mínimo do `Hasher` (sem fake por desenho, #70): sha256 do `repr` ordenado.

    Devolve sha256 hex porque o `DatasetContentFingerprint` recusa outra forma (#160).
    """

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        return sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()

    def hash_text(self, text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()


class _TickClock:
    """Clock UTC que avança um segundo por chamada (só os timestamps mudam no rerun)."""

    def __init__(self) -> None:
        self._now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


# --- silver sintético ----------------------------------------------------------------


def _silver(cohort: Cohort) -> dict[str, list[dict[str, object]]]:
    runs = [
        {
            "run_id": run.run_id,
            "asset": _ASSET,
            "parent_sweep_id": _SWEEP,
            "feature_set_name": run.feature_set_name,
            "config_signature": run.config_signature,
            "fold": run.fold,
            "seed": run.seed,
            "model_version": run.model,
        }
        for run in cohort.runs
    ]
    feature_set = {run.run_id: run.feature_set_name for run in cohort.runs}
    facts = [
        {
            "run_id": record.run_id,
            "model_version": record.model,
            "asset": _ASSET,
            "feature_set_name": feature_set.get(record.run_id, "fs-core"),
            "split": record.split,
            "horizon": record.horizon,
            "decision_idx": record.decision_idx,
            "timestamp_utc": record.decision_timestamp,
            "target_timestamp_utc": record.target_timestamp,
            "quantile_level": record.quantile_level,
            "value_raw": record.value_raw,
            "value_guardrail": record.value_guardrail,
            "guardrail_applied": int(record.guardrail_applied),
            "year": 2024,
        }
        for record in cohort.records
    ]
    return {"dim_run": runs, "fact_oos_predictions": facts}


def _dataset(cohort: Cohort) -> list[dict[str, object]]:
    """Linhas do dataset: aquecimento (NaN em `feat_a`) + as sessões do cohort."""
    realized = cohort.realized
    first = datetime.fromisoformat(realized.timestamps[0])
    warmup: list[dict[str, object]] = [
        {
            "timestamp": first - timedelta(days=_WARMUP - i),
            "feat_a": math.nan,
            "target_return": 0.5,
        }
        for i in range(_WARMUP)
    ]
    return warmup + [
        {
            "timestamp": datetime.fromisoformat(ts),
            "feat_a": 1.0 + index / 100,
            "target_return": value,
        }
        for index, (ts, value) in enumerate(zip(realized.timestamps, realized.returns, strict=True))
    ]


def _grid(cohort: Cohort) -> TrainingGrid:
    return build_training_grid(_dataset(cohort), columns=_GRID_COLUMNS)


def _fingerprint(cohort: Cohort) -> str:
    """O fingerprint congelado do cohort: o da sua grade, pela função do dono (#128)."""
    return grid_fingerprint(_grid(cohort), hasher=_StubHasher(), asset_id=_ASSET)


class _Log:
    def __init__(self) -> None:
        self.events: list[str] = []


class _SpyReader(FakeSilverTableReader):
    def __init__(
        self,
        rows: Mapping[str, Sequence[Mapping[str, object]]],
        log: _Log,
        partition_keys: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        if partition_keys is None:
            super().__init__(rows)
        else:
            super().__init__(rows, partition_keys)
        self._log = log

    def read(self, **kwargs: object) -> Sequence[Mapping[str, object]]:  # type: ignore[override]
        self._log.events.append(f"read:{kwargs['table']}")
        return super().read(**kwargs)  # type: ignore[arg-type]


class _SpyGrid(FakeTrainingGridReader):
    def __init__(self, rows: Sequence[Mapping[str, object]] | None, log: _Log) -> None:
        super().__init__(
            {} if rows is None else {_ASSET: rows}, columns=_GRID_COLUMNS, hasher=_StubHasher()
        )
        self._log = log

    def __call__(self, *, asset_id: str) -> tuple[TrainingGrid, DatasetContentFingerprint]:
        self._log.events.append("read:grid")
        return super().__call__(asset_id=asset_id)


class _SpyBackend(FakeMcsBackend):
    def __init__(
        self,
        log: _Log,
        *,
        fail: BaseException | None = None,
        estimates: Sequence[float] | None = None,
    ) -> None:
        super().__init__(block_length=_BLOCK)
        self._log = log
        self._fail = fail
        self._estimates = estimates
        self.block_series: list[tuple[float, ...]] = []
        self.index_calls: list[dict[str, object]] = []

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        self._log.events.append("backend:block")
        if is_constant(series) or len(series) < MIN_BLOCK_LENGTH_OBS:
            raise AssertionError("the backend received an invalid series")
        self.block_series.append(tuple(series))
        if self._fail is not None:
            raise self._fail
        if self._estimates is not None:  # uma estimativa por par, em ciclo
            return self._estimates[(len(self.block_series) - 1) % len(self._estimates)]
        return super().optimal_block_length(series=series)

    def bootstrap_indices(self, **kwargs: object) -> BootstrapIndices:  # type: ignore[override]
        self._log.events.append("backend:indices")
        self.index_calls.append(dict(kwargs))
        return super().bootstrap_indices(**kwargs)  # type: ignore[arg-type]


class _SpyStoreGold(InMemoryGoldStore):
    def __init__(self, log: _Log) -> None:
        super().__init__()
        self._log = log

    def publish(self, **kwargs: object) -> None:  # type: ignore[override]
        self._log.events.append("publish")
        super().publish(**kwargs)  # type: ignore[arg-type]


class _SpyBuilder(FakeGoldBuilder):
    def __init__(self, name: str, log: _Log, **kwargs: object) -> None:
        super().__init__(name, **kwargs)  # type: ignore[arg-type]
        self._log = log

    def build(self, inputs: GoldInputs) -> GoldTable:
        self._log.events.append(f"build:{self.name}")
        return super().build(inputs)


def _builders(log: _Log) -> list[FakeGoldBuilder]:
    quality = _SpyBuilder(_QUALITY, log, runs_when_blocked=True)
    others = [_SpyBuilder(name, log, depends_on=frozenset({_QUALITY})) for name in _CONFIRMATORY]
    return [*reversed(others), quality]  # registro fora de ordem: a ordem é do grafo


@dataclasses.dataclass
class _Harness:
    use_case: RefreshGold
    reader: _SpyReader
    grid: _SpyGrid
    backend: _SpyBackend
    gold: _SpyStoreGold
    log: _Log
    fingerprint: str
    conformal: FakeConformalCalibration

    def __call__(self, **changes: object) -> RefreshGoldResult:
        return self.use_case(_command(**{"dataset_fingerprint": self.fingerprint, **changes}))


def _command(**changes: object) -> RefreshGoldCommand:
    kwargs: dict[str, object] = {
        "asset": _ASSET,
        "parent_sweep_id": _SWEEP,
        "horizons": _HORIZONS,
        "window_deficits": {},
        "parameters": _PARAMETERS,
        "dataset_fingerprint": "0" * 64,
    }
    kwargs.update(changes)
    return RefreshGoldCommand(**kwargs)  # type: ignore[arg-type]


def _harness(  # noqa: PLR0913 — um parâmetro por colaborador trocável (keyword-only)
    cohort: Cohort | None = None,
    *,
    silver: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    seed_dataset: bool = True,
    fail: BaseException | None = None,
    clock: object | None = None,
    builders: Callable[[_Log], Sequence[FakeGoldBuilder]] = _builders,
    dataset: Sequence[Mapping[str, object]] | None = None,
    partition_keys: Mapping[str, tuple[str, ...]] | None = None,
    estimates: Sequence[float] | None = None,
    conformal: FakeConformalCalibration | None = None,
) -> _Harness:
    cohort = make_cohort() if cohort is None else cohort
    log = _Log()
    reader = _SpyReader(_silver(cohort) if silver is None else silver, log, partition_keys)
    rows = (_dataset(cohort) if dataset is None else dataset) if seed_dataset else None
    grid = _SpyGrid(rows, log)
    backend = _SpyBackend(log, fail=fail, estimates=estimates)
    gold = _SpyStoreGold(log)
    port = FakeConformalCalibration() if conformal is None else conformal
    use_case = RefreshGold(
        silver_reader=reader,
        grid_reader=grid,
        clock=FakeClock() if clock is None else clock,  # type: ignore[arg-type]
        mcs_backend=backend,
        gold_store=gold,
        builders=builders(log),
        conformal_calibration=port,
        hasher=FloatRefusingHasher(),
    )
    return _Harness(use_case, reader, grid, backend, gold, log, _fingerprint(cohort), port)


def _gap_cohort() -> Cohort:
    cohort = make_cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    return drop_records(cohort, at_point("tft", 1, 1, gap))


def _published(harness: _Harness) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    current = harness.gold.current(_command().partition)
    assert current is not None
    return current


# --- ordem e guardas (C1, C3, C4) ------------------------------------------------------


@pytest.mark.unit
def test_graph_checked_before_read() -> None:
    """Grafo inválido ergue no construtor, antes de qualquer leitura (C1, I15)."""

    def cyclic(log: _Log) -> list[FakeGoldBuilder]:
        return [
            _SpyBuilder("a", log, depends_on=frozenset({"b"})),
            _SpyBuilder("b", log, depends_on=frozenset({"a"})),
        ]

    log = _Log()
    reader = _SpyReader(_silver(make_cohort()), log)
    with pytest.raises(ValueError, match="builder dependency cycle"):
        RefreshGold(
            silver_reader=reader,
            grid_reader=_SpyGrid(None, log),
            clock=FakeClock(),
            mcs_backend=_SpyBackend(log),
            gold_store=_SpyStoreGold(log),
            builders=cyclic(log),
            conformal_calibration=FakeConformalCalibration(),
            hasher=FloatRefusingHasher(),
        )
    assert log.events == []
    assert _harness().use_case.build_order[0] == _QUALITY


@pytest.mark.unit
def test_identifier_before_path() -> None:
    harness = _harness()
    with pytest.raises(ValueError, match=r"^asset must match"):
        harness(asset="a/b")
    assert harness.log.events == []


@pytest.mark.unit
def test_cohort_empty_raises() -> None:
    harness = _harness(silver={"dim_run": [], "fact_oos_predictions": []})
    with pytest.raises(ValueError, match="has no dim_run rows"):
        harness()
    assert harness.gold.publishes == 0
    assert harness.log.events == ["read:dim_run"]


@pytest.mark.unit
def test_dataset_empty_raises() -> None:
    """Dataset sem linha do ativo: `NoUsableRowsError` do dono da grade propaga (C4)."""
    harness = _harness(seed_dataset=False)
    with pytest.raises(NoUsableRowsError):
        harness()
    assert harness.gold.publishes == 0


# --- leitura (D3, I3, I6, I7) ----------------------------------------------------------


@pytest.mark.unit
def test_foreign_run_rows_dropped() -> None:
    """Fatos de run fora do cohort (mesma partição) são descartados na leitura."""
    cohort = make_cohort()
    silver = _silver(cohort)
    foreign = [
        {**row, "run_id": "foreign-run", "value_raw": 9.0, "value_guardrail": 9.0}
        for row in silver["fact_oos_predictions"][:40]
    ]
    other_cohort_run = {**silver["dim_run"][0], "run_id": "other", "parent_sweep_id": "sweep-99"}
    polluted = {
        "dim_run": [*silver["dim_run"], other_cohort_run],
        "fact_oos_predictions": [*silver["fact_oos_predictions"], *foreign],
    }
    baseline, harness = _harness(cohort), _harness(cohort, silver=polluted)
    assert harness() == baseline()
    assert _published(harness) == _published(baseline)


@pytest.mark.unit
def test_guardrail_int_to_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    """`guardrail_applied` int 0/1 → `bool` (I6); outro valor ergue."""
    cohort = make_cohort()
    special = cohort.special
    assert special is not None
    flagged = replace_records(
        cohort,
        at_point(special.model, special.seed, special.horizon, special.target_timestamp),
        lambda r: dataclasses.replace(r, guardrail_applied=True),
    )
    seen: list[object] = []
    real = refresh_gold_module.SeriesAssembly.assemble

    def _spy(records: Sequence[ForecastRecord], *args: object, **kwargs: object) -> AssembledCohort:
        seen.extend(record.guardrail_applied for record in records)
        return real(records, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(refresh_gold_module.SeriesAssembly, "assemble", staticmethod(_spy))
    assert _harness(flagged)().status is RefreshStatus.COMPLETED
    assert {type(flag) for flag in seen} == {bool}
    assert seen.count(True) == len(special.raw)
    silver = _silver(cohort)
    silver["fact_oos_predictions"][0]["guardrail_applied"] = 2
    with pytest.raises(ValueError, match="guardrail_applied must be the int 0 or 1"):
        _harness(cohort, silver=silver)()


@pytest.mark.unit
def test_realized_read_once() -> None:
    harness = _harness()
    harness()
    assert harness.grid.calls == [_ASSET]
    assert harness.log.events.count("read:grid") == 1


# --- pré-condições e MCS (I11, I12, C6, C7) ---------------------------------------------


@pytest.mark.unit
def test_mcs_block_from_rule() -> None:
    """Bloco passado ao backend = `ModelConfidenceSet.block_length` das estimativas."""
    harness = _harness()
    assert harness().status is RefreshStatus.COMPLETED
    blocks = {(call["n_obs"], call["block_size"]) for call in harness.backend.index_calls}
    assert {block for _, block in blocks} == {max(1, 3), max(2, 3)} == {3}


@pytest.mark.unit
def test_mcs_reps_seed_schemes() -> None:
    harness = _harness()
    harness()
    calls = harness.backend.index_calls
    assert len(calls) == len(_HORIZONS) * len(_PARAMETERS.mcs_schemes)
    assert all(
        c["reps"] == _PARAMETERS.mcs_reps and c["seed"] == _PARAMETERS.mcs_seed for c in calls
    )
    assert [c["scheme"] for c in calls] == list(_PARAMETERS.mcs_schemes) * len(_HORIZONS)


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [ZeroDivisionError, OverflowError, FloatingPointError],
    ids=lambda error: error.__name__,
)
def test_arithmetic_error_fails_precondition(error: type[ArithmeticError]) -> None:
    """Toda subclasse de `ArithmeticError` do backend vira FAIL `backend_arithmetic` (A1)."""
    harness = _harness(fail=error("numerically undefined"))
    result = harness()
    assert result.status is RefreshStatus.BLOCKED
    kinds = {(f.check, f.kind) for f in result.failed_checks}
    assert kinds == {("statistical_preconditions", "backend_arithmetic")}
    assert harness.backend.index_calls == []


@pytest.mark.unit
def test_other_backend_error_propagates() -> None:
    harness = _harness(fail=RuntimeError("backend bug"))
    with pytest.raises(RuntimeError, match="backend bug"):
        harness()
    assert harness.gold.publishes == 0


@pytest.mark.unit
def test_factory_never_short(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cohort de um modelo: a fábrica nunca recebe k < 2; BLOCKED `insufficient_models`."""
    real = refresh_gold_module.paired_pinball_losses

    def _guarded(series_by_model: Mapping[str, Sequence[CoverageSeries]]) -> PairedLossSeries:
        if len(series_by_model) < 2:  # noqa: PLR2004 — MIN_MODELS
            raise AssertionError("factory called with k < 2")
        return real(series_by_model)

    monkeypatch.setattr(refresh_gold_module, "paired_pinball_losses", _guarded)
    result = _harness(make_cohort(seeds={"tft": (1, 2)}))()
    assert result.status is RefreshStatus.BLOCKED
    assert {(f.check, f.kind) for f in result.failed_checks} == {
        ("statistical_preconditions", "insufficient_models")
    }


def _twin_cohort() -> Cohort:
    """`gbx` com as MESMAS perdas do `gbm`: diferencial gbm - gbx constante (zero)."""
    cohort = make_cohort(seeds={"gbm": (None,), "gbx": (None,), "tft": (1,)})
    gbm = {
        (r.horizon, r.target_timestamp, r.quantile_level): r
        for r in cohort.records
        if r.model == "gbm"
    }

    def _copy(record: ForecastRecord) -> ForecastRecord:
        twin = gbm[record.horizon, record.target_timestamp, record.quantile_level]
        return dataclasses.replace(
            record,
            value_raw=twin.value_raw,
            value_guardrail=twin.value_guardrail,
            guardrail_applied=twin.guardrail_applied,
        )

    return replace_records(cohort, lambda r: r.model == "gbx", _copy)


@pytest.mark.unit
def test_backend_never_invalid() -> None:
    """Par constante nunca chega ao backend (o espião ergue se chegar); BLOCKED com a causa."""
    harness = _harness(_twin_cohort())
    result = harness()
    assert result.status is RefreshStatus.BLOCKED
    assert FailedCheck in {type(f) for f in result.failed_checks}
    assert {(f.check, f.kind) for f in result.failed_checks} == {
        ("statistical_preconditions", "constant_differential")
    }
    assert harness.backend.block_series  # os outros pares foram ao backend
    assert all(not is_constant(series) for series in harness.backend.block_series)


@pytest.mark.unit
def test_seeds_averaged_by_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fábrica recebe, por modelo, as S séries `common` (tft com 2 seeds → 2)."""
    received: list[dict[str, int]] = []
    real = refresh_gold_module.paired_pinball_losses

    def _spy(series_by_model: Mapping[str, Sequence[CoverageSeries]]) -> PairedLossSeries:
        received.append({model: len(series) for model, series in series_by_model.items()})
        return real(series_by_model)

    monkeypatch.setattr(refresh_gold_module, "paired_pinball_losses", _spy)
    _harness()()
    assert received == [{"gbm": 1, "tft": 2}] * len(_HORIZONS)


# --- publicação (C5, I14, I15, I16, I17) -----------------------------------------------


@pytest.mark.unit
def test_blocked_publishes_checks_only() -> None:
    harness = _harness(_gap_cohort())
    result = harness()
    manifest, tables = _published(harness)
    assert result.status is RefreshStatus.BLOCKED
    assert list(tables) == [f"gold_{_QUALITY}"]
    assert manifest["status"] == "BLOCKED"
    assert manifest["rows_by_table"] == {f"gold_{_QUALITY}": len(tables[f"gold_{_QUALITY}"])}
    assert harness.backend.index_calls == []


@pytest.mark.unit
def test_blocked_result_failed_checks() -> None:
    result = _harness(_gap_cohort())()
    assert (
        FailedCheck(
            check="alignment_check",
            kind="interior_gap",
            horizon=1,
            model="tft",
            seed=1,
            occurrences=1,
            detail=result.failed_checks[0].detail,
        )
        in result.failed_checks
    )
    assert all(f.check == "alignment_check" for f in result.failed_checks)


@pytest.mark.unit
def test_exception_before_publish() -> None:
    class _Broken(FakeGoldBuilder):
        def build(self, inputs: GoldInputs) -> GoldTable:
            raise KeyError("mapping bug")

    def broken(log: _Log) -> list[FakeGoldBuilder]:
        return [*_builders(log)[:-1], _Broken(_QUALITY, runs_when_blocked=True)]

    harness = _harness(builders=broken)
    with pytest.raises(KeyError, match="mapping bug"):
        harness()
    assert harness.gold.publishes == 0
    assert harness.gold.current(_command().partition) is None


@pytest.mark.unit
def test_effects_order() -> None:
    """Leituras → backend → builders (na ordem do grafo) → publish, por um registro comum."""
    harness = _harness()
    harness()
    events = harness.log.events
    kinds = [event.split(":")[0] for event in events]
    first = {kind: kinds.index(kind) for kind in ("backend", "build", "publish")}
    last_read = max(i for i, kind in enumerate(kinds) if kind == "read")
    last_backend = max(i for i, kind in enumerate(kinds) if kind == "backend")
    last_build = max(i for i, kind in enumerate(kinds) if kind == "build")
    assert last_read < first["backend"] < last_backend < first["build"]
    assert last_build < first["publish"] == len(events) - 1
    assert events[first["build"]] == f"build:{_QUALITY}"
    assert events[:3] == ["read:dim_run", "read:fact_oos_predictions", "read:grid"]


@pytest.mark.unit
def test_step_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=refresh_gold_module.__name__):
        _harness()()
    lines = [r.getMessage() for r in caplog.records if r.name == refresh_gold_module.__name__]
    steps = [line for line in lines if " step=" in line]
    assert [line.split("step=")[1].split()[0] for line in steps] == list(_EXPECTED_STEPS)
    assert all(" duration_s=" in line and " in=" in line and " out=" in line for line in steps)
    assert lines[-1].startswith("refresh_gold status=COMPLETED")


@pytest.mark.unit
def test_manifest_carries_parameters() -> None:
    cohort = make_cohort(prefixes={"tft": 1})
    harness = _harness(cohort)
    result = harness(window_deficits={"tft": 1})
    manifest, _ = _published(harness)
    realized = cohort.realized
    assert result.status is RefreshStatus.COMPLETED
    assert manifest["status"] == "COMPLETED"
    assert manifest["parameters"]["preregistration_ref"] == _PREREG  # type: ignore[index]
    assert manifest["parameters"]["mcs_reps"] == _PARAMETERS.mcs_reps  # type: ignore[index]
    assert manifest["preregistration_ref"] == _PREREG
    assert manifest["horizons"] == list(_HORIZONS)
    assert manifest["window_deficits"] == {"tft": 1}
    assert manifest["dataset_fingerprint"] == _fingerprint(cohort)
    assert manifest["realized"] == {
        "n_sessions": realized.n_sessions,
        "returns_fsum": realized.returns_fsum,
        "first_timestamp": realized.first_timestamp,
        "last_timestamp": realized.last_timestamp,
    }
    assert manifest["n_runs"] == len(cohort.runs)
    assert manifest["build_order"] == [_QUALITY, *sorted(_CONFIRMATORY)]


@pytest.mark.unit
def test_rerun_identical() -> None:
    """Mesmas entradas → mesmas tabelas; no manifesto só os timestamps mudam (I16)."""
    harness = _harness(clock=_TickClock())
    first_result = harness()
    first_manifest, first_tables = _published(harness)
    second_result = harness()
    second_manifest, second_tables = _published(harness)
    assert first_result == second_result
    assert second_tables == first_tables
    changed = {k for k in first_manifest if first_manifest[k] != second_manifest[k]}
    assert changed == {"started_at", "finished_at"}


@pytest.mark.unit
def test_completed_publishes_all_tables() -> None:
    harness = _harness()
    result = harness()
    manifest, tables = _published(harness)
    names = [f"gold_{name}" for name in (_QUALITY, *sorted(_CONFIRMATORY))]
    assert result.status is RefreshStatus.COMPLETED
    assert result.failed_checks == ()
    assert list(tables) == names
    assert (
        dict(result.rows_by_table)
        == manifest["rows_by_table"]
        == {name: len(rows) for name, rows in tables.items()}
    )
    assert all(row["preregistration_ref"] == _PREREG for name in names[1:] for row in tables[name])


# --- grade de treino (ADR 6.4.0009; C10, I5, I7, I16) --------------------------------


@pytest.mark.unit
def test_fingerprint_mismatch_publishes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grade de outro dado → `GridFingerprintMismatchError` sem montar nem publicar (C10)."""
    assembled: list[object] = []
    real = refresh_gold_module.SeriesAssembly.assemble

    def _spy(*args: object, **kwargs: object) -> AssembledCohort:
        assembled.append(args)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(refresh_gold_module.SeriesAssembly, "assemble", staticmethod(_spy))
    harness = _harness()
    with pytest.raises(GridFingerprintMismatchError, match="C10"):
        harness(dataset_fingerprint="f" * 64)
    assert assembled == []
    assert harness.gold.publishes == 0
    assert "publish" not in harness.log.events


@pytest.mark.unit
def test_realized_from_training_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Realizado = a grade aparada (índice 0 = primeira sessão pós-aquecimento)."""
    cohort = make_cohort()
    seen: list[RealizedReturns] = []
    real = refresh_gold_module.SeriesAssembly.assemble

    def _spy(
        records: Sequence[ForecastRecord], runs: object, realized: RealizedReturns, **kwargs: object
    ) -> AssembledCohort:
        seen.append(realized)
        return real(records, runs, realized, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(refresh_gold_module.SeriesAssembly, "assemble", staticmethod(_spy))
    result = _harness(cohort)()
    grid = _grid(cohort)
    [realized] = seen
    assert result.status is RefreshStatus.COMPLETED
    assert realized.timestamps == grid.timestamps_iso() == cohort.realized.timestamps
    assert realized.returns == grid.column("target_return")
    assert realized.index_of(cohort.realized.timestamps[0]) == 0
    assert grid.trimmed_prefix == _WARMUP


@pytest.mark.unit
def test_manifest_grid_trimmed_prefix() -> None:
    cohort = make_cohort()
    harness = _harness(cohort)
    harness()
    manifest, tables = _published(harness)
    assert manifest["grid_trimmed_prefix"] == _WARMUP
    assert manifest["dataset_fingerprint"] == _fingerprint(cohort)
    assert tables  # geração publicada


@pytest.mark.unit
def test_block_size_from_distinct_estimates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Estimativas distintas por par (2,2 e 4,7): bloco = `block_length` da regra (L1)."""
    captured: list[PairedLossSeries] = []
    real = refresh_gold_module.paired_pinball_losses

    def _spy(series_by_model: Mapping[str, Sequence[CoverageSeries]]) -> PairedLossSeries:
        series = real(series_by_model)
        captured.append(series)
        return series

    monkeypatch.setattr(refresh_gold_module, "paired_pinball_losses", _spy)
    estimates = (2.2, 4.7)
    cohort = make_cohort(seeds={"gbm": (None,), "naive": (None,), "tft": (1, 2)})
    harness = _harness(cohort, estimates=estimates)
    assert harness().status is RefreshStatus.COMPLETED
    expected: list[int] = []
    served = 0  # o backend serve as estimativas em ciclo, na ordem das chamadas
    for series in captured:
        by_pair: dict[tuple[str, str], float] = {}
        for pair in series.model_pairs():
            by_pair[pair] = estimates[served % len(estimates)]
            served += 1
        block = ModelConfidenceSet.block_length(series, block_estimates=by_pair)
        expected += [block] * len(_PARAMETERS.mcs_schemes)
    assert [call["block_size"] for call in harness.backend.index_calls] == expected
    assert set(expected) == {math.ceil(max(estimates))}


@pytest.mark.unit
def test_blocked_logs_skip_reports_and_mcs(caplog: pytest.LogCaptureFixture) -> None:
    """Refresh BLOCKED: sem `step=reports`/`step=mcs`, linha final `status=BLOCKED` (L2)."""
    with caplog.at_level(logging.INFO, logger=refresh_gold_module.__name__):
        _harness(_gap_cohort())()
    lines = [r.getMessage() for r in caplog.records if r.name == refresh_gold_module.__name__]
    steps = [line.split("step=")[1].split()[0] for line in lines if " step=" in line]
    assert "reports" not in steps
    assert "mcs" not in steps
    skipped = ("reports", "mcs", "profiles", "mcs_blocks")
    assert steps == [s for s in _EXPECTED_STEPS if s not in skipped]
    assert lines[-1].startswith("refresh_gold status=BLOCKED")


@pytest.mark.unit
def test_post_filter_drops_superset_rows() -> None:
    """Leitor que devolve superconjunto: os pós-filtros do use case descartam (A3)."""
    cohort = make_cohort()
    silver = _silver(cohort)
    alien_run = {**silver["dim_run"][0], "run_id": "alien", "parent_sweep_id": "sweep-99"}
    other_asset = [
        {**row, "asset": "MSFT", "value_raw": 7.0, "value_guardrail": 7.0}
        for row in silver["fact_oos_predictions"][:14]
    ]
    wide = {
        "dim_run": [*silver["dim_run"], alien_run],
        "fact_oos_predictions": [*silver["fact_oos_predictions"], *other_asset],
    }
    keys = {"dim_run": ("asset",), "fact_oos_predictions": ("feature_set_name",)}
    baseline, harness = _harness(cohort), _harness(cohort, silver=wide, partition_keys=keys)
    assert harness() == baseline()
    assert _published(harness) == _published(baseline)
    assert len(harness.reader.read(layer="silver", table="dim_run", filters={"asset": _ASSET})) == (
        len(cohort.runs) + 1
    )


@pytest.mark.unit
def test_candidate_absent_blocks() -> None:
    """Cohort sem o candidato: BLOCKED com `required_model_missing` (A4)."""
    result = _harness(make_cohort(seeds={"gbm": (None,), "naive": (None,)}))()
    assert result.status is RefreshStatus.BLOCKED
    assert ("alignment_check", "required_model_missing", "tft") in {
        (f.check, f.kind, f.model) for f in result.failed_checks
    }


@pytest.mark.unit
def test_shuffled_dataset_rows_same_result() -> None:
    """Linhas do dataset embaralhadas no leitor: mesmas tabelas e manifesto (A5, I16)."""
    cohort = make_cohort()
    rows = _dataset(cohort)
    shuffled = rows[1::2] + rows[::2]
    assert shuffled != rows
    baseline, harness = _harness(cohort), _harness(cohort, dataset=shuffled)
    assert harness() == baseline()
    assert _published(harness) == _published(baseline)


# --- Stage 6.6 Task 13: perfis de séries novas e MCS por bloco ---------------------------


class _BlockFailingBackend(_SpyBackend):
    """Spy que ergue para um `block_size` escolhido (só nas rodadas por bloco)."""

    def __init__(
        self, log: _Log, *, failing_block: int, error: type[Exception] = ArithmeticError
    ) -> None:
        super().__init__(log)
        self._failing_block = failing_block
        self._error = error

    def bootstrap_indices(self, **kwargs: object) -> BootstrapIndices:  # type: ignore[override]
        if kwargs["block_size"] == self._failing_block:
            self.index_calls.append(dict(kwargs))
            raise self._error("injected block failure")
        return super().bootstrap_indices(**kwargs)


def _inputs_of(harness: _Harness, **changes: object) -> GoldInputs:
    captured: list[GoldInputs] = []
    real = harness.use_case._builders[0].build

    def spy(inputs: GoldInputs) -> GoldTable:
        captured.append(inputs)
        return real(inputs)

    harness.use_case._builders[0].build = spy  # type: ignore[method-assign]
    harness(**changes)
    return captured[0]


@pytest.mark.unit
def test_block_sensitivities_reach_the_backend_on_the_primary_scheme() -> None:
    harness = _harness()
    inputs = _inputs_of(harness, parameters=_R1_PARAMETERS)
    runs = inputs.mcs_block_reports
    assert [(r.horizon, r.block_rule) for r in runs] == [
        (h, rule) for h in _HORIZONS for rule in ("h", "sqrt_T")
    ]
    for run in runs:
        n_points = next(p.n_common for p in inputs.horizon_reports if p.horizon == run.horizon)
        expected = run.horizon if run.block_rule == "h" else math.isqrt(n_points - 1) + 1
        assert run.block_size == expected
        assert run.scheme is _PARAMETERS.mcs_schemes[0]
        assert run.report is not None
        assert run.report.block_size == expected
    sizes = [c["block_size"] for c in harness.backend.index_calls]
    assert sizes[len(_HORIZONS) * len(_PARAMETERS.mcs_schemes) :] == [r.block_size for r in runs]


@pytest.mark.unit
def test_block_runs_use_the_plan_reps_seed_and_alpha() -> None:
    """I8 no MCS por bloco: reps, seed e alpha são os do plano (Auditoria de Testes, M18/M29)."""
    harness = _harness()
    inputs = _inputs_of(harness, parameters=_R1_PARAMETERS)
    block_calls = harness.backend.index_calls[len(_HORIZONS) * len(_PARAMETERS.mcs_schemes) :]
    assert len(block_calls) == len(inputs.mcs_block_reports)
    for call in block_calls:
        assert (call["reps"], call["seed"]) == (_PARAMETERS.mcs_reps, _PARAMETERS.mcs_seed)
    for run in inputs.mcs_block_reports:
        assert run.report is not None
        assert run.report.alpha == _PARAMETERS.mcs_alpha
        assert (run.report.reps, run.report.seed) == (_PARAMETERS.mcs_reps, _PARAMETERS.mcs_seed)


@pytest.mark.unit
def test_backend_failure_on_one_block_rule_is_isolated() -> None:
    cohort = make_cohort()
    n_common = _inputs_of(_harness(cohort), parameters=_R1_PARAMETERS).horizon_reports[0].n_common
    failing = math.isqrt(n_common - 1) + 1  # o l = ceil(sqrt(T)) do primeiro horizonte
    inputs = _inputs_of(_with_backend(cohort, failing), parameters=_R1_PARAMETERS)
    errors = [r for r in inputs.mcs_block_reports if r.report is None]
    assert errors and all(r.block_size == failing and "injected" in r.detail for r in errors)
    assert all(r.report is not None for r in inputs.mcs_block_reports if r.block_size != failing)
    assert len(inputs.mcs_reports) == len(_HORIZONS) * len(_PARAMETERS.mcs_schemes)
    result = _with_backend(cohort, failing)(parameters=_R1_PARAMETERS)
    assert result.status is RefreshStatus.COMPLETED
    assert result.profile_error_units == len(errors)


def _with_backend(cohort: Cohort, failing: int) -> _Harness:
    harness = _harness(cohort)
    harness.use_case._mcs_backend = _BlockFailingBackend(_Log(), failing_block=failing)
    return harness


@pytest.mark.unit
def test_r0_has_no_block_runs_and_only_mc_and_differentials() -> None:
    inputs = _inputs_of(_harness())
    assert inputs.mcs_block_reports == ()
    assert len(inputs.profile_reports) == len(_HORIZONS)
    for report in inputs.profile_reports:
        assert report.differentials
        assert (report.dm_profiles, report.stationarity, report.partial_degeneracy) == (
            None,
            None,
            None,
        )
    assert inputs.profile_reports[0].monte_carlo


@pytest.mark.unit
def test_blocked_refresh_has_no_profiles() -> None:
    harness = _harness(_gap_cohort())
    result = harness(parameters=_R1_PARAMETERS)
    assert result.status is RefreshStatus.BLOCKED
    assert result.profile_error_units == 0
    assert result.conformal_error_units == 0  # Stage 7.2 Task 17: o port entra na Task 19
    assert harness.backend.index_calls == []


def _verdict_inputs(inputs: GoldInputs) -> tuple[object, ...]:
    return (
        inputs.check_results,
        inputs.horizon_reports,
        inputs.mcs_reports,
        inputs.block_estimates,
    )


@pytest.mark.unit
@pytest.mark.parametrize("target", ["monte_carlo", "stationarity", "adjacent", "dm", "mcs_block"])
def test_profile_failure_leaves_the_verdict_inputs_identical(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """CA11, lado da escrita: uma falha injetada em cada tipo de unidade de perfil não muda
    os relatórios do veredito e é contada em `profile_error_units`."""
    cohort = make_cohort()
    baseline = _inputs_of(_harness(cohort), parameters=_R1_PARAMETERS)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise ValueError("injected")

    if target == "monte_carlo":
        monkeypatch.setattr(
            profile_reports.ChristoffersenTest, "monte_carlo_p_values", staticmethod(boom)
        )
    elif target == "stationarity":
        monkeypatch.setattr(
            profile_reports.DifferentialStationarity, "evaluate", staticmethod(boom)
        )
    elif target == "adjacent":
        monkeypatch.setattr(profile_reports, "adjacent_collapse_rates", boom)
    elif target == "dm":
        monkeypatch.setattr(dm_profiles, "DieboldMariano", _FailingDm)

    def make() -> _Harness:
        # MCS por bloco: falha só no l = h = 1 (o MCS primário usa l >= 3 com o fake)
        return _with_backend(cohort, 1) if target == "mcs_block" else _harness(cohort)

    inputs = _inputs_of(make(), parameters=_R1_PARAMETERS)
    assert _verdict_inputs(inputs) == _verdict_inputs(baseline)
    expected = _affected_units(target, baseline)
    # > 1 nas unidades de perfil: a contagem por horizonte (e não por unidade) seria pega
    assert expected == 1 if target == "mcs_block" else expected > 1
    assert make()(parameters=_R1_PARAMETERS).profile_error_units == expected


def _affected_units(target: str, baseline: GoldInputs) -> int:
    """Unidades que a falha injetada atinge, contadas a partir da execução sem falha."""
    profiles = baseline.profile_reports
    if target == "monte_carlo":
        return sum(len(p.monte_carlo) for p in profiles)
    if target == "stationarity":  # um par por d_t
        return sum(len(p.differentials) for p in profiles)
    if target == "adjacent":  # uma linha de erro por série (modelo, seed, amostra)
        return sum(len(report.series) for report in baseline.horizon_reports)
    if target == "dm":  # recortes com série: os que chegam à chamada do DM
        return sum(
            1
            for p in profiles
            if p.dm_profiles is not None
            for row in p.dm_profiles.rows
            if row.n_points is not None
        )
    return sum(1 for run in baseline.mcs_block_reports if run.block_size == 1)


@pytest.mark.unit
@pytest.mark.parametrize("target", ["adjacent", "mcs_block"])
def test_programming_errors_in_profiles_propagate(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """I4: só `ValueError`/`ArithmeticError` vira unidade `error`; outro erro é bug e sobe."""
    cohort = make_cohort()
    harness = _harness(cohort)
    if target == "adjacent":

        def boom(*_args: object, **_kwargs: object) -> object:
            raise TypeError("injected bug")

        monkeypatch.setattr(profile_reports, "adjacent_collapse_rates", boom)
    else:
        harness.use_case._mcs_backend = _BlockFailingBackend(
            _Log(), failing_block=1, error=TypeError
        )
    with pytest.raises(TypeError, match="injected"):
        harness(parameters=_R1_PARAMETERS)


@pytest.mark.unit
def test_final_log_line_reports_profile_error_units(caplog: pytest.LogCaptureFixture) -> None:
    """I4: a contagem de unidades de perfil com erro fica visível ao operador."""
    harness = _with_backend(make_cohort(), 1)
    with caplog.at_level(logging.INFO):
        result = harness(parameters=_R1_PARAMETERS)
    assert result.profile_error_units > 0
    last = [r.getMessage() for r in caplog.records if r.getMessage().startswith("refresh_gold")]
    assert last[-1].endswith(f"profile_error_units={result.profile_error_units}")


class _FailingDm:
    """Substitui o `DieboldMariano` só dentro do `dm_profiles` (o gate usa o original)."""

    @staticmethod
    def compare(*_args: object, **_kwargs: object) -> object:
        raise ValueError("injected")


# --- Stage 7.2 Task 19: a etapa conformal pelo port -----------------------------------

_CONFORMAL = ConformalParameters.from_mapping(
    {**conformal_block(), "pairs": [[0.1, 0.9], [0.25, 0.75]]}
)
_C_PARAMETERS = dataclasses.replace(_PARAMETERS, conformal_parameters=_CONFORMAL)
# no fold 0, o alvo da decisão 3 em h=2 cai no test_start: o calib para na decisão 2
_CALIB_DECISIONS = {"0": (0, 1, 2), "1": (14, 15, 16, 17)}
_SPLIT_ID = _CONFORMAL.variant_of_record
_NEXCP_ID = _CONFORMAL.sensitivity


def _conformal_cohort(calib: Mapping[str, tuple[int, ...]] = _CALIB_DECISIONS) -> Cohort:
    return with_calib(make_cohort(folds=("0", "1")), model="tft", calib_decisions=calib)


def _conformal_harness(
    cohort: Cohort | None = None, port: FakeConformalCalibration | None = None
) -> _Harness:
    return _harness(_conformal_cohort() if cohort is None else cohort, conformal=port)


@pytest.mark.unit
def test_one_port_call_with_only_the_ok_assembly_units() -> None:
    harness = _conformal_harness(_conformal_cohort({"0": _CALIB_DECISIONS["0"]}))
    harness(parameters=_C_PARAMETERS)
    [command] = harness.conformal.calls
    assert {(u.fold_index, u.seed, u.horizon) for u in command.units} == {
        (0, seed, h) for seed in (1, 2) for h in _HORIZONS
    }
    assert command.pairs == _CONFORMAL.pairs
    assert command.variants == (_SPLIT_ID, _NEXCP_ID)
    assert command.nexcp_rho == _CONFORMAL.nexcp_rho


@pytest.mark.unit
def test_assembly_undefined_units_become_rows_without_reaching_the_port() -> None:
    harness = _conformal_harness(_conformal_cohort({"0": _CALIB_DECISIONS["0"]}))
    inputs = _inputs_of(harness, parameters=_C_PARAMETERS)
    undefined = [u for u in inputs.conformal_reports.units if u.fold_raw == "1"]
    assert len(undefined) == 2 * 2 * len(_CONFORMAL.pairs) * 2  # seeds x h x pares x variantes
    assert {(u.status, u.reason) for u in undefined} == {("undefined", "unit has no calib point")}
    [command] = harness.conformal.calls
    assert all(u.fold_index != 1 for u in command.units)
    # sem o fold 1, nenhuma (seed, h, variante) tem cobertura completa
    assert inputs.conformal_reports.coverage == ()
    assert len(inputs.conformal_reports.undefined_coverage) == 2 * 2 * 2


@pytest.mark.unit
def test_port_error_unit_counts_and_makes_that_coverage_undefined() -> None:
    port = FakeConformalCalibration(force_status={(1, 2, 2): ("error", "forced")})
    harness = _conformal_harness(port=port)
    result = harness(parameters=_C_PARAMETERS)
    # C4-6 (CA15): unidades (fold, seed, h) distintas, não linhas (pares x variantes)
    assert result.conformal_error_units == 1
    inputs = _inputs_of(_conformal_harness(port=port), parameters=_C_PARAMETERS)
    undefined = {
        (u.seed, u.horizon, u.variant) for u in inputs.conformal_reports.undefined_coverage
    }
    assert undefined == {(2, 2, _SPLIT_ID), (2, 2, _NEXCP_ID)}
    covered = {(r.seed, r.horizon, r.variant) for r in inputs.conformal_reports.coverage}
    assert (
        covered
        == {(seed, h, v) for seed in (1, 2) for h in _HORIZONS for v in (_SPLIT_ID, _NEXCP_ID)}
        - undefined
    )
    reasons = {u.reason for u in inputs.conformal_reports.undefined_coverage}
    assert all("forced" in reason for reason in reasons)


@pytest.mark.unit
def test_port_exception_propagates_and_nothing_is_published() -> None:
    harness = _conformal_harness(port=FakeConformalCalibration(raises=RuntimeError("port down")))
    with pytest.raises(RuntimeError, match="port down"):
        harness(parameters=_C_PARAMETERS)
    assert "publish" not in harness.log.events


@pytest.mark.unit
def test_without_block_the_port_is_not_called() -> None:
    harness = _conformal_harness()
    result = harness(parameters=_PARAMETERS)
    assert harness.conformal.calls == []
    assert result.conformal_error_units == 0


@pytest.mark.unit
def test_blocked_generation_does_not_call_the_port() -> None:
    cohort = _conformal_cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    harness = _conformal_harness(drop_records(cohort, at_point("tft", 1, 1, gap)))
    result = harness(parameters=_C_PARAMETERS)
    assert result.status is RefreshStatus.BLOCKED
    assert harness.conformal.calls == []
    assert result.conformal_error_units == 0


@pytest.mark.unit
def test_verdict_inputs_identical_with_and_without_block() -> None:
    with_block = _inputs_of(_conformal_harness(), parameters=_C_PARAMETERS)
    without = _inputs_of(_conformal_harness(), parameters=_PARAMETERS)
    for name in (
        "horizon_reports",
        "mcs_reports",
        "profile_reports",
        "check_results",
        "block_estimates",
    ):
        assert getattr(with_block, name) == getattr(without, name), name
    assert not with_block.conformal_reports.is_empty
    assert without.conformal_reports.is_empty


@pytest.mark.unit
def test_conformal_n_evaluated_equals_the_native_n() -> None:
    # I8/I14: o n da linha conformal é o do `CoverageMetrics` da série nativa (model_full)
    inputs = _inputs_of(_conformal_harness(), parameters=_C_PARAMETERS)
    assert inputs.conformal_reports.coverage
    for report in inputs.conformal_reports.coverage:
        [native] = [
            r.coverage
            for h in inputs.horizon_reports
            if h.horizon == report.horizon
            for r in h.series
            if (r.model, r.seed, r.sample) == ("tft", report.seed, SampleKind.MODEL_FULL)
        ]
        assert report.n_evaluated == native.n_evaluated
        assert report.n_points == native.n_points


class _ReversedPort(FakeConformalCalibration):
    """Devolve as linhas do fake em ordem invertida (o join tem de ser por chave e alvo)."""

    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult:
        result = super().__call__(command)
        return CalibrateConformalResult(units=tuple(reversed(result.units)))


@pytest.mark.unit
def test_limits_joined_by_target_not_by_position() -> None:
    plain = _inputs_of(_conformal_harness(), parameters=_C_PARAMETERS)
    reversed_ = _inputs_of(_conformal_harness(port=_ReversedPort()), parameters=_C_PARAMETERS)
    assert reversed_.conformal_reports.coverage == plain.conformal_reports.coverage
    assert reversed_.conformal_reports.seed_means == plain.conformal_reports.seed_means
    assert sorted(reversed_.conformal_reports.units, key=repr) == sorted(
        plain.conformal_reports.units, key=repr
    )


@pytest.mark.unit
def test_seed_mean_over_complete_seeds_only() -> None:
    port = FakeConformalCalibration(force_status={(0, 2, 1): ("error", "forced")})
    inputs = _inputs_of(_conformal_harness(port=port), parameters=_C_PARAMETERS)
    for mean in inputs.conformal_reports.seed_means:
        if mean.horizon == 1:
            assert (mean.seeds_used, mean.seeds_excluded) == ((1,), (2,))
        else:
            assert (mean.seeds_used, mean.seeds_excluded) == ((1, 2), ())


# --- Checkpoint C das Tasks 16-19 (task-19-fix) ----------------------------------------


@pytest.mark.unit
def test_two_error_units_count_two() -> None:
    """C4-6: a contagem é de unidades distintas com alguma linha `error`."""
    port = FakeConformalCalibration(
        force_status={(1, 2, 2): ("error", "forced"), (0, 1, 1): ("error", "forced")}
    )
    assert _conformal_harness(port=port)(parameters=_C_PARAMETERS).conformal_error_units == 2  # noqa: PLR2004


@pytest.mark.unit
def test_port_undefined_unit_makes_that_coverage_undefined() -> None:
    """C4-4: `undefined` do port não conta como erro e tira a cobertura daquela seed e h."""
    port = FakeConformalCalibration(force_status={(0, 2, 1): ("undefined", "forced undefined")})
    harness = _conformal_harness(port=port)
    result = harness(parameters=_C_PARAMETERS)
    assert result.status is RefreshStatus.COMPLETED
    assert result.conformal_error_units == 0
    inputs = _inputs_of(_conformal_harness(port=port), parameters=_C_PARAMETERS)
    undefined = {
        (u.seed, u.horizon, u.variant): u.reason
        for u in inputs.conformal_reports.undefined_coverage
    }
    assert set(undefined) == {(2, 1, _SPLIT_ID), (2, 1, _NEXCP_ID)}
    assert all("forced undefined" in reason for reason in undefined.values())
    records = [
        u for u in inputs.conformal_reports.units if (u.fold_raw, u.seed, u.horizon) == ("0", 2, 1)
    ]
    assert {u.status for u in records} == {"undefined"}


@pytest.mark.unit
def test_seed_undefined_in_every_horizon_is_excluded_from_every_mean() -> None:
    """C4-4 (U4): a seed sem cobertura em todo horizonte sai de toda média."""
    port = FakeConformalCalibration(
        force_status={(0, 2, h): ("undefined", "forced undefined") for h in _HORIZONS}
    )
    inputs = _inputs_of(_conformal_harness(port=port), parameters=_C_PARAMETERS)
    means = inputs.conformal_reports.seed_means
    assert len(means) == len(_HORIZONS) * 2
    assert {(m.seeds_used, m.seeds_excluded) for m in means} == {((1,), (2,))}


@pytest.mark.unit
def test_native_point_without_a_unit_makes_the_coverage_undefined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C4-5: alvo nativo fora das unidades ok (o vão entre folds) → `undefined`, COMPLETED."""
    original = ConformalAssembly.assemble

    def with_gap(*args: object, **kwargs: object) -> ConformalAssemblyResult:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        return dataclasses.replace(result, uncovered_targets={(1, 1): ("gap-target",)})

    monkeypatch.setattr(ConformalAssembly, "assemble", staticmethod(with_gap))
    harness = _conformal_harness()
    result = harness(parameters=_C_PARAMETERS)
    assert result.status is RefreshStatus.COMPLETED
    inputs = _inputs_of(_conformal_harness(), parameters=_C_PARAMETERS)
    undefined = {
        (u.seed, u.horizon, u.variant): u.reason
        for u in inputs.conformal_reports.undefined_coverage
    }
    assert set(undefined) == {(1, 1, _SPLIT_ID), (1, 1, _NEXCP_ID)}
    assert all("native targets without a unit" in r for r in undefined.values())


def _cohort_with_folds(folds: tuple[str, str], calib: Mapping[str, tuple[int, ...]]) -> Cohort:
    return with_calib(make_cohort(folds=folds), model="tft", calib_decisions=calib)


@pytest.mark.unit
def test_zero_corrections_match_native_with_units_out_of_temporal_order() -> None:
    """C4-7: o fold "1" vem antes do "0" no tempo; o join por alvo mantém cada y no seu limite."""
    cohort = _cohort_with_folds(("1", "0"), {"1": (0, 1, 2), "0": (14, 15, 16, 17)})
    inputs = _inputs_of(_conformal_harness(cohort), parameters=_C_PARAMETERS)
    assert inputs.conformal_reports.coverage
    for report in inputs.conformal_reports.coverage:
        [native] = [
            r.coverage
            for h in inputs.horizon_reports
            if h.horizon == report.horizon
            for r in h.series
            if (r.model, r.seed, r.sample) == ("tft", report.seed, SampleKind.MODEL_FULL)
        ]
        per_level = dict(native.per_level)
        for pair in report.per_pair:
            assert pair.lower_tail.coverage == per_level[pair.lower_level]
            assert pair.upper_tail.coverage == per_level[pair.upper_level]


@pytest.mark.unit
def test_folds_with_the_same_integer_never_reach_the_port() -> None:
    """C4-8: "01" e "1" ficam `undefined` na montagem; o refresh segue COMPLETED."""
    cohort = _cohort_with_folds(("01", "1"), {"01": (0, 1, 2), "1": (14, 15, 16, 17)})
    harness = _conformal_harness(cohort)
    result = harness(parameters=_C_PARAMETERS)
    assert result.status is RefreshStatus.COMPLETED
    assert harness.conformal.calls == []
    inputs = _inputs_of(_conformal_harness(cohort), parameters=_C_PARAMETERS)
    assert inputs.conformal_reports.coverage == ()
    assert {u.fold_raw for u in inputs.conformal_reports.units} == {"01", "1"}
    assert all("same integer fold" in (u.reason or "") for u in inputs.conformal_reports.units)


# --- Checkpoint C das Tasks 20-22 (task-19-fix, C5-1) ----------------------------------


@pytest.mark.unit
def test_port_rows_map_back_to_the_raw_fold() -> None:
    """C5-1: o port devolve o inteiro 1; o registro volta com o fold cru "01"."""
    cohort = _cohort_with_folds(("01", "2"), {"01": (0, 1, 2), "2": (14, 15, 16, 17)})
    harness = _conformal_harness(cohort)
    inputs = _inputs_of(harness, parameters=_C_PARAMETERS)
    [command] = harness.conformal.calls
    assert {u.fold_index for u in command.units} == {1, 2}
    records = inputs.conformal_reports.units
    assert {(u.fold_raw, u.fold_index) for u in records} == {("01", 1), ("2", 2)}
    assert {u.status for u in records} == {"ok"}
    assert inputs.conformal_reports.undefined_coverage == ()
    assert {(r.seed, r.horizon) for r in inputs.conformal_reports.coverage} == {
        (seed, h) for seed in (1, 2) for h in _HORIZONS
    }


@pytest.mark.unit
def test_assembly_undefined_reason_names_the_raw_fold() -> None:
    """TA-9 (mutante RG02): o motivo começa pelo fold cru da unidade culpada."""
    harness = _conformal_harness(_conformal_cohort({"0": _CALIB_DECISIONS["0"]}))
    inputs = _inputs_of(harness, parameters=_C_PARAMETERS)
    reasons = [u.reason for u in inputs.conformal_reports.undefined_coverage]
    assert reasons
    assert all(r.startswith("assembly unit fold '1': unit has no calib point") for r in reasons)


# --- Stage 7.3 Task 30: a etapa h3 -------------------------------------------------------

_H3_HORIZONS = (1, 7)


_H3_REPS = 37
_H3_BOOTSTRAP_SEED = 7


def _h3_parameters_for_test() -> H3Parameters:
    from tests.unit.features.evaluation._h3_parameters import h3_block  # noqa: PLC0415

    block: dict[str, Any] = copy.deepcopy(h3_block())
    block["k_p"] = 2
    block["ablation"]["seeds"] = [1, 2]
    # TA-10: B e semente do bootstrap ≠ os de produção (1000, 129), para que o repasse do
    # plano ao `bootstrap_indices` seja distinguível de um literal
    block["reps"] = _H3_REPS
    block["bootstrap_seed"] = _H3_BOOTSTRAP_SEED
    return H3Parameters.from_mapping(block)


_H3_PARAMETERS = dataclasses.replace(_PARAMETERS, h3_parameters=_h3_parameters_for_test())


def _h3_cohort() -> Cohort:
    from tests.unit.features.evaluation._h3_parameters import (  # noqa: PLC0415
        SYNTHETIC_PARTITION,
    )

    variables = {f: family for family, features in SYNTHETIC_PARTITION.items() for f in features}
    variables["relative_time_idx"] = "none"
    base = make_cohort(
        folds=("0", "1"), seeds={"gbm": (None,), "tft": (1, 2)}, horizons=_H3_HORIZONS
    )
    permuted = with_permuted(base, shift=0.01)
    return with_vsn(with_ablation(permuted, seeds=(1, 2), shift=0.01), variables=variables)


def _h3_silver(cohort: Cohort) -> dict[str, list[dict[str, object]]]:
    silver = _silver(cohort)
    ablation_id = _h3_parameters_for_test().ablation_cohort_id
    silver["dim_run"] += [
        {
            "run_id": run.run_id,
            "asset": _ASSET,
            "parent_sweep_id": ablation_id,
            "feature_set_name": run.feature_set_name,
            "config_signature": run.config_signature,
            "fold": run.fold,
            "seed": run.seed,
            "model_version": run.model,
        }
        for run in cohort.ablation_runs
    ]
    silver["fact_oos_predictions"] += [
        {
            "run_id": r.run_id,
            "model_version": r.model,
            "asset": _ASSET,
            "feature_set_name": "fs_all_ablation",
            "split": r.split,
            "horizon": r.horizon,
            "decision_idx": r.decision_idx,
            "timestamp_utc": r.decision_timestamp,
            "target_timestamp_utc": r.target_timestamp,
            "quantile_level": r.quantile_level,
            "value_raw": r.value_raw,
            "value_guardrail": r.value_guardrail,
            "guardrail_applied": int(r.guardrail_applied),
            "year": int(r.decision_timestamp[:4]),
        }
        for r in cohort.ablation_records
    ]
    feature_set = {run.run_id: run.feature_set_name for run in cohort.runs}
    silver["fact_permuted_predictions"] = [
        {
            "run_id": r.run_id,
            "model_version": r.model,
            "asset": _ASSET,
            "feature_set_name": feature_set[r.run_id],
            "permuted_family": r.permuted_family,
            "permutation_index": r.permutation_index,
            "permutation_seed": r.permutation_seed,
            "permutation_algorithm": r.permutation_algorithm,
            "partition_hash": r.partition_hash,
            "horizon": r.horizon,
            "decision_idx": r.decision_idx,
            "timestamp_utc": r.decision_timestamp,
            "target_timestamp_utc": r.target_timestamp,
            "quantile_level": r.quantile_level,
            "value_raw": r.value_raw,
            "value_guardrail": r.value_guardrail,
            "guardrail_applied": int(r.guardrail_applied),
            "year": int(r.decision_timestamp[:4]),
        }
        for r in cohort.permuted
    ]
    silver["fact_vsn_weights"] = [
        {
            "run_id": r.run_id,
            "model_version": r.model,
            "asset": _ASSET,
            "feature_set_name": feature_set[r.run_id],
            "decision_idx": r.decision_idx,
            "timestamp_utc": r.decision_timestamp,
            "variable": r.variable,
            "family": r.family,
            "weight": r.weight,
            "year": int(r.decision_timestamp[:4]),
        }
        for r in cohort.vsn
    ]
    return silver


class _FailAfter(_SpyBackend):
    """Backend que só falha nas chamadas de b̂ depois das `ok` primeiras (as da 6.4)."""

    def __init__(self, log: _Log, *, ok: int, error: BaseException) -> None:
        super().__init__(log)
        self._ok = ok
        self._error = error

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        if len(self.block_series) >= self._ok:
            self.block_series.append(tuple(series))
            raise self._error
        return super().optimal_block_length(series=series)


def _h3_harness() -> _Harness:
    cohort = _h3_cohort()
    return _harness(cohort, silver=_h3_silver(cohort))


def _h3_run(harness: _Harness, parameters: RefreshParameters = _H3_PARAMETERS) -> GoldInputs:
    return _inputs_of(harness, parameters=parameters, horizons=_H3_HORIZONS)


def _reads(harness: _Harness, table: str) -> list[dict[str, object]]:
    return [filters for _, name, filters in harness.reader.reads if name == table]


def _calls_without_h3() -> int:
    """Quantas estimativas de b̂ a 6.4 pede neste cohort (as do H3 vêm depois)."""
    probe = _h3_harness()
    _h3_run(probe, _PARAMETERS)
    return len(probe.backend.block_series)


@pytest.mark.unit
def test_permuted_and_vsn_read_one_run_per_call_with_run_id_filter() -> None:
    harness = _h3_harness()
    inputs = _h3_run(harness)
    candidate = sorted(r.run_id for r in _h3_cohort().runs if r.model == "tft")
    for table in ("fact_permuted_predictions", "fact_vsn_weights"):
        reads = _reads(harness, table)
        assert sorted(str(f["run_id"]) for f in reads) == candidate, table
    assert inputs.h3_reports.permutation is not None
    assert inputs.h3_reports.permutation.status == "ok"


@pytest.mark.unit
def test_ablation_partition_read_once_per_year_never_without_year() -> None:
    harness = _h3_harness()
    _h3_run(harness)
    ablation_reads = [
        f
        for f in _reads(harness, "fact_oos_predictions")
        if f["feature_set_name"] == "fs_all_ablation"
    ]
    assert ablation_reads == [
        {"asset": _ASSET, "feature_set_name": "fs_all_ablation", "year": 2024}
    ]


@pytest.mark.unit
def test_confirmatory_records_never_read_fs_all_ablation() -> None:
    harness = _h3_harness()
    inputs = _h3_run(harness)
    confirmatory = [f for f in _reads(harness, "fact_oos_predictions") if "year" not in f]
    assert confirmatory
    assert all(f["feature_set_name"] != "fs_all_ablation" for f in confirmatory)
    assert inputs.h3_reports.ablation is not None
    assert inputs.h3_reports.ablation.status == "ok"


@pytest.mark.unit
def test_one_bootstrap_indices_call_serves_both_methods() -> None:
    before = _calls_without_h3()
    harness = _h3_harness()
    inputs = _h3_run(harness)
    h3_calls = [c for c in harness.backend.index_calls if c["reps"] == _H3_REPS]
    assert len(h3_calls) == 1
    [call] = h3_calls
    assert (call["reps"], call["seed"]) == (_H3_REPS, _H3_BOOTSTRAP_SEED)
    assert call["scheme"] is BootstrapScheme.STATIONARY
    assert len(harness.backend.block_series) - before == 16  # noqa: PLR2004
    assert call["block_size"] == 7  # noqa: PLR2004 — max(7, ⌈2,5⌉), o piso
    assert inputs.h3_reports.block_length == call["block_size"]
    assert inputs.h3_reports.max_block_estimate == _BLOCK


def _failing_h3(error: BaseException) -> GoldInputs:
    before = _calls_without_h3()
    harness = _h3_harness()
    harness.use_case._mcs_backend = _FailAfter(harness.log, ok=before, error=error)
    return _h3_run(harness)


@pytest.mark.unit
@pytest.mark.parametrize("error", [ArithmeticError("singular"), ZeroDivisionError("zero")])
def test_invalid_series_or_arithmetic_error_gives_undefined_reading(error: Exception) -> None:
    inputs = _failing_h3(error)
    reading = inputs.h3_reports.reading
    assert reading is not None
    assert reading.status == "undefined"
    assert reading.sustained is False
    assert "bootstrap undefined" in str(reading.reason)
    assert inputs.status is RefreshStatus.COMPLETED
    # TA-14 (R6): sem bootstrap, nem bloco nem b̂ máximo
    assert inputs.h3_reports.block_length is None
    assert inputs.h3_reports.max_block_estimate is None


@pytest.mark.unit
def test_constant_series_gives_undefined_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    from financial_forecasting.features.evaluation.domain.services import (  # noqa: PLC0415
        joint_contribution as module,
    )

    def invalid(series: Sequence[float]) -> None:
        raise ValueError("optimal_block_length needs a non-constant series")

    monkeypatch.setattr(module, "validate_block_length_request", invalid)
    reading = _h3_run(_h3_harness()).h3_reports.reading
    assert reading is not None
    assert reading.status == "undefined"
    assert "invalid series" in str(reading.reason)


@pytest.mark.unit
def test_h3_failure_never_changes_other_tables() -> None:
    reference = _h3_run(_h3_harness(), _PARAMETERS)
    failing = _failing_h3(ArithmeticError("x"))
    for name in ("horizon_reports", "mcs_reports", "profile_reports", "check_results"):
        assert getattr(failing, name) == getattr(reference, name), name
    assert reference.h3_reports.is_empty
    assert not failing.h3_reports.is_empty


@pytest.mark.unit
def test_without_h3_block_no_h3_read() -> None:
    harness = _h3_harness()
    inputs = _h3_run(harness, _PARAMETERS)
    assert _reads(harness, "fact_permuted_predictions") == []
    assert _reads(harness, "fact_vsn_weights") == []
    assert all("year" not in f for f in _reads(harness, "fact_oos_predictions"))
    assert inputs.h3_reports.is_empty


@pytest.mark.unit
def test_blocked_generation_has_no_h3() -> None:
    cohort = _h3_cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    cohort = drop_records(cohort, at_point("tft", 1, 1, gap))
    harness = _harness(cohort, silver=_h3_silver(cohort))
    inputs = _h3_run(harness)
    assert inputs.status is RefreshStatus.BLOCKED
    assert inputs.h3_reports.is_empty
    assert _reads(harness, "fact_permuted_predictions") == []


@pytest.mark.unit
def test_unexpected_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    from financial_forecasting.features.evaluation.application.use_cases import (  # noqa: PLC0415
        refresh_gold as module,
    )

    def broken(**kwargs: object) -> object:
        raise RuntimeError("bug in the assembly")

    monkeypatch.setattr(module.AttributionAssembly, "assemble", staticmethod(broken))
    harness = _h3_harness()
    with pytest.raises(RuntimeError, match="bug in the assembly"):
        harness(parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)
    assert "publish" not in harness.log.events


@pytest.mark.unit
def test_contribution_receives_the_bonferroni_level(monkeypatch: pytest.MonkeyPatch) -> None:
    from financial_forecasting.features.evaluation.domain.services import (  # noqa: PLC0415
        joint_contribution as module,
    )

    levels: list[float] = []
    real = module.FamilyContribution.evaluate

    def spy(differentials: Any, *, bootstrap: Any, level: float) -> Any:  # noqa: ANN401
        levels.append(level)
        return real(differentials, bootstrap=bootstrap, level=level)

    monkeypatch.setattr(module.FamilyContribution, "evaluate", staticmethod(spy))
    _h3_run(_h3_harness())
    assert levels == [0.9875, 0.9875]
    assert _h3_parameters_for_test().interval_level == 0.9875  # noqa: PLR2004


@pytest.mark.unit
def test_method_undefined_in_assembly_runs_no_bootstrap() -> None:
    """C8-1: com a LOCO indefinida, nenhum b̂ nem índice de H3 (o bloco é das 16 séries)."""
    before = _calls_without_h3()
    cohort = _h3_cohort()
    silver = _h3_silver(cohort)
    missing = loco_model_of("fundamental")
    silver["dim_run"] = [row for row in silver["dim_run"] if row["model_version"] != missing]
    harness = _harness(cohort, silver=silver)
    inputs = _h3_run(harness)
    assert len(harness.backend.block_series) == before
    assert [c for c in harness.backend.index_calls if c["reps"] == _H3_REPS] == []
    reports = inputs.h3_reports
    assert reports.permutation is not None and reports.ablation is not None
    assert reports.permutation.reason == JOINT_BLOCK_NEEDS_BOTH
    assert "has no run" in str(reports.ablation.reason)
    assert reports.block_length is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "damage", "report", "reason"),
    [
        ("fact_vsn_weights", {"weight": 1.5}, "vsn", "weight must be a finite float in [0, 1]"),
        ("fact_vsn_weights", {"weight": math.inf}, "vsn", "weight must be a finite float"),
        ("fact_vsn_weights", "duplicate", "vsn", "twice at decision"),
        ("fact_permuted_predictions", {"value_guardrail": math.inf}, "permutation", "h="),
    ],
    ids=["vsn-weight-1.5", "vsn-weight-inf", "vsn-duplicate", "permuted-inf"],
)
def test_bad_attribution_row_is_undefined_never_aborts(
    table: str, damage: object, report: str, reason: str
) -> None:
    """C8-2: ValueError de registro ou redução vira `undefined` com o motivo (I16)."""
    cohort = _h3_cohort()
    silver = _h3_silver(cohort)
    rows = silver[table]
    if damage == "duplicate":
        rows.append(dict(rows[0]))
    else:
        rows[0] = {**rows[0], **damage}  # type: ignore[dict-item]
    harness = _harness(cohort, silver=silver)
    inputs = _h3_run(harness)
    assert inputs.status is RefreshStatus.COMPLETED
    target = getattr(inputs.h3_reports, report)
    assert target is not None
    assert target.status == "undefined"
    assert reason in str(target.reason), target.reason


@pytest.mark.unit
def test_candidate_run_without_vsn_rows_makes_the_vsn_undefined() -> None:
    """C8-10: um run do candidato sem linhas de VSN deixa o resumo undefined com o motivo."""
    cohort = _h3_cohort()
    silver = _h3_silver(cohort)
    run_id = sorted(r.run_id for r in cohort.runs if r.model == "tft")[0]
    silver["fact_vsn_weights"] = [r for r in silver["fact_vsn_weights"] if r["run_id"] != run_id]
    inputs = _h3_run(_harness(cohort, silver=silver))
    vsn = inputs.h3_reports.vsn
    assert vsn is not None
    assert vsn.status == "undefined"
    assert f"run {run_id}: no vsn rows" in str(vsn.reason)


class _CountingAfter(_SpyBackend):
    """Depois das `ok` chamadas da 6.4, um b̂ distinto por série de H3 (TA-2).

    A i-ésima série (1..16) recebe i/2 (0,5 … 8,0), menos a 11ª (LOCO), que recebe 9,3:
    o máximo não é a primeira nem a última série e passa de 7, então ⌈·⌉ e o piso 7
    contam.
    """

    def __init__(self, log: _Log, *, ok: int) -> None:
        super().__init__(log)
        self._ok = ok

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        value = super().optimal_block_length(series=series)
        index = len(self.block_series) - self._ok
        if index <= 0:
            return value
        return 9.3 if index == 11 else index / 2  # noqa: PLR2004


@pytest.mark.unit
def test_block_is_the_joint_max_over_the_16_series() -> None:
    """C8-3/TA-2: b̂ distinto por série; o máximo (9,3) é da 11ª, uma série da LOCO."""
    before = _calls_without_h3()
    harness = _h3_harness()
    harness.use_case._mcs_backend = _CountingAfter(harness.log, ok=before)
    inputs = _h3_run(harness)
    backend = harness.use_case._mcs_backend
    assert len(backend.block_series) - before == 16  # noqa: PLR2004
    assert inputs.h3_reports.max_block_estimate == 9.3  # noqa: PLR2004
    assert inputs.h3_reports.block_length == 10  # noqa: PLR2004 — max(7, ⌈9,3⌉)
    [call] = [c for c in backend.index_calls if c["reps"] == _H3_REPS]
    assert call["block_size"] == 10  # noqa: PLR2004


@pytest.mark.unit
def test_level_follows_family_alpha_of_the_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """C8-7: family_alpha = 0,1 ⇒ nível 1 - 0,1/4 = 0,975 (mata o 0,9875 literal, M2)."""
    from financial_forecasting.features.evaluation.domain.services import (  # noqa: PLC0415
        joint_contribution as module,
    )

    levels: list[float] = []
    real = module.FamilyContribution.evaluate

    def spy(differentials: Any, *, bootstrap: Any, level: float) -> Any:  # noqa: ANN401
        levels.append(level)
        return real(differentials, bootstrap=bootstrap, level=level)

    monkeypatch.setattr(module.FamilyContribution, "evaluate", staticmethod(spy))
    block = _h3_parameters_for_test().as_payload()
    block["family_alpha"] = 0.1
    parameters = dataclasses.replace(_PARAMETERS, h3_parameters=H3Parameters.from_mapping(block))
    inputs = _h3_run(_h3_harness(), parameters)
    assert levels == [0.975, 0.975]
    assert inputs.h3_reports.permutation is not None
    assert inputs.h3_reports.permutation.level == 0.975  # noqa: PLR2004


@pytest.mark.unit
@pytest.mark.parametrize("split", ["val", "calib"])
def test_ablation_rows_outside_test_are_ignored(
    split: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C8-9/TA-14 (R8): linhas `val` ou `calib` da ablação (valores absurdos) não entram
    nas perdas da LOCO, e o refresh nem as entrega à redução (só `test` é materializado,
    I19 — a redução também filtra, então o resultado sozinho não distingue os filtros)."""
    real_reduce = refresh_gold_module.reduce_ablation_run
    splits: set[str] = set()

    def spy(records: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        splits.update(record.split for record in records)
        return real_reduce(records, **kwargs)

    cohort = _h3_cohort()
    clean = _h3_run(_harness(cohort, silver=_h3_silver(cohort)))
    silver = _h3_silver(cohort)
    validation = [
        {**row, "split": split, "value_raw": 9.0, "value_guardrail": 9.0}
        for row in silver["fact_oos_predictions"]
        if row["feature_set_name"] == "fs_all_ablation"
    ]
    silver["fact_oos_predictions"] += validation
    monkeypatch.setattr(refresh_gold_module, "reduce_ablation_run", spy)
    noisy = _h3_run(_harness(cohort, silver=silver))
    assert validation
    assert splits == {"test"}
    assert noisy.h3_reports.ablation == clean.h3_reports.ablation
    assert noisy.h3_reports.ablation_differentials == clean.h3_reports.ablation_differentials


# --- Stage 8.1: identidade do silver consumido (A2 com fakes, A7, D4, I6, I7) ----------


def _silver_content_of(harness: _Harness, **changes: object) -> SilverContent:
    return harness(**changes).manifest.silver_content


def _h3_content(
    silver: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    cohort: Cohort | None = None,
    partition_keys: Mapping[str, tuple[str, ...]] | None = None,
) -> SilverContent:
    harness = _harness(
        _h3_cohort() if cohort is None else cohort, silver=silver, partition_keys=partition_keys
    )
    return _silver_content_of(harness, parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)


def _prefixed(content: SilverContent, table: str) -> set[str]:
    return {key for key in content.units if key.split("|")[0] == table}


@pytest.mark.unit
def test_manifest_carries_silver_content() -> None:
    cohort = make_cohort()
    harness = _harness(cohort)
    result = harness()
    manifest, _ = _published(harness)

    content = SilverContent.from_mapping(manifest["silver_content"])  # type: ignore[arg-type]
    assert content == result.manifest.silver_content
    assert set(content.tables) == {"dim_run", "fact_oos_predictions", "realized"}
    assert _prefixed(content, "dim_run") == {f"dim_run|{_SWEEP}"}
    assert _prefixed(content, "realized") == {f"realized|{_ASSET}"}
    assert _prefixed(content, "fact_oos_predictions") == {
        unit_key("fact_oos_predictions", record.run_id, 2024) for record in cohort.records
    }


@pytest.mark.unit
def test_result_manifest_equals_published_manifest() -> None:
    harness = _harness()
    result = harness()
    manifest, _ = _published(harness)

    assert result.manifest.as_mapping() == manifest


@pytest.mark.unit
def test_blocked_hashes_exactly_dim_run_facts_and_realized() -> None:
    """A7: com `BLOCKED`, só o lido antes dos checks entra (nada da leitura de H3)."""
    cohort = _h3_cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    cohort = drop_records(cohort, at_point("tft", 1, 1, gap))
    harness = _harness(cohort, silver=_h3_silver(cohort))
    result = harness(parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)

    assert result.status is RefreshStatus.BLOCKED
    content = result.manifest.silver_content
    assert set(content.tables) == {"dim_run", "fact_oos_predictions", "realized"}
    assert _prefixed(content, "dim_run") == {f"dim_run|{_SWEEP}"}


@pytest.mark.unit
def test_completed_with_h3_hashes_the_five_tables() -> None:
    cohort = _h3_cohort()
    harness = _harness(cohort, silver=_h3_silver(cohort))
    result = harness(parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)

    assert result.status is RefreshStatus.COMPLETED
    content = result.manifest.silver_content
    assert set(content.tables) == {
        "dim_run",
        "fact_oos_predictions",
        "fact_permuted_predictions",
        "fact_vsn_weights",
        "realized",
    }
    ablation_id = _h3_parameters_for_test().ablation_cohort_id
    assert _prefixed(content, "dim_run") == {f"dim_run|{_SWEEP}", f"dim_run|{ablation_id}"}
    ablation_units = {
        unit_key("fact_oos_predictions", r.run_id, int(r.decision_timestamp[:4]))
        for r in cohort.ablation_records
        if r.split == "test"
    }
    assert ablation_units <= _prefixed(content, "fact_oos_predictions")
    tft_runs = {run.run_id for run in cohort.runs if run.model == "tft"}
    assert {key.split("|")[1] for key in _prefixed(content, "fact_permuted_predictions")} == (
        tft_runs
    )


def _discard_case(case: str, silver: dict[str, list[dict[str, object]]], cohort: Cohort) -> None:
    """Acrescenta ao silver linhas que o refresh lê ou nem pede, e descarta (A2(c))."""
    gbm = next(run for run in cohort.runs if run.model == "gbm")
    if case == "other-sweep":
        silver["dim_run"].append(
            {**silver["dim_run"][0], "run_id": "alien", "parent_sweep_id": "x"}
        )
    elif case == "ablation-calib":
        silver["fact_oos_predictions"] += [
            {**row, "split": "calib", "value_raw": 9.0}
            for row in silver["fact_oos_predictions"]
            if row["feature_set_name"] == "fs_all_ablation"
        ]
    elif case == "ablation-year-outside":
        silver["fact_oos_predictions"] += [
            {**row, "year": 1999}
            for row in silver["fact_oos_predictions"]
            if row["feature_set_name"] == "fs_all_ablation"
        ]
    else:  # "non-candidate-attribution"
        for table in ("fact_permuted_predictions", "fact_vsn_weights"):
            silver[table] += [
                {**row, "run_id": gbm.run_id, "model_version": gbm.model}
                for row in silver[table][:5]
            ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "case", ["other-sweep", "ablation-calib", "ablation-year-outside", "non-candidate-attribution"]
)
def test_rows_discarded_by_post_filters_do_not_change_digest(case: str) -> None:
    cohort = _h3_cohort()
    # `dim_run` só por `asset`: o leitor devolve o superconjunto e o use case pós-filtra
    keys = {**SILVER_PARTITIONS, "dim_run": ("asset",)}
    baseline = _h3_content(_h3_silver(cohort), cohort=cohort, partition_keys=keys)
    silver = _h3_silver(cohort)
    _discard_case(case, silver, cohort)

    assert _h3_content(silver, cohort=cohort, partition_keys=keys) == baseline


@pytest.mark.unit
@pytest.mark.parametrize(
    ("column", "unusable"), [("fold", "fold-x"), ("seed", None)], ids=["fold", "seed"]
)
def test_rows_of_a_run_with_unusable_fold_or_seed_do_not_change_digest(
    column: str, unusable: object
) -> None:
    """Run do candidato com fold ou seed inutilizável vira `undefined`: nada dele é lido."""
    cohort = _h3_cohort()
    run = sorted(r.run_id for r in cohort.runs if r.model == "tft")[0]

    def silver_with_unusable_fold(value_raw: float | None) -> dict[str, list[dict[str, object]]]:
        silver = _h3_silver(cohort)
        silver["dim_run"] = [
            {**row, column: unusable} if row["run_id"] == run else row for row in silver["dim_run"]
        ]
        if value_raw is not None:
            silver["fact_permuted_predictions"] = [
                {**row, "value_raw": value_raw} if row["run_id"] == run else row
                for row in silver["fact_permuted_predictions"]
            ]
        return silver

    baseline = _h3_content(silver_with_unusable_fold(None), cohort=cohort)
    changed = _h3_content(silver_with_unusable_fold(9.0), cohort=cohort)

    assert changed == baseline
    assert run not in {
        key.split("|")[1] for key in _prefixed(baseline, "fact_permuted_predictions")
    }


@pytest.mark.unit
def test_gold_tables_identical_with_and_without_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum número muda com o hash, e o hash não muta as linhas devolvidas pelo leitor."""
    cohort = _h3_cohort()
    hashed = _harness(cohort, silver=_h3_silver(cohort))
    returned: list[tuple[Sequence[Mapping[str, object]], object]] = []
    real_read = hashed.reader.read

    def snapshot(**kwargs: object) -> Sequence[Mapping[str, object]]:
        rows = real_read(**kwargs)
        returned.append((rows, copy.deepcopy(rows)))
        return rows

    hashed.reader.read = snapshot  # type: ignore[method-assign]
    hashed(parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)

    constant = SilverContentHash(value="0" * 64)
    monkeypatch.setattr(
        accumulator_module.SilverContentHash, "of_unit", classmethod(lambda cls, **_: constant)
    )
    unhashed = _harness(cohort, silver=_h3_silver(cohort))
    unhashed(parameters=_H3_PARAMETERS, horizons=_H3_HORIZONS)

    assert _published(unhashed)[1] == _published(hashed)[1]
    assert returned
    assert all(rows == before for rows, before in returned)


@pytest.mark.unit
def test_attribution_post_filter_by_run_id_when_the_partition_has_other_runs() -> None:
    """CC2-1: sem `run_id` na partição, a leitura de um run traz as linhas dos outros runs
    do candidato; o pós-filtro as descarta antes do hash (o digest é o da partição por run)."""
    cohort = _h3_cohort()
    silver = _h3_silver(cohort)
    without_run_id = {
        **SILVER_PARTITIONS,
        "fact_permuted_predictions": ("asset", "feature_set_name", "year"),
        "fact_vsn_weights": ("asset", "feature_set_name", "year"),
    }
    candidate_runs = {r.run_id for r in cohort.runs if r.model == "tft"}
    assert len({row["run_id"] for row in silver["fact_permuted_predictions"]}) == len(
        candidate_runs
    )

    assert _h3_content(silver, cohort=cohort, partition_keys=without_run_id) == _h3_content(
        silver, cohort=cohort
    )
