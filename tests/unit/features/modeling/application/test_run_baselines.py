"""Unit tests do use case `RunBaselines` — tudo com fakes (skill `pytest-with-fakes`).

Infra: `FakeMedallionStore` semeado via `seed_read_only` (Task 04),
`FakeBaselineForecaster` (Task 05), `FakeAnalyticsRepository` (4.2),
`FakeHasher` (1.4) e o `WalkForwardSplitter` REAL sobre grade sintética de dias
úteis contíguos (mesma técnica dos testes da 5.1).

Prova (concept 5.2 §4/§5/§6; A5-unit/A6/A8):

- happy path: 5 specs x 2 folds -> 1 `BaselineRunSummary` e 1 linha `dim_run`
  por (spec x fold) com `model_version='baseline_*'`, `fold=str(i)`,
  `seed=None`, `parent_sweep_id=cohort_id`; predições LONG com `split="test"`
  e grade completa por decisão x horizonte; `target_timestamp_utc` alinhado por
  índice de sessão (I2, resolvido só pelo persister 4.3);
- I9: duas invocações idênticas (estado zerado) -> mesmos `run_id`s;
- C2: cada validação ergue SEM nenhuma chamada a store/repo (store contador);
- C7: read vazio ergue;
- C6: decisões na cauda sem janela completa -> `rows_skipped`, sem linha
  fabricada;
- A6/I6 em duas camadas: stub de splitter com blocos test sobrepostos ->
  `ValueError` C9 do serviço 5.1 ("ambiguous operationally-latest..."); unit
  direto do helper puro `_assert_zero_removal` (defesa-em-profundidade, sem
  ramo morto).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.application.use_cases import (
    run_baselines as run_baselines_module,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
    RunBaselinesCommand,
    _assert_zero_removal,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.fold_split import (
    FoldSplit,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.domain.services.trading_calendar import (
    TradingCalendar,
)
from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_baseline_forecaster import (
    FakeBaselineForecaster,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)

# -- grade sintética e comando canônico dos testes -------------------------------

_FRIDAY = 4  # datetime.weekday(): 0=segunda ... 4=sexta
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_HQ_WINDOW = 20  # override de teste do W=252 (ADR 5.2.0003)
_N_FOLDS = 2
_TEST_SIZE = 3
_N_SPECS = 5
_COHORT_ID = "cohort-h2"

_SCOPE = ScopeSpec(
    asset_id="TEST", feature_set_name="fs_test", max_horizon=2, cohort_id=_COHORT_ID
)


class _FakeClock:
    """Clock determinístico — só para satisfazer o construtor do fake 4.2 (I5)."""

    def now(self) -> datetime:
        return datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)


class _CountingStore(FakeMedallionStore):
    """FakeMedallionStore que CONTA leituras (prova C2: erguer antes de I/O)."""

    def __init__(self) -> None:
        super().__init__()
        self.read_calls = 0

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        self.read_calls += 1
        return super().read(layer=layer, table=table, filters=filters)


def _weekday_sessions(count: int, *, start: date = date(2021, 1, 4)) -> tuple[date, ...]:
    """`count` dias úteis contíguos (seg a sex) a partir de `start` (uma segunda)."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


_SESSIONS = _weekday_sessions(_N_SESSIONS)


def _returns(n: int = _N_SESSIONS) -> tuple[float, ...]:
    """Série sintética determinística de retornos (variação suficiente p/ ar1)."""
    rng = random.Random(11)
    return tuple(0.001 + rng.gauss(0.0, 0.01) for _ in range(n))


def _dataset_rows(sessions: Sequence[date], returns: Sequence[float]) -> list[dict[str, object]]:
    return [
        {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": value,
        }
        for day, value in zip(sessions, returns, strict=True)
    ]


def _seeded_store() -> _CountingStore:
    store = _CountingStore()
    store.seed_read_only(
        layer="processed",
        table="dataset_tft",
        asset=_SCOPE.asset_id,
        rows=_dataset_rows(_SESSIONS, _returns()),
    )
    return store


def _splitter(sessions: tuple[date, ...] = _SESSIONS) -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))


def _command(**overrides: object) -> RunBaselinesCommand:
    base: dict[str, object] = {
        "scope": _SCOPE,
        "specs": BaselineSpec.canonical_five(historical_quantiles_window=_HQ_WINDOW),
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "n_folds": _N_FOLDS,
        "test_size": _TEST_SIZE,
        "val_size": 5,
        "calib_size": 5,
        "embargo": 1,
        "schema_version": 1,
    }
    base.update(overrides)
    return RunBaselinesCommand(**base)  # type: ignore[arg-type]


def _build(
    store: FakeMedallionStore | None = None,
    splitter: WalkForwardSplitter | None = None,
) -> tuple[RunBaselines, FakeAnalyticsRepository]:
    repo = FakeAnalyticsRepository(clock=_FakeClock())
    hasher: Hasher = FakeHasher()
    use_case = RunBaselines(
        store=store if store is not None else _seeded_store(),
        splitter=splitter if splitter is not None else _splitter(),
        forecaster=FakeBaselineForecaster(),
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        hasher=hasher,
    )
    return use_case, repo


