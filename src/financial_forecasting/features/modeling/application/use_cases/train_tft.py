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
via o port `PredictionPersister` (4.3) com `model_version='tft_quantile'`.

**Imports cross-BC (decisão consciente, precedentes rastreados):** idênticos aos
do `train_gbm_quantile.py` (5.3) — `modeling.application -> analytics_store` só
de DADOS (DTO + VOs; a persistência entra pelos ports `PredictionPersister`/
`RunRecordPersister` deste slice, issue #68 / ADR 0.0.0053) pela justificativa do
dono único do `target_timestamp` (ADR 4.3.0001), e `modeling.application ->
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
- **I10 — identidade persistida:** a `config_signature` (um dos 9 slots do
  `run_id`) inclui as tuplas ordenadas de `feature_names` E de
  `known_feature_names` — a tipagem é parte da identidade do run, não só o
  conjunto. A identidade é o caminho ÚNICO dos VOs da 1.4 (`RunId.compute`,
  `ConfigSignature.compute`); `schema_version` é coluna de `dim_run`, nunca
  chave (issue #65, ADR 5.2.0004).
- **I11 — 1 obs por ponto alinhado:** mesma chave estrutural e mesma asserção de
  remoção-zero de 5.2/5.3.

Casos de erro (concept §6): C1 (dataset vazio), C2 (comando inválido ANTES de
qualquer I/O), C6 (coluna esperada ausente), C7 (`DuplicateKeyError` propaga no
rerun idêntico); C3/C4/C5/C10 erguem no trainer (port).

**Funções públicas para a inferência (Stage 7.1, ADR 7.1.0001 item 2):**
`load_tft_panel`, `tft_run_identity`, `tft_artifact_dir` e
`assert_emission_within_request` são o corpo que o treino já usava, extraído sem
mudar valor persistido — os use cases que predizem a partir do checkpoint as
chamam em vez de recopiar a leitura do painel, a identidade do run, a regra do
diretório do artefato e a guarda de emissão.

**Treino por subconjunto de famílias (Stage 7.3, ablação LOCO; ADR 7.3.0003 item 2):**
o comando aceita `excluded_family` (uma das `TFT_FAMILIES`, ou `None`) e
`model_version`. O painel é lido e aparado pelo conjunto COMPLETO de colunas
(`build_training_grid`) e só então perde as colunas da família, então a geometria
(timestamps, folds, decisões, `split_fingerprint`) é a mesma em toda configuração
(I2). O `run_id` usa o `feature_set_hash` do subconjunto e o `model_version` do
comando, e o `model_version` vai a toda linha persistida e ao `dim_run` (I3). O
comando default (`None`, `tft_quantile`) dá exatamente a identidade de antes (I1).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_tft_contract import (  # noqa: E501
    DATASET_TFT_LAYER,
    DATASET_TFT_TABLE,
    TARGET_COLUMN,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    FEATURE_SPECS,
    feature_set_hash,
    list_feature_specs,
)
from financial_forecasting.features.modeling.application.pipeline_version import (
    PIPELINE_VERSION,
)
from financial_forecasting.features.modeling.domain.services import loco_identity
from financial_forecasting.features.modeling.domain.services.operationally_latest_dedup import (
    deduplicate_operationally_latest,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.domain.value_objects.config_signature import (
    ConfigSignature,
)
from financial_forecasting.shared.domain.value_objects.run_id import RunId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from financial_forecasting.features.modeling.application.ports.out.prediction_persister import (
        PredictionPersister,
    )
    from financial_forecasting.features.modeling.application.ports.out.run_record_persister import (
        RunRecordPersister,
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
    )

logger = logging.getLogger(__name__)

_SPLIT = "test"
MODEL_VERSION = "tft_quantile"
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

# Famílias da registry na ordem do ADR 0.0.0016 e o `model_version` de uma configuração
# LOCO (Stage 7.3): a regra nome ↔ família mora no domínio (`loco_identity`, dono único).
TFT_FAMILIES: Final = loco_identity.TFT_FAMILIES
loco_model_version = loco_identity.loco_model_version


def registry_family_partition() -> dict[str, tuple[str, ...]]:
    """Features habilitadas da registry por `spec.family`, na ordem da registry.

    É a partição que a ablação congela e que o hash de H3 identifica (ADR 7.3.0002
    item 4); as famílias saem na ordem de `TFT_FAMILIES`.
    """
    specs = list_feature_specs(enabled_only=True)
    return {
        family: tuple(spec.name for spec in specs if spec.family == family)
        for family in TFT_FAMILIES
    }


def _check_family(excluded_family: str | None) -> None:
    try:
        loco_identity.configuration_of(excluded_family)
    except ValueError as exc:
        raise ValueError(f"{exc} (C2)") from exc


def tft_feature_set_hash(excluded_family: str | None) -> str:
    """`feature_set_hash` do conjunto treinado: a registry sem a família excluída.

    Com `None` é o `feature_set_hash()` de sempre (I1).
    """
    _check_family(excluded_family)
    if excluded_family is None:
        return feature_set_hash()
    return feature_set_hash(
        {name: spec for name, spec in FEATURE_SPECS.items() if spec.family != excluded_family}
    )


def _expected_model_versions(excluded_family: str | None) -> tuple[str, ...]:
    configuration = loco_identity.configuration_of(excluded_family)
    loco = loco_identity.loco_model_version(configuration)
    return (MODEL_VERSION, loco) if excluded_family is None else (loco,)


@dataclass(frozen=True)
class TftPanel:
    """O painel do grid único como o treino o monta (`load_tft_panel`).

    `rows` é a matriz na ordem de `feature_names` (desconhecidas + conhecidas);
    `known_feature_names` é o subconjunto conhecido (I2) — o mesmo que entra na
    identidade do run.
    """

    timestamps: tuple[str, ...]
    target: tuple[float, ...]
    sessions: tuple[date, ...]
    rows: tuple[tuple[float, ...], ...]
    feature_names: tuple[str, ...]
    known_feature_names: tuple[str, ...]


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
    # Stage 7.3 (ablação LOCO): família fora do painel e versão do modelo da
    # configuração; os defaults são o candidato confirmatório (I1).
    excluded_family: str | None = None
    model_version: str = MODEL_VERSION


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


def load_tft_panel(
    *, store: MedallionStore, asset_id: str, excluded_family: str | None = None
) -> TftPanel:
    """O painel do ativo pelo grid único, com a tipagem da registry (I2) — C1/C6.

    É a leitura que o `TrainTft` faz: as colunas são `unknown_feature_names()`
    seguidas de `known_feature_names()`. Quem prediz a partir do checkpoint
    (Stage 7.1) monta o painel por aqui, nunca por uma cópia. Com
    `excluded_family` (Stage 7.3), o grid é aparado pelo conjunto COMPLETO e só
    então as colunas da família saem do painel (I2: geometria igual).
    """
    _check_family(excluded_family)
    unknown_names = unknown_feature_names()
    known_names = known_feature_names()
    full_names = unknown_names + known_names
    if excluded_family is None:
        return _read_panel(
            store=store, asset_id=asset_id, feature_names=full_names, known_names=known_names
        )
    dropped = set(registry_family_partition()[excluded_family])
    return _read_panel(
        store=store,
        asset_id=asset_id,
        feature_names=tuple(name for name in full_names if name not in dropped),
        known_names=tuple(name for name in known_names if name not in dropped),
        grid_columns=full_names,
    )


def _read_panel(
    *,
    store: MedallionStore,
    asset_id: str,
    feature_names: tuple[str, ...],
    known_names: tuple[str, ...],
    grid_columns: tuple[str, ...] | None = None,
) -> TftPanel:
    """Corpo único da leitura: (timestamps ISO, target_return, sessões, matriz).

    Checa o vazio com o código deste use case (C1) e delega ordenação,
    validação e corte do prefixo sem valor ao `build_training_grid` (D11 da
    Stage 5.5; ADR 5.5.0004) — o mesmo grid dos outros modelos. Recebe as
    colunas explícitas porque a caracterização da leitura da 5.5
    (`test_dataset_loading_characterization.py`) a exercita com colunas
    arbitrárias; o use case e a inferência leem por `load_tft_panel`.
    `grid_columns` (default: `feature_names`) são as colunas que aparam o grid;
    a matriz sai só com `feature_names`.
    """
    rows = store.read(layer=DATASET_TFT_LAYER, table=DATASET_TFT_TABLE, filters={"asset": asset_id})
    if not rows:
        raise ValueError(
            f"dataset ({DATASET_TFT_LAYER!r}, {DATASET_TFT_TABLE!r}) is empty for "
            f"asset {asset_id!r} — nothing to train (C1)"
        )
    trim_columns = feature_names if grid_columns is None else grid_columns
    grid = build_training_grid(rows, columns=(*trim_columns, TARGET_COLUMN))
    return TftPanel(
        timestamps=grid.timestamps_iso(),
        target=grid.column(TARGET_COLUMN),
        sessions=grid.sessions(),
        rows=grid.matrix(feature_names),
        feature_names=feature_names,
        known_feature_names=known_names,
    )


def tft_run_identity(
    *,
    command: TrainTftCommand,
    feature_names: Sequence[str],
    known_names: Sequence[str],
    fold: FoldSplit,
    hasher: Hasher,
) -> tuple[str, str]:
    """`(config_signature, run_id)` de um fold — caminho único da 1.4 (I10).

    `config_signature` = configuração completa do run MENOS o que os outros
    8 slots do `RunId` já carregam: `seed` sai de `asdict(params)` (tem
    slot), `model_version` não entra (tem slot), `schema_version` não entra
    em lugar nenhum (é coluna). A tipagem known/unknown entra aqui (I10).
    `max_horizon` é, no TFT, o comprimento do decodificador (ADR 5.4.0002)
    — mais um motivo para viver na config e não só na purga (ADR 5.2.0004).
    """
    params = {key: value for key, value in asdict(command.params).items() if key != "seed"}
    config_signature = ConfigSignature.compute(
        hasher=hasher,
        config={
            "scope": {
                "feature_set_name": command.scope.feature_set_name,
                "max_horizon": command.scope.max_horizon,
                "cohort_id": command.scope.cohort_id,
            },
            "params": params,
            "feature_names": list(feature_names),
            "known_feature_names": list(known_names),
            "horizons": list(command.horizons),
            "quantile_levels": list(command.quantile_levels),
        },
    )
    run_id = RunId.compute(
        hasher=hasher,
        asset=command.scope.asset_id,
        feature_set_hash=tft_feature_set_hash(command.excluded_family),
        trial_number=None,  # só o sweep tem trials, e ele não persiste runs
        fold=str(fold.fold_index),
        seed=command.params.seed,
        model_version=command.model_version,
        config_signature=config_signature.value,
        split_signature=fold.fingerprint.value,
        pipeline_version=PIPELINE_VERSION,
    )
    return config_signature.value, run_id.value


def tft_artifact_dir(artifacts_root: Path, run_id: str) -> Path:
    """Diretório do artefato de um run: `<artifacts_root>/tft/<run_id>` (D9)."""
    return artifacts_root / _ARTIFACT_SUBDIR / run_id


def assert_emission_within_request(
    *,
    grids: Mapping[int, Mapping[int, Sequence[float]]],
    requested_decision_indices: Sequence[int],
    horizons: Sequence[int],
    partition: str,
) -> None:
    """O port só pode devolver pares que o use case PEDIU (D5; I12 da 7.1).

    Sem esta checagem, um índice de `train`/`calib` devolvido por engano pelo
    adapter (bug de piso de decisão — o risco que D5 cita para exigir faixas
    contíguas) viraria predição out-of-sample persistida e entraria na
    inferência do Step 6. O concept põe o controle do anti-vazamento no use
    case; confiar só no argumento de entrada deixaria metade do controle fora.
    `partition` nomeia a faixa pedida na mensagem (`"test"` no treino,
    `"test"`/`"calib"` na predição a partir do checkpoint).
    """
    unexpected_decisions = sorted(set(grids) - set(requested_decision_indices))
    if unexpected_decisions:
        raise ValueError(
            f"trainer emitted decisions outside the requested {partition} range: "
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
        persist_predictions: PredictionPersister,
        persist_run_record: RunRecordPersister,
        tracker: ExperimentTracker,
        hasher: Hasher,
        artifacts_root: Path,
    ) -> None:
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._persist_predictions = persist_predictions
        self._persist_run_record = persist_run_record
        self._tracker = tracker
        self._hasher = hasher
        self._artifacts_root = artifacts_root

    def __call__(self, command: TrainTftCommand) -> TrainTftResult:
        """Executa o fluxo por fold e devolve um summary por fold (ver módulo)."""
        _validate_command(command)  # C2 — antes de qualquer I/O

        # Painel e tipagem pela MESMA função que a predição a partir do checkpoint
        # usa (Stage 7.1): a ordem desconhecidas + conhecidas tem uma definição só.
        panel = load_tft_panel(
            store=self._store,
            asset_id=command.scope.asset_id,
            excluded_family=command.excluded_family,
        )  # C1/C6
        feature_names = panel.feature_names
        known_names = panel.known_feature_names
        dataset_timestamps, returns, sessions, feature_rows = (
            panel.timestamps,
            panel.target,
            panel.sessions,
            panel.rows,
        )
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
        emissions: list[
            tuple[FoldSplit, str, str, dict[int, dict[int, QuantileForecast]], TftTrainingResult]
        ] = []

        for fold in folds:
            # O `run_id` é calculado ANTES do treino porque o diretório do
            # artefato é derivado dele (D9) — tudo o que entra nos 9 slots já é
            # conhecido nesse ponto.
            config_signature, run_id = self._identity(command, feature_names, known_names, fold)
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
            assert_emission_within_request(
                grids=training.grids,
                requested_decision_indices=tuple(index_by_session[day] for day in fold.test),
                horizons=command.horizons,
                partition=_SPLIT,
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

            emissions.append((fold, run_id, config_signature, forecasts_by_decision, training))

        # I11 (duas camadas): duplicata real empata chave+rank e ergue no próprio
        # serviço 5.1; a remoção-zero fica atrás como defesa-em-profundidade.
        deduped = deduplicate_operationally_latest(
            entries,
            alignment_key=lambda entry: entry[:_ALIGNMENT_KEY_WIDTH],
            operational_rank=lambda entry: entry[4],
        )
        _assert_zero_removal(before=len(entries), after=len(deduped))

        for fold, run_id, config_signature, forecasts_by_decision, training in emissions:
            # `dim_run` junto da persistência das predições, não no laço de
            # treino: gravar antes deixaria linhas órfãs (run sem predição) se o
            # guard de dedup ou o persister erguesse, e o rerun idêntico (C7)
            # passaria a colidir também aqui.
            self._write_dim_run(command, fold, run_id, config_signature)
            rows_written = 0
            rows_skipped = 0
            for decision_idx, forecasts in forecasts_by_decision.items():
                result = self._persist_predictions(
                    PersistPredictionsCommand(
                        run_id=run_id,
                        split=_SPLIT,
                        model_version=command.model_version,
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
                    model_version=command.model_version,
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
            "model_version": command.model_version,
            "phase": _CONFIRMATORY_PHASE,
            "fold": str(fold.fold_index),
        }
        try:
            tracking_run_id = self._tracker.start_run(run_name=f"{command.model_version}-{run_id}")
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

        artifact_dir = tft_artifact_dir(self._artifacts_root, run_id)
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

    def _identity(
        self,
        command: TrainTftCommand,
        feature_names: tuple[str, ...],
        known_names: tuple[str, ...],
        fold: FoldSplit,
    ) -> tuple[str, str]:
        """`(config_signature, run_id)` de um fold — delega a `tft_run_identity` (I10)."""
        return tft_run_identity(
            command=command,
            feature_names=feature_names,
            known_names=known_names,
            fold=fold,
            hasher=self._hasher,
        )

    def _write_dim_run(
        self,
        command: TrainTftCommand,
        fold: FoldSplit,
        run_id: str,
        config_signature: str,
    ) -> None:
        """Grava 1 `RunRecord` por fold em `dim_run` — `seed` preenchida (I10)."""
        record = RunRecord(
            run_id=run_id,
            asset=command.scope.asset_id,
            parent_sweep_id=command.scope.cohort_id,
            feature_set_name=command.scope.feature_set_name,
            config_signature=config_signature,
            split_fingerprint=fold.fingerprint.value,
            fold=str(fold.fold_index),
            seed=command.params.seed,
            model_version=command.model_version,
            schema_version=command.schema_version,
        )
        # `analytics_store` grava (dono de `dim_run`); `created_at_utc` é do adapter (4.2 I5).
        self._persist_run_record(record)


# -- validação do comando (C2) ---------------------------------------------------


def _validate_command(command: TrainTftCommand) -> None:
    """C2: comando inválido ergue `ValueError` ANTES de qualquer I/O."""
    _check_family(command.excluded_family)
    allowed = _expected_model_versions(command.excluded_family)
    if command.model_version not in allowed:
        raise ValueError(
            f"model_version {command.model_version!r} does not pair with excluded_family "
            f"{command.excluded_family!r}; expected one of {list(allowed)} (C2)"
        )
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


# -- params do tracker (I12) ---------------------------------------------------------


def _tracking_params(command: TrainTftCommand, fold: FoldSplit, run_id: str) -> dict[str, object]:
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
        "model_version": command.model_version,
        "pipeline_version": PIPELINE_VERSION,
        **asdict(command.params),
    }
