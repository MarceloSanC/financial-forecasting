"""Unit do serviço de domínio `quantile_training_validation` (issue #71).

Oráculo independente da validação C4 do port `QuantileModelTrainer`, que antes
vivia em duas cópias idênticas (adapter LightGBM e dublê in-memory). O contract
test cobria as bordas com `match=r"C4"` — um matcher que passa para QUALQUER
mensagem C4, então trocar um guard por outro passava despercebido. Aqui cada
borda é verificada pela MENSAGEM inteira, e as três posições do laço de largura
(train/early_stop/test) e as duas do laço de comprimento de rótulo
(train/early_stop) são exercitadas uma a uma — o contract test só tocava
`train_rows` e os rótulos de train, e por isso uma edição unilateral nas outras
quatro passava verde (medido antes da extração).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.modeling.domain.services.quantile_training_validation import (
    validate_training_structure,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_FEATURES = ("f0", "f1", "f2")
_HORIZONS = (1, 2)
_N_TRAIN, _N_MONITOR, _N_TEST = 6, 4, 3


def _rows(count: int, width: int = 3) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(r * width + c) for c in range(width)) for r in range(count))


def _labels(count: int) -> tuple[float, ...]:
    return tuple(float(i) for i in range(count))


_TRAIN_ROWS = _rows(_N_TRAIN)
_MONITOR_ROWS = _rows(_N_MONITOR)
_TEST_ROWS = _rows(_N_TEST)
_TRAIN_LABELS: Mapping[int, Sequence[float]] = {h: _labels(_N_TRAIN) for h in _HORIZONS}
_MONITOR_LABELS: Mapping[int, Sequence[float]] = {h: _labels(_N_MONITOR) for h in _HORIZONS}
_DECISIONS = (10, 11, 12)


def _validate(**overrides: Any) -> None:  # noqa: ANN401 — overrides heterogêneos por borda
    kwargs: dict[str, Any] = {
        "feature_names": _FEATURES,
        "train_rows": _TRAIN_ROWS,
        "train_labels_by_horizon": _TRAIN_LABELS,
        "early_stop_rows": _MONITOR_ROWS,
        "early_stop_labels_by_horizon": _MONITOR_LABELS,
        "test_rows": _TEST_ROWS,
        "test_decision_indices": _DECISIONS,
    }
    kwargs.update(overrides)
    validate_training_structure(**kwargs)


@pytest.mark.unit
def test_a_consistent_request_passes_silently() -> None:
    assert _validate() is None


@pytest.mark.unit
def test_empty_train_rows_are_structurally_valid() -> None:
    """Treino vazio é C3 (dado insuficiente), não C4 — a validação não o barra.

    Fixa a fronteira ENTRE os dois casos: se este teste ficar vermelho, alguém
    puxou uma regra de suficiência de dados para dentro da validação estrutural.
    """
    assert _validate(train_rows=(), train_labels_by_horizon={h: () for h in _HORIZONS}) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"feature_names": ()}, "feature_names must be non-empty (C4)"),
        (
            {"train_labels_by_horizon": {}, "early_stop_labels_by_horizon": {}},
            "train_labels_by_horizon must be non-empty (C4)",
        ),
        (
            {"early_stop_labels_by_horizon": {1: _labels(_N_MONITOR)}},
            "train and early_stop label horizons must match; got [1, 2] vs [1] (C4)",
        ),
        (
            {
                "early_stop_labels_by_horizon": {
                    1: _labels(_N_MONITOR),
                    3: _labels(_N_MONITOR),
                }
            },
            "train and early_stop label horizons must match; got [1, 2] vs [1, 3] (C4)",
        ),
        (
            {"early_stop_rows": ()},
            "early_stop_rows must be non-empty — no monitor, no m* (C4)",
        ),
        (
            {"test_decision_indices": (10, 11)},
            "test_decision_indices length 2 != test_rows length 3 (C4)",
        ),
        (
            {"train_rows": (*_TRAIN_ROWS[:2], _TRAIN_ROWS[2][:2], *_TRAIN_ROWS[3:])},
            "train_rows[2] width 2 != len(feature_names)=3 (C4)",
        ),
        (
            {"early_stop_rows": (_MONITOR_ROWS[0][:1], *_MONITOR_ROWS[1:])},
            "early_stop_rows[0] width 1 != len(feature_names)=3 (C4)",
        ),
        (
            {"test_rows": (*_TEST_ROWS[:2], (*_TEST_ROWS[2], 9.0))},
            "test_rows[2] width 4 != len(feature_names)=3 (C4)",
        ),
        (
            {"train_labels_by_horizon": {1: _labels(_N_TRAIN), 2: _labels(_N_TRAIN - 1)}},
            "train labels for horizon 2 length 5 != rows length 6 (C4)",
        ),
        (
            {
                "early_stop_labels_by_horizon": {
                    1: _labels(_N_MONITOR + 1),
                    2: _labels(_N_MONITOR),
                }
            },
            "early_stop labels for horizon 1 length 5 != rows length 4 (C4)",
        ),
    ],
)
def test_each_structural_violation_raises_with_its_own_message(
    overrides: dict[str, Any], expected: str
) -> None:
    """Cada borda tem mensagem própria — `match=r"C4"` não distingue guard trocado."""
    with pytest.raises(ValueError) as raised:
        _validate(**overrides)

    assert str(raised.value) == expected


@pytest.mark.unit
def test_horizon_mismatch_is_checked_before_the_empty_monitor() -> None:
    """A ordem dos guards é observável: horizontes descasados vencem monitor vazio."""
    with pytest.raises(ValueError, match=r"horizons must match"):
        _validate(early_stop_rows=(), early_stop_labels_by_horizon={1: ()})


@pytest.mark.unit
def test_width_is_checked_before_label_lengths() -> None:
    """Largura errada vence comprimento de rótulo errado — precedência congelada."""
    with pytest.raises(ValueError, match=r"train_rows\[0\] width"):
        _validate(
            train_rows=(_TRAIN_ROWS[0][:2], *_TRAIN_ROWS[1:]),
            train_labels_by_horizon={h: _labels(_N_TRAIN - 1) for h in _HORIZONS},
        )
