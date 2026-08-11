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
| predição | painel inteiro                                 | `min(test)+1`  |

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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import lightning.pytorch as pl
import pandas as pd
from lightning.pytorch.callbacks import Callback, EarlyStopping, ModelCheckpoint
from pytorch_forecasting import QuantileLoss, TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data.encoders import GroupNormalizer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainingParams,
        TftTrainingResult,
    )

_TIME_IDX_COLUMN = "time_idx"
_TARGET_COLUMN = "target"
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


def _validate_structure(  # noqa: PLR0913 — validação coesa da fronteira (C4)
    *,
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    rows: Sequence[Sequence[float]],
    target: Sequence[float],
    train_decision_indices: Sequence[int],
    early_stop_decision_indices: Sequence[int],
    test_decision_indices: Sequence[int],
    max_horizon: int,
    horizons: Sequence[int],
) -> None:
    """C4 — mesma regra do fake, para a suite de contrato ter paridade."""
    if len(target) != len(rows):
        msg = f"len(target)={len(target)} != len(rows)={len(rows)} (C4)"
        raise ValueError(msg)
    width = len(feature_names)
    for position, row in enumerate(rows):
        if len(row) != width:
            msg = f"rows[{position}] tem {len(row)} colunas, esperado {width} (C4)"
            raise ValueError(msg)
    unknown_known = set(known_feature_names) - set(feature_names)
    if unknown_known:
        msg = f"known_feature_names não contido em feature_names: {sorted(unknown_known)} (C4)"
        raise ValueError(msg)
    if max_horizon < 1:
        msg = f"max_horizon deve ser >= 1, recebido {max_horizon} (C4)"
        raise ValueError(msg)
    if not horizons:
        msg = "horizons não pode ser vazio (C4)"
        raise ValueError(msg)
    out_of_range = [h for h in horizons if not 1 <= h <= max_horizon]
    if out_of_range:
        msg = f"horizons {out_of_range} fora de 1..{max_horizon} (C4)"
        raise ValueError(msg)
    if not early_stop_decision_indices:
        msg = "early_stop_decision_indices vazio — sem monitor não há seleção de época (C4)"
        raise ValueError(msg)

    panel_size = len(rows)
    for name, indices in (
        ("train_decision_indices", train_decision_indices),
        ("early_stop_decision_indices", early_stop_decision_indices),
        ("test_decision_indices", test_decision_indices),
    ):
        _validate_contiguous(name, indices, panel_size)


def _validate_contiguous(name: str, indices: Sequence[int], panel_size: int) -> None:
    """C4/D5 — faixa contígua, crescente e dentro do painel.

    Contiguidade não é capricho: a biblioteca só expressa piso de decisão, então
    um conjunto arbitrário não seria honrável — e um port que aceita o que o
    adapter não honra produz divergência fake<->real silenciosa no monitor.
    """
    for position, index in enumerate(indices):
        if not 0 <= index < panel_size:
            msg = f"{name}[{position}]={index} fora do painel de {panel_size} sessões (C4)"
            raise ValueError(msg)
        if position > 0 and index != indices[position - 1] + 1:
            msg = (
                f"{name} deve ser uma faixa contígua e crescente; "
                f"{indices[position - 1]} seguido de {index} (C4)"
            )
            raise ValueError(msg)


def _eligible(
    indices: Sequence[int], *, encoder_length: int, max_horizon: int, panel_size: int
) -> tuple[int, ...]:
    """Decisões com janela E decodificador completos (I17) — regra do port."""
    return tuple(
        index
        for index in indices
        if index >= encoder_length - 1 and index + max_horizon <= panel_size - 1
    )


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
    finite = [
        (position, loss)
        for position, loss in enumerate(history)
        if math.isfinite(loss)
    ]
    if not finite:
        msg = (
            "perda de validação nunca foi finita — nenhum checkpoint utilizável "
            "foi produzido (C10)"
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
    def _emit(
        *,
        model: Any,  # noqa: ANN401 — modelo da lib não cruza a fronteira do port
        prediction_dataset: Any,  # noqa: ANN401
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
        prediction = model.predict(
            prediction_dataset,
            mode="quantiles",
            return_index=True,
            return_decoder_lengths=True,
            batch_size=batch_size,
            num_workers=0,
        )
        decision_of_sample = [
            int(time_idx) - 1 for time_idx in prediction.index[_TIME_IDX_COLUMN]
        ]
        lengths = [int(length) for length in prediction.decoder_lengths]

        best_sample_by_decision: dict[int, int] = {}
        for sample, decision in enumerate(decision_of_sample):
            current = best_sample_by_decision.get(decision)
            if current is None or lengths[sample] > lengths[current]:
                best_sample_by_decision[decision] = sample

        grids: dict[int, dict[int, tuple[float, ...]]] = {}
        for decision, sample in sorted(best_sample_by_decision.items()):
            by_horizon: dict[int, tuple[float, ...]] = {}
            for horizon in horizons:
                if horizon > lengths[sample]:
                    continue  # passo além do decodificador real: não existe
                values = tuple(
                    float(value) for value in prediction.output[sample, horizon - 1, :]
                )
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
        """
        _validate_structure(
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
        panel_size = len(rows)
        encoder_length = params.max_encoder_length
        fitted = _eligible(
            train_decision_indices,
            encoder_length=encoder_length,
            max_horizon=max_horizon,
            panel_size=panel_size,
        )
        monitored = _eligible(
            early_stop_decision_indices,
            encoder_length=encoder_length,
            max_horizon=max_horizon,
            panel_size=panel_size,
        )
        if not fitted:
            msg = (
                "nenhuma decisão de treino sobrou após exigir janela de contexto de "
                f"{encoder_length} sessões e decodificador de {max_horizon} passos (C3)"
            )
            raise ValueError(msg)
        if not monitored:
            msg = (
                "nenhuma decisão de monitor sobrou após exigir janela de contexto de "
                f"{encoder_length} sessões e decodificador de {max_horizon} passos (C3)"
            )
            raise ValueError(msg)

        frame = self._panel_frame(feature_names, rows, target)
        unknown_names = [name for name in feature_names if name not in set(known_feature_names)]

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
                frame,
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
        trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)

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
