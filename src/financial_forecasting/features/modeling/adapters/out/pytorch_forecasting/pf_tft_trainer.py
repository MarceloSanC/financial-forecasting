"""Adapter `PfTftTrainer` — implementa os ports `TftTrainer` e `TftCheckpointPredictor`.

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
adiante dele — o use case reprovaria com `assert_emission_within_request`.

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

**Predição a partir do checkpoint (Stage 7.1; port `TftCheckpointPredictor`).**
`predict_from_checkpoint` usa a MESMA receita do dataset de predição
(`_prediction_dataset`, que o `build_datasets` também usa) e o MESMO `_emit`
(ADR 7.1.0001 item 3). Os bytes do checkpoint são lidos uma vez: o sha256 deles é
conferido e o modelo é carregado deles (C10 — sem janela entre hash e unpickle);
o dataset é reconstruído do `dataset_parameters` gravado no checkpoint, com o
normalizador já ajustado (nada é reajustado — I3); as entradas declaradas são
conferidas contra as passadas (C4). A predição roda com `num_threads` pedido e
algoritmos determinísticos desligados — o estado em que o treino emitiu o teste
(o `fit` restaura a flag antes do `_emit`) —, restaurando os dois depois.
"""

from __future__ import annotations

import io
import math
import pickle
import platform
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import metadata
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

import lightning.pytorch as pl
import pandas as pd
import torch
from lightning.fabric.utilities.exceptions import MisconfigurationException
from lightning.pytorch.callbacks import Callback, EarlyStopping, ModelCheckpoint
from pytorch_forecasting import QuantileLoss, TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data.encoders import GroupNormalizer

from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
    sha256_of_stream,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    ModelTrainingError,
)
from financial_forecasting.features.modeling.domain.services.tft_panel_geometry import (
    resolve_panel_geometry,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (  # noqa: E501
        TftAttributionPrediction,
        TftCheckpointPrediction,
    )
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
# traduzidas e continuam `ValueError`. A carga do checkpoint (Stage 7.1) soma os dois
# que o `torch.load` ergue sobre bytes que não são checkpoint, também verificados no
# container: `pickle.UnpicklingError` (lixo, zip inválido) e `EOFError` (arquivo vazio).
_BACKEND_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    KeyError,
    RuntimeError,
    TypeError,
    AssertionError,
    MisconfigurationException,
    pickle.UnpicklingError,
    EOFError,
)
_GROUP_COLUMN = "series"
# Grupo constante: o painel que atravessa o port é de UM ativo (o do ScopeSpec).
# A biblioteca exige um `group_ids`; este valor não carrega informação e é
# detalhe interno do adapter (ADR 5.4.0004).
_SINGLE_GROUP = "asset"
_AUTO_NORMALIZER_ENCODER_THRESHOLD = 20
_SKLEARN_DISTRIBUTION = "scikit-learn"


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


def _prediction_dataset(
    parameters: dict[str, Any],
    frame: Any,  # noqa: ANN401 — pandas.DataFrame não cruza a fronteira do port
    *,
    decision_indices: Sequence[int],
    max_horizon: int,
) -> Any:  # noqa: ANN401 — TimeSeriesDataSet não cruza a fronteira do port
    """Receita ÚNICA do dataset de predição — treino (teste) e checkpoint (teste/calib).

    `parameters` é o `get_parameters()` do dataset de treino (no treino) ou o
    `dataset_parameters` gravado no checkpoint (na inferência): o normalizador
    vem ajustado e nada é reajustado. TETO pelo recorte do quadro (a lib só
    expressa piso; sem o teto o dataset geraria decisões depois do bloco
    pedido — todo fold que não é o último tem painel adiante dele). O último par
    legítimo precisa do índice `max(decisões) + max_horizon`. Cauda variável
    (D2/I16): sem `min_prediction_length=1` o default herdado (`min == max`)
    descartaria as decisões da ponta do painel.
    """
    return TimeSeriesDataSet.from_parameters(
        parameters,
        frame.iloc[: max(decision_indices) + max_horizon + 1],
        min_prediction_idx=min(decision_indices) + 1,
        min_prediction_length=1,
        stop_randomization=True,
    )


def _require_contiguous(decisions: Sequence[int]) -> None:
    """Faixa de decisões não vazia, contígua e crescente (contrato do port, D5)."""
    if not decisions or any(b != a + 1 for a, b in pairwise(decisions)):
        msg = f"decision indices must be a non-empty contiguous increasing range: {decisions!r}"
        raise ValueError(msg)


