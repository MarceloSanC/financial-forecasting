"""Use case `RunBaselines` — as 5 specs de baseline sob o harness walk-forward.

Orquestra (concept 5.2 §4, fluxo por referência — é o contrato): lê o dataset
TFT via `MedallionStore` (par read-only `("processed", "dataset_tft")` — D3),
gera folds via `WalkForwardSplitter` (5.1), invoca o `BaselineForecaster` por
(spec x fold), aplica o guardrail via `QuantileForecast.from_raw` (4.3, I5),
registra 1 `RunRecord` por (spec x fold) em `dim_run` (I10/D5), aplica o dedup
operationally-latest (5.1) com chave ESTRUTURAL de índices e **remoção-zero
assertada** (I6) e persiste as predições LONG via `PersistPredictions` (4.3)
com `model_version='baseline_<family>'` e `split="test"`.

**Import cross-BC `modeling.application -> analytics_store.application`
(decisão consciente e rastreada — concept 5.2 §8):** este é o primeiro import
use case -> use case entre BCs do repo. Justificativa por referência: (i) nenhum
contrato do LAYOUT/`.importlinter` proíbe import cross-BC na mesma camada
(`hexagonal-layers` é por container; a direção inward é preservada); (ii) a
alternativa — falar direto com o `AnalyticsRepository` e remontar as linhas
LONG — duplicaria a resolução do `target_timestamp`, violando o dono único do
ADR 4.3.0001 (exatamente o bug Gap 6 que o 4.3 existe para impedir).

Invariantes materializadas aqui:

- **I2 — alinhamento por sessão:** o use case faz APENAS aritmética de índices
  (ISO-date -> índice na grade densa); quem resolve `target_timestamp_utc` é
  exclusivamente o persister 4.3.
- **I6 — 1 obs por ponto alinhado (duas camadas):** a chave estrutural
  `(split, horizon, decision_idx + horizon, quantile_level)` com rank
  `decision_idx` faz toda duplicata real empatar chave+rank e **erguer no
  próprio serviço 5.1** (C9, "ambiguous operationally-latest..."); a asserção
  de remoção-zero (`_assert_zero_removal`) fica atrás dela como
  defesa-em-profundidade, testável por unit direto.
- **I9 — determinismo:** sem clock/aleatoriedade; mesma entrada -> mesmos
  payloads e hashes (`run_id`/`config_signature` canônicos via `Hasher` 1.4).

Casos de erro (concept §6): C2 (comando inválido ergue ANTES de qualquer I/O),
C7 (dataset vazio ergue), C6 (janela de predição incompleta pula e conta —
tratado DENTRO do 4.3), C8 (`DuplicateKeyError` propaga), C9 (empate no dedup
ergue no serviço 5.1).
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
    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        BaselineForecaster,
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

# Entrada estrutural do dedup (I6): (split, horizon, decision_idx + horizon,
# quantile_level) é a chave de alinhamento; o último campo (decision_idx) é o rank.
_StructuralEntry = tuple[str, int, int, float, int]
_ALIGNMENT_KEY_WIDTH = 4


@dataclass(frozen=True)
class RunBaselinesCommand:
    """DTO de entrada — cohort, specs, grade e geometria do walk-forward.

    Campos (concept §4):
        scope: identidade do cohort (`asset_id`, `feature_set_name`,
            `max_horizon`, `cohort_id`).
        specs: specs de baseline (default do caller:
            `BaselineSpec.canonical_five(...)`), sem `model_version` duplicado.
        horizons: horizontes de previsão (ex.: `(1, 7)`);
            `max(horizons) <= scope.max_horizon`.
        quantile_levels: grade densa comum do cohort (crescente, única, em (0, 1)).
        n_folds / test_size / val_size / calib_size / embargo: geometria do
            `WalkForwardSplitter` (5.1) — validada pelo próprio splitter.
        schema_version: versão dos schemas silver gravados.
    """

    scope: ScopeSpec
    specs: tuple[BaselineSpec, ...]
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    n_folds: int
    test_size: int
    val_size: int
    calib_size: int
    embargo: int
    schema_version: int


@dataclass(frozen=True)
class BaselineRunSummary:
    """DTO de saída — agregado de um (spec x fold) persistido."""

    run_id: str
    model_version: str
    fold_index: int
    rows_written: int
    rows_skipped: int


@dataclass(frozen=True)
class RunBaselinesResult:
    """DTO de saída — um `BaselineRunSummary` por (spec x fold)."""

    runs: tuple[BaselineRunSummary, ...]


def _assert_zero_removal(*, before: int, after: int) -> None:
    """Defesa-em-profundidade de I6: o dedup NUNCA pode ter removido entradas.

    Com a chave estrutural usada (horizon fixo na chave => mesmo
    `decision_idx + horizon` => mesmo `decision_idx`), toda duplicata real
    empata chave+rank e ergue ANTES no serviço 5.1 (C9). Este helper fica
    atrás como segunda camada — se algum dia o dedup colapsar silenciosamente,
    a duplicata de ponto alinhado é bug de geometria a montante, nunca
    silenciável.
    """
    if before != after:
        raise ValueError(
            f"dedup removed {before - after} aligned-point entries — "
            "upstream fold geometry bug (I6)"
        )


class RunBaselines:
    """Use case que emite e persiste as 5 specs de baseline sob o harness 5.1."""

    def __init__(  # noqa: PLR0913 — portas coesas do fluxo (concept §4)
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        forecaster: BaselineForecaster,
        persist_predictions: PersistPredictions,
        analytics_repository: AnalyticsRepository,
        hasher: Hasher,
    ) -> None:
        self._store = store
        self._splitter = splitter
        self._forecaster = forecaster
        self._persist_predictions = persist_predictions
        self._analytics_repository = analytics_repository
        self._hasher = hasher

    def __call__(self, command: RunBaselinesCommand) -> RunBaselinesResult:
        """Executa o fluxo (spec x fold) e devolve um summary por par (ver módulo)."""
        _validate_command(command)  # C2 — antes de qualquer I/O

        dataset_timestamps, returns, sessions = self._load_dataset(command.scope)  # C7
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
        # I2: mapeia ISO-date -> índice na grade densa; daqui em diante o use
        # case faz SÓ aritmética de índices (timestamp é do persister 4.3).
        index_by_session = {day.isoformat(): idx for idx, day in enumerate(sessions)}

        summaries: list[BaselineRunSummary] = []
        for spec in command.specs:
            summaries.extend(
                self._run_spec(
                    command=command,
                    spec=spec,
                    folds=folds,
                    index_by_session=index_by_session,
                    dataset_timestamps=dataset_timestamps,
                    returns=returns,
                )
            )
        return RunBaselinesResult(runs=tuple(summaries))

    # -- leitura do dataset (D3/C7) -------------------------------------------

    def _load_dataset(
        self, scope: ScopeSpec
    ) -> tuple[tuple[str, ...], tuple[float, ...], tuple[date, ...]]:
        """Lê o dataset TFT e extrai (timestamps ISO, target_return, sessões)."""
        rows = self._store.read(
            layer=_DATASET_LAYER, table=_DATASET_TABLE, filters={"asset": scope.asset_id}
        )
        if not rows:
            raise ValueError(
                f"dataset ({_DATASET_LAYER!r}, {_DATASET_TABLE!r}) is empty for "
                f"asset {scope.asset_id!r} — nothing to forecast (C7)"
            )
        parsed = sorted(
            ((_timestamp_of(row), _target_return_of(row)) for row in rows),
            key=lambda pair: pair[0],
        )
        dataset_timestamps = tuple(ts.isoformat() for ts, _ in parsed)
        returns = tuple(value for _, value in parsed)
        sessions = tuple(ts.date() for ts, _ in parsed)
        return dataset_timestamps, returns, sessions

    # -- fluxo por spec ---------------------------------------------------------

    def _run_spec(  # noqa: PLR0913 — estado coeso de uma spec sob todos os folds
        self,
        *,
        command: RunBaselinesCommand,
        spec: BaselineSpec,
        folds: tuple[FoldSplit, ...],
        index_by_session: Mapping[str, int],
        dataset_timestamps: tuple[str, ...],
        returns: tuple[float, ...],
    ) -> list[BaselineRunSummary]:
        """Emite, registra `dim_run`, deduplica (I6) e persiste uma spec."""
        emissions: list[tuple[FoldSplit, str, dict[int, dict[int, QuantileForecast]]]] = []
        entries: list[_StructuralEntry] = []

        for fold in folds:
            train_end_idx = index_by_session[fold.train[-1]]
            decision_indices = tuple(index_by_session[day] for day in fold.test)
            raw = self._forecaster.forecast(
                spec=spec,
                returns=returns,
                train_end_idx=train_end_idx,
                decision_indices=decision_indices,
                horizons=command.horizons,
                quantile_levels=command.quantile_levels,
            )
            forecasts_by_decision: dict[int, dict[int, QuantileForecast]] = {}
            for decision_idx in decision_indices:
                grids = raw[decision_idx]
                forecasts_by_decision[decision_idx] = {
                    horizon: QuantileForecast.from_raw(
                        levels=command.quantile_levels,
                        raw_values=tuple(grids[horizon]),
                    )
                    for horizon in command.horizons
                }  # guardrail 4.3 (I5) — degenerada passa com applied=False
                entries.extend(
                    (_SPLIT, horizon, decision_idx + horizon, level, decision_idx)
                    for horizon in command.horizons
                    for level in command.quantile_levels
                )

            run_id = self._hasher.hash_mapping(_run_payload(command, spec, fold))
            self._write_dim_run(command, spec, fold, run_id)
            emissions.append((fold, run_id, forecasts_by_decision))

        # I6 (duas camadas): duplicata real empata chave+rank e ergue no próprio
        # serviço 5.1 (C9); a remoção-zero fica atrás como defesa-em-profundidade.
        deduped = deduplicate_operationally_latest(
            entries,
            # Índices literais: os 4 primeiros campos são a chave de alinhamento;
            # o 5º (decision_idx) é o rank operacional.
            alignment_key=lambda entry: entry[:_ALIGNMENT_KEY_WIDTH],
            operational_rank=lambda entry: entry[4],
        )
        _assert_zero_removal(before=len(entries), after=len(deduped))

        summaries: list[BaselineRunSummary] = []
        for fold, run_id, forecasts_by_decision in emissions:
            rows_written = 0
            rows_skipped = 0
            for decision_idx, forecasts in forecasts_by_decision.items():
                result = self._persist_predictions(
                    PersistPredictionsCommand(
                        run_id=run_id,
                        split=_SPLIT,
                        model_version=spec.model_version,
                        asset=command.scope.asset_id,
                        feature_set_name=command.scope.feature_set_name,
                        schema_version=command.schema_version,
                        decision_idx=decision_idx,
                        dataset_timestamps=dataset_timestamps,
                        forecasts=forecasts,
                    )
                )  # C6 tratado DENTRO do 4.3; DuplicateKeyError propaga (C8)
                rows_written += result.rows_written
                rows_skipped += result.rows_skipped
            summaries.append(
                BaselineRunSummary(
                    run_id=run_id,
                    model_version=spec.model_version,
                    fold_index=fold.fold_index,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                )
            )
        return summaries

    def _write_dim_run(
        self,
        command: RunBaselinesCommand,
        spec: BaselineSpec,
        fold: FoldSplit,
        run_id: str,
    ) -> None:
        """Grava 1 `RunRecord` por (spec x fold) em `dim_run` (I9/I10/D5)."""
        record = RunRecord(
            run_id=run_id,
            asset=command.scope.asset_id,
            parent_sweep_id=command.scope.cohort_id,
            feature_set_name=command.scope.feature_set_name,
            config_signature=self._hasher.hash_mapping(_config_payload(command, spec)),
            split_fingerprint=fold.fingerprint.value,
            fold=str(fold.fold_index),
            seed=None,  # baselines não têm semente (I9)
            model_version=spec.model_version,
            schema_version=command.schema_version,
        )
        rows: list[Row] = [asdict(record)]
        # O adapter injeta `created_at_utc` write-time (4.2 I5).
        self._analytics_repository.write(layer=_SILVER_LAYER, table=_DIM_RUN_TABLE, rows=rows)


# -- validação do comando (C2) ---------------------------------------------------


def _validate_command(command: RunBaselinesCommand) -> None:
    """C2: comando inválido ergue `ValueError` ANTES de qualquer I/O."""
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

    if not command.specs:
        raise ValueError("specs must be non-empty (C2)")
    model_versions = [spec.model_version for spec in command.specs]
    if len(set(model_versions)) != len(model_versions):
        raise ValueError(f"specs must not share model_version; got {model_versions} (C2)")


# -- payloads canônicos (I9) ------------------------------------------------------


def _spec_payload(spec: BaselineSpec) -> dict[str, object]:
    """Campos da spec como payload canônico (identidade da configuração)."""
    return {
        "family": spec.family,
        "window": spec.window,
        "decay_lambda": spec.decay_lambda,
        "model_version": spec.model_version,
    }


def _config_payload(command: RunBaselinesCommand, spec: BaselineSpec) -> dict[str, object]:
    """Payload do `config_signature`: spec + horizons + levels + schema_version."""
    return {
        "spec": _spec_payload(spec),
        "horizons": list(command.horizons),
        "quantile_levels": list(command.quantile_levels),
        "schema_version": command.schema_version,
    }


def _run_payload(
    command: RunBaselinesCommand, spec: BaselineSpec, fold: FoldSplit
) -> dict[str, object]:
    """Payload do `run_id`: scope + spec + fingerprint do fold + grade (I9/I10)."""
    return {
        "scope": {
            "asset_id": command.scope.asset_id,
            "feature_set_name": command.scope.feature_set_name,
            "max_horizon": command.scope.max_horizon,
            "cohort_id": command.scope.cohort_id,
        },
        "spec": _spec_payload(spec),
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
    """Extrai o `target_return` numérico da row (r_t das fórmulas do doc §3)."""
    value = row.get("target_return")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row 'target_return' must be numeric; got {value!r}")
    return float(value)
