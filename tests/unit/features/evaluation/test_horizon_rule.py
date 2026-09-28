"""Unit test da regra única de horizonte (`_horizon.validate_horizon`).

Prova (concept 6.3 I1, C1, C9): "`int` não-`bool` ≥ 1" tem uma escrita, consumida pela
`HitSequence` e pela banda de Wilson (e, nas Tasks 07-09, pelos demais relatórios).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    wilson_band as wilson_band_module,
)
from financial_forecasting.features.evaluation.domain.value_objects import (
    hit_sequence as hit_sequence_module,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitSequence,
)

HitSequenceFactory = Callable[..., HitSequence]


@pytest.mark.unit
@pytest.mark.parametrize("value", [1, 7, 30])
def test_horizon_rule_accepts_positive_int(value: int) -> None:
    validate_horizon(value, field="horizon")


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, 1.0, "1", None],
    ids=["zero", "neg", "true", "false", "float", "str", "none"],
)
def test_horizon_rule_rejects_with_the_field_name(value: object) -> None:
    with pytest.raises(ValueError, match=r"^my_horizon must be an int >= 1"):
        validate_horizon(value, field="my_horizon")  # type: ignore[arg-type]


def _reject(*_: object, **__: object) -> None:
    raise ValueError("single horizon rule called")


@pytest.mark.unit
def test_horizon_rule_is_consumed_by_the_hit_sequence(
    make_hit_sequence: HitSequenceFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hit_sequence_module, "validate_horizon", _reject)

    with pytest.raises(ValueError, match="single horizon rule called"):
        make_hit_sequence((True, False))


@pytest.mark.unit
def test_horizon_rule_is_consumed_by_the_wilson_band(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wilson_band_module, "validate_horizon", _reject)

    with pytest.raises(ValueError, match="single horizon rule called"):
        wilson_band_module.WilsonBand.evaluate(
            horizon=1, count=10, n=500, nominal=0.02, band_level=0.95
        )
