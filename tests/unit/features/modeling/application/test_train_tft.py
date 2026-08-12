"""Unit tests do use case `TrainTft` — tudo com fakes (skill `pytest-with-fakes`).

Infra: `FakeMedallionStore` semeado via `seed_read_only`, `InMemoryTftTrainer`
(Task 04), `FakeAnalyticsRepository` (4.2), `FakeExperimentTracker` (1.5),
`FakeHasher` (1.4) e o `WalkForwardSplitter` REAL sobre grade sintética de dias
úteis contíguos (mesma técnica de 5.2/5.3). Os retornos codificam o índice da
sessão e as features codificam (índice, coluna) — qualquer deslocamento de
partição vira diferença numérica detectável.

Prova (concept 5.4 §4/§5/§6; A3/A6/A11-parcial):

- happy path: 2 folds -> 1 `TftRunSummary` e 1 linha `dim_run` por fold, com
  `model_version='tft_quantile'` e `seed` PREENCHIDA (I10);
- **A3 (I2 como REGRA):** as duas listas de tipagem saem de `spec.tft_typing`;
  uma spec `known` injetada troca de lista SOZINHA; `time_idx` nunca aparece;
- **A6 (I4/I7):** nenhum índice de `calib` chega ao port como decisão de treino
  ou de monitor — assertado sobre os argumentos capturados da chamada;
- **I16:** o use case persiste exatamente os pares que o port emitiu, e
  `rows_skipped` é ZERO por construção (a condição de emissão do port e a de
  pulo do 4.3 são a mesma desigualdade);
- **I5:** grade crua cruzada -> persistida ordenada. O `InMemoryTftTrainer`
  emite grade monótona por construção, então este caso usa um stub dedicado —
  sem ele a asserção de guardrail seria VÁCUA (achado do Checkpoint C, bloco 1);
- C1/C2 (uma cláusula por teste)/C6 e `_assert_zero_removal` (I11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
    TftTrainingResult,
)
from financial_forecasting.features.modeling.application.use_cases import train_tft as module
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
    TrainTftCommand,
    _assert_zero_removal,
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
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_hasher import FakeHasher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )

pytestmark = pytest.mark.unit

_FRIDAY = 4
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_N_FOLDS = 2
_TEST_SIZE = 3
_VAL_SIZE = 5
_CALIB_SIZE = 5
_EMBARGO = 1
_SEED = 42
_ENCODER_LENGTH = 12
_COHORT_ID = "cohort-h2"
_EXPECTED_MODEL_VERSION = "tft_quantile"
_EXCLUDED_FROM_TYPING = ("time_idx", "timestamp", "asset_id", "target_return")

_SCOPE = ScopeSpec(asset_id="TEST", feature_set_name="fs_test", max_horizon=2, cohort_id=_COHORT_ID)


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _StubSpec:
    """Spec mínima — só o que a regra de tipagem lê (`name`, `tft_typing`)."""

    name: str
    tft_typing: str


class _CrossedGridTrainer(InMemoryTftTrainer):
    """Stub que emite grade DECRESCENTE (cruzada) — prova o guardrail I5.

    O `InMemoryTftTrainer` emite grade monótona por construção, então uma
    asserção de guardrail escrita sobre ele passaria sem provar nada.
    """

    def train_and_predict(self, **kwargs: Any) -> TftTrainingResult:  # noqa: ANN401
        result = super().train_and_predict(**kwargs)
        levels = kwargs["quantile_levels"]
        crossed = tuple(0.03 - 0.01 * position for position in range(len(levels)))
        grids = {
            decision_idx: dict.fromkeys(by_horizon, crossed)
            for decision_idx, by_horizon in result.grids.items()
        }
        return TftTrainingResult(
            grids=grids,
            best_epoch=result.best_epoch,
            best_val_loss=result.best_val_loss,
            val_loss_by_epoch=result.val_loss_by_epoch,
            fitted_decision_count=result.fitted_decision_count,
            monitored_decision_count=result.monitored_decision_count,
            normalizer_center=result.normalizer_center,
            normalizer_scale=result.normalizer_scale,
            artifact_path=result.artifact_path,
        )


class _OutOfRangeGridTrainer(InMemoryTftTrainer):
    """Emite, no ÚLTIMO fold, um par cujo `t + h` cai fora do painel.

    Serve para o contador de pulos do 4.3 ter algo a contar — sem isso
    `rows_skipped` é sempre 0 e um acumulador quebrado passa verde.
    """

    def train_and_predict(self, **kwargs: Any) -> TftTrainingResult:  # noqa: ANN401
        result = super().train_and_predict(**kwargs)
        test_indices = kwargs["test_decision_indices"]
        if not test_indices:
            return result
        last_decision = test_indices[-1]
        longest_horizon = max(kwargs["horizons"])
        if last_decision + longest_horizon <= len(kwargs["target"]) - 1:
            return result  # este fold não toca a cauda; nada a forçar
        grids = {decision: dict(by_h) for decision, by_h in result.grids.items()}
        grids.setdefault(last_decision, {})[longest_horizon] = tuple(
            0.01 * (position + 1) for position in range(len(kwargs["quantile_levels"]))
        )
        return TftTrainingResult(
            grids=grids,
            best_epoch=result.best_epoch,
            best_val_loss=result.best_val_loss,
            val_loss_by_epoch=result.val_loss_by_epoch,
            fitted_decision_count=result.fitted_decision_count,
            monitored_decision_count=result.monitored_decision_count,
            normalizer_center=result.normalizer_center,
            normalizer_scale=result.normalizer_scale,
            artifact_path=result.artifact_path,
        )


class _CountingStore(FakeMedallionStore):
    """Conta leituras — prova que C2 ergue ANTES de qualquer I/O."""

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
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


_SESSIONS = _weekday_sessions(_N_SESSIONS)
_FEATURE_NAMES = unknown_feature_names() + known_feature_names()


def _dataset_rows(
    *, drop_column: str | None = None, none_feature_at: int | None = None
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(_SESSIONS):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": idx / 1000.0,
            # Colunas presentes de propósito: a tipagem NUNCA pode adotá-las.
            "time_idx": idx,
            "fundamentals_effective_date": None,
        }
        for position, name in enumerate(_FEATURE_NAMES):
            row[name] = float(idx) + (position + 1) / 100.0
        if none_feature_at is not None and idx == none_feature_at:
            row[_FEATURE_NAMES[0]] = None
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
        rows=rows if rows is not None else _dataset_rows(),
    )
    return store


def _command(**overrides: object) -> TrainTftCommand:
    base: dict[str, object] = {
        "scope": _SCOPE,
        "params": TftTrainingParams(seed=_SEED, max_encoder_length=_ENCODER_LENGTH, max_epochs=3),
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "n_folds": _N_FOLDS,
        "test_size": _TEST_SIZE,
        "val_size": _VAL_SIZE,
        "calib_size": _CALIB_SIZE,
        "embargo": _EMBARGO,
        "schema_version": 1,
    }
    base.update(overrides)
    return TrainTftCommand(**base)  # type: ignore[arg-type]


def _folds() -> tuple[Any, ...]:
    """Folds reais da geometria dos testes (os mesmos que o use case verá)."""
    splitter = WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS)))
    return splitter.split(
        _SESSIONS,
        _SCOPE,
        n_folds=_N_FOLDS,
        test_size=_TEST_SIZE,
        val_size=_VAL_SIZE,
        calib_size=_CALIB_SIZE,
        embargo=_EMBARGO,
        hasher=FakeHasher(),
    )


def _index_by_session() -> dict[str, int]:
    return {day.isoformat(): idx for idx, day in enumerate(_SESSIONS)}


def _build(
    tmp_path: Path,
    store: FakeMedallionStore | None = None,
    trainer: InMemoryTftTrainer | None = None,
    tracker: Any = None,  # noqa: ANN401 — qualquer dublê do port serve
) -> tuple[TrainTft, FakeAnalyticsRepository, InMemoryTftTrainer, Any]:
    """Constrói o use case JÁ com os dublês — nada é injetado por atributo."""
    repo = FakeAnalyticsRepository(clock=_FakeClock())
    resolved_trainer = trainer if trainer is not None else InMemoryTftTrainer()
    resolved_tracker = tracker if tracker is not None else FakeExperimentTracker()
    use_case = TrainTft(
        store=store if store is not None else _seeded_store(),
        splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
        trainer=resolved_trainer,
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        tracker=resolved_tracker,
        hasher=FakeHasher(),
        artifacts_root=tmp_path / "artifacts",
    )
    return use_case, repo, resolved_trainer, resolved_tracker


# -- happy path -------------------------------------------------------------------


def test_one_summary_and_dim_run_row_per_fold(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path)

    result = use_case(_command())

    assert len(result.runs) == _N_FOLDS
    dim_rows = repo.read(layer="silver", table="dim_run")
    assert len(dim_rows) == _N_FOLDS
    for position, summary in enumerate(result.runs):
        assert summary.model_version == _EXPECTED_MODEL_VERSION
        assert summary.fold_index == position
    for row in dim_rows:
        assert row["model_version"] == _EXPECTED_MODEL_VERSION
        assert row["seed"] == _SEED  # I10 — seed PREENCHIDA
        assert row["parent_sweep_id"] == _COHORT_ID


def test_artifact_dir_is_derived_from_artifacts_root_and_run_id(tmp_path: Path) -> None:
    """D9: a origem do `artifact_dir` é o use case, não o adapter."""
    use_case, _, trainer, _ = _build(tmp_path)

    result = use_case(_command())

    expected = tmp_path / "artifacts" / "tft" / result.runs[-1].run_id
    assert trainer.last_call["artifact_dir"] == str(expected)


# -- A3: tipagem como REGRA (I2/D4) ------------------------------------------------


def test_unknown_list_is_exactly_the_registry_unknown_specs() -> None:
    from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (  # noqa: E501, PLC0415
        list_feature_specs,
    )

    expected = tuple(
        spec.name for spec in list_feature_specs(enabled_only=True) if spec.tft_typing == "unknown"
    )
    assert unknown_feature_names() == expected


def test_known_list_is_calendar_when_registry_has_no_known_spec() -> None:
    assert known_feature_names() == ("day_of_week", "month")


def test_registry_known_spec_moves_to_the_known_list_on_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A regra é `spec.tft_typing`, não a fotografia de hoje.

    Registrar uma spec `known` amanhã tem de mover a coluna sozinha — se este
    teste falhar, alguém trocou a regra por uma lista paralela.
    """
    specs = (
        _StubSpec(name="close_return", tft_typing="unknown"),
        _StubSpec(name="is_holiday_eve", tft_typing="known"),
    )
    monkeypatch.setattr(module, "list_feature_specs", lambda **_: specs)

    assert unknown_feature_names() == ("close_return",)
    assert known_feature_names() == ("is_holiday_eve", "day_of_week", "month")


