"""Fake in-memory do port `TftTrainer` — stdlib-only, determinístico.

Materializa TODAS as regras do contrato (concept 5.4 §4) que não dependem de
`torch`: validação estrutural (C4), regra de janela/decodificador completos e
contagens declaradas (I17), erguer por histórico insuficiente (C3), regra de
emissão na cauda (I16), modo fit-only e determinismo (I9). É o oráculo de FORMA
da suite de contrato (`[fake, real]`), e o que permite testar o use case
`TrainTft` inteiro sem instalar nem carregar a pilha de deep learning.

**A emissão lê `target[t + h]` de propósito** — inclusive para decisões de teste.
Isso NÃO é uma afirmação de modelagem (o fake não é um modelo, e um modelo real
não conhece o futuro): é o que torna o oráculo de alinhamento (A15, perna fake)
discriminante. Com a mediana emitida sendo exatamente `target[t + h]`, um
deslocamento de um passo no mapeamento decisão↔horizonte falha o teste. A perna
real prova o mesmo invariante por outro método — asserção de caixa-branca sobre
o índice devolvido pela predição —, porque um modelo de fumaça de 2 épocas não
tem precisão para um oráculo de proximidade.

O que o fake NÃO cobre, por construção (declarado aqui para a auditoria não
confundir com lacuna): C5 (emissão não finita — a emissão do fake é sempre
finita), C10 (checkpoint inutilizável — o fake sempre grava) e A4(c)
(normalizador — o fake não tem um ajustado por biblioteca). Os três vivem na
perna real, na linha do finding herdado da Stage 5.3 sobre o C5.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Any

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainingParams,
    )

# Épocas simuladas: o suficiente para o histórico ter um argmin INTERIOR, que é
# a forma que o mecanismo de parada antecipada produz quando de fato para cedo.
_SIMULATED_EPOCHS = 5
_MEDIAN_LEVEL = 0.5


def _validate_contiguous(name: str, indices: Sequence[int], panel_size: int) -> None:
    """C4: faixa contígua, crescente e dentro do painel.

    A contiguidade não é capricho: o adapter real só expressa PISO de decisão
    (a biblioteca não tem teto), e o teto vem de recortar o quadro. Aceitar aqui
    um conjunto que o real não honra produziria divergência fake<->real
    silenciosa justamente no monitor — onde ela significaria `calib` entrando na
    perda de validação.
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
    """Decisões com janela de contexto E decodificador completos (I17).

    Janela completa sse `t >= encoder_length - 1` (a janela é `[t-L+1, t]`,
    terminando em `t` INCLUSIVE); decodificador completo sse
    `t + max_horizon <= panel_size - 1`.
    """
    return tuple(
        index
        for index in indices
        if index >= encoder_length - 1 and index + max_horizon <= panel_size - 1
    )