def _declared_mismatches(  # noqa: PLR0913 — uma entrada declarada por argumento
    *,
    parameters: dict[str, Any],
    checkpoint_levels: Sequence[float],
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    max_horizon: int,
    quantile_levels: Sequence[float],
) -> list[str]:
    """O que o checkpoint declara diferente do pedido (C4); lista vazia = confere."""
    known = list(known_feature_names)
    unknown = [name for name in feature_names if name not in set(known)]
    mismatches = []
    if list(parameters.get("time_varying_known_reals", [])) != known:
        mismatches.append(
            f"known reals {parameters.get('time_varying_known_reals')!r} != {known!r}"
        )
    expected_unknown = [*unknown, _TARGET_COLUMN]
    if list(parameters.get("time_varying_unknown_reals", [])) != expected_unknown:
        mismatches.append(
            f"unknown reals {parameters.get('time_varying_unknown_reals')!r} "
            f"!= {expected_unknown!r}"
        )
    if parameters.get("max_prediction_length") != max_horizon:
        mismatches.append(
            f"max_prediction_length {parameters.get('max_prediction_length')!r} != {max_horizon}"
        )
    if [float(level) for level in checkpoint_levels] != [float(q) for q in quantile_levels]:
        mismatches.append(
            f"quantile levels {list(checkpoint_levels)!r} != {list(quantile_levels)!r}"
        )
    return mismatches


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


SUPPORTED_ACCELERATORS: frozenset[str] = frozenset({"cpu", "gpu"})


def _predict_trainer_kwargs(accelerator: str) -> dict[str, Any]:
    """`trainer_kwargs` do `predict`: sem logger, o accelerator da instância, 1 device."""
    return {
        "logger": False,
        "accelerator": accelerator,
        "devices": 1,
        "enable_progress_bar": False,
        "enable_model_summary": False,
    }


def _best_sample_by_decision(
    decision_of_sample: Sequence[int], lengths: Sequence[int], requested: frozenset[int]
) -> dict[int, int]:
    """Decisão pedida → amostra de decodificador MAIS LONGO (regra única do `_emit`).

    Filtro EXPLÍCITO pelas decisões pedidas. Recortar o quadro não basta: com
    decodificador mínimo de 1 passo, a decisão seguinte à última pedida ainda cabe no
    quadro (usa uma linha só) e a biblioteca a gera. O contrato do port é "para cada
    decisão de teste", e o use case reprovaria o excedente (D5).
    """
    best: dict[int, int] = {}
    for sample, decision in enumerate(decision_of_sample):
        if decision not in requested:
            continue
        current = best.get(decision)
        if current is None or lengths[sample] > lengths[current]:
            best[decision] = sample
    return best


def _identity_dataloader(dataset: Any, batch_size: int) -> Any:  # noqa: ANN401 — tipos da lib
    """O dataloader que o `predict` monta para um `TimeSeriesDataSet` (identidade, I7)."""
    return dataset.to_dataloader(train=False, batch_size=batch_size, num_workers=0)


def _load_checked_checkpoint(  # noqa: PLR0913 — as entradas conferidas, uma por argumento
    *,
    checkpoint_path: str,
    expected_sha256: str,
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    max_horizon: int,
    quantile_levels: Sequence[float],
    artifact_changed: type[Exception],
    checkpoint_mismatch: type[Exception],
) -> tuple[Any, dict[str, Any]]:
    """Bytes lidos uma vez, sha256 antes da carga (C10) e entradas declaradas (C4)."""
    data = Path(checkpoint_path).read_bytes()  # lidos UMA vez (C10)
    observed = sha256_of_stream(io.BytesIO(data))
    if observed != expected_sha256:
        msg = (
            f"checkpoint {checkpoint_path} sha256 {observed[:12]} != expected "
            f"{expected_sha256[:12]} — not loaded (C10)"
        )
        raise artifact_changed(msg)
    with _translating_backend_errors():
        model = TemporalFusionTransformer.load_from_checkpoint(io.BytesIO(data))
    parameters = dict(model.dataset_parameters)
    mismatches = _declared_mismatches(
        parameters=parameters,
        checkpoint_levels=list(model.loss.quantiles),
        feature_names=feature_names,
        known_feature_names=known_feature_names,
        max_horizon=max_horizon,
        quantile_levels=quantile_levels,
    )
    if mismatches:
        msg = f"checkpoint {checkpoint_path} declares other inputs: {'; '.join(mismatches)} (C4)"
        raise checkpoint_mismatch(msg)
    return model, parameters


