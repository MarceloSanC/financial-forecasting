"""Unit tests do use case `TrainGbmQuantile` — tudo com fakes (skill `pytest-with-fakes`).

Infra: `FakeMedallionStore` semeado via `seed_read_only`,
`FakeQuantileModelTrainer` (envolto num capturador), `FakeAnalyticsRepository`
(4.2), `FakeHasher` (1.4) e o `WalkForwardSplitter` REAL sobre grade sintética
de dias úteis contíguos (mesma técnica da 5.2). Os retornos codificam o índice
da sessão (`returns[i] = i/1000`) e as features codificam (índice, coluna) —
qualquer deslocamento de partição/label vira diferença numérica detectável.

Prova (concept 5.3 §4/§5/§6; A1/A4-unit/A7/A8):

- happy path: 2 folds -> 1 `GbmRunSummary` e 1 linha `dim_run` por fold com
  `model_version='gbm_quantile'`, `seed` PREENCHIDA (I7), `fold=str(i)`,
  `parent_sweep_id=cohort_id`, `best_iteration_by_horizon` propagado;
  predições LONG com `split="test"`, grade completa por decisão x horizonte e
  `target_timestamp_utc` por índice de sessão (I1/I2, resolvido só pelo 4.3);
- I10: `feature_names` passado ao port == registry enabled + calendário, SEM
  nenhuma coluna excluída (mata o mutante de leakage `target_return`-feature);
- A7/I12: labels == `target_return[idx + h]` do grid completo, exatos; fonte
  máxima de label de train/early_stop < início da partição seguinte; matrizes
  passadas == exatamente as partições do fold (calib NUNCA);
- I6: mutar valores nas sessões de calib não altera nada persistido;
- I3: grade crua cruzada -> persistida ordenada com `guardrail_applied=1`;
- C1/C2/C6 e I8 (`_assert_zero_removal`); I4/I9: run_ids determinísticos;
  cauda sem janela completa -> `rows_skipped` exato, nada fabricado.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
    QuantileTrainingResult,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantile,
    TrainGbmQuantileCommand,
    _assert_zero_removal,
    expected_feature_names,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.domain.services.trading_calendar import (
    TradingCalendar,
)
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )
    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.domain.value_objects.fold_split import (
        FoldSplit,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

# -- grade sintética e comando canônico dos testes -------------------------------

_FRIDAY = 4  # datetime.weekday(): 0=segunda ... 4=sexta
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_N_FOLDS = 2
_TEST_SIZE = 3
_SEED = 42
_MIN_DATA_IN_LEAF = 5
_COHORT_ID = "cohort-h2"
_FEATURE_NAMES = expected_feature_names()

_SCOPE = ScopeSpec(
    asset_id="TEST", feature_set_name="fs_test", max_horizon=2, cohort_id=_COHORT_ID
)


class _FakeClock:
    """Clock determinístico — só para satisfazer o construtor do fake 4.2 (I5)."""

    def now(self) -> datetime:
        return datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)


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


class _CapturingTrainer(FakeQuantileModelTrainer):
    """Fake que registra cada chamada do port (prova I6/I10/A7 por captura)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def train_and_predict(  # noqa: PLR0913 — assinatura do port
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        self.calls.append(
            {
                "feature_names": tuple(feature_names),
                "train_rows": tuple(tuple(r) for r in train_rows),
                "train_labels_by_horizon": {
                    h: tuple(v) for h, v in train_labels_by_horizon.items()
                },
                "early_stop_rows": tuple(tuple(r) for r in early_stop_rows),
                "early_stop_labels_by_horizon": {
                    h: tuple(v) for h, v in early_stop_labels_by_horizon.items()
                },
                "test_rows": tuple(tuple(r) for r in test_rows),
                "test_decision_indices": tuple(test_decision_indices),
            }
        )
        return super().train_and_predict(
            params=params,
            feature_names=feature_names,
            train_rows=train_rows,
            train_labels_by_horizon=train_labels_by_horizon,
            early_stop_rows=early_stop_rows,
            early_stop_labels_by_horizon=early_stop_labels_by_horizon,
            test_rows=test_rows,
            test_decision_indices=test_decision_indices,
            quantile_levels=quantile_levels,
        )


class _CrossedGridTrainer(FakeQuantileModelTrainer):
    """Stub que emite grade DECRESCENTE (cruzada) — prova o guardrail I3."""

    def train_and_predict(  # noqa: PLR0913 — assinatura do port
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        crossed = tuple(0.03 - 0.01 * k for k in range(len(quantile_levels)))
        grids: dict[int, GridByHorizon] = {
            decision_idx: dict.fromkeys(train_labels_by_horizon, crossed)
            for decision_idx in test_decision_indices
        }
        return QuantileTrainingResult(
            grids=grids,
            best_iteration_by_horizon=dict.fromkeys(train_labels_by_horizon, 1),
        )


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
    """`returns[i] = i/1000` — o VALOR codifica o índice (mutação de label vira diff)."""
    return tuple(i / 1000.0 for i in range(n))


def _feature_value(session_idx: int, column_position: int) -> float:
    """Valor determinístico codificando (sessão, coluna) — prova partições exatas."""
    return float(session_idx) + (column_position + 1) / 100.0


def _dataset_rows(
    sessions: Sequence[date],
    returns: Sequence[float],
    *,
    drop_column: str | None = None,
    mutate_indices: frozenset[int] = frozenset(),
) -> list[dict[str, object]]:
    """Rows com TODAS as colunas esperadas + excluídas (prova I10 por presença)."""
    rows: list[dict[str, object]] = []
    for idx, (day, value) in enumerate(zip(sessions, returns, strict=True)):
        shift = 1000.0 if idx in mutate_indices else 0.0
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": value + shift,
            # Colunas excluídas presentes de propósito: I10 exige que NUNCA
            # virem feature mesmo disponíveis no dataset.
            "time_idx": idx,
            "fundamentals_effective_date": None,
        }
        for position, name in enumerate(_FEATURE_NAMES):
            row[name] = _feature_value(idx, position) + shift
        if drop_column is not None:
            row.pop(drop_column)
        rows.append(row)
    return rows


def _seeded_store(rows: list[dict[str, object]] | None = None) -> _CountingStore:
    store = _CountingStore()
    store.seed_read_only(
        layer="processed",
        table="dataset_tft",
        asset=_SCOPE.asset_id,
        rows=rows if rows is not None else _dataset_rows(_SESSIONS, _returns()),
    )
    return store


def _splitter(sessions: tuple[date, ...] = _SESSIONS) -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))


