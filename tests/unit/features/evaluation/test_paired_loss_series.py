"""Unit test do VO `PairedLossSeries` (A1, C1, C2, I2; ADR 6.2.0001).

Um caso por ramo de C1 (inclusive T = h, T < h, perda negativa e nome repetido), a
série k = 3 com um par de colunas de diferencial constante **aceita** (a variância
nula é pré-condição do MCS, não do VO) e os acessores conferidos à mão.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_TIMESTAMPS = (
    "2024-01-02T00:00:00+00:00",
    "2024-01-03T00:00:00+00:00",
    "2024-01-04T00:00:00+00:00",
    "2024-01-05T00:00:00+00:00",
)
# "a" - "b" = 0,5 em todo ponto: par de comparadores com diferencial constante.
_LOSSES_A = (1.0, 2.0, 3.0, 4.0)
_LOSSES_B = (0.5, 1.5, 2.5, 3.5)
_LOSSES_C = (4.0, 1.0, 0.0, 2.0)


def _fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "horizon": 1,
        "models": ("a", "b", "c"),
        "target_timestamps": _TIMESTAMPS,
        "losses": (_LOSSES_A, _LOSSES_B, _LOSSES_C),
    }
    fields.update(overrides)
    return fields


def _series(**overrides: object) -> PairedLossSeries:
    return PairedLossSeries(**_fields(**overrides))  # type: ignore[arg-type]


def _with_loss(value: object) -> tuple[tuple[object, ...], ...]:
    return (_LOSSES_A, (0.5, value, 2.5, 3.5), _LOSSES_C)


_INVALID_CASES = [
    pytest.param({"horizon": 0}, "horizon must be", id="horizon-zero"),
    pytest.param({"horizon": True}, "horizon must be", id="horizon-bool"),
    pytest.param({"horizon": 1.0}, "horizon must be", id="horizon-float"),
    pytest.param({"models": ("a",), "losses": (_LOSSES_A,)}, "k >= 2", id="single-model"),
    pytest.param({"models": ("a", "", "c")}, "non-empty str", id="empty-name"),
    pytest.param({"models": ("a", 7, "c")}, "non-empty str", id="name-not-str"),
    pytest.param({"models": ("a", "a", "c")}, "unique", id="repeated-name"),
    pytest.param(
        {"target_timestamps": _TIMESTAMPS[:1], "losses": ((1.0,), (0.5,), (4.0,))},
        "T >= 2",
        id="single-point",
    ),
    pytest.param({"horizon": 4}, r"T > h\), got T=4 and h=4", id="t-equals-h"),
    pytest.param({"horizon": 5}, r"T > h\), got T=4 and h=5", id="t-below-h"),
    pytest.param(
        {"target_timestamps": (_TIMESTAMPS[0], _TIMESTAMPS[0], *_TIMESTAMPS[2:])},
        "strictly increasing",
        id="timestamp-repeated",
    ),
    pytest.param(
        {"target_timestamps": (_TIMESTAMPS[1], _TIMESTAMPS[0], *_TIMESTAMPS[2:])},
        "strictly increasing",
        id="timestamp-out-of-order",
    ),
    pytest.param({"losses": (_LOSSES_A, _LOSSES_B)}, "one column per model", id="columns-ne-k"),
    pytest.param(
        {"losses": (_LOSSES_A, _LOSSES_B[:3], _LOSSES_C)}, "3 losses for T=4", id="column-ne-t"
    ),
    pytest.param({"losses": _with_loss(math.nan)}, "finite number >= 0", id="loss-nan"),
    pytest.param({"losses": _with_loss(math.inf)}, "finite number >= 0", id="loss-inf"),
    pytest.param({"losses": _with_loss(None)}, "finite number >= 0", id="loss-none"),
    pytest.param({"losses": _with_loss(True)}, "finite number >= 0", id="loss-bool"),
    pytest.param({"losses": _with_loss(-0.25)}, "finite number >= 0", id="loss-negative"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("overrides", "message"), _INVALID_CASES)
def test_pls_invalid_construction_raises(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _series(**overrides)


@pytest.mark.unit
def test_pls_degenerate_pair_accepted() -> None:
    """Par de colunas com diferencial constante passa: var(L_a - L_b) = 0 é do MCS."""
    series = _series()
    assert series.n_points == len(_TIMESTAMPS)
    assert series.differential("a", "b") == (0.5, 0.5, 0.5, 0.5)


@pytest.mark.unit
def test_pls_model_pairs_order() -> None:
    assert _series().model_pairs() == (("a", "b"), ("a", "c"), ("b", "c"))


@pytest.mark.unit
def test_pls_differential_sign_is_first_minus_second() -> None:
    series = _series()
    assert series.differential("a", "c") == (-3.0, 1.0, 3.0, 2.0)
    assert series.differential("c", "a") == (3.0, -1.0, -3.0, -2.0)


@pytest.mark.unit
def test_pls_losses_of_column() -> None:
    series = _series()
    assert series.losses_of("a") == _LOSSES_A
    assert series.losses_of("b") == _LOSSES_B
    assert series.losses_of("c") == _LOSSES_C


@pytest.mark.unit
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda s: s.losses_of("z"), id="losses-of"),
        pytest.param(lambda s: s.differential("z", "a"), id="differential-first"),
        pytest.param(lambda s: s.differential("a", "z"), id="differential-second"),
    ],
)
def test_pls_unknown_name_raises(call: Callable[[PairedLossSeries], object]) -> None:
    with pytest.raises(ValueError, match="unknown model 'z'"):
        call(_series())


@pytest.mark.unit
def test_pls_same_model_differential_raises() -> None:
    with pytest.raises(ValueError, match="two distinct models"):
        _series().differential("b", "b")


@pytest.mark.unit
def test_pls_frozen() -> None:
    series = _series()
    with pytest.raises(dataclasses.FrozenInstanceError):
        series.horizon = 2  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"models": ["a", "b", "c"]}, "models must be a tuple", id="models"),
        pytest.param(
            {"target_timestamps": list(_TIMESTAMPS)}, "target_timestamps must be", id="timestamps"
        ),
        pytest.param(
            {"losses": [_LOSSES_A, _LOSSES_B, _LOSSES_C]}, "losses must be a tuple", id="losses"
        ),
        pytest.param(
            {"losses": (_LOSSES_A, list(_LOSSES_B), _LOSSES_C)},
            r"losses\[1\] must be a tuple",
            id="column",
        ),
    ],
)
def test_pls_mutable_container_rejected(overrides: dict[str, object], message: str) -> None:
    """Lista validada poderia ser mutada depois (ex.: perda -5,0): só tuple é aceito."""
    with pytest.raises(ValueError, match=message):
        _series(**overrides)
