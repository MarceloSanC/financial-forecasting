"""Fake in-memory do port `QuantileModelTrainer` — NÃO um mock.

`FakeQuantileModelTrainer` honra o MESMO contrato observável do adapter real
(`LightgbmQuantileTrainer`) — mesma validação estrutural (C4), mesmo limiar de
treino insuficiente (C3, `params.min_data_in_leaf`), mesma política de NaN
(I11: label não finito exclui o par do fit E do monitor) e mesmo determinismo
(I4) — divergindo apenas no MODELO: em vez de K boosters, emite o quantil
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

from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    sample_quantiles_type7,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        GbmTrainingParams,
    )

from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    QuantileTrainingResult,
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
        _validate_structure(
            feature_names=feature_names,
            train_rows=train_rows,
            train_labels_by_horizon=train_labels_by_horizon,
            early_stop_rows=early_stop_rows,
            early_stop_labels_by_horizon=early_stop_labels_by_horizon,
            test_rows=test_rows,
            test_decision_indices=test_decision_indices,
        )

        grid_by_horizon: dict[int, tuple[float, ...]] = {}
        for horizon, labels in train_labels_by_horizon.items():
            finite = tuple(label for label in labels if math.isfinite(label))
            if len(finite) < params.min_data_in_leaf:
                raise ValueError(
                    f"horizon {horizon}: {len(finite)} finite-label train pairs "
                    f"< min_data_in_leaf={params.min_data_in_leaf} (C3)"
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


def _validate_structure(  # noqa: PLR0913 — espelha a validação C4 do adapter real
    *,
    feature_names: Sequence[str],
    train_rows: Sequence[Sequence[float]],
    train_labels_by_horizon: Mapping[int, Sequence[float]],
    early_stop_rows: Sequence[Sequence[float]],
    early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
    test_rows: Sequence[Sequence[float]],
    test_decision_indices: Sequence[int],
) -> None:
    """C4: estrutura inconsistente ergue `ValueError` (paridade fake<->real)."""
    if not feature_names:
        raise ValueError("feature_names must be non-empty (C4)")
    if not train_labels_by_horizon:
        raise ValueError("train_labels_by_horizon must be non-empty (C4)")
    if set(train_labels_by_horizon) != set(early_stop_labels_by_horizon):
        raise ValueError(
            "train and early_stop label horizons must match; got "
            f"{sorted(train_labels_by_horizon)} vs "
            f"{sorted(early_stop_labels_by_horizon)} (C4)"
        )
    if not early_stop_rows:
        raise ValueError("early_stop_rows must be non-empty — no monitor, no m* (C4)")
    if len(test_decision_indices) != len(test_rows):
        raise ValueError(
            f"test_decision_indices length {len(test_decision_indices)} != "
            f"test_rows length {len(test_rows)} (C4)"
        )
    width = len(feature_names)
    for block_name, rows in (
        ("train_rows", train_rows),
        ("early_stop_rows", early_stop_rows),
        ("test_rows", test_rows),
    ):
        for position, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(
                    f"{block_name}[{position}] width {len(row)} != "
                    f"len(feature_names)={width} (C4)"
                )
    for block_name, rows_len, labels_by_horizon in (
        ("train", len(train_rows), train_labels_by_horizon),
        ("early_stop", len(early_stop_rows), early_stop_labels_by_horizon),
    ):
        for horizon, labels in labels_by_horizon.items():
            if len(labels) != rows_len:
                raise ValueError(
                    f"{block_name} labels for horizon {horizon} length "
                    f"{len(labels)} != rows length {rows_len} (C4)"
                )