def _folds() -> tuple[FoldSplit, ...]:
    """Folds reais da geometria canônica (mesmos que o use case verá)."""
    return _splitter().split(
        _SESSIONS,
        _SCOPE,
        n_folds=_N_FOLDS,
        test_size=_TEST_SIZE,
        val_size=5,
        calib_size=5,
        embargo=1,
        hasher=FakeHasher(),
    )


def _command(**overrides: object) -> TrainGbmQuantileCommand:
    base: dict[str, object] = {
        "scope": _SCOPE,
        "params": GbmTrainingParams(seed=_SEED, min_data_in_leaf=_MIN_DATA_IN_LEAF),
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
    return TrainGbmQuantileCommand(**base)  # type: ignore[arg-type]


def _build(
    store: FakeMedallionStore | None = None,
    trainer: FakeQuantileModelTrainer | None = None,
) -> tuple[TrainGbmQuantile, FakeAnalyticsRepository]:
    repo = FakeAnalyticsRepository(clock=_FakeClock())
    hasher: Hasher = FakeHasher()
    use_case = TrainGbmQuantile(
        store=store if store is not None else _seeded_store(),
        splitter=_splitter(),
        trainer=trainer if trainer is not None else FakeQuantileModelTrainer(),
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        hasher=hasher,
    )
    return use_case, repo


# -- happy path (A1/A4-unit) -------------------------------------------------------


@pytest.mark.unit
def test_happy_path_one_summary_and_dim_run_row_per_fold() -> None:
    """2 folds -> 2 summaries e 2 linhas `dim_run` com seed PREENCHIDA (I7)."""
    use_case, repo = _build()

    result = use_case(_command())

    assert len(result.runs) == _N_FOLDS
    dim_run = repo.read(layer="silver", table="dim_run")
    assert len(dim_run) == _N_FOLDS
    assert {str(r["model_version"]) for r in dim_run} == {"gbm_quantile"}
    assert {str(r["fold"]) for r in dim_run} == {"0", "1"}
    assert all(r["seed"] == _SEED for r in dim_run)
    assert all(r["parent_sweep_id"] == _COHORT_ID for r in dim_run)
    assert all(r["split_fingerprint"] for r in dim_run)
    assert {s.run_id for s in result.runs} == {str(r["run_id"]) for r in dim_run}
    # best_iteration do fake (=1 por horizonte) propagado verbatim ao Result.
    assert all(
        s.best_iteration_by_horizon == dict.fromkeys(_HORIZONS, 1) for s in result.runs
    )


@pytest.mark.unit
def test_happy_path_predictions_long_grid_complete_and_aligned() -> None:
    """Predições LONG: `split="test"`, grade completa, `target_timestamp` por I1."""
    use_case, repo = _build()

    result = use_case(_command())

    rows = repo.read(layer="silver", table="fact_oos_predictions")
    assert rows, "expected persisted prediction rows"
    assert all(r["split"] == "test" for r in rows)
    assert {str(r["model_version"]) for r in rows} == {"gbm_quantile"}
    grids: dict[tuple[object, ...], set[float]] = {}
    for row in rows:
        key = (row["run_id"], row["decision_idx"], row["horizon"])
        grids.setdefault(key, set()).add(float(str(row["quantile_level"])))
    assert all(levels == set(_LEVELS) for levels in grids.values())
    iso = [
        datetime(day.year, day.month, day.day, tzinfo=UTC).isoformat() for day in _SESSIONS
    ]
    for row in rows:
        decision_idx = int(str(row["decision_idx"]))
        horizon = int(str(row["horizon"]))
        assert row["timestamp_utc"] == iso[decision_idx]
        assert row["target_timestamp_utc"] == iso[decision_idx + horizon]
    written = sum(s.rows_written for s in result.runs)
    assert len(rows) == written


@pytest.mark.unit
def test_tail_decisions_skip_and_count_without_fabricating() -> None:
    """Cauda sem janela completa conta em rows_skipped, nada fabricado (via 4.3)."""
    use_case, repo = _build()

    result = use_case(_command())

    # Último fold: decisões 117/118/119 numa grade de 120 -> h=1 pula em 119;
    # h=2 pula em 118 e 119 => 3 pares (decisão, horizonte) x 3 níveis.
    expected_skips = 3 * len(_LEVELS)
    last = next(s for s in result.runs if s.fold_index == _N_FOLDS - 1)
    assert last.rows_skipped == expected_skips
    assert last.rows_written == len(_HORIZONS) * _TEST_SIZE * len(_LEVELS) - expected_skips
    rows = repo.read(layer="silver", table="fact_oos_predictions")
    max_pos = _N_SESSIONS - 1
    assert all(int(str(r["decision_idx"])) + int(str(r["horizon"])) <= max_pos for r in rows)


# -- I10: feature set exato (mata o mutante de leakage) ----------------------------


@pytest.mark.unit
def test_i10_feature_names_exact_composition_and_exclusions() -> None:
    """`feature_names` == registry enabled (ordem) + calendário; excluídas NUNCA."""
    trainer = _CapturingTrainer()
    use_case, _ = _build(trainer=trainer)

    use_case(_command())

    assert trainer.calls, "expected the port to be called"
    captured = trainer.calls[0]["feature_names"]
    assert captured == _FEATURE_NAMES
    assert captured[-2:] == ("day_of_week", "month")
    excluded = {"timestamp", "asset_id", "fundamentals_effective_date", "target_return", "time_idx"}
    assert excluded.isdisjoint(captured)
    # Sem lista paralela: composição vem do registry (fonte única, 3.4).
    from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (  # noqa: E501, PLC0415
        list_feature_specs,
    )

    assert captured[:-2] == tuple(s.name for s in list_feature_specs(enabled_only=True))


@pytest.mark.unit
def test_i10_matrices_carry_the_exact_partition_feature_values() -> None:
    """Matrizes passadas ao port == valores das partições exatas do fold (I6/I10)."""
    trainer = _CapturingTrainer()
    use_case, _ = _build(trainer=trainer)

    use_case(_command())

    folds = _folds()
    index_by_session = {day.isoformat(): idx for idx, day in enumerate(_SESSIONS)}
    for call, fold in zip(trainer.calls, folds, strict=True):
        for block, partition in (
            ("train_rows", fold.train),
            ("early_stop_rows", fold.early_stop),
            ("test_rows", fold.test),
        ):
            expected = tuple(
                tuple(
                    _feature_value(index_by_session[day], position)
                    for position in range(len(_FEATURE_NAMES))
                )
                for day in partition
            )
            assert call[block] == expected, f"{block} != partição exata do fold"
        assert call["test_decision_indices"] == tuple(
            index_by_session[day] for day in fold.test
        )


# -- A7/I12: alinhamento e anti-leakage dos labels ---------------------------------


@pytest.mark.unit
def test_a7_labels_are_target_return_shifted_exactly_by_horizon() -> None:
    """Labels == `returns[idx + h]` EXATOS (retorno codifica índice — mutação vira diff)."""
    trainer = _CapturingTrainer()
    use_case, _ = _build(trainer=trainer)

    use_case(_command())

    returns = _returns()
    folds = _folds()
    index_by_session = {day.isoformat(): idx for idx, day in enumerate(_SESSIONS)}
    for call, fold in zip(trainer.calls, folds, strict=True):
        for block, partition in (
            ("train_labels_by_horizon", fold.train),
            ("early_stop_labels_by_horizon", fold.early_stop),
        ):
            indices = tuple(index_by_session[day] for day in partition)
            labels_by_horizon = call[block]
            assert isinstance(labels_by_horizon, dict)
            for horizon in _HORIZONS:
                expected = tuple(returns[idx + horizon] for idx in indices)
                assert labels_by_horizon[horizon] == expected
                # Sensibilidade a mutação: o deslocamento t+h-1 difere numericamente.
                mutant = tuple(returns[idx + horizon - 1] for idx in indices)
                assert labels_by_horizon[horizon] != mutant


@pytest.mark.unit
def test_a7_label_sources_never_reach_the_next_partition() -> None:
    """Fontes de label OBSERVADAS na captura < início da partição seguinte.

    Decodifica a sessão-fonte de cada label passado ao port
    (`returns[i] = i/1000` => fonte = round(label*1000)) — inspeciona o que o
    use case FEZ, não a aritmética do splitter (F3, Checkpoint C bloco 1).
    """
    trainer = _CapturingTrainer()
    use_case, _ = _build(trainer=trainer)

    use_case(_command())

    index_by_session = {day.isoformat(): idx for idx, day in enumerate(_SESSIONS)}
    for call, fold in zip(trainer.calls, _folds(), strict=True):
        early_stop_start = index_by_session[fold.early_stop[0]]
        calib_start = index_by_session[fold.calib[0]]
        train_labels = call["train_labels_by_horizon"]
        early_stop_labels = call["early_stop_labels_by_horizon"]
        assert isinstance(train_labels, dict)
        assert isinstance(early_stop_labels, dict)
        for horizon in _HORIZONS:
            train_sources = [round(label * 1000) for label in train_labels[horizon]]
            assert max(train_sources) < early_stop_start
            monitor_sources = [
                round(label * 1000) for label in early_stop_labels[horizon]
            ]
            assert max(monitor_sources) < calib_start


@pytest.mark.unit
def test_fake_trainer_rejects_monitor_without_finite_labels() -> None:
    """Paridade I11/C3 do fake: monitor sem NENHUM label finito ergue (F2, Cb1)."""
    trainer = FakeQuantileModelTrainer()
    params = GbmTrainingParams(seed=_SEED, min_data_in_leaf=1)

    with pytest.raises(ValueError, match=r"monitor.*C3|C3.*monitor|finite-label monitor"):
        trainer.train_and_predict(
            params=params,
            feature_names=("f0",),
            train_rows=((1.0,), (1.0,), (1.0,)),
            train_labels_by_horizon={1: (0.01, 0.02, 0.03)},
            early_stop_rows=((1.0,), (1.0,)),
            early_stop_labels_by_horizon={1: (float("nan"), float("nan"))},
            test_rows=((1.0,),),
            test_decision_indices=(9,),
            quantile_levels=(0.5,),
        )


def _unreachable_calib_indices() -> frozenset[int]:
    """Sessões de calib que NENHUMA entrada do port alcança (em fold algum).

    Com múltiplos folds, labels de early_stop de um fold alcançam o gap de
    purga e podem cair DENTRO do calib de outro fold (sobreposição cross-fold
    inerente ao walk-forward expansivo — achado F1 do Checkpoint C bloco 1).
    A propriedade I6 verdadeira para QUALQUER trainer que honre o contrato é:
    valores de sessões que não alimentam matriz nem label não mudam nada.
    """
    index_by_session = {day.isoformat(): idx for idx, day in enumerate(_SESSIONS)}
    folds = _folds()
    calib = {index_by_session[day] for fold in folds for day in fold.calib}
    reachable: set[int] = set()
    for fold in folds:
        for partition in (fold.train, fold.early_stop, fold.test):
            for day in partition:
                reachable.add(index_by_session[day])  # features passadas ao port
        for partition in (fold.train, fold.early_stop):
            for day in partition:
                for horizon in _HORIZONS:
                    reachable.add(index_by_session[day] + horizon)  # fontes de label
    unreachable = frozenset(calib - reachable)
    assert unreachable, "geometria de teste sem sessão de calib inalcançável"
    return unreachable


@pytest.mark.unit
def test_i6_calib_value_mutation_does_not_change_anything_persisted() -> None:
    """Mutar sessões de calib inalcançáveis pelo port -> mesmíssimas predições."""
    baseline_case, baseline_repo = _build()
    baseline_case(_command())
    mutated_rows = _dataset_rows(
        _SESSIONS, _returns(), mutate_indices=_unreachable_calib_indices()
    )
    mutated_case, mutated_repo = _build(store=_seeded_store(mutated_rows))
    mutated_case(_command())

    baseline_facts = baseline_repo.read(layer="silver", table="fact_oos_predictions")
    mutated_facts = mutated_repo.read(layer="silver", table="fact_oos_predictions")
    assert list(baseline_facts) == list(mutated_facts)


# -- I3: guardrail aplicado sobre grade crua cruzada -------------------------------


@pytest.mark.unit
def test_i3_crossed_raw_grid_is_persisted_rearranged_with_flag() -> None:
    """Grade decrescente do port -> `value_guardrail` crescente, flag=1, raw preservado."""
    use_case, repo = _build(trainer=_CrossedGridTrainer())

    use_case(_command())

    rows = repo.read(layer="silver", table="fact_oos_predictions")
    assert rows
    assert all(int(str(r["guardrail_applied"])) == 1 for r in rows)
    by_key: dict[tuple[object, ...], list[tuple[float, float, float]]] = {}
    for row in rows:
        key = (row["run_id"], row["decision_idx"], row["horizon"])
        by_key.setdefault(key, []).append(
            (
                float(str(row["quantile_level"])),
                float(str(row["value_raw"])),
                float(str(row["value_guardrail"])),
            )
        )
    for grid in by_key.values():
        ordered = sorted(grid)  # por nível crescente
        raw = [value_raw for _, value_raw, _ in ordered]
        guardrail = [value_guardrail for _, _, value_guardrail in ordered]
        assert raw == sorted(raw, reverse=True)  # cru veio decrescente (cruzado)
        assert guardrail == sorted(guardrail)  # rearranjo CFG: crescente


# -- C1/C2/C6: validações ----------------------------------------------------------


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
def test_c2_params_validate_at_construction() -> None:
    """C2-params: o DTO ergue na CONSTRUÇÃO — antes até de existir comando."""
    with pytest.raises(ValueError, match="learning_rate"):
        _command(params=GbmTrainingParams(seed=_SEED, learning_rate=0.0))


@pytest.mark.unit
def test_c1_empty_dataset_raises() -> None:
    """C1: read devolvendo vazio para o asset do escopo ergue ValueError."""
    empty_store = _CountingStore()  # nada semeado
    use_case, _ = _build(store=empty_store)

    with pytest.raises(ValueError, match=r"C1"):
        use_case(_command())


@pytest.mark.unit
def test_c6_missing_expected_feature_column_raises_naming_it() -> None:
    """C6: coluna esperada ausente ergue nomeando a faltante (drift registry x dataset)."""
    dropped = _FEATURE_NAMES[0]
    rows = _dataset_rows(_SESSIONS, _returns(), drop_column=dropped)
    use_case, _ = _build(store=_seeded_store(rows))

    with pytest.raises(ValueError, match=r"C6") as excinfo:
        use_case(_command())

    assert dropped in str(excinfo.value)


# -- I4/I9: determinismo -----------------------------------------------------------


@pytest.mark.unit
def test_i4_run_ids_and_signatures_deterministic_across_invocations() -> None:
    """Mesma entrada (estado zerado) -> mesmos run_ids e best_iterations."""
    first, _ = _build()
    second, _ = _build()

    runs_a = first(_command()).runs
    runs_b = second(_command()).runs

    assert [
        (s.run_id, s.model_version, s.fold_index, dict(s.best_iteration_by_horizon))
        for s in runs_a
    ] == [
        (s.run_id, s.model_version, s.fold_index, dict(s.best_iteration_by_horizon))
        for s in runs_b
    ]


# -- I8: remoção-zero do dedup -----------------------------------------------------


@pytest.mark.unit
def test_i8_assert_zero_removal_helper() -> None:
    """Defesa-em-profundidade: remoção > 0 ergue com a contagem exata."""
    _assert_zero_removal(before=10, after=10)  # não ergue

    with pytest.raises(ValueError, match=r"removed 3 .*I8"):
        _assert_zero_removal(before=10, after=7)
