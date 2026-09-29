"""Unit test da regra única de horizonte (`_horizon.validate_horizon`).

Prova (concept 6.3 I1, C1, C9): "`int` não-`bool` ≥ 1" tem uma escrita, consumida pela
`HitSequence` e pela banda de Wilson (e, nas Tasks 07-09, pelos demais relatórios).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    christoffersen_test as christoffersen_test_module,
)
from financial_forecasting.features.evaluation.domain.services import (
    var_descriptive as var_descriptive_module,
)
from financial_forecasting.features.evaluation.domain.services import (
    wilson_band as wilson_band_module,
)
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
)
from financial_forecasting.features.evaluation.domain.services.var_descriptive import (
    VarDescriptive,
)
from financial_forecasting.features.evaluation.domain.value_objects import (
    hit_sequence as hit_sequence_module,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
    validate_positive_int,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
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


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, True, 2.0], ids=["zero", "bool", "float"])
def test_horizon_rule_positive_int_is_shared_with_draws(value: object) -> None:
    """Checkpoint C bloco 3: "inteiro positivo" tem uma regra (horizonte e `draws`)."""
    with pytest.raises(ValueError, match=r"^draws must be an int >= 1"):
        validate_positive_int(value, field="draws")  # type: ignore[arg-type]


@pytest.mark.unit
def test_horizon_rule_is_consumed_by_the_new_reports(
    make_hit_sequence: HitSequenceFactory,
    make_series: Callable[..., CoverageSeries],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Os relatórios das Tasks 07-09 validam o horizonte pela regra única: o
    `ChristoffersenReport` via a identidade do VO, o `MonteCarloPValues` e o
    `VarDescriptiveReport` no próprio módulo (trocar o nome muda o erro)."""
    sequence = make_hit_sequence((True, False, True, False))
    report = ChristoffersenTest.evaluate(sequence, min_violations=0)
    mc = ChristoffersenTest.monte_carlo_p_values(sequence, min_violations=0, draws=3, seed=1)
    grid = (-0.04, -0.03, 0.0, 0.03, 0.04)
    var_report = VarDescriptive.backtest(
        make_series([grid, grid], [0.0, 0.05], levels=(0.02, 0.05, 0.5, 0.95, 0.98)),
        tolerance=1e-9,
        min_violations=0,
    )

    for module, rebuild in (
        (hit_sequence_module, lambda: dataclasses.replace(report)),
        (christoffersen_test_module, lambda: dataclasses.replace(mc)),
        (var_descriptive_module, lambda: dataclasses.replace(var_report)),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(module, "validate_horizon", _reject)
            with pytest.raises(ValueError, match="single horizon rule called"):
                rebuild()


@pytest.mark.unit
def test_horizon_rule_multi_step_threshold_at_two(
    make_hit_sequence: HitSequenceFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limiar único `is_multi_step` (h = 2 é o primeiro multi-passo): a banda de Wilson
    ganha o aviso, LR_ind/LR_cc viram descritivos (salvo na sub-série DGT) e o MC é
    recusado; em h = 1 nada disso. Os três leitores passam pela mesma função."""
    one = make_hit_sequence((True, False, True, False))
    two = make_hit_sequence((True, False, True, False), horizon=2)
    wilson = {
        h: wilson_band_module.WilsonBand.evaluate(
            horizon=h, count=1, n=4, nominal=0.05, band_level=0.95
        ).serial_dependence_warning
        for h in (1, 2)
    }

    assert wilson == {1: False, 2: True}
    assert ChristoffersenTest.evaluate(one, min_violations=0).independence_descriptive is False
    assert ChristoffersenTest.evaluate(two, min_violations=0).independence_descriptive is True
    sub = two.dgt_partition()[0]
    assert ChristoffersenTest.evaluate(sub, min_violations=0).independence_descriptive is False
    ChristoffersenTest.monte_carlo_p_values(one, min_violations=0, draws=2, seed=1)
    with pytest.raises(ValueError, match="require horizon == 1"):
        ChristoffersenTest.monte_carlo_p_values(two, min_violations=0, draws=2, seed=1)

    for module in (christoffersen_test_module, wilson_band_module):
        monkeypatch.setattr(module, "is_multi_step", lambda _: True)
    assert wilson_band_module.WilsonBand.evaluate(
        horizon=1, count=1, n=4, nominal=0.05, band_level=0.95
    ).serial_dependence_warning
    with pytest.raises(ValueError, match="require horizon == 1"):
        ChristoffersenTest.monte_carlo_p_values(one, min_violations=0, draws=2, seed=1)