@pytest.mark.parametrize("column", _EXCLUDED_FROM_TYPING)
def test_excluded_columns_never_enter_either_typing_list(column: str) -> None:
    """`time_idx` é índice do painel, não covariável (D4/ADR 5.3.0003)."""
    assert column not in unknown_feature_names()
    assert column not in known_feature_names()


def test_port_receives_known_names_as_a_subset_of_feature_names(tmp_path: Path) -> None:
    use_case, _, trainer, _ = _build(tmp_path)

    use_case(_command())

    feature_names = trainer.last_call["feature_names"]
    known_names = trainer.last_call["known_feature_names"]
    assert set(known_names) <= set(feature_names)
    assert feature_names == unknown_feature_names() + known_feature_names()


# -- A6: calib fora de treino e monitor (I4/I7) ------------------------------------


def test_decision_ranges_match_each_fold_exactly(tmp_path: Path) -> None:
    """Igualdade por fold, não apenas disjunção no último.

    Assertar só "calib não intersecta" no ÚLTIMO fold deixa passar duas
    mutações com forma de vazamento: monitorar sobre o próprio treino, e usar
    `calib` como monitor apenas no fold 0. Por isso aqui se exige **igualdade**
    das três faixas, em **todos** os folds.
    """
    use_case, _, trainer, _ = _build(tmp_path)
    index_by_session = _index_by_session()
    folds = _folds()

    use_case(_command())

    assert len(trainer.calls) == len(folds)
    for fold, call in zip(folds, trainer.calls, strict=True):
        expected_train = tuple(index_by_session[day] for day in fold.train)
        expected_monitor = tuple(index_by_session[day] for day in fold.early_stop)
        expected_test = tuple(index_by_session[day] for day in fold.test)
        calib_indices = {index_by_session[day] for day in fold.calib}

        assert call["train_decision_indices"] == expected_train
        assert call["early_stop_decision_indices"] == expected_monitor
        assert call["test_decision_indices"] == expected_test
        assert not (calib_indices & set(expected_train))
        assert not (calib_indices & set(expected_monitor))