def _check_family_columns(
    parameters: Mapping[str, Any],
    permuted_columns: Mapping[str, Sequence[str]],
    *,
    error: type[Exception],
) -> None:
    """C5/I8: toda coluna de família é real `unknown` do encoder no checkpoint."""
    unknown = set(parameters.get("time_varying_unknown_reals", []))
    known = set(parameters.get("time_varying_known_reals", []))
    for family, names in permuted_columns.items():
        offending = [name for name in names if name not in unknown or name in known]
        if not names or offending:
            msg = (
                f"family {family!r}: columns {offending or list(names)!r} are not unknown "
                "encoder reals in the checkpoint (C5)"
            )
            raise error(msg)


def donor_blocks(
    encoder_cont: Any,  # noqa: ANN401 — tensor da lib
    encoder_lengths: Any,  # noqa: ANN401
    best_sample_by_decision: Mapping[int, int],
    decisions: Sequence[int],
    columns: Mapping[str, Sequence[int]],
) -> tuple[dict[str, list[Any]], int]:
    """Família → bloco doador por POSIÇÃO em `decisions`, e o comprimento L do encoder.

    O bloco é `encoder_cont[amostra, :L, colunas da família]` da amostra de decodificador
    mais longo de cada decisão. Toda decisão precisa de amostra e todas têm o mesmo L;
    senão `ValueError` (o adapter nunca trunca nem completa).
    """
    missing = [decision for decision in decisions if decision not in best_sample_by_decision]
    if missing:
        msg = f"decisions without a prediction sample cannot take part in a swap: {missing!r}"
        raise ValueError(msg)
    samples = [best_sample_by_decision[decision] for decision in decisions]
    lengths = {int(encoder_lengths[sample]) for sample in samples}
    if len(lengths) != 1:
        msg = f"encoder lengths differ between the decisions: {sorted(lengths)!r}"
        raise ValueError(msg)
    (length,) = lengths
    blocks = {
        family: [encoder_cont[sample, :length, list(cols)].clone() for sample in samples]
        for family, cols in columns.items()
    }
    return blocks, length


def _swapping_collate(  # noqa: PLR0913 — o que a troca de uma (família, k) precisa
    dataset: Any,  # noqa: ANN401 — TimeSeriesDataSet
    *,
    decisions: Sequence[int],
    permutation: Sequence[int],
    columns: Sequence[int],
    blocks: Sequence[Any],
    encoder_length: int,
) -> Any:  # noqa: ANN401 — callable do DataLoader
    """`collate_fn` que troca o encoder das colunas da família pelo bloco do doador.

    A decisão de cada amostra é lida de `decoder_time_idx[i, 0] - 1` (a mesma amarração
    do `_emit`); a decisão na posição p recebe o bloco da posição `permutation[p]`.
    Amostra de decisão fora do pedido passa intacta.
    """
    position = {decision: p for p, decision in enumerate(decisions)}
    default = dataset._collate_fn  # o collate da lib, envolvido
    cols = list(columns)

    def collate(batch: Any) -> Any:  # noqa: ANN401
        x, y = default(batch)
        decision_of_sample = (x["decoder_time_idx"][:, 0] - 1).tolist()
        for i, decision in enumerate(decision_of_sample):
            p = position.get(int(decision))
            if p is None:
                continue
            if int(x["encoder_lengths"][i]) != encoder_length:
                msg = (
                    f"decision {decision}: encoder length {int(x['encoder_lengths'][i])} != "
                    f"{encoder_length} of the donor blocks"
                )
                raise ValueError(msg)
            x["encoder_cont"][i, :encoder_length, cols] = blocks[permutation[p]]
        return x, y

    return collate


