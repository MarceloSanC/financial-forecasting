"""Use case `TrainGbmQuantile` — GBM quantílico sob o harness walk-forward.

Orquestra (concept 5.3 §4, fluxo por referência — é o contrato): lê o dataset
TFT via `MedallionStore` (par read-only `("processed", "dataset_tft")`), fixa o
conjunto de features (registry 3.4 + calendário — I10/ADR 5.3.0003), gera folds
via `WalkForwardSplitter` (5.1), monta matrizes e labels por horizonte do grid
COMPLETO de sessões (I1/I12 — `target_return[idx + h]`, nunca NaN-padded),
invoca o `QuantileModelTrainer` uma vez por fold (K x H boosters no adapter —
ADR 5.3.0001), aplica o guardrail via `QuantileForecast.from_raw` (4.3, I3),
registra 1 `RunRecord` por fold em `dim_run` (I7 — `seed` PREENCHIDA, primeiro
produtor com semente não nula), aplica o dedup operationally-latest (5.1) com
chave ESTRUTURAL e **remoção-zero assertada** (I8) e persiste as predições LONG
via `PersistPredictions` (4.3) com `model_version='gbm_quantile'` e
`split="test"`.

**Imports cross-BC (decisão consciente, precedentes rastreados):**
`modeling.application -> analytics_store.application` segue a justificativa por
referência do `run_baselines.py` (5.2 §8 — dono único do `target_timestamp`,
ADR 4.3.0001); `modeling.application -> feature_engineering.domain`
(`list_feature_specs`) é consumo declarado no roadmap 5.3
(`contratos_consumidos: FeatureRegistry`) — import application -> domain
cross-BC preserva a direção inward e nenhum contrato do `.importlinter` o
proíbe.

Invariantes materializadas aqui (concept §5):

- **I2/I1 — alinhamento por sessão:** só aritmética de índices; quem resolve
  `target_timestamp_utc` é exclusivamente o persister 4.3.
- **I6 — calib intocada:** o port recebe APENAS train/early_stop/test; a
  partição calib não alimenta matriz, label nem monitor (reservada ao
  conformal do Step 7 — ADR 5.1.0002).
- **I10 — feature set fixo:** registry `enabled_only=True` na ordem de
  inserção + `day_of_week` + `month`; `timestamp`/`asset_id`/
  `fundamentals_effective_date`/`target_return`/`time_idx` NUNCA viram
  feature (anti-leakage/ADR 5.3.0003); a tupla ordenada entra nos payloads
  de `run_id`/`config_signature` (I7 — auditabilidade do desenho).
- **I8 — 1 obs por ponto alinhado:** mesma chave estrutural e mesma asserção
  de remoção-zero da 5.2.
- **I4 — determinismo:** sem clock/aleatoriedade própria; a semente é a do
  comando e os hashes são canônicos via `Hasher` (1.4).

Casos de erro (concept §6): C1 (dataset vazio ergue), C2 (comando inválido
ergue ANTES de qualquer I/O; params já validados na construção do DTO),
C6 (coluna esperada ausente ergue nomeando as faltantes), C7
(`DuplicateKeyError` propaga no rerun idêntico — semântica de replay é desenho
da 5.5); C3/C4/C5 erguem no trainer (port).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from typing import TYPE_CHECKING

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)
from financial_forecasting.features.modeling.domain.services.operationally_latest_dedup import (
    deduplicate_operationally_latest,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        AnalyticsRepository,
    )
    from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
        PersistPredictions,
    )
    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        GbmTrainingParams,
        QuantileModelTrainer,
        QuantileTrainingResult,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.features.modeling.domain.value_objects.fold_split import (
        FoldSplit,
    )
    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
        ScopeSpec,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
        Row,
    )

_DATASET_LAYER = "processed"
_DATASET_TABLE = "dataset_tft"
_SILVER_LAYER = "silver"
_DIM_RUN_TABLE = "dim_run"
_SPLIT = "test"
_MODEL_VERSION = "gbm_quantile"

# Colunas de calendário incluídas como ordinais (ADR 5.3.0003 — paridade com o
# TFT known covariates) e colunas do dataset que NUNCA viram feature (I10).
_CALENDAR_FEATURES = ("day_of_week", "month")
_EXCLUDED_COLUMNS = frozenset(
    {"timestamp", "asset_id", "fundamentals_effective_date", "target_return", "time_idx"}
)

# Entrada estrutural do dedup (I8): (split, horizon, decision_idx + horizon,
# quantile_level) é a chave de alinhamento; o último campo (decision_idx) é o rank.
_StructuralEntry = tuple[str, int, int, float, int]
_ALIGNMENT_KEY_WIDTH = 4


@dataclass(frozen=True)
class TrainGbmQuantileCommand:
    """DTO de entrada — cohort, params pré-registrados, grade e geometria.

    Campos (concept §4):
        scope: identidade do cohort (`asset_id`, `feature_set_name`,
            `max_horizon`, `cohort_id`).
        params: hiperparâmetros pré-registrados + seed (validados na
            construção do próprio `GbmTrainingParams` — C2-params).
        horizons: horizontes de previsão (ex.: `(1, 7)`);
            `max(horizons) <= scope.max_horizon`.
        quantile_levels: grade densa comum do cohort (crescente, única, em (0, 1)).
        n_folds / test_size / val_size / calib_size / embargo: geometria do
            `WalkForwardSplitter` (5.1) — validada pelo próprio splitter.
        schema_version: versão dos schemas silver gravados.
    """

    scope: ScopeSpec
    params: GbmTrainingParams
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    n_folds: int
    test_size: int
    val_size: int
    calib_size: int
    embargo: int
    schema_version: int


@dataclass(frozen=True)
class GbmRunSummary:
    """DTO de saída — agregado de um fold persistido + iteração selecionada."""

    run_id: str
    model_version: str
    fold_index: int
    rows_written: int
    rows_skipped: int
    best_iteration_by_horizon: Mapping[int, int]


@dataclass(frozen=True)
class TrainGbmQuantileResult:
    """DTO de saída — um `GbmRunSummary` por fold."""

    runs: tuple[GbmRunSummary, ...]


def _assert_zero_removal(*, before: int, after: int) -> None:
    """Defesa-em-profundidade de I8: o dedup NUNCA pode ter removido entradas.

    Mesma prova da 5.2: com horizon fixo na chave, mesmo
    `decision_idx + horizon` => mesmo `decision_idx`, então toda duplicata real
    empata chave+rank e ergue ANTES no serviço 5.1 (C9). Este helper fica
    atrás como segunda camada — duplicata de ponto alinhado é bug de geometria
    a montante, nunca silenciável.
    """
    if before != after:
        raise ValueError(
            f"dedup removed {before - after} aligned-point entries — "
            "upstream fold geometry bug (I8)"
        )


def expected_feature_names() -> tuple[str, ...]:
    """Conjunto e ordem canônicos das features do GBM (I10/ADR 5.3.0003).

    Registry `enabled_only=True` na ordem de inserção (fonte única, 3.4) +
    calendário ordinal. Público de propósito: os testes pinam a composição
    contra esta função, e ela contra o registry — sem lista paralela.
    """
    registry_names = tuple(spec.name for spec in list_feature_specs(enabled_only=True))
    return registry_names + _CALENDAR_FEATURES


class TrainGbmQuantile:
    """Use case que treina e persiste o GBM quantílico sob o harness 5.1."""

    def __init__(  # noqa: PLR0913 — portas coesas do fluxo (concept §4)
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        trainer: QuantileModelTrainer,
        persist_predictions: PersistPredictions,
        analytics_repository: AnalyticsRepository,
        hasher: Hasher,
    ) -> None:
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._persist_predictions = persist_predictions
        self._analytics_repository = analytics_repository
        self._hasher = hasher

    def __call__(self, command: TrainGbmQuantileCommand) -> TrainGbmQuantileResult:
        """Executa o fluxo por fold e devolve um summary por fold (ver módulo)."""
        _validate_command(command)  # C2 — antes de qualquer I/O
        feature_names = expected_feature_names()

        dataset_timestamps, returns, sessions, feature_rows = self._load_dataset(
            command.scope, feature_names
        )  # C1/C6
        folds = self._splitter.split(
            sessions,
            command.scope,
            n_folds=command.n_folds,
            test_size=command.test_size,
            val_size=command.val_size,
            calib_size=command.calib_size,
            embargo=command.embargo,
            hasher=self._hasher,
        )
        index_by_session = {day.isoformat(): idx for idx, day in enumerate(sessions)}

        summaries: list[GbmRunSummary] = []
        entries: list[_StructuralEntry] = []
        emissions: list[tuple[FoldSplit, str, dict[int, dict[int, QuantileForecast]], Mapping[int, int]]] = []  # noqa: E501

        for fold in folds:
            training = self._train_fold(
                command=command,
                fold=fold,
                index_by_session=index_by_session,
                returns=returns,
                feature_rows=feature_rows,
                feature_names=feature_names,
            )
            decision_indices = tuple(index_by_session[day] for day in fold.test)
            forecasts_by_decision: dict[int, dict[int, QuantileForecast]] = {}
            for decision_idx in decision_indices:
                grids = training.grids[decision_idx]
                forecasts_by_decision[decision_idx] = {
                    horizon: QuantileForecast.from_raw(
                        levels=command.quantile_levels,
                        raw_values=tuple(grids[horizon]),
                    )
                    for horizon in command.horizons
                }  # guardrail 4.3 (I3) — rearranjo CFG por decisão x horizonte
                entries.extend(
                    (_SPLIT, horizon, decision_idx + horizon, level, decision_idx)
                    for horizon in command.horizons
                    for level in command.quantile_levels
                )

            run_id = self._hasher.hash_mapping(_run_payload(command, feature_names, fold))
            self._write_dim_run(command, feature_names, fold, run_id)
            emissions.append(
                (fold, run_id, forecasts_by_decision, training.best_iteration_by_horizon)
            )

        # I8 (duas camadas): duplicata real empata chave+rank e ergue no próprio
        # serviço 5.1 (C9); a remoção-zero fica atrás como defesa-em-profundidade.
        deduped = deduplicate_operationally_latest(
            entries,
            alignment_key=lambda entry: entry[:_ALIGNMENT_KEY_WIDTH],
            operational_rank=lambda entry: entry[4],
        )
        _assert_zero_removal(before=len(entries), after=len(deduped))

        for fold, run_id, forecasts_by_decision, best_iterations in emissions:
            rows_written = 0
            rows_skipped = 0
            for decision_idx, forecasts in forecasts_by_decision.items():
                result = self._persist_predictions(
                    PersistPredictionsCommand(
                        run_id=run_id,
                        split=_SPLIT,
                        model_version=_MODEL_VERSION,
                        asset=command.scope.asset_id,
                        feature_set_name=command.scope.feature_set_name,
                        schema_version=command.schema_version,
                        decision_idx=decision_idx,
                        dataset_timestamps=dataset_timestamps,
                        forecasts=forecasts,
                    )
                )  # janela incompleta pula e conta DENTRO do 4.3; C7 propaga
                rows_written += result.rows_written
                rows_skipped += result.rows_skipped
            summaries.append(
                GbmRunSummary(
                    run_id=run_id,
                    model_version=_MODEL_VERSION,
                    fold_index=fold.fold_index,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    best_iteration_by_horizon=dict(best_iterations),
                )
            )
        return TrainGbmQuantileResult(runs=tuple(summaries))

    # -- leitura do dataset (C1/C6) ---------------------------------------------

    def _load_dataset(
        self, scope: ScopeSpec, feature_names: tuple[str, ...]
    ) -> tuple[tuple[str, ...], tuple[float, ...], tuple[date, ...], tuple[tuple[float, ...], ...]]:
        """Lê o dataset TFT: (timestamps ISO, target_return, sessões, matriz)."""
        rows = self._store.read(
            layer=_DATASET_LAYER, table=_DATASET_TABLE, filters={"asset": scope.asset_id}
        )
        if not rows:
            raise ValueError(
                f"dataset ({_DATASET_LAYER!r}, {_DATASET_TABLE!r}) is empty for "
                f"asset {scope.asset_id!r} — nothing to train (C1)"
            )
        # C6: presença NOMINAL das colunas esperadas (registry x dataset drift).
        # `row.get(...) is None` não distingue "coluna ausente" de "NaN legítimo";
        # a presença é checada por chave na primeira row (schema homogêneo do
        # parquet — todas as rows saem do mesmo arquivo/SELECT *).
        missing = tuple(name for name in feature_names if name not in rows[0])
        if missing:
            raise ValueError(
                f"dataset is missing expected feature columns {missing!r} — "
                "registry x dataset drift (C6)"
            )
        parsed = sorted(
            (
                (
                    _timestamp_of(row),
                    _target_return_of(row),
                    tuple(_feature_value_of(row, name) for name in feature_names),
                )
                for row in rows
            ),
            key=lambda triple: triple[0],
        )
        dataset_timestamps = tuple(ts.isoformat() for ts, _, _ in parsed)
        returns = tuple(value for _, value, _ in parsed)
        sessions = tuple(ts.date() for ts, _, _ in parsed)
        feature_rows = tuple(features for _, _, features in parsed)
        return dataset_timestamps, returns, sessions, feature_rows

    # -- treino de um fold (I1/I6/I12) ------------------------------------------

    def _train_fold(  # noqa: PLR0913 — estado coeso de um fold (concept §4)
        self,
        *,
        command: TrainGbmQuantileCommand,
        fold: FoldSplit,
        index_by_session: Mapping[str, int],
        returns: tuple[float, ...],
        feature_rows: tuple[tuple[float, ...], ...],
        feature_names: tuple[str, ...],
    ) -> QuantileTrainingResult:
        """Monta matrizes/labels do fold e delega ao port (calib NUNCA — I6)."""
        train_indices = tuple(index_by_session[day] for day in fold.train)
        early_stop_indices = tuple(index_by_session[day] for day in fold.early_stop)
        decision_indices = tuple(index_by_session[day] for day in fold.test)

        return self._trainer.train_and_predict(
            params=command.params,
            feature_names=feature_names,
            train_rows=tuple(feature_rows[idx] for idx in train_indices),
            train_labels_by_horizon={
                horizon: _labels_from_full_grid(train_indices, returns, horizon)
                for horizon in command.horizons
            },
            early_stop_rows=tuple(feature_rows[idx] for idx in early_stop_indices),
            early_stop_labels_by_horizon={
                horizon: _labels_from_full_grid(early_stop_indices, returns, horizon)
                for horizon in command.horizons
            },
            test_rows=tuple(feature_rows[idx] for idx in decision_indices),
            test_decision_indices=decision_indices,
            quantile_levels=command.quantile_levels,
        )

    def _write_dim_run(
        self,
        command: TrainGbmQuantileCommand,
        feature_names: tuple[str, ...],
        fold: FoldSplit,
        run_id: str,
    ) -> None:
        """Grava 1 `RunRecord` por fold em `dim_run` — `seed` PREENCHIDA (I7)."""
        record = RunRecord(
            run_id=run_id,
            asset=command.scope.asset_id,
            parent_sweep_id=command.scope.cohort_id,
            feature_set_name=command.scope.feature_set_name,
            config_signature=self._hasher.hash_mapping(
                _config_payload(command, feature_names)
            ),
            split_fingerprint=fold.fingerprint.value,
            fold=str(fold.fold_index),
            seed=command.params.seed,
            model_version=_MODEL_VERSION,
            schema_version=command.schema_version,
        )
        rows: list[Row] = [asdict(record)]
        # O adapter injeta `created_at_utc` write-time (4.2 I5).
        self._analytics_repository.write(layer=_SILVER_LAYER, table=_DIM_RUN_TABLE, rows=rows)


# -- labels do grid completo (I1/I12) ----------------------------------------------


def _labels_from_full_grid(
    indices: tuple[int, ...], returns: tuple[float, ...], horizon: int
) -> tuple[float, ...]:
    """`target_return[idx + horizon]` do array COMPLETO de sessões (I1/I12).

    A geometria do splitter 5.1 (gap = max_horizon + embargo) garante que todo
    label de train/early_stop cai no máximo dentro do gap de purga; estourar o
    grid aqui é bug de chamador, nunca NaN-padding silencioso.
    """
    labels: list[float] = []
    for idx in indices:
        target = idx + horizon
        if target >= len(returns):
            raise ValueError(
                f"label index {target} (decision {idx} + horizon {horizon}) beyond "
                f"session grid of {len(returns)} — splitter geometry bug (I12)"
            )
        labels.append(returns[target])
    return tuple(labels)


# -- validação do comando (C2) ---------------------------------------------------


def _validate_command(command: TrainGbmQuantileCommand) -> None:
    """C2: comando inválido ergue `ValueError` ANTES de qualquer I/O.

    `params` já se auto-valida na construção (`GbmTrainingParams.__post_init__`).
    """
    levels = command.quantile_levels
    if not levels:
        raise ValueError("quantile_levels must be non-empty (C2)")
    if any(not 0.0 < tau < 1.0 for tau in levels):
        raise ValueError(f"quantile_levels must all be in (0, 1); got {levels} (C2)")
    if any(b <= a for a, b in pairwise(levels)):
        raise ValueError(
            f"quantile_levels must be strictly increasing and unique; got {levels} (C2)"
        )

    if not command.horizons:
        raise ValueError("horizons must be non-empty (C2)")
    if any(h < 1 for h in command.horizons):
        raise ValueError(f"horizons must all be >= 1; got {command.horizons} (C2)")
    if len(set(command.horizons)) != len(command.horizons):
        raise ValueError(f"horizons must be unique; got {command.horizons} (C2)")
    if max(command.horizons) > command.scope.max_horizon:
        raise ValueError(
            f"max(horizons)={max(command.horizons)} exceeds "
            f"scope.max_horizon={command.scope.max_horizon} (C2)"
        )


# -- payloads canônicos (I4/I7) ----------------------------------------------------


def _params_payload(params: GbmTrainingParams) -> dict[str, object]:
    """Campos dos params como payload canônico (identidade da configuração)."""
    return {
        "seed": params.seed,
        "num_boost_round_max": params.num_boost_round_max,
        "num_leaves": params.num_leaves,
        "learning_rate": params.learning_rate,
        "min_data_in_leaf": params.min_data_in_leaf,
        "model_version": _MODEL_VERSION,
    }


def _config_payload(
    command: TrainGbmQuantileCommand, feature_names: tuple[str, ...]
) -> dict[str, object]:
    """Payload do `config_signature`: params + features + grade + schema (I7)."""
    return {
        "params": _params_payload(command.params),
        "feature_names": list(feature_names),
        "horizons": list(command.horizons),
        "quantile_levels": list(command.quantile_levels),
        "schema_version": command.schema_version,
    }


def _run_payload(
    command: TrainGbmQuantileCommand,
    feature_names: tuple[str, ...],
    fold: FoldSplit,
) -> dict[str, object]:
    """Payload do `run_id`: scope + params + features + fingerprint + fold (I7)."""
    return {
        "scope": {
            "asset_id": command.scope.asset_id,
            "feature_set_name": command.scope.feature_set_name,
            "max_horizon": command.scope.max_horizon,
            "cohort_id": command.scope.cohort_id,
        },
        "params": _params_payload(command.params),
        "feature_names": list(feature_names),
        "split_fingerprint": fold.fingerprint.value,
        "fold_index": fold.fold_index,
        "horizons": list(command.horizons),
        "quantile_levels": list(command.quantile_levels),
        "schema_version": command.schema_version,
    }


# -- parsing defensivo das rows do dataset ----------------------------------------


def _timestamp_of(row: Row) -> datetime:
    """Extrai o `timestamp` tz-aware da row (premissa do par read-only da 3.5)."""
    value = row.get("timestamp")
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(
            f"dataset row 'timestamp' must be a tz-aware datetime; got {value!r}"
        )
    return value


def _target_return_of(row: Row) -> float:
    """Extrai o `target_return` numérico da row (o label é `returns[idx + h]` — I1)."""
    value = row.get("target_return")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row 'target_return' must be numeric; got {value!r}")
    return float(value)


def _feature_value_of(row: Row, column: str) -> float:
    """Extrai um valor de feature: numérico vira float, None vira NaN (I11)."""
    value = row.get(column)
    if value is None:
        return float("nan")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(
            f"dataset row {column!r} must be numeric or None; got {value!r}"
        )
    return float(value)