def test_monitored_decision_count_is_reported_per_fold(tmp_path: Path) -> None:
    """I17 — a contagem efetiva do monitor chega ao summary, não fica no port."""
    use_case, _, _, _ = _build(tmp_path)

    result = use_case(_command())

    assert all(summary.monitored_decision_count == _VAL_SIZE for summary in result.runs)
    assert all(summary.fitted_decision_count > 0 for summary in result.runs)


# -- I16: nada fabricado, nada pulado ----------------------------------------------


def test_rows_skipped_is_zero_because_the_port_emits_only_valid_pairs(
    tmp_path: Path,
) -> None:
    """A condição de emissão do port e a de pulo do 4.3 são a MESMA desigualdade."""
    use_case, _, _, _ = _build(tmp_path)

    result = use_case(_command())

    assert all(summary.rows_skipped == 0 for summary in result.runs)
    assert all(summary.rows_written > 0 for summary in result.runs)


def test_out_of_range_pair_from_the_port_is_counted_as_skipped(tmp_path: Path) -> None:
    """O contador de pulos é REAL, não uma constante zero.

    Sem este caso, `rows_skipped` sempre valeria 0 e um acumulador quebrado
    passaria despercebido — o zero do teste acima não discrimina "o port só
    emitiu pares válidos" de "o contador está morto".
    """
    use_case, _, _, _ = _build(tmp_path, trainer=_OutOfRangeGridTrainer())

    result = use_case(_command())

    assert sum(summary.rows_skipped for summary in result.runs) == len(_LEVELS)