# -- happy path (A5-unit / C6) ----------------------------------------------------


@pytest.mark.unit
def test_happy_path_one_summary_and_dim_run_row_per_spec_fold() -> None:
    """5 specs x 2 folds -> 10 summaries e 10 linhas `dim_run` com metadados D5."""
    use_case, repo = _build()

    result = use_case(_command())

    assert len(result.runs) == _N_SPECS * _N_FOLDS
    dim_run = repo.read(layer="silver", table="dim_run")
    assert len(dim_run) == _N_SPECS * _N_FOLDS
    expected_versions = {f"baseline_{s.family}" for s in _command().specs}
    assert {str(r["model_version"]) for r in dim_run} == expected_versions
    assert {str(r["fold"]) for r in dim_run} == {"0", "1"}
    assert all(r["seed"] is None for r in dim_run)
    assert all(r["parent_sweep_id"] == _COHORT_ID for r in dim_run)
    assert all(r["split_fingerprint"] for r in dim_run)
    # run_id dos summaries referenciado 1:1 nas linhas de dim_run (I10).
    assert {s.run_id for s in result.runs} == {str(r["run_id"]) for r in dim_run}


@pytest.mark.unit
def test_happy_path_predictions_long_grid_complete_and_aligned() -> None:
    """Predições LONG: `split="test"`, grade completa por decisão x horizonte, I2."""
    use_case, repo = _build()

    result = use_case(_command())

    rows = repo.read(layer="silver", table="fact_oos_predictions")
    assert rows, "expected persisted prediction rows"
    assert all(r["split"] == "test" for r in rows)
    assert {str(r["model_version"]) for r in rows} == {
        f"baseline_{s.family}" for s in _command().specs
    }
    # Grade completa: cada (run, decisão, horizonte) persistido tem TODOS os níveis.
    grids: dict[tuple[object, ...], set[float]] = {}
    for row in rows:
        key = (row["run_id"], row["decision_idx"], row["horizon"])
        grids.setdefault(key, set()).add(float(str(row["quantile_level"])))
    assert all(levels == set(_LEVELS) for levels in grids.values())
    # I2: target_timestamp_utc = dataset_timestamps[decision_idx + horizon],
    # resolvido exclusivamente pelo persister 4.3 (indexação por sessão).
    iso = [
        datetime(day.year, day.month, day.day, tzinfo=UTC).isoformat() for day in _SESSIONS
    ]
    for row in rows:
        decision_idx = int(str(row["decision_idx"]))
        horizon = int(str(row["horizon"]))
        assert row["timestamp_utc"] == iso[decision_idx]
        assert row["target_timestamp_utc"] == iso[decision_idx + horizon]
    # Contagem exata: nada fabricado além da grade emitida menos os skips (C6).
    written = sum(s.rows_written for s in result.runs)
    assert len(rows) == written


@pytest.mark.unit
def test_c6_tail_decisions_skip_and_count_without_fabricating() -> None:
    """C6: decisões na cauda sem janela completa para h contam em rows_skipped."""
    use_case, repo = _build()

    result = use_case(_command())

    # Último fold: decisões 117/118/119 numa grade de 120 -> h que estoura pula.
    last_fold = [s for s in result.runs if s.fold_index == _N_FOLDS - 1]
    assert all(s.rows_skipped > 0 for s in last_fold)
    # Nenhuma linha fabricada: todo target_timestamp persistido existe na grade.
    rows = repo.read(layer="silver", table="fact_oos_predictions")
    max_pos = _N_SESSIONS - 1
    assert all(int(str(r["decision_idx"])) + int(str(r["horizon"])) <= max_pos for r in rows)


@pytest.mark.unit
def test_i9_run_ids_deterministic_across_invocations() -> None:
    """I9: mesma entrada (estado zerado) -> exatamente os mesmos run_ids."""
    first, _ = _build()
    second, _ = _build()

    runs_a = first(_command()).runs
    runs_b = second(_command()).runs

    assert [(s.run_id, s.model_version, s.fold_index) for s in runs_a] == [
        (s.run_id, s.model_version, s.fold_index) for s in runs_b
    ]


