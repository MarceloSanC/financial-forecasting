"""Adapter `PfTftTrainer` — implementa o port `TftTrainer` com `pytorch-forecasting`.

Única casa de `torch`/`lightning`/`pytorch_forecasting` no BC `modeling`
(concept 5.4 §8, I13). A fronteira do port troca só primitivos; a montagem do
`DataFrame`, do `TimeSeriesDataSet` e do treinamento vive toda aqui.

**Mecanismo de recorte por partição (D5).** A biblioteca só expressa PISO de
decisão (`min_prediction_idx`) — não existe teto. O teto vem de **recortar o
quadro** passado a cada dataset:

| dataset  | quadro                                        | piso           |
|----------|-----------------------------------------------|----------------|
| treino   | `rows[0 : max(train) + max_horizon + 1]`       | `min(train)+1` |
| monitor  | `rows[0 : max(early_stop) + max_horizon + 1]`  | `min(es)+1`    |
| predição | `rows[0 : max(test) + max_horizon + 1]`        | `min(test)+1`  |

O recorte da predição não é simetria estética: sem ele o dataset geraria
decisões DEPOIS do bloco de teste, e todo fold que não é o último tem painel
adiante dele — o use case reprovaria com `_assert_emission_within_request`.

O quadro do monitor terminar antes de `calib` é o que torna a invariância de
A4(a) **estrutural**, e não uma esperança: as sessões de `calib`/`test` sequer
existem no `DataFrame` que alimenta o monitor.

O quadro de treino inclui `max_horizon` sessões além do bloco `train` de
propósito: são os RÓTULOS das últimas decisões de treino (o decodificador de
`t` cobre `t+1..t+max_horizon`). São sessões de purga, estritamente antes de
`early_stop` — daí a definição de *quadro de treino* em I4(b) do concept, e daí
a população contra a qual o normalizador é verificado (A4c).

**Três armadilhas da biblioteca, verificadas antes de escrever este adapter:**

1. `target_normalizer="auto"` escolhe um normalizador POR JANELA quando
   `max_encoder_length > 20` — o que valeria em produção (60) e não nas
   geometrias pequenas dos testes (~12). O normalizador é fixado explicitamente
   (ADR 5.4.0006), senão a suite validaria um caminho que a produção não usa e a
   cláusula (b) de I4 ficaria sem objeto verificável.
2. A saída de predição é RETANGULAR e preenchida na cauda; sem os comprimentos
   reais de decodificador, o padding viraria predição fabricada (I15).
3. O Lightning não guarda histórico de perda por época — só o último valor. O
   histórico (contrato do port) vem de um callback próprio, que ignora a
   passagem de sanidade: uma entrada antes da época 0 deslocaria o índice e
   quebraria a identidade `best_epoch == argmin` (D11).
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import lightning.pytorch as pl
import pandas as pd
import torch
from lightning.fabric.utilities.exceptions import MisconfigurationException
from lightning.pytorch.callbacks import Callback, EarlyStopping, ModelCheckpoint
from pytorch_forecasting import QuantileLoss, TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data.encoders import GroupNormalizer

from financial_forecasting.features.modeling.domain.exceptions.backend import (
    ModelTrainingError,
)
from financial_forecasting.features.modeling.domain.services.tft_panel_geometry import (
    resolve_panel_geometry,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainingParams,
        TftTrainingResult,
    )

_TIME_IDX_COLUMN = "time_idx"
_TARGET_COLUMN = "target"
# Vocabulário de falha da pilha `pytorch-forecasting`/`lightning`/`torch` (issue #84),
# ENUMERADO — nunca `except Exception`. Verificado no container (pytorch-forecasting
# 1.8.0, lightning 2.6.5, torch 2.13): a lib ergue `ValueError` (48 sítios; ex.
# NA/inf no painel, nível fora da grade da `QuantileLoss`), `KeyError` (5),
# `RuntimeError` (5 + os do torch), `TypeError` (3) e usa 305 `assert`
# (`AssertionError`); o Lightning ergue `MisconfigurationException` (subclasse
# direta de `Exception`, invisível a qualquer `except ValueError`). Os
# `ValueError` da REGRA do port (C3/C4/C5/C10) são erguidos FORA das seções
# traduzidas e continuam `ValueError`.
_BACKEND_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    KeyError,
    RuntimeError,
    TypeError,
    AssertionError,
    MisconfigurationException,
)
_GROUP_COLUMN = "series"
# Grupo constante: o painel que atravessa o port é de UM ativo (o do ScopeSpec).
# A biblioteca exige um `group_ids`; este valor não carrega informação e é
# detalhe interno do adapter (ADR 5.4.0004).
_SINGLE_GROUP = "asset"
_AUTO_NORMALIZER_ENCODER_THRESHOLD = 20


@dataclass(frozen=True)
class _TftDatasets:
    """Seam interno de teste: os três datasets + o que precisa ser verificado.

    Existe para que os critérios da Task 07 (A4c, contagens de I17) sejam
    verificáveis no próprio commit, sem depender do treino da Task 08.
    """

    training: Any
    monitor: Any
    prediction: Any
    normalizer_center: float
    normalizer_scale: float
    fitted_decision_count: int
    monitored_decision_count: int


@contextmanager
def _translating_backend_errors() -> Iterator[None]:
    """Seção de código da biblioteca: qualquer falha enumerada vira `ModelTrainingError`.

    A original vai em `__cause__` (`raise ... from exc`) — nunca se perde. Só envolve
    chamadas à lib; a regra do port (`resolve_panel_geometry`, C5, C10) fica de fora.
    """
    try:
        yield
    except _BACKEND_ERRORS as exc:
        msg = f"pytorch-forecasting/lightning failed: {type(exc).__name__}: {exc}"
        raise ModelTrainingError(msg) from exc


class _LossHistory(Callback):
    """Callback que acumula a perda de validação POR ÉPOCA (D11).

    O Lightning expõe só o ÚLTIMO valor das métricas; o histórico é contrato do
    port (`val_loss_by_epoch`), então precisa ser coletado explicitamente. A
    guarda de sanidade não é cosmética: o mesmo gancho dispara na passagem de
    sanidade, e uma entrada antes da época 0 deslocaria todo o índice —
    quebrando a identidade `best_epoch == argmin` que A5 usa como prova.

    """

    def __init__(self) -> None:
        self.losses: list[float] = []

    def on_validation_epoch_end(self, trainer: Any, pl_module: Any) -> None:  # noqa: ANN401
        if getattr(trainer, "sanity_checking", False):
            return
        value = trainer.callback_metrics.get("val_loss")
        if value is not None:
            self.losses.append(float(value))


@dataclass(frozen=True)
class _TftFit:
    """Seam interno do treino: o que sai do ajuste, antes de qualquer predição."""

    model: Any
    val_loss_by_epoch: tuple[float, ...]
    best_epoch: int
    best_val_loss: float
    artifact_path: str


def _select_best_epoch(history: Sequence[float]) -> int:
    """Época de MENOR perda de validação (I6), desempate pela mais antiga.

    Helper puro de propósito: é o que permite testar a seleção — e o C10 de
    histórico não finito — sem depender de um treino divergir de verdade.
    """
    finite = [(position, loss) for position, loss in enumerate(history) if math.isfinite(loss)]
    if not finite:
        msg = (
            "perda de validação nunca foi finita — nenhum checkpoint utilizável foi produzido (C10)"
        )
        raise ValueError(msg)
    return min(finite, key=lambda pair: (pair[1], pair[0]))[0]


def _assert_finite(values: Sequence[float], *, decision: int, horizon: int) -> None:
    """C5 — nada não finito sai silenciosamente.

    Avaliado **depois** do recorte por comprimento de decodificador: as posições
    de padding da cauda são não finitas por construção, então checar antes faria
    toda cauda legítima erguer.
    """
    if not all(math.isfinite(value) for value in values):
        msg = (
            f"grade não finita emitida para decisão {decision}, horizonte "
            f"{horizon}: {values!r} (C5)"
        )
        raise ValueError(msg)


def _require_checkpoint(path: str | None) -> str:
    """C10 — caminho vazio significa que nada foi salvo; falhar aqui é o certo.

    Devolver um `artifact_path` inválido só quebraria na Stage 7.1, longe da
    causa.
    """
    if not path:
        msg = (
            "treino terminou sem checkpoint utilizável (caminho vazio) — "
            "verifique se houve ao menos uma época de validação finita (C10)"
        )
        raise ValueError(msg)
    return path


class PfTftTrainer:
    """Treinador do TFT quantílico sobre `pytorch-forecasting` (satisfaz o port)."""

    def train_and_predict(  # noqa: PLR0913 — espelha a assinatura do port
        self,
        *,
        params: TftTrainingParams,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        train_decision_indices: Sequence[int],
        early_stop_decision_indices: Sequence[int],
        test_decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        artifact_dir: str,
    ) -> TftTrainingResult:
        """Implementa o contrato do port `TftTrainer` (concept 5.4 §4)."""
        from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (  # noqa: PLC0415
            TftTrainingResult,
        )

        datasets = self.build_datasets(
            params=params,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            rows=rows,
            target=target,
            train_decision_indices=train_decision_indices,
            early_stop_decision_indices=early_stop_decision_indices,
            test_decision_indices=test_decision_indices,
            max_horizon=max_horizon,
            horizons=horizons,
        )
        # Fit-only (varredura): sem decisões de teste não há checkpoint a
        # escrever nem grade a emitir (ADR 5.4.0005).
        write_checkpoint = bool(test_decision_indices)
        fitted = self.fit(
            datasets=datasets,
            params=params,
            quantile_levels=quantile_levels,
            artifact_dir=artifact_dir,
            write_checkpoint=write_checkpoint,
        )
        grids = (
            self._emit(
                model=fitted.model,
                prediction_dataset=datasets.prediction,
                requested_decisions=frozenset(test_decision_indices),
                horizons=horizons,
                quantile_levels=quantile_levels,
                batch_size=params.batch_size,
            )
            if test_decision_indices
            else {}
        )
        return TftTrainingResult(
            grids=grids,
            best_epoch=fitted.best_epoch,
            best_val_loss=fitted.best_val_loss,
            val_loss_by_epoch=fitted.val_loss_by_epoch,
            fitted_decision_count=datasets.fitted_decision_count,
            monitored_decision_count=datasets.monitored_decision_count,
            normalizer_center=datasets.normalizer_center,
            normalizer_scale=datasets.normalizer_scale,
            artifact_path=fitted.artifact_path,
        )

    @staticmethod
    def _emit(  # noqa: PLR0913 — parâmetros coesos da regra de emissão
        *,
        model: Any,  # noqa: ANN401 — modelo da lib não cruza a fronteira do port
        prediction_dataset: Any,  # noqa: ANN401
        requested_decisions: frozenset[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
    ) -> dict[int, dict[int, tuple[float, ...]]]:
        """Grade crua por (decisão x horizonte), recortada pelo decodificador real.

        Três detalhes que não são opcionais:

        1. **A chave de decisão vem do índice devolvido pela predição**, nunca de
           uma contagem paralela mantida aqui. O `time_idx` do índice é o
           PRIMEIRO passo do decodificador, logo a decisão é `time_idx - 1`. É
           essa amarração que impede o off-by-one da classe registrada no ADR
           4.3.0001 como o bug mais caro do repositório antigo.
        2. **A saída é retangular e preenchida na cauda.** Sem recortar por
           `decoder_lengths`, o padding viraria predição fabricada (I15).
        3. **Uma decisão pode aparecer em MAIS DE UMA amostra** quando o
           comprimento mínimo do decodificador é 1: a biblioteca gera também as
           janelas curtas. Fica a de decodificador MAIS LONGO — é a geometria
           com que o modelo foi treinado (treino e monitor usam sempre
           `max_horizon` passos), então usar a curta quando a longa existe
           avaliaria o modelo numa forma de entrada que ele nunca viu.
        """
        with _translating_backend_errors():
            prediction = model.predict(
                prediction_dataset,
                mode="quantiles",
                return_index=True,
                return_decoder_lengths=True,
                batch_size=batch_size,
                num_workers=0,
                # `predict` constrói um `Trainer` PRÓPRIO com os defaults da lib —
                # `logger=True` escreve `lightning_logs/` no diretório de trabalho a
                # cada chamada, e `accelerator="auto"` poderia predizer em GPU
                # enquanto o treino foi fixado em CPU (o que enfraqueceria I9).
                # Fixar aqui é o único ponto onde isso é controlável.
                trainer_kwargs={
                    "logger": False,
                    "accelerator": "cpu",
                    "devices": 1,
                    "enable_progress_bar": False,
                    "enable_model_summary": False,
                },
            )
        decision_of_sample = [int(time_idx) - 1 for time_idx in prediction.index[_TIME_IDX_COLUMN]]
        lengths = [int(length) for length in prediction.decoder_lengths]

        best_sample_by_decision: dict[int, int] = {}
        for sample, decision in enumerate(decision_of_sample):
            # Filtro EXPLÍCITO pelas decisões pedidas. Recortar o quadro não
            # basta: com decodificador mínimo de 1 passo, a decisão seguinte à
            # última pedida ainda cabe no quadro (usa uma linha só) e a
            # biblioteca a gera. O contrato do port é "para cada decisão de
            # teste", e o use case reprovaria o excedente (D5).
            if decision not in requested_decisions:
                continue
            current = best_sample_by_decision.get(decision)
            if current is None or lengths[sample] > lengths[current]:
                best_sample_by_decision[decision] = sample

        grids: dict[int, dict[int, tuple[float, ...]]] = {}
        for decision, sample in sorted(best_sample_by_decision.items()):
            by_horizon: dict[int, tuple[float, ...]] = {}
            for horizon in horizons:
                if horizon > lengths[sample]:
                    continue  # passo além do decodificador real: não existe
                values = tuple(float(value) for value in prediction.output[sample, horizon - 1, :])
                _assert_finite(values, decision=decision, horizon=horizon)
                if len(values) != len(quantile_levels):
                    msg = (
                        f"grade emitida com {len(values)} valores para "
                        f"{len(quantile_levels)} níveis (decisão {decision}, "
                        f"horizonte {horizon})"
                    )
                    raise ValueError(msg)
                by_horizon[horizon] = values
            if by_horizon:
                grids[decision] = by_horizon
        return grids

    def build_datasets(  # noqa: PLR0913 — espelha a fronteira do port
        self,
        *,
        params: TftTrainingParams,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        train_decision_indices: Sequence[int],
        early_stop_decision_indices: Sequence[int],
        test_decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
    ) -> _TftDatasets:
        """Monta os três datasets pelo mecanismo de recorte por partição (D5).

        Público (sem underscore) de propósito: é o seam que torna A4(c) e as
        contagens de I17 verificáveis sem depender do treino.

        A regra do painel (C4/I17/C3) é do domínio (`tft_panel_geometry`, #75);
        aqui fica só o que é `pytorch_forecasting`: `TimeSeriesDataSet`,
        `from_dataset` e o recorte dos quadros pelas faixas elegíveis.
        """
        encoder_length = params.max_encoder_length
        geometry = resolve_panel_geometry(
            encoder_length=encoder_length,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            rows=rows,
            target=target,
            train_decision_indices=train_decision_indices,
            early_stop_decision_indices=early_stop_decision_indices,
            test_decision_indices=test_decision_indices,
            max_horizon=max_horizon,
            horizons=horizons,
        )
        fitted = geometry.fitted_decisions
        monitored = geometry.monitored_decisions

        # Código NOSSO fica fora da seção traduzida (F3 da auditoria do PR #88): um
        # `float(None)` aqui seria bug do chamador, não falha da lib.
        frame = self._panel_frame(feature_names, rows, target)
        unknown_names = [name for name in feature_names if name not in set(known_feature_names)]

        with _translating_backend_errors():
            training = TimeSeriesDataSet(
                frame.iloc[: max(fitted) + max_horizon + 1],
                time_idx=_TIME_IDX_COLUMN,
                target=_TARGET_COLUMN,
                group_ids=[_GROUP_COLUMN],
                min_encoder_length=encoder_length,
                max_encoder_length=encoder_length,
                min_prediction_length=max_horizon,
                max_prediction_length=max_horizon,
                min_prediction_idx=min(fitted) + 1,
                time_varying_known_reals=list(known_feature_names),
                time_varying_unknown_reals=[*unknown_names, _TARGET_COLUMN],
                # Explícito, NUNCA "auto" (ADR 5.4.0006): acima de 20 sessões de
                # janela o automático escolheria um normalizador POR JANELA, e a
                # produção (60) cairia num caminho que os testes (~12) não usam.
                target_normalizer=GroupNormalizer(groups=[]),
                add_relative_time_idx=True,
                allow_missing_timesteps=False,
            )
            # Monitor e predição DERIVADOS do de treino: é o que herda o
            # normalizador já ajustado em vez de reajustar (I4b). Construí-los do
            # zero sobre o painel inteiro é exatamente o vazamento que o ADR
            # 5.4.0001 cláusula 2 existe para impedir.
            monitor = TimeSeriesDataSet.from_dataset(
                training,
                frame.iloc[: max(monitored) + max_horizon + 1],
                min_prediction_idx=min(monitored) + 1,
                stop_randomization=True,
            )
            prediction = (
                TimeSeriesDataSet.from_dataset(
                    training,
                    # TETO também aqui: a lib só expressa piso, então sem recortar o
                    # quadro o dataset geraria decisões DEPOIS do bloco de teste —
                    # e todo fold que não é o último tem painel adiante dele. O
                    # último par legítimo precisa do índice `max(test) + max_horizon`.
                    frame.iloc[: max(test_decision_indices) + max_horizon + 1],
                    min_prediction_idx=min(test_decision_indices) + 1,
                    # Cauda variável (D2/I16): sem isto o default herdado
                    # (`min == max`) descartaria as decisões da ponta do painel.
                    min_prediction_length=1,
                    stop_randomization=True,
                )
                if test_decision_indices
                else None
            )
            center, scale = self._normalizer_parameters(training)
        return _TftDatasets(
            training=training,
            monitor=monitor,
            prediction=prediction,
            normalizer_center=center,
            normalizer_scale=scale,
            fitted_decision_count=len(fitted),
            monitored_decision_count=len(monitored),
        )

    def fit(
        self,
        *,
        datasets: _TftDatasets,
        params: TftTrainingParams,
        quantile_levels: Sequence[float],
        artifact_dir: str,
        write_checkpoint: bool,
    ) -> _TftFit:
        """Ajusta o modelo e devolve o melhor checkpoint (I6/D6/D11).

        Seam público: os critérios de A5 e C10 são verificáveis aqui, sem
        depender do caminho de predição.
        """
        # Re-semear a CADA chamada: o gerador global avança entre elas, então
        # semear uma vez no import não daria o determinismo que I9 afirma.
        pl.seed_everything(params.seed, workers=True)

        train_loader = datasets.training.to_dataloader(
            train=True, batch_size=params.batch_size, num_workers=0
        )
        val_loader = datasets.monitor.to_dataloader(
            train=False, batch_size=params.batch_size, num_workers=0
        )
        with _translating_backend_errors():
            model = TemporalFusionTransformer.from_dataset(
                datasets.training,
                learning_rate=params.learning_rate,
                hidden_size=params.hidden_size,
                attention_head_size=params.attention_head_size,
                dropout=params.dropout,
                hidden_continuous_size=params.hidden_continuous_size,
                # A grade é a do COMANDO: o default da biblioteca são 7 níveis
                # fixos que não são a grade densa do projeto.
                loss=QuantileLoss(quantiles=list(quantile_levels)),
            )
            history = _LossHistory()
            callbacks: list[Any] = [
                history,
                EarlyStopping(monitor="val_loss", patience=params.patience, mode="min"),
            ]
            checkpoint: Any = None
            if write_checkpoint:
                checkpoint = ModelCheckpoint(
                    dirpath=artifact_dir, monitor="val_loss", mode="min", save_top_k=1
                )
                callbacks.append(checkpoint)
            # `Trainer(deterministic=True)` liga uma flag GLOBAL de processo do
            # torch e nunca a desliga — ela vazaria para o resto da suite (o adapter
            # FinBERT, por exemplo, ergue sob algoritmos determinísticos). I9 exige
            # restaurar; daí o `finally` abaixo.
            deterministic_before = torch.are_deterministic_algorithms_enabled()
            trainer = pl.Trainer(
                max_epochs=params.max_epochs,
                accelerator="cpu",
                devices=1,
                deterministic=True,
                # Sem passagem de sanidade: ela dispara o mesmo gancho ANTES da
                # época 0 e deslocaria todo o histórico, quebrando a identidade
                # `best_epoch == argmin` que A5 usa como prova (D11).
                num_sanity_val_steps=0,
                enable_checkpointing=write_checkpoint,
                enable_progress_bar=False,
                enable_model_summary=False,
                logger=False,
                callbacks=callbacks,
            )
            try:
                trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)
            finally:
                torch.use_deterministic_algorithms(deterministic_before)

        val_loss_by_epoch = tuple(history.losses)
        best_epoch = _select_best_epoch(val_loss_by_epoch)
        if not write_checkpoint:
            return _TftFit(
                model=model,
                val_loss_by_epoch=val_loss_by_epoch,
                best_epoch=best_epoch,
                best_val_loss=val_loss_by_epoch[best_epoch],
                artifact_path="",
            )
        artifact_path = _require_checkpoint(checkpoint.best_model_path)
        # Restauração EXPLÍCITA: o callback de parada antecipada não a faz, e
        # sem ela a predição usaria os pesos da última época (I6/D6).
        with _translating_backend_errors():
            restored = TemporalFusionTransformer.load_from_checkpoint(artifact_path)
        return _TftFit(
            model=restored,
            val_loss_by_epoch=val_loss_by_epoch,
            best_epoch=best_epoch,
            best_val_loss=val_loss_by_epoch[best_epoch],
            artifact_path=artifact_path,
        )

    @staticmethod
    def _panel_frame(
        feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
    ) -> Any:  # noqa: ANN401 — pandas.DataFrame não cruza a fronteira do port
        data = {
            name: [float(row[position]) for row in rows]
            for position, name in enumerate(feature_names)
        }
        data[_TARGET_COLUMN] = [float(value) for value in target]
        frame = pd.DataFrame(data)
        frame[_TIME_IDX_COLUMN] = range(len(rows))
        frame[_GROUP_COLUMN] = _SINGLE_GROUP
        return frame

    @staticmethod
    def _normalizer_parameters(training: Any) -> tuple[float, float]:  # noqa: ANN401
        """Centro/escala AJUSTADOS pelo normalizador (nunca recalculados).

        Recalcular aqui tornaria a asserção de A4(c) tautológica — ela existe
        justamente para comparar o que a biblioteca ajustou contra a estatística
        do quadro de treino.
        """
        fitted = training.target_normalizer.norm_
        return float(fitted["center"]), float(fitted["scale"])