def test_last_fold_emits_fewer_pairs_for_the_longer_horizon(tmp_path: Path) -> None:
    """Cauda do painel: h=2 perde uma decisão que h=1 mantém (I16)."""
    use_case, repo, _, _ = _build(tmp_path)

    result = use_case(_command())

    last_run_id = result.runs[-1].run_id
    rows = [
        row
        for row in repo.read(layer="silver", table="fact_oos_predictions")
        if row["run_id"] == last_run_id
    ]
    shorter_horizon, longer_horizon = _HORIZONS
    decisions_h1 = {
        row["target_timestamp_utc"] for row in rows if row["horizon"] == shorter_horizon
    }
    decisions_h2 = {row["target_timestamp_utc"] for row in rows if row["horizon"] == longer_horizon}
    assert len(decisions_h1) > len(decisions_h2)


# -- I5: guardrail --------------------------------------------------------------


def test_crossed_grid_is_persisted_sorted(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path, trainer=_CrossedGridTrainer())

    use_case(_command())

    rows = repo.read(layer="silver", table="fact_oos_predictions")
    by_key: dict[tuple[object, object, object], list[tuple[float, float]]] = {}
    for row in rows:
        key = (row["run_id"], row["target_timestamp_utc"], row["horizon"])
        by_key.setdefault(key, []).append(
            (float(row["quantile_level"]), float(row["value_guardrail"]))
        )
    assert by_key
    for grid in by_key.values():
        values = [value for _, value in sorted(grid)]
        assert values == sorted(values)
    # O guardrail precisa ter SIDO aplicado: se a flag vier 0, a grade saiu
    # ordenada por acaso e o teste não provou o rearranjo.
    assert all(row["guardrail_applied"] == 1 for row in rows)


