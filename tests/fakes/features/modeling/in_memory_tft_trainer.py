"""Fake in-memory do port `TftTrainer` — stdlib-only, determinístico.

Materializa TODAS as regras do contrato (concept 5.4 §4) que não dependem de
`torch`: validação estrutural (C4), regra de janela/decodificador completos e
contagens declaradas (I17) e histórico insuficiente (C3) — as três DELEGADAS ao
serviço de domínio `tft_panel_geometry` (issue #75), a mesma casa única que o
adapter real usa —, regra de emissão na cauda (I16), modo fit-only e
determinismo (I9). É o oráculo de FORMA da suite de contrato (`[fake, real]`), e
o que permite testar o use case `TrainTft` inteiro sem instalar nem carregar a
pilha de deep learning.

**A emissão lê `target[t + h]` de propósito** — inclusive para decisões de teste.
Isso NÃO é uma afirmação de modelagem (o fake não é um modelo, e um modelo real
não conhece o futuro): é o que torna o oráculo de alinhamento (A15, perna fake)
discriminante. Com a mediana emitida sendo exatamente `target[t + h]`, um
deslocamento de um passo no mapeamento decisão↔horizonte falha o teste. A perna
real prova o mesmo invariante por outro método — asserção de caixa-branca sobre
o índice devolvido pela predição —, porque um modelo de fumaça de 2 épocas não
tem precisão para um oráculo de proximidade.

O que o fake NÃO cobre, por construção (declarado aqui para a auditoria não
confundir com lacuna, e para que ninguém escreva sobre ele uma asserção vácua):

- **C5** (emissão não finita) e **C10** (checkpoint inutilizável): a emissão do
  fake é sempre finita e ele sempre grava.
- **A4(c)** (normalizador): o fake não tem um ajustado por biblioteca.
- **A4(a) e A4(b)** (anti-vazamento por mutação): a saída do fake depende
  APENAS de `target[t + h]` e da escala do quadro de treino. Mutar `calib` não
  muda nada aqui — então uma prova de anti-vazamento escrita sobre o fake seria
  vácua. As duas vivem no adapter real (Tasks 08 e 09).
- **Guardrail I5** (rearranjo monótono): a grade do fake é monótona por
  construção (`anchor + (level - 0.5) * scale`, com níveis crescentes e
  `scale > 0`), então o `QuantileForecast.from_raw` nunca é exercitado através
  dele. Um teste do use case que afirme "guardrail aplicado" usando este fake
  não prova nada — precisa de uma grade deliberadamente cruzada.
- **I9 na cláusula semente↔saída:** o fake é função pura dos argumentos e não lê
  `params.seed`. O determinismo que ele demonstra é o de ausência de estado, não
  o de semeadura — essa cláusula é da perna real.

Todos seguem a linha do finding herdado da Stage 5.3 sobre o C5: declarar onde a
prova vive em vez de fingir paridade.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Any

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingResult,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    ModelTrainingError,
)
from financial_forecasting.features.modeling.domain.services.tft_panel_geometry import (
    resolve_panel_geometry,
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


class InMemoryTftTrainer:
    """Fake determinístico que satisfaz o port `TftTrainer` por duck-typing.

    `simulate_backend_failure`: quando informado, o fake ergue a exceção do contrato
    (`ModelTrainingError`) com essa mensagem no MESMO ponto em que o adapter real chama a
    biblioteca — DEPOIS da regra do port (issue #84). É o que permite ao contract
    test provar que fake e real erguem o mesmo tipo quando "a lib falhou".
    """

    # Default de CLASSE: subclasses de teste que redefinem `__init__` sem chamar
    # `super().__init__()` continuam sem falha simulada.
    _simulate_backend_failure: str | None = None

    def __init__(self, *, simulate_backend_failure: str | None = None) -> None:
        self._simulate_backend_failure = simulate_backend_failure
        # Histórico COMPLETO das chamadas — consumido pelas asserções
        # estruturais de A6 (faixas de decisão por fold) e A10 (fit-only na
        # varredura). Guardar só a última deixaria os folds anteriores sem
        # cobertura: um vazamento restrito ao fold 0 passaria verde.
        self.calls: list[dict[str, Any]] = []
        self.call_count = 0

    @property
    def last_call(self) -> dict[str, Any]:
        """Última chamada registrada (`{}` se nenhuma)."""
        return self.calls[-1] if self.calls else {}

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
        self.calls.append(
            {
                "params": params,
                "feature_names": tuple(feature_names),
                "known_feature_names": tuple(known_feature_names),
                # O painel entra no registro para que a política de ausência
                # (None -> NaN) seja verificável na FRONTEIRA, e não só por
                # inspeção do parser do use case.
                "rows": tuple(tuple(row) for row in rows),
                "target": tuple(target),
                "train_decision_indices": tuple(train_decision_indices),
                "early_stop_decision_indices": tuple(early_stop_decision_indices),
                "test_decision_indices": tuple(test_decision_indices),
                "max_horizon": max_horizon,
                "horizons": tuple(horizons),
                "quantile_levels": tuple(quantile_levels),
                "artifact_dir": artifact_dir,
            }
        )

        # A regra do painel (C4/I17/C3) é do domínio (`tft_panel_geometry`, #75):
        # o fake fica só com a aritmética stdlib da simulação.
        geometry = resolve_panel_geometry(
            encoder_length=params.max_encoder_length,
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
        panel_size = geometry.panel_size
        fitted = geometry.fitted_decisions
        monitored = geometry.monitored_decisions
        if self._simulate_backend_failure is not None:
            # No ponto em que o real monta os `TimeSeriesDataSet` — depois da regra.
            raise ModelTrainingError(self._simulate_backend_failure) from RuntimeError(
                "simulated backend failure"
            )

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