class InMemoryTftTrainer:
    """Fake determinístico que satisfaz o port `TftTrainer` por duck-typing."""

    def __init__(self) -> None:
        # Argumentos da última chamada — consumidos pelas asserções estruturais
        # de A6 (nenhum índice de calib como decisão) e A10 (fit-only na varredura).
        self.last_call: dict[str, Any] = {}
        self.call_count = 0

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
        """Simula o treino e emite a grade crua conforme o contrato do port."""
        self.call_count += 1
        self.last_call = {
            "params": params,
            "feature_names": tuple(feature_names),
            "known_feature_names": tuple(known_feature_names),
            "train_decision_indices": tuple(train_decision_indices),
            "early_stop_decision_indices": tuple(early_stop_decision_indices),
            "test_decision_indices": tuple(test_decision_indices),
            "max_horizon": max_horizon,
            "horizons": tuple(horizons),
            "quantile_levels": tuple(quantile_levels),
            "artifact_dir": artifact_dir,
        }

        panel_size = self._validate_structure(
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

        fitted = _eligible(
            train_decision_indices,
            encoder_length=params.max_encoder_length,
            max_horizon=max_horizon,
            panel_size=panel_size,
        )
        monitored = _eligible(
            early_stop_decision_indices,
            encoder_length=params.max_encoder_length,
            max_horizon=max_horizon,
            panel_size=panel_size,
        )
        if not fitted:
            msg = (
                "nenhuma decisão de treino sobrou após exigir janela de contexto de "
                f"{params.max_encoder_length} sessões e decodificador de {max_horizon} "
                "passos (C3)"
            )
            raise ValueError(msg)
        if not monitored:
            msg = (
                "nenhuma decisão de monitor sobrou após exigir janela de contexto de "
                f"{params.max_encoder_length} sessões e decodificador de {max_horizon} "
                "passos (C3)"
            )
            raise ValueError(msg)

        center, scale = self._fit_normalizer(target, fitted, max_horizon)
        val_loss_by_epoch = self._simulated_history(params)
        best_epoch = val_loss_by_epoch.index(min(val_loss_by_epoch))

        grids = self._emit(
            target=target,
            test_decision_indices=test_decision_indices,
            horizons=horizons,
            quantile_levels=quantile_levels,
            panel_size=panel_size,
            scale=scale,
        )
        # Fit-only (varredura): nenhum checkpoint é escrito — a varredura roda
        # dezenas de treinos e não deve deixar arquivos órfãos (ADR 5.4.0005).
        artifact_path = (
            "" if not test_decision_indices else self._write_artifact(artifact_dir, best_epoch)
        )

        return TftTrainingResult(
            grids=grids,
            best_epoch=best_epoch,
            best_val_loss=val_loss_by_epoch[best_epoch],
            val_loss_by_epoch=val_loss_by_epoch,
            fitted_decision_count=len(fitted),
            monitored_decision_count=len(monitored),
            normalizer_center=center,
            normalizer_scale=scale,
            artifact_path=artifact_path,
        )

    # -- C4 --------------------------------------------------------------------

    def _validate_structure(  # noqa: PLR0913 — validação coesa da fronteira
        self,
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
    ) -> int:
        """Valida a estrutura da fronteira e devolve o tamanho do painel (C4)."""
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
        _validate_contiguous("train_decision_indices", train_decision_indices, panel_size)
        _validate_contiguous(
            "early_stop_decision_indices", early_stop_decision_indices, panel_size
        )
        _validate_contiguous("test_decision_indices", test_decision_indices, panel_size)
        return panel_size

    # -- simulação determinística ---------------------------------------------

    @staticmethod
    def _fit_normalizer(
        target: Sequence[float], fitted: Sequence[int], max_horizon: int
    ) -> tuple[float, float]:
        """Centro/escala sobre o QUADRO de treino (I4b), espelhando o real.

        Quadro = até `max(decisões de treino) + max_horizon` inclusive: as
        sessões extras são os rótulos das últimas decisões de treino, e estão
        estritamente antes de `early_stop`.
        """
        frame = target[: fitted[-1] + max_horizon + 1]
        center = statistics.fmean(frame)
        scale = statistics.stdev(frame) if len(frame) > 1 else 1.0
        return center, scale or 1.0

    @staticmethod
    def _simulated_history(params: TftTrainingParams) -> tuple[float, ...]:
        """Histórico com argmin INTERIOR — a forma de um treino que parou cedo."""
        epochs = min(params.max_epochs, _SIMULATED_EPOCHS)
        losses = [1.0 - 0.1 * index for index in range(epochs)]
        if epochs > 1:
            # Última época pior que a anterior: best_epoch < len - 1, que é o que
            # torna a mutação "não restaurar o melhor checkpoint" observável.
            losses[-1] = losses[0] + 1.0
        return tuple(losses)

    @staticmethod
    def _emit(  # noqa: PLR0913 — parâmetros coesos da regra de emissão
        *,
        target: Sequence[float],
        test_decision_indices: Sequence[int],
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        panel_size: int,
        scale: float,
    ) -> dict[int, dict[int, tuple[float, ...]]]:
        """Grade crua dos pares que I16 autoriza (`t + h <= panel_size - 1`).

        A mediana é exatamente `target[t + h]` — ver a nota do módulo sobre por
        que o fake lê o alvo futuro e o que isso prova (A15, perna fake).
        """
        grids: dict[int, dict[int, tuple[float, ...]]] = {}
        for decision_idx in test_decision_indices:
            by_horizon: dict[int, tuple[float, ...]] = {}
            for horizon in horizons:
                target_position = decision_idx + horizon
                if target_position > panel_size - 1:
                    continue
                anchor = target[target_position]
                by_horizon[horizon] = tuple(
                    anchor + (level - _MEDIAN_LEVEL) * scale for level in quantile_levels
                )
            if by_horizon:
                grids[decision_idx] = by_horizon
        return grids

    @staticmethod
    def _write_artifact(artifact_dir: str, best_epoch: int) -> str:
        """Grava um checkpoint determinístico e devolve o caminho.

        O arquivo precisa EXISTIR: o fake do `ExperimentTracker` valida a
        existência em `log_artifact`, então um fake que só devolvesse a string
        reprovaria A8 por um motivo que nada tem a ver com o rastreamento.
        """
        directory = Path(artifact_dir)
        directory.mkdir(parents=True, exist_ok=True)
        checkpoint = directory / f"epoch={best_epoch}.ckpt"
        checkpoint.write_text(f"fake-tft-checkpoint epoch={best_epoch}\n", encoding="utf-8")
        return str(checkpoint)
