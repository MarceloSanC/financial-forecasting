"""Use case `TrainTft` — candidato TFT quantílico sob o harness walk-forward.

Orquestra (concept 5.4 §4, fluxo por referência — é o contrato): lê o dataset
TFT via `MedallionStore` (par read-only `("processed", "dataset_tft")`), fixa a
tipagem known/unknown a partir da registry 3.4 (I2/D4), gera folds via
`WalkForwardSplitter` (5.1), deriva as três faixas de índices de decisão do
`FoldSplit`, invoca o `TftTrainer` uma vez por fold (UM modelo com decodificador
de `max_horizon` passos — ADR 5.4.0002), aplica o guardrail via
`QuantileForecast.from_raw` (4.3, I5), registra 1 `RunRecord` por fold em
`dim_run` (I10 — `seed` preenchida), aplica o dedup operationally-latest (5.1)
com chave ESTRUTURAL e remoção-zero assertada (I11) e persiste as predições LONG
via `PersistPredictions` (4.3) com `model_version='tft_quantile'`.

**Imports cross-BC (decisão consciente, precedentes rastreados):** idênticos aos
do `train_gbm_quantile.py` (5.3) — `modeling.application ->
analytics_store.application` pela justificativa do dono único do
`target_timestamp` (ADR 4.3.0001), e `modeling.application ->
feature_engineering.domain` como consumo declarado no roadmap.

Invariantes materializadas aqui (concept §5):

- **I2 — tipagem como REGRA, não fotografia:** desconhecidas são as specs com
  `tft_typing == 'unknown'`; conhecidas são as com `tft_typing == 'known'` MAIS
  o calendário. Hoje a registry só tem `unknown`, mas registrar uma spec `known`
  amanhã move a coluna de lista sozinha — nenhuma lista paralela.
- **I4/I7 — o que o port pode ajustar é o que os índices declaram:** só as
  sessões de `train` viram decisões de treino e só as de `early_stop` viram
  monitor. `calib` NUNCA entra em nenhuma das duas (o contexto passado é assunto
  do adapter, ADR 5.4.0001).
- **I16 — emissão na cauda:** o port emite apenas os pares `(t, h)` com
  `t + h` dentro do painel; o use case persiste exatamente o que recebeu. Como
  essa é a MESMA desigualdade do pulo do 4.3, `rows_skipped` é zero por
  construção nesta Stage — e o teste assere isso em vez de ignorar.
- **I10 — identidade persistida:** o payload do `run_id` inclui as tuplas
  ordenadas de `feature_names` E de `known_feature_names` — a tipagem é parte da
  identidade do run, não só o conjunto.
- **I11 — 1 obs por ponto alinhado:** mesma chave estrutural e mesma asserção de
  remoção-zero de 5.2/5.3.

Casos de erro (concept §6): C1 (dataset vazio), C2 (comando inválido ANTES de
qualquer I/O), C6 (coluna esperada ausente), C7 (`DuplicateKeyError` propaga no
rerun idêntico); C3/C4/C5/C10 erguem no trainer (port).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
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
    from collections.abc import Mapping, Sequence
    from datetime import date

    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        AnalyticsRepository,
    )
    from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
        PersistPredictions,
    )
    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainer,
        TftTrainingParams,
        TftTrainingResult,
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
    from financial_forecasting.shared.application.ports.out.experiment_tracker import (
        ExperimentTracker,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
        Row,
    )

logger = logging.getLogger(__name__)

_DATASET_LAYER = "processed"
_DATASET_TABLE = "dataset_tft"
_SILVER_LAYER = "silver"
_DIM_RUN_TABLE = "dim_run"
_SPLIT = "test"
_MODEL_VERSION = "tft_quantile"
_ARTIFACT_SUBDIR = "tft"

# Calendário como covariáveis CONHECIDAS (D4/I2). Declarado aqui e não na
# registry porque estas colunas não são features dela — registrá-las a montante
# mudaria `feature_set_hash` e o conjunto que alimenta o dataset (3.5) e o GBM
# (5.3). Piso declarado; o tratamento geral é a issue #58.
_CALENDAR_KNOWN_FEATURES = ("day_of_week", "month")
# Rótulo de fase do run (I12). Distingue este fluxo da varredura exploratória,
# que marca `phase='exploratory'` (ADR 5.4.0005) — a separação estrutural é o
# grafo de dependências do `RunTftSweep`; o rótulo é a segunda camada.
_CONFIRMATORY_PHASE = "confirmatory_ready"
_KNOWN_TYPING = "known"
_UNKNOWN_TYPING = "unknown"

# Entrada estrutural do dedup (I11): (split, horizon, decision_idx + horizon,
# quantile_level) é a chave de alinhamento; o último campo é o rank operacional.
_StructuralEntry = tuple[str, int, int, float, int]
_ALIGNMENT_KEY_WIDTH = 4


@dataclass(frozen=True)
class TrainTftCommand:
    """DTO de entrada — cohort, params pré-registrados, grade e geometria."""

    scope: ScopeSpec
    params: TftTrainingParams
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    n_folds: int
    test_size: int
    val_size: int
    calib_size: int
    embargo: int
    schema_version: int


@dataclass(frozen=True)
class TftRunSummary:
    """DTO de saída — agregado de um fold persistido + mecanismo de parada."""

    run_id: str
    model_version: str
    fold_index: int
    rows_written: int
    rows_skipped: int
    best_epoch: int
    best_val_loss: float
    fitted_decision_count: int
    monitored_decision_count: int
    artifact_path: str
    tracking_run_id: str


@dataclass(frozen=True)
class TrainTftResult:
    """DTO de saída — um `TftRunSummary` por fold."""

    runs: tuple[TftRunSummary, ...]


def unknown_feature_names() -> tuple[str, ...]:
    """Covariáveis DESCONHECIDAS: specs da registry tipadas `unknown` (I2).

    Derivado de `spec.tft_typing`, nunca de lista paralela — é o que o ADR
    3.4.0002 estabeleceu ao promover a tipagem para campo validado da spec.
    """
    return tuple(
        spec.name
        for spec in list_feature_specs(enabled_only=True)
        if spec.tft_typing == _UNKNOWN_TYPING
    )


def known_feature_names() -> tuple[str, ...]:
    """Covariáveis CONHECIDAS: specs `known` da registry + calendário (I2/D4).

    A regra é essa, não a fotografia de hoje (a registry só tem `unknown`): uma
    spec registrada como `known` amanhã entra aqui sozinha, sem tocar em código.
    """
    registry_known = tuple(
        spec.name
        for spec in list_feature_specs(enabled_only=True)
        if spec.tft_typing == _KNOWN_TYPING
    )
    return registry_known + _CALENDAR_KNOWN_FEATURES


def _assert_zero_removal(*, before: int, after: int) -> None:
    """Defesa-em-profundidade de I11: o dedup NUNCA pode ter removido entradas.

    **Inatingível por construção neste fluxo, e isso é declarado de propósito**
    (mesma situação do precedente 5.3): a chave de alinhamento
    `(split, horizon, decision_idx + horizon, quantile_level)` determina
    `decision_idx`, que é o próprio rank operacional — então uma duplicata real
    empata chave E rank, e o serviço 5.1 ergue ambiguidade antes de chegar aqui.
    Somado a isso, as entradas nascem de um `dict`, então nem repetição
    estrutural existe. O guard fica como segunda camada para quando a composição
    de cohort (5.5) juntar execuções cujos pontos alinhados se sobreponham.
    Auditoria: não procure teste de fluxo que o dispare — não existe caminho.
    """
    if before != after:
        raise ValueError(
            f"dedup removed {before - after} aligned-point entries — "
            "upstream fold geometry bug (I11)"
        )


def _assert_emission_within_request(
    *,
    grids: Mapping[int, Mapping[int, Sequence[float]]],
    test_decision_indices: tuple[int, ...],
    horizons: tuple[int, ...],
) -> None:
    """O port só pode devolver pares que o use case PEDIU (D5).

    Sem esta checagem, um índice de `train`/`calib` devolvido por engano pelo
    adapter (bug de piso de decisão — o risco que D5 cita para exigir faixas
    contíguas) viraria predição out-of-sample persistida e entraria na
    inferência do Step 6. O concept põe o controle do anti-vazamento no use
    case; confiar só no argumento de entrada deixaria metade do controle fora.
    """
    unexpected_decisions = sorted(set(grids) - set(test_decision_indices))
    if unexpected_decisions:
        raise ValueError(
            "trainer emitted decisions outside the requested test range: "
            f"{unexpected_decisions!r} (D5)"
        )
    emitted_horizons = {horizon for by_horizon in grids.values() for horizon in by_horizon}
    unexpected_horizons = sorted(emitted_horizons - set(horizons))
    if unexpected_horizons:
        raise ValueError(
            f"trainer emitted horizons that were not requested: {unexpected_horizons!r} (D5)"
        )


class TrainTft:
    """Use case que treina e persiste o candidato TFT sob o harness 5.1."""

    def __init__(  # noqa: PLR0913 — portas coesas do fluxo (concept §4)
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        trainer: TftTrainer,
        persist_predictions: PersistPredictions,
        analytics_repository: AnalyticsRepository,
        tracker: ExperimentTracker,
        hasher: Hasher,
        artifacts_root: Path,
    ) -> None:
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._persist_predictions = persist_predictions
        self._analytics_repository = analytics_repository
        self._tracker = tracker
        self._hasher = hasher
        self._artifacts_root = artifacts_root

    def __call__(self, command: TrainTftCommand) -> TrainTftResult:
        """Executa o fluxo por fold e devolve um summary por fold (ver módulo)."""
        _validate_command(command)  # C2 — antes de qualquer I/O

        unknown_names = unknown_feature_names()
        known_names = known_feature_names()
        feature_names = unknown_names + known_names

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

        summaries: list[TftRunSummary] = []
        entries: list[_StructuralEntry] = []
        emissions: list[tuple[FoldSplit, str, dict[int, dict[int, QuantileForecast]], TftTrainingResult]] = []  # noqa: E501

        for fold in folds:
            # O `run_id` é calculado ANTES do treino porque o diretório do
            # artefato é derivado dele (D9) — tudo o que entra no payload já é
            # conhecido nesse ponto.
            run_id = self._hasher.hash_mapping(
                _run_payload(command, feature_names, known_names, fold)
            )
            training = self._train_fold(
                command=command,
                fold=fold,
                index_by_session=index_by_session,
                returns=returns,
                feature_rows=feature_rows,
                feature_names=feature_names,
                known_names=known_names,
                run_id=run_id,
            )
            _assert_emission_within_request(
                grids=training.grids,
                test_decision_indices=tuple(index_by_session[day] for day in fold.test),
                horizons=command.horizons,
            )
            forecasts_by_decision: dict[int, dict[int, QuantileForecast]] = {}
            for decision_idx, grids in training.grids.items():
                forecasts_by_decision[decision_idx] = {
                    horizon: QuantileForecast.from_raw(
                        levels=command.quantile_levels,
                        raw_values=tuple(raw_grid),
                    )
                    for horizon, raw_grid in grids.items()
                }  # guardrail 4.3 (I5) — rearranjo CFG por decisão x horizonte
                entries.extend(
                    (_SPLIT, horizon, decision_idx + horizon, level, decision_idx)
                    for horizon in grids
                    for level in command.quantile_levels
                )

            emissions.append((fold, run_id, forecasts_by_decision, training))

        # I11 (duas camadas): duplicata real empata chave+rank e ergue no próprio
        # serviço 5.1; a remoção-zero fica atrás como defesa-em-profundidade.
        deduped = deduplicate_operationally_latest(
            entries,
            alignment_key=lambda entry: entry[:_ALIGNMENT_KEY_WIDTH],
            operational_rank=lambda entry: entry[4],
        )
        _assert_zero_removal(before=len(entries), after=len(deduped))

        for fold, run_id, forecasts_by_decision, training in emissions:
            # `dim_run` junto da persistência das predições, não no laço de
            # treino: gravar antes deixaria linhas órfãs (run sem predição) se o
            # guard de dedup ou o persister erguesse, e o rerun idêntico (C7)
            # passaria a colidir também aqui.
            self._write_dim_run(command, feature_names, known_names, fold, run_id)
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
                )  # C7 propaga no rerun idêntico
                rows_written += result.rows_written
                rows_skipped += result.rows_skipped
            # I12/C8 — rastrear DEPOIS de persistir. A ordem é o que torna a
            # absorção da falha segura: ela nunca pode esconder uma persistência
            # incompleta, porque nesse ponto a persistência já terminou.
            tracking_run_id = self._track_fold(command, fold, run_id, training)
            summaries.append(
                TftRunSummary(
                    run_id=run_id,
                    model_version=_MODEL_VERSION,
                    fold_index=fold.fold_index,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    best_epoch=training.best_epoch,
                    best_val_loss=training.best_val_loss,
                    fitted_decision_count=training.fitted_decision_count,
                    monitored_decision_count=training.monitored_decision_count,
                    artifact_path=training.artifact_path,
                    tracking_run_id=tracking_run_id,
                )
            )
        return TrainTftResult(runs=tuple(summaries))

    # -- rastreamento do run (I12/C8) -------------------------------------------

    def _track_fold(
        self,
        command: TrainTftCommand,
        fold: FoldSplit,
        run_id: str,
        training: TftTrainingResult,
    ) -> str:
        """Registra o run do fold e devolve o id do tracker (`""` se falhou).

        C8 — a falha é **absorvida**, não propagada: as predições do fold já
        estão persistidas, e propagar destruiria o resultado de um trabalho
        concluído. Tracking é observabilidade; a fonte da verdade é
        `fact_oos_predictions`.
        """
        # Fora do `try` de propósito: montar o payload é código NOSSO. Um
        # AttributeError aqui seria defeito do use case, não backend fora do ar,
        # e absorvê-lo como "tracking failed" esconderia um bug de programação
        # atrás de uma mensagem de observabilidade.
        params = _tracking_params(command, fold, run_id)
        summary_metrics = {
            "best_val_loss": training.best_val_loss,
            "best_epoch": float(training.best_epoch),
            "fitted_decisions": float(training.fitted_decision_count),
            "monitored_decisions": float(training.monitored_decision_count),
        }
        tags = {
            "model_version": _MODEL_VERSION,
            "phase": _CONFIRMATORY_PHASE,
            "fold": str(fold.fold_index),
        }
        try:
            tracking_run_id = self._tracker.start_run(run_name=f"{_MODEL_VERSION}-{run_id}")
            self._tracker.log_params(params)
            for epoch, loss in enumerate(training.val_loss_by_epoch):
                self._tracker.log_metrics({"val_loss": loss}, step=epoch)
            self._tracker.log_metrics(summary_metrics)
            self._tracker.set_tags(tags)
            if training.artifact_path:
                self._tracker.log_artifact(training.artifact_path)
            self._tracker.end_run()
        except Exception:
            logger.exception(
                "experiment tracking failed for run_id=%s (fold %s) — predictions "
                "were already persisted and remain valid (C8)",
                run_id,
                fold.fold_index,
            )
            # Fechar o run mesmo na falha: sem isto ele fica ATIVO e o
            # `start_run` do fold seguinte ergue "run já ativo" no backend real
            # — a falha de um fold contaminaria todos os posteriores.
            self._close_run_quietly(run_id)
            return ""
        return tracking_run_id

    def _close_run_quietly(self, run_id: str) -> None:
        """Encerra o run ativo ignorando falha — limpeza best-effort (C8)."""
        try:
            self._tracker.end_run()
        except Exception:
            logger.debug("could not close tracking run for run_id=%s", run_id)

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

    # -- treino de um fold (I4/I7) ---------------------------------------------

    def _train_fold(  # noqa: PLR0913 — estado coeso de um fold (concept §4)
        self,
        *,
        command: TrainTftCommand,
        fold: FoldSplit,
        index_by_session: Mapping[str, int],
        returns: tuple[float, ...],
        feature_rows: tuple[tuple[float, ...], ...],
        feature_names: tuple[str, ...],
        known_names: tuple[str, ...],
        run_id: str,
    ) -> TftTrainingResult:
        """Deriva as faixas de decisão do fold e delega ao port (calib NUNCA)."""
        train_indices = tuple(index_by_session[day] for day in fold.train)
        early_stop_indices = tuple(index_by_session[day] for day in fold.early_stop)
        test_indices = tuple(index_by_session[day] for day in fold.test)

        artifact_dir = self._artifacts_root / _ARTIFACT_SUBDIR / run_id
        return self._trainer.train_and_predict(
            params=command.params,
            feature_names=feature_names,
            known_feature_names=known_names,
            rows=feature_rows,
            target=returns,
            train_decision_indices=train_indices,
            early_stop_decision_indices=early_stop_indices,
            test_decision_indices=test_indices,
            max_horizon=command.scope.max_horizon,
            horizons=command.horizons,
            quantile_levels=command.quantile_levels,
            artifact_dir=str(artifact_dir),
        )

    def _write_dim_run(
        self,
        command: TrainTftCommand,
        feature_names: tuple[str, ...],
        known_names: tuple[str, ...],
        fold: FoldSplit,
        run_id: str,
    ) -> None:
        """Grava 1 `RunRecord` por fold em `dim_run` — `seed` preenchida (I10)."""
        record = RunRecord(
            run_id=run_id,
            asset=command.scope.asset_id,
            parent_sweep_id=command.scope.cohort_id,
            feature_set_name=command.scope.feature_set_name,
            config_signature=self._hasher.hash_mapping(
                _config_payload(command, feature_names, known_names)
            ),
            split_fingerprint=fold.fingerprint.value,
            fold=str(fold.fold_index),
            seed=command.params.seed,
            model_version=_MODEL_VERSION,
            schema_version=command.schema_version,
        )
        rows: list[Row] = [asdict(record)]
        self._analytics_repository.write(layer=_SILVER_LAYER, table=_DIM_RUN_TABLE, rows=rows)


# -- validação do comando (C2) ---------------------------------------------------


def _validate_command(command: TrainTftCommand) -> None:
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


# -- payloads canônicos (I9/I10) --------------------------------------------------


def _params_payload(params: TftTrainingParams) -> dict[str, object]:
    """Campos dos params como payload canônico (identidade da configuração)."""
    return {
        "seed": params.seed,
        "max_encoder_length": params.max_encoder_length,
        "hidden_size": params.hidden_size,
        "attention_head_size": params.attention_head_size,
        "dropout": params.dropout,
        "hidden_continuous_size": params.hidden_continuous_size,
        "learning_rate": params.learning_rate,
        "max_epochs": params.max_epochs,
        "patience": params.patience,
        "batch_size": params.batch_size,
        "model_version": _MODEL_VERSION,
    }


def _tracking_params(
    command: TrainTftCommand, fold: FoldSplit, run_id: str
) -> dict[str, object]:
    """Params logados no tracker (I12): identidade + geometria do fold."""
    return {
        "run_id": run_id,
        "asset_id": command.scope.asset_id,
        "feature_set_name": command.scope.feature_set_name,
        "cohort_id": command.scope.cohort_id,
        "fold_index": fold.fold_index,
        "split_fingerprint": fold.fingerprint.value,
        "horizons": list(command.horizons),
        "quantile_levels": list(command.quantile_levels),
        "n_folds": command.n_folds,
        "test_size": command.test_size,
        "val_size": command.val_size,
        "calib_size": command.calib_size,
        "embargo": command.embargo,
        **_params_payload(command.params),
    }


def _config_payload(
    command: TrainTftCommand,
    feature_names: tuple[str, ...],
    known_names: tuple[str, ...],
) -> dict[str, object]:
    """Payload do `config_signature`: params + tipagem + grade + schema (I10)."""
    return {
        "params": _params_payload(command.params),
        "feature_names": list(feature_names),
        "known_feature_names": list(known_names),
        "horizons": list(command.horizons),
        "quantile_levels": list(command.quantile_levels),
        "schema_version": command.schema_version,
    }


def _run_payload(
    command: TrainTftCommand,
    feature_names: tuple[str, ...],
    known_names: tuple[str, ...],
    fold: FoldSplit,
) -> dict[str, object]:
    """Payload do `run_id`: scope + params + tipagem + fingerprint + fold (I10)."""
    return {
        "scope": {
            "asset_id": command.scope.asset_id,
            "feature_set_name": command.scope.feature_set_name,
            "max_horizon": command.scope.max_horizon,
            "cohort_id": command.scope.cohort_id,
        },
        "params": _params_payload(command.params),
        "feature_names": list(feature_names),
        "known_feature_names": list(known_names),
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
        raise ValueError(f"dataset row 'timestamp' must be a tz-aware datetime; got {value!r}")
    return value


def _target_return_of(row: Row) -> float:
    """Extrai o `target_return` numérico da row (o alvo do passo h é `[t + h]`)."""
    value = row.get("target_return")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row 'target_return' must be numeric; got {value!r}")
    return float(value)


def _feature_value_of(row: Row, column: str) -> float:
    """Extrai um valor de feature: numérico vira float, None vira NaN."""
    value = row.get(column)
    if value is None:
        return float("nan")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row {column!r} must be numeric or None; got {value!r}")
    return float(value)