class PfTftTrainer:
    """TFT quantílico sobre `pytorch-forecasting`.

    Satisfaz os ports `TftTrainer` (treino + teste) e `TftCheckpointPredictor`
    (predição a partir do checkpoint gravado, Stage 7.1).

    O `accelerator` do Lightning é da INSTÂNCIA (Stage 7.3, ADR 7.3.0004 itens 1-2):
    o mesmo valor vai ao `Trainer` do `fit`, ao `Trainer` interno do `predict` no
    `_emit` e à chave `accelerator` dos `settings` da predição a partir do
    checkpoint. O default `"cpu"` é o caminho confirmatório da 5.4/7.1, intacto; o
    composition root monta uma instância `"gpu"` só para o cohort de ablação (ROCm).
    """

    def __init__(self, accelerator: str = "cpu") -> None:
        if accelerator not in SUPPORTED_ACCELERATORS:
            msg = (
                f"accelerator must be one of {sorted(SUPPORTED_ACCELERATORS)}, "
                f"got {accelerator!r}"
            )
            raise ValueError(msg)
        self._accelerator = accelerator

    @property
    def accelerator(self) -> str:
        """O `accelerator` do Lightning desta instância."""
        return self._accelerator

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
                accelerator=self._accelerator,
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

    def predict_from_checkpoint(  # noqa: PLR0913 — espelha a assinatura do port
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
    ) -> TftCheckpointPrediction:
        """Implementa o contrato do port `TftCheckpointPredictor` (concept 7.1 §4)."""
        from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (  # noqa: PLC0415, E501
            ArtifactChangedError,
            CheckpointMismatchError,
            TftCheckpointPrediction,
        )

        decisions = tuple(decision_indices)
        _require_contiguous(decisions)  # regra do pedido: antes de ler qualquer byte
        model, parameters = _load_checked_checkpoint(
            checkpoint_path=checkpoint_path,
            expected_sha256=expected_sha256,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            max_horizon=max_horizon,
            quantile_levels=quantile_levels,
            artifact_changed=ArtifactChangedError,
            checkpoint_mismatch=CheckpointMismatchError,
        )
        frame = self._panel_frame(feature_names, rows, target)

        threads_before = torch.get_num_threads()
        deterministic_before = torch.are_deterministic_algorithms_enabled()
        warn_only_before = torch.is_deterministic_algorithms_warn_only_enabled()
        try:
            torch.set_num_threads(num_threads)
            torch.use_deterministic_algorithms(False)
            with _translating_backend_errors():
                dataset = _prediction_dataset(
                    parameters, frame, decision_indices=decisions, max_horizon=max_horizon
                )
                center, scale = self._normalizer_parameters(dataset)
            grids = self._emit(
                model=model,
                prediction_dataset=dataset,
                requested_decisions=frozenset(decisions),
                horizons=horizons,
                quantile_levels=quantile_levels,
                batch_size=batch_size,
                accelerator=self._accelerator,
            )
        finally:
            torch.set_num_threads(threads_before)
            torch.use_deterministic_algorithms(deterministic_before, warn_only=warn_only_before)
        return TftCheckpointPrediction(
            grids=grids,
            normalizer_center=center,
            normalizer_scale=scale,
            settings=self._settings(batch_size=batch_size, num_threads=num_threads),
        )

    def predict_attribution_from_checkpoint(  # noqa: PLR0913 — espelha a assinatura do port
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
        permuted_columns: Mapping[str, Sequence[str]],
        donors: Sequence[Sequence[int]],
    ) -> TftAttributionPrediction:
        """Implementa `predict_attribution_from_checkpoint` (concept 7.3 §4, I6-I8; ADR 7.3.0002).

        Passagens sobre o MESMO dataset de predição do 7.1 (`_prediction_dataset`):

        1. uma passagem `mode="raw"` com `return_x`, de onde saem os blocos doadores
           (`encoder_cont[:L, colunas da família]` da amostra de decodificador mais longo
           de cada decisão) e os pesos da VSN do encoder;
        2. a identidade, pelo `_emit`, sobre o dataloader que o `predict` montaria
           (`to_dataloader(train=False, batch_size, num_workers=0)`);
        3. uma passagem por (família, k): o `collate_fn` da lib é envolvido, e a janela
           inteira do encoder das colunas da família de cada amostra é trocada pelo bloco
           da decisão doadora, lido da tabela da passagem 1 — o doador pode estar em
           qualquer lote. O decodificador e as outras colunas ficam intactos.
        """
        from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (  # noqa: PLC0415, E501
            ArtifactChangedError,
            CheckpointMismatchError,
            FamilyFeatureKnownError,
            TftAttributionPrediction,
            check_donors,
        )

        decisions = tuple(decision_indices)
        _require_contiguous(decisions)
        check_donors(donors, n_decisions=len(decisions))
        model, parameters = _load_checked_checkpoint(
            checkpoint_path=checkpoint_path,
            expected_sha256=expected_sha256,
            feature_names=feature_names,
            known_feature_names=known_feature_names,
            max_horizon=max_horizon,
            quantile_levels=quantile_levels,
            artifact_changed=ArtifactChangedError,
            checkpoint_mismatch=CheckpointMismatchError,
        )
        _check_family_columns(parameters, permuted_columns, error=FamilyFeatureKnownError)
        frame = self._panel_frame(feature_names, rows, target)

        threads_before = torch.get_num_threads()
        deterministic_before = torch.are_deterministic_algorithms_enabled()
        warn_only_before = torch.is_deterministic_algorithms_warn_only_enabled()
        try:
            torch.set_num_threads(num_threads)
            torch.use_deterministic_algorithms(False)
            with _translating_backend_errors():
                dataset = _prediction_dataset(
                    parameters, frame, decision_indices=decisions, max_horizon=max_horizon
                )
                center, scale = self._normalizer_parameters(dataset)
                raw = model.predict(
                    _identity_dataloader(dataset, batch_size),
                    mode="raw",
                    return_x=True,
                    return_index=True,
                    return_decoder_lengths=True,
                    trainer_kwargs=_predict_trainer_kwargs(self._accelerator),
                )
                interpretation = model.interpret_output(raw.output, reduction="none")
            best = _best_sample_by_decision(
                [int(time_idx) - 1 for time_idx in raw.index[_TIME_IDX_COLUMN]],
                [int(length) for length in raw.decoder_lengths],
                frozenset(decisions),
            )
            columns = {
                family: [list(dataset.reals).index(name) for name in names]
                for family, names in permuted_columns.items()
            }
            blocks, encoder_length = donor_blocks(
                raw.x["encoder_cont"], raw.x["encoder_lengths"], best, decisions, columns
            )
            emit = {
                "model": model,
                "requested_decisions": frozenset(decisions),
                "horizons": horizons,
                "quantile_levels": quantile_levels,
                "batch_size": batch_size,
                "accelerator": self._accelerator,
            }
            identity = self._emit(
                prediction_dataset=_identity_dataloader(dataset, batch_size), **emit
            )
            permuted: dict[tuple[str, int], dict[int, dict[int, tuple[float, ...]]]] = {}
            for family, family_columns in columns.items():
                for k, permutation in enumerate(donors, start=1):
                    collate = _swapping_collate(
                        dataset,
                        decisions=decisions,
                        permutation=permutation,
                        columns=family_columns,
                        blocks=blocks[family],
                        encoder_length=encoder_length,
                    )
                    loader = dataset.to_dataloader(
                        train=False, batch_size=batch_size, num_workers=0, collate_fn=collate
                    )
                    permuted[(family, k)] = self._emit(prediction_dataset=loader, **emit)
        finally:
            torch.set_num_threads(threads_before)
            torch.use_deterministic_algorithms(deterministic_before, warn_only=warn_only_before)
        weights = interpretation["encoder_variables"]
        names = list(model.encoder_variables)
        return TftAttributionPrediction(
            identity=identity,
            permuted=permuted,
            encoder_weights={
                decision: {name: float(weights[sample, j]) for j, name in enumerate(names)}
                for decision, sample in sorted(best.items())
            },
            normalizer_center=center,
            normalizer_scale=scale,
            settings=self._settings(batch_size=batch_size, num_threads=num_threads),
        )

    def _settings(self, *, batch_size: int, num_threads: int) -> dict[str, str]:
        """Os parâmetros da inferência, em texto (`SETTINGS_KEYS` do port)."""
        return {
            "batch_size": str(batch_size),
            "num_workers": "0",
            "accelerator": self._accelerator,
            "num_threads": str(num_threads),
            "deterministic_algorithms": "false",
            "cpu_capability": str(torch.backends.cpu.get_cpu_capability()),
            "platform": platform.platform(),
            _SKLEARN_DISTRIBUTION: metadata.version(_SKLEARN_DISTRIBUTION),
        }

    @staticmethod
    def _emit(  # noqa: PLR0913 — parâmetros coesos da regra de emissão
        *,
        model: Any,  # noqa: ANN401 — modelo da lib não cruza a fronteira do port
        prediction_dataset: Any,  # noqa: ANN401
        requested_decisions: frozenset[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        accelerator: str = "cpu",
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
                # Fixar aqui é o único ponto onde isso é controlável: vai o
                # `accelerator` da instância, o mesmo do `fit` (Stage 7.3).
                trainer_kwargs=_predict_trainer_kwargs(accelerator),
            )
        decision_of_sample = [int(time_idx) - 1 for time_idx in prediction.index[_TIME_IDX_COLUMN]]
        lengths = [int(length) for length in prediction.decoder_lengths]
        best_sample_by_decision = _best_sample_by_decision(
            decision_of_sample, lengths, requested_decisions
        )

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
            # Predição pela receita única (`_prediction_dataset`), com os
            # parâmetros do dataset de treino — `from_dataset` é exatamente
            # `from_parameters(get_parameters(), ...)`; a predição a partir do
            # checkpoint usa a mesma função com o `dataset_parameters` gravado.
            prediction = (
                _prediction_dataset(
                    training.get_parameters(),
                    frame,
                    decision_indices=test_decision_indices,
                    max_horizon=max_horizon,
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
                accelerator=self._accelerator,
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