# -- C2: comando inválido ergue ANTES de qualquer I/O -------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"quantile_levels": ()},
        {"quantile_levels": (0.1, 0.9, 0.5)},
        {"quantile_levels": (0.1, 0.5, 1.5)},
        {"quantile_levels": (0.1, 0.1, 0.5)},
        {"horizons": ()},
        {"horizons": (0, 1)},
        {"horizons": (1, 1)},
        {"horizons": (1, 3)},  # max > scope.max_horizon=2
        {"specs": ()},
        {
            "specs": (
                BaselineSpec(family="zero_return"),
                BaselineSpec(family="zero_return"),
            )
        },
    ],
    ids=[
        "levels-empty",
        "levels-not-increasing",
        "levels-out-of-range",
        "levels-duplicated",
        "horizons-empty",
        "horizons-non-positive",
        "horizons-duplicated",
        "horizon-exceeds-max",
        "specs-empty",
        "specs-duplicated-model-version",
    ],
)
def test_c2_invalid_command_raises_before_any_io(overrides: dict[str, object]) -> None:
    """C2: cada validação ergue sem NENHUMA chamada a store/repo."""
    store = _seeded_store()
    use_case, repo = _build(store=store)

    with pytest.raises(ValueError, match=r"C2"):
        use_case(_command(**overrides))

    assert store.read_calls == 0
    assert list(repo.read(layer="silver", table="dim_run")) == []
    assert list(repo.read(layer="silver", table="fact_oos_predictions")) == []


@pytest.mark.unit
def test_c7_empty_dataset_raises() -> None:
    """C7: read devolvendo vazio para o asset do escopo ergue ValueError."""
    empty_store = _CountingStore()  # nada semeado
    use_case, _ = _build(store=empty_store)

    with pytest.raises(ValueError, match=r"C7"):
        use_case(_command())


# -- A6/I6: remoção-zero do dedup (duas camadas) -------------------------------------


class _OverlappingSplitter(WalkForwardSplitter):
    """Stub: devolve folds pré-fabricados com blocos test SOBREPOSTOS (bug de geometria)."""

    def __init__(self, folds: tuple[FoldSplit, ...]) -> None:
        # O calendar do pai não é usado: split é sobrescrito por completo.
        super().__init__(TradingCalendar(TradingSessions(sessions=_SESSIONS)))
        self._folds = folds

    def split(  # noqa: PLR0913 — assinatura do serviço 5.1
        self,
        sessions: Sequence[date],
        scope: ScopeSpec,
        *,
        n_folds: int,
        test_size: int,
        val_size: int,
        calib_size: int,
        embargo: int,
        hasher: Hasher,
    ) -> tuple[FoldSplit, ...]:
        return self._folds


def _fold_with_test(
    fold_index: int, train_end: int, test_slice: slice
) -> FoldSplit:
    """FoldSplit válido (blocos ordenados) com bloco test escolhido a dedo."""
    iso = [day.isoformat() for day in _SESSIONS]
    return FoldSplit(
        fold_index=fold_index,
        train=tuple(iso[:train_end]),
        early_stop=tuple(iso[train_end + 2 : train_end + 5]),
        calib=tuple(iso[train_end + 7 : train_end + 10]),
        test=tuple(iso[test_slice]),
        fingerprint=SplitFingerprint.compute(
            hasher=FakeHasher(),
            train=iso[:train_end],
            val=iso[train_end + 2 : train_end + 5],
            test=iso[test_slice],
            calib=iso[train_end + 7 : train_end + 10],
        ),
    )


@pytest.mark.unit
def test_c9_overlapping_test_blocks_raise_in_dedup_service() -> None:
    """C9 (1ª linha de defesa): duplicata de ponto alinhado ergue no serviço 5.1."""
    overlapping = (
        _fold_with_test(0, train_end=50, test_slice=slice(70, 73)),
        _fold_with_test(1, train_end=55, test_slice=slice(70, 73)),  # MESMO bloco test
    )
    use_case, _ = _build(splitter=_OverlappingSplitter(overlapping))
    command = _command(specs=(BaselineSpec(family="zero_return"),))

    with pytest.raises(ValueError, match=r"ambiguous operationally-latest"):
        use_case(command)


@pytest.mark.unit
def test_i6_assert_zero_removal_helper() -> None:
    """I6 (defesa-em-profundidade): helper puro, testável sem ramo morto."""
    _assert_zero_removal(before=12, after=12)  # não ergue

    with pytest.raises(ValueError, match=r"dedup removed 3 aligned-point entries"):
        _assert_zero_removal(before=12, after=9)


@pytest.mark.unit
def test_i6_wiring_lossy_dedup_raises_through_use_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I6 (wiring pinado): dedup stubado que COLAPSA entradas faz o use case erguer.

    Prova que `_assert_zero_removal` está de fato CHAMADO no fluxo (deletar a
    chamada mata este teste): monkeypatch de `deduplicate_operationally_latest`
    no namespace de `run_baselines` devolvendo menos entradas -> o `ValueError`
    com a mensagem I6 do helper propaga pela invocação normal.
    """
    def _lossy_dedup(
        records: Sequence[object], **_kwargs: object
    ) -> tuple[object, ...]:
        materialized = tuple(records)
        return materialized[:-1]  # colapsa 1 entrada SILENCIOSAMENTE (o bug I6)

    monkeypatch.setattr(
        run_baselines_module, "deduplicate_operationally_latest", _lossy_dedup
    )
    use_case, _ = _build()

    with pytest.raises(ValueError, match=r"dedup removed 1 aligned-point entries"):
        use_case(_command(specs=(BaselineSpec(family="zero_return"),)))
