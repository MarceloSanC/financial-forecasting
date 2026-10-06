"""Unit test de `block_sensitivity_length` (Stage 6.6 Task 03; concept D8, I6).

`"h"` devolve o horizonte; `"sqrt_T"` devolve o teto inteiro exato de raiz de T (nunca o
truncamento do default da `arch`); regra fora de `BLOCK_SENSITIVITIES` é recusada.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    BLOCK_SENSITIVITIES,
    block_sensitivity_length,
)


@pytest.mark.parametrize(
    ("n_points", "expected"),
    [(1500, 39), (1521, 39), (1522, 40), (11, 4), (2, 2), (4, 2), (5, 3)],
)
def test_sqrt_t_is_the_exact_integer_ceiling(n_points: int, expected: int) -> None:
    assert block_sensitivity_length("sqrt_T", horizon=1, n_points=n_points) == expected


def test_sqrt_t_ignores_the_horizon() -> None:
    """Checkpoint C bloco 1 (T4): a regra sqrt_T não leva piso h (não é a regra primária)."""
    assert block_sensitivity_length("sqrt_T", horizon=7, n_points=11) == 4  # noqa: PLR2004


@pytest.mark.parametrize("horizon", [1, 7])
def test_h_is_the_horizon(horizon: int) -> None:
    assert block_sensitivity_length("h", horizon=horizon, n_points=1500) == horizon


@pytest.mark.parametrize(
    ("rule", "horizon", "n_points", "message"),
    [
        ("sqrt_t", 1, 100, "rule must be one of"),
        ("max", 1, 100, "rule must be one of"),
        ("h", 0, 100, "horizon"),
        ("h", True, 100, "horizon"),
        ("sqrt_T", 1, 1, "T >= 2"),
        ("sqrt_T", 0, 100, "horizon"),
        ("h", 1, 0, "T >= 2"),
        ("h", 7, 7, "T > h"),
        ("sqrt_T", 1, True, "n_points"),
        ("sqrt_T", 1, 10.0, "n_points"),
    ],
)
def test_invalid_requests(rule: str, horizon: object, n_points: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        block_sensitivity_length(rule, horizon=horizon, n_points=n_points)  # type: ignore[arg-type]


def test_declared_rules() -> None:
    assert BLOCK_SENSITIVITIES == ("h", "sqrt_T")