# -- casos de erro ----------------------------------------------------------------


def test_empty_dataset_raises(tmp_path: Path) -> None:
    store = _CountingStore()
    store.seed_read_only(layer="processed", table="dataset_tft", asset=_SCOPE.asset_id, rows=[])
    use_case, _, _, _ = _build(tmp_path, store=store)

    with pytest.raises(ValueError, match="C1"):
        use_case(_command())


def test_missing_expected_column_raises_naming_it(tmp_path: Path) -> None:
    dropped = unknown_feature_names()[0]
    use_case, _, _, _ = _build(tmp_path, store=_seeded_store(_dataset_rows(drop_column=dropped)))

    with pytest.raises(ValueError, match=dropped):
        use_case(_command())


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"horizons": ()}, id="horizons-vazio"),
        pytest.param({"horizons": (1, 1)}, id="horizons-duplicado"),
        pytest.param({"horizons": (0, 1)}, id="horizonte-abaixo-de-1"),
        pytest.param({"horizons": (1, 5)}, id="horizonte-acima-do-max-do-scope"),
        pytest.param({"quantile_levels": ()}, id="niveis-vazio"),
        pytest.param({"quantile_levels": (0.0, 0.5)}, id="nivel-fora-do-intervalo"),
        pytest.param({"quantile_levels": (0.5, 0.1)}, id="niveis-nao-crescentes"),
    ],
)
def test_invalid_command_raises_before_any_io(tmp_path: Path, overrides: dict[str, object]) -> None:
    """C2 — uma cláusula por caso, e nenhuma leitura acontece."""
    store = _seeded_store()
    use_case, _, _, _ = _build(tmp_path, store=store)

    with pytest.raises(ValueError, match="C2"):
        use_case(_command(**overrides))

    assert store.read_calls == 0


# -- I11 ---------------------------------------------------------------------------


def test_persisted_rows_pin_the_schema_columns(tmp_path: Path) -> None:
    """`split`, `schema_version` e identidade do cohort não podem derivar."""
    use_case, repo, _, _ = _build(tmp_path)

    use_case(_command())

    rows = repo.read(layer="silver", table="fact_oos_predictions")
    assert rows
    for row in rows:
        assert row["split"] == "test"
        assert row["schema_version"] == 1
        assert row["model_version"] == _EXPECTED_MODEL_VERSION
        assert row["asset"] == _SCOPE.asset_id
        assert row["feature_set_name"] == _SCOPE.feature_set_name


