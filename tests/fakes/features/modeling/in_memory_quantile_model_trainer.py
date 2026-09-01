"""Fake in-memory do port `QuantileModelTrainer` — NÃO um mock.

`FakeQuantileModelTrainer` honra o MESMO contrato observável do adapter real
(`LightgbmQuantileTrainer`) — mesma validação estrutural (C4), mesmo limiar de
treino insuficiente (C3, `params.min_data_in_leaf`), mesma política de NaN
(I11: label não finito exclui o par do fit E do monitor) e mesmo determinismo
(I4). A partir da issue #71 a paridade do C4 é ESTRUTURAL e não mantida à mão:
as duas pernas chamam o mesmo serviço de domínio
`quantile_training_validation.validate_training_structure` (antes eram 49
linhas idênticas de cada lado). O dublê diverge apenas no MODELO: em vez
de K boosters, emite o quantil
empírico tipo 7 (`sample_quantiles_type7`, serviço de domínio da 5.2) dos
labels finitos de treino do horizonte, idêntico para toda decisão de teste
(feature-blind). Essa é exatamente a emissão do adapter real sob features
constantes (oráculo A6 do concept), então fake e real colapsam no mesmo valor
no caso discriminante da suite de contrato
(`tests/contract/features/modeling/test_quantile_model_trainer_contract.py`).

`best_iteration_by_horizon`: sempre `1` — o menor valor 1-based válido do
contrato (o fake não tem histórico de iterações; a mecânica de seleção de `m*`
é provada no adapter real pela sua suite de integração).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    QuantileTrainingResult,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    sample_quantiles_type7,
)
from financial_forecasting.features.modeling.domain.services.quantile_training_validation import (
    validate_training_structure,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        GbmTrainingParams,
    )

_FAKE_BEST_ITERATION = 1


class FakeQuantileModelTrainer:
    """Implementação in-memory determinística do contrato `QuantileModelTrainer`."""

    def train_and_predict(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        """Emite o quantil tipo 7 dos labels finitos de train (ver docstring)."""
        validate_training_structure(
            feature_names=feature_names,
            train_rows=train_rows,
            train_labels_by_horizon=train_labels_by_horizon,
            early_stop_rows=early_stop_rows,
            early_stop_labels_by_horizon=early_stop_labels_by_horizon,
            test_rows=test_rows,
            test_decision_indices=test_decision_indices,
        )

        grid_by_horizon: dict[int, tuple[float, ...]] = {}
        # `sorted` espelha a ordem de iteração do adapter real — com múltiplos
        # horizontes inválidos, fake e real erguem C3 apontando o MESMO
        # horizonte (F1 do Checkpoint C bloco 2).
        for horizon in sorted(train_labels_by_horizon):
            labels = train_labels_by_horizon[horizon]
            finite = tuple(label for label in labels if math.isfinite(label))
            if len(finite) < params.min_data_in_leaf:
                raise ValueError(
                    f"horizon {horizon}: {len(finite)} finite-label train pairs "
                    f"< min_data_in_leaf={params.min_data_in_leaf} (C3)"
                )
            monitor_labels = early_stop_labels_by_horizon[horizon]
            if not any(math.isfinite(label) for label in monitor_labels):
                # Paridade com o real (I11): monitor pós-filtragem vazio não é
                # "seguir sem monitor" — é dado insuficiente (F2, Checkpoint C b1).
                raise ValueError(
                    f"horizon {horizon}: early_stop has no finite-label monitor "
                    "pairs (C3)"
                )
            grid_by_horizon[horizon] = sample_quantiles_type7(
                values=finite, levels=quantile_levels
            )

        grids: dict[int, GridByHorizon] = {
            decision_idx: dict(grid_by_horizon) for decision_idx in test_decision_indices
        }
        best_iterations = dict.fromkeys(train_labels_by_horizon, _FAKE_BEST_ITERATION)
        return QuantileTrainingResult(
            grids=grids, best_iteration_by_horizon=best_iterations
        )

