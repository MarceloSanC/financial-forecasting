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

import dataclasses
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta

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
from financial_forecasting.features.evaluation.application.use_cases import (
    refresh_gold as refresh_gold_module,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    GridFingerprintMismatchError,
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
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
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
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
from tests.fakes.features.evaluation.fake_gold_builder import FakeGoldBuilder
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.fakes.features.evaluation.fake_silver_table_reader import FakeSilverTableReader
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.evaluation.gold._cohort_factory import (
    Cohort,
    at_point,
    drop_records,
    make_cohort,
    replace_records,
    targets_of,
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
)
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
    "build",
    "publish",
)


class _StubHasher:
    """Dublê mínimo do `Hasher` (sem fake por desenho, #70): `repr` ordenado."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        return repr(sorted(payload.items()))

    def hash_text(self, text: str) -> str:
        return text


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
) -> _Harness:
    cohort = make_cohort() if cohort is None else cohort
    log = _Log()
    reader = _SpyReader(_silver(cohort) if silver is None else silver, log, partition_keys)
    rows = (_dataset(cohort) if dataset is None else dataset) if seed_dataset else None
    grid = _SpyGrid(rows, log)
    backend = _SpyBackend(log, fail=fail, estimates=estimates)
    gold = _SpyStoreGold(log)
    use_case = RefreshGold(
        silver_reader=reader,
        grid_reader=grid,
        clock=FakeClock() if clock is None else clock,  # type: ignore[arg-type]
        mcs_backend=backend,
        gold_store=gold,
        builders=builders(log),
    )
    return _Harness(use_case, reader, grid, backend, gold, log, _fingerprint(cohort))


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
    assert steps == [s for s in _EXPECTED_STEPS if s not in ("reports", "mcs")]
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
