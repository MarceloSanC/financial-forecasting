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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainingParams,
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


class PfTftTrainer:
    """Treinador do TFT quantílico sobre `pytorch-forecasting` (satisfaz o port)."""

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

        # Import local: mantém o custo de carregar torch/lightning fora do
        # import do módulo (o composition root já usa proxy lazy pelo mesmo
        # motivo; aqui é defesa em profundidade para quem instancie direto).
        from pytorch_forecasting import TimeSeriesDataSet  # noqa: PLC0415
        from pytorch_forecasting.data.encoders import GroupNormalizer  # noqa: PLC0415

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

    @staticmethod
    def _panel_frame(
        feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
    ) -> Any:  # noqa: ANN401 — pandas.DataFrame não cruza a fronteira do port
        import pandas as pd  # noqa: PLC0415

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
