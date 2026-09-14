"""Golden do `TftTrainer` — trava das DUAS pernas antes do refactor (issue #75).

Rede de regressão da movimentação de `_validate_contiguous`, `_eligible` e
`_validate_structure` (adapter `PfTftTrainer` ↔ fake `InMemoryTftTrainer`, duplicados
linha a linha) para o serviço de domínio `tft_panel_geometry`. É **refactor puro**:
nem as contagens declaradas (I17) nem o texto das mensagens de erro (C3/C4) podem
mudar. Este módulo congela, em literais, o que foi capturado ANTES da movimentação
(base `develop` pós-#32), pelo caminho PÚBLICO de cada perna:

- **fake** — `InMemoryTftTrainer.train_and_predict(...)` (stdlib, sem torch);
- **real** — `PfTftTrainer.build_datasets(...)`, o seam público que valida, calcula
  a elegibilidade e monta os `TimeSeriesDataSet` SEM treinar (a regra que a #75 move
  roda toda antes de qualquer chamada à biblioteca, e é isso que este golden trava).

Duas travas:

1. **Contagens de I17** — `fitted_decision_count`/`monitored_decision_count` para 6
   geometrias (janela 12/20/25, decodificador 2/3, monitor encostado na ponta),
   IDÊNTICAS nas duas pernas.
2. **Bordas C3/C4** — 10 estruturas inválidas erguem `ValueError` com a mensagem
   IDÊNTICA nas duas pernas; o texto exato está congelado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.contract

_LEGS = ("fake", "real")

# -- fixture determinística (geometria canônica do contract test) ---------------

_PANEL = 54
_ENCODER_LENGTH = 12
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_TRAIN = tuple(range(30))
_EARLY_STOP = tuple(range(33, 38))
_TEST = tuple(range(49, 54))
_FEATURES = ("close_return", "rsi_14", "day_of_week", "month")
_KNOWN = ("day_of_week", "month")
_LEVELS = (0.1, 0.5, 0.9)


def _params(encoder_length: int = _ENCODER_LENGTH) -> TftTrainingParams:
    return TftTrainingParams(
        seed=7,
        max_encoder_length=encoder_length,
        hidden_size=4,
        attention_head_size=1,
        hidden_continuous_size=2,
        max_epochs=2,
        patience=2,
        batch_size=8,
        learning_rate=0.01,
    )


def _panel() -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [0.001 * index for index in range(_PANEL)]
    return rows, target


def _kwargs(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    rows, target = _panel()
    kwargs: dict[str, Any] = {
        "params": _params(),
        "feature_names": _FEATURES,
        "known_feature_names": _KNOWN,
        "rows": rows,
        "target": target,
        "train_decision_indices": _TRAIN,
        "early_stop_decision_indices": _EARLY_STOP,
        "test_decision_indices": _TEST,
        "max_horizon": _MAX_HORIZON,
        "horizons": _HORIZONS,
    }
    kwargs.update(overrides)
    return kwargs


def _counts(leg: str, tmp_path: Path, **overrides: Any) -> tuple[int, int]:  # noqa: ANN401
    """`(fitted, monitored)` pelo caminho público de cada perna."""
    kwargs = _kwargs(**overrides)
    if leg == "fake":
        result = InMemoryTftTrainer().train_and_predict(
            **kwargs, quantile_levels=_LEVELS, artifact_dir=str(tmp_path / "ckpt")
        )
        return result.fitted_decision_count, result.monitored_decision_count
    datasets = PfTftTrainer().build_datasets(**kwargs)
    return datasets.fitted_decision_count, datasets.monitored_decision_count


# -- golden das contagens (I17) — idênticas nas duas pernas ---------------------

_GEOMETRIES: dict[str, dict[str, Any]] = {
    "canonical": {},
    "encoder_20": {"params": _params(20)},
    "encoder_25_cuts_train": {"params": _params(25)},
    "horizon_3": {"max_horizon": 3, "horizons": (1, 2, 3)},
    "monitor_at_the_edge": {"early_stop_decision_indices": (49, 50, 51, 52)},
    "encoder_1_everything_fits": {"params": _params(1)},
}

_GOLDEN_COUNTS: dict[str, tuple[int, int]] = {
    "canonical": (19, 5),
    "encoder_20": (11, 5),
    "encoder_25_cuts_train": (6, 5),
    "horizon_3": (19, 5),
    "monitor_at_the_edge": (19, 3),
    "encoder_1_everything_fits": (30, 5),
}

# -- golden das bordas (C3/C4) — mensagens idênticas nas duas pernas ------------

_BOUNDARY_CASES: dict[str, dict[str, Any]] = {
    "encoder_longer_than_train": {"params": _params(40)},
    "monitor_without_full_decoder": {"early_stop_decision_indices": (_PANEL - 2, _PANEL - 1)},
    "row_width_mismatch": {"rows": [*_panel()[0][:3], [1.0], *_panel()[0][4:]]},
    "target_length_mismatch": {"target": _panel()[1][:-1]},
    "known_names_not_contained": {"known_feature_names": ("not_a_column",)},
    "non_contiguous_decision_range": {"train_decision_indices": (*range(20), 25)},
    "index_outside_panel": {"test_decision_indices": (_PANEL, _PANEL + 1)},
    "horizon_outside_decoder": {"horizons": (1, 7)},
    "empty_horizons": {"horizons": ()},
    "empty_monitor": {"early_stop_decision_indices": ()},
    "max_horizon_below_one": {"max_horizon": 0, "horizons": ()},
}

_GOLDEN_BOUNDARY_MESSAGES: dict[str, str] = {
    "encoder_longer_than_train": (
        "nenhuma decisão de treino sobrou após exigir janela de contexto de 40 sessões e "
        "decodificador de 2 passos (C3)"
    ),
    "monitor_without_full_decoder": (
        "nenhuma decisão de monitor sobrou após exigir janela de contexto de 12 sessões e "
        "decodificador de 2 passos (C3)"
    ),
    "row_width_mismatch": "rows[3] tem 1 colunas, esperado 4 (C4)",
    "target_length_mismatch": "len(target)=53 != len(rows)=54 (C4)",
    "known_names_not_contained": (
        "known_feature_names não contido em feature_names: ['not_a_column'] (C4)"
    ),
    "non_contiguous_decision_range": (
        "train_decision_indices deve ser uma faixa contígua e crescente; 19 seguido de 25 (C4)"
    ),
    "index_outside_panel": "test_decision_indices[0]=54 fora do painel de 54 sessões (C4)",
    "horizon_outside_decoder": "horizons [7] fora de 1..2 (C4)",
    "empty_horizons": "horizons não pode ser vazio (C4)",
    "empty_monitor": (
        "early_stop_decision_indices vazio — sem monitor não há seleção de época (C4)"
    ),
    "max_horizon_below_one": "max_horizon deve ser >= 1, recebido 0 (C4)",
}


# -- travas --------------------------------------------------------------------


@pytest.mark.parametrize("leg", _LEGS)
@pytest.mark.parametrize("geometry", sorted(_GEOMETRIES))
def test_declared_counts_match_the_frozen_geometry_in_both_legs(
    leg: str, geometry: str, tmp_path: Path
) -> None:
    """`(fitted, monitored)` batem com o golden — o mesmo literal nas duas pernas (I17)."""
    assert _counts(leg, tmp_path, **_GEOMETRIES[geometry]) == _GOLDEN_COUNTS[geometry]


@pytest.mark.parametrize("leg", _LEGS)
@pytest.mark.parametrize("case", sorted(_BOUNDARY_CASES))
def test_boundary_message_is_frozen_and_identical_in_both_legs(
    leg: str, case: str, tmp_path: Path
) -> None:
    """Cada borda C3/C4 ergue `ValueError` com o texto EXATO congelado, nas 2 pernas."""
    with pytest.raises(ValueError) as raised:
        _counts(leg, tmp_path, **_BOUNDARY_CASES[case])

    assert str(raised.value) == _GOLDEN_BOUNDARY_MESSAGES[case]