def test_typing_is_part_of_the_run_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I10 — mover uma spec de `unknown` para `known` MUDA o run_id.

    **A escolha de QUAL spec mover é o teste.** `feature_names` é
    `unknown_names + known_names`, então mover uma spec do MEIO do bloco
    `unknown` também muda a ORDEM da lista — e o run_id passaria a diferir por
    causa da ordem, com `known_feature_names` fora do payload. Uma versão
    anterior deste teste movia a primeira coluna e por isso não distinguia as
    duas hipóteses: era verde mesmo sem a tipagem na identidade.

    Movendo a ÚLTIMA spec `unknown`, ela cai imediatamente antes do calendário
    e a lista concatenada fica **byte a byte idêntica** nos dois cenários — a
    asserção do meio prova isso. Aí a única diferença possível entre os dois
    run_id é a tipagem, e é este o cenário de colisão real: dois modelos com o
    mesmo conjunto de colunas e tipagens diferentes (o que I2 declara ser
    mudança viva, não hipotética) indistinguíveis na identidade persistida —
    `DuplicateKeyError` no armazém append-only no melhor caso, e dois modelos
    diferentes com o mesmo `run_id` no cohort da 5.5 no pior.
    """
    columns = _FEATURE_NAMES[:3]
    all_unknown = tuple(_StubSpec(name=name, tft_typing="unknown") for name in columns)
    last_known = (
        *(_StubSpec(name=name, tft_typing="unknown") for name in columns[:-1]),
        _StubSpec(name=columns[-1], tft_typing="known"),
    )

    def _run_with(
        specs: tuple[_StubSpec, ...], directory: Path
    ) -> tuple[str, str, tuple[str, ...]]:
        monkeypatch.setattr(module, "list_feature_specs", lambda **_: specs)
        use_case, repo, trainer, _ = _build(directory)
        run_id = use_case(_command()).runs[0].run_id
        signature = next(
            str(row["config_signature"])
            for row in repo.read(layer="silver", table="dim_run")
            if row["run_id"] == run_id
        )
        return run_id, signature, tuple(trainer.calls[0]["feature_names"])

    first, first_signature, first_columns = _run_with(all_unknown, tmp_path / "a")
    second, second_signature, second_columns = _run_with(last_known, tmp_path / "b")

    # Sem esta asserção o teste não separa "a tipagem entra na identidade" de
    # "a ordem das colunas mudou".
    assert first_columns == second_columns
    assert first != second
    # `config_signature` tem a MESMA forma e o mesmo risco: é por ela que a 5.5
    # reconhece "mesma configuração" ao compor o cohort.
    assert first_signature != second_signature


def test_emission_outside_the_requested_range_raises(tmp_path: Path) -> None:
    """D5 — o use case não persiste decisão que ele não pediu."""

    class _RogueTrainer(InMemoryTftTrainer):
        def train_and_predict(self, **kwargs: Any) -> TftTrainingResult:  # noqa: ANN401
            result = super().train_and_predict(**kwargs)
            grids = dict(result.grids)
            grids[0] = {1: tuple(0.0 for _ in kwargs["quantile_levels"])}
            return TftTrainingResult(
                grids=grids,
                best_epoch=result.best_epoch,
                best_val_loss=result.best_val_loss,
                val_loss_by_epoch=result.val_loss_by_epoch,
                fitted_decision_count=result.fitted_decision_count,
                monitored_decision_count=result.monitored_decision_count,
                normalizer_center=result.normalizer_center,
                normalizer_scale=result.normalizer_scale,
                artifact_path=result.artifact_path,
            )

    use_case, _, _, _ = _build(tmp_path, trainer=_RogueTrainer())

    with pytest.raises(ValueError, match="outside the requested test range"):
        use_case(_command())


def test_none_feature_reaches_the_port_as_nan(tmp_path: Path) -> None:
    """Política de ausência: `None` no dataset vira NaN na fronteira do port."""
    use_case, _, trainer, _ = _build(
        tmp_path, store=_seeded_store(_dataset_rows(none_feature_at=0))
    )

    use_case(_command())

    value = trainer.calls[0]["rows"][0][0]
    assert value != value  # NaN != NaN  # noqa: PLR0124


def test_zero_removal_guard_raises_when_dedup_removed_entries() -> None:
    with pytest.raises(ValueError, match="I11"):
        _assert_zero_removal(before=10, after=9)


def test_zero_removal_guard_is_silent_when_nothing_was_removed() -> None:
    _assert_zero_removal(before=10, after=10)
