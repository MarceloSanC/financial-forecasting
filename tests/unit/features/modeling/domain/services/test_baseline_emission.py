"""Unit do serviço de domínio `baseline_emission` (issue #66).

Testa DIRETAMENTE a política que antes vivia duplicada no adapter
`statsforecast` e no fake in-memory. O valor deste módulo é ter um oráculo
independente para a regra: enquanto ela morava nos dois lados, qualquer
asserção sobre ela era feita duas vezes sobre a MESMA execução, e uma edição
num lado só passava silenciosa.

Cobre, em ordem:

- `validate_structure` — as 10 pré-condições estruturais + C5 de entrada, cada
  uma com a mensagem que a distingue (não basta "ergueu": tem de ergueR pelo
  motivo certo, senão um guard a mais mascara o guard que falta).
- `emit_decision` — as 5 famílias contra o oráculo de fórmula (os serviços de
  domínio da 5.2 chamados diretamente), o ramo I7 de família forjada, C1 do
  `historical_quantiles`, variância zero do `ewma_vol` e o guard de
  `ar1_params` ausente.
- `emit_baseline_grids` — a COMPOSIÇÃO, que é a parte da regra que os
  chamadores não podem mais reimplementar: valida antes de estimar, estima UMA
  vez sobre o train congelado, e só chama o estimador na família `ar1`.
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.domain.services.baseline_emission import (
    emit_baseline_grids,
    emit_decision,
    validate_structure,
)
from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ar1_step_forecast,
    ewma_variance_path,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    degenerate_grid,
    gaussian_grid,
    sample_quantiles_type7,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 3)
_SERIES = tuple(0.001 * (i + 1) * (-1) ** i for i in range(30))
_TRAIN_END_IDX = 19
_DECISION = 25
_AR1_PARAMS = (0.001, 0.4, 4e-05)

_ZERO_SPEC = BaselineSpec(family="zero_return")
_MEAN_SPEC = BaselineSpec(family="historical_mean")
_AR1_SPEC = BaselineSpec(family="ar1")
_EWMA_SPEC = BaselineSpec(family="ewma_vol", decay_lambda=0.94)
_HQ_SPEC = BaselineSpec(family="historical_quantiles", window=20)


def _emit(spec: BaselineSpec, **overrides: object) -> dict[int, tuple[float, ...]]:
    kwargs: dict[str, object] = {
        "spec": spec,
        "returns": _SERIES,
        "train_end_idx": _TRAIN_END_IDX,
        "decision_idx": _DECISION,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "ar1_params": _AR1_PARAMS,
    }
    kwargs.update(overrides)
    return dict(emit_decision(**kwargs))  # type: ignore[arg-type]


# -- validate_structure --------------------------------------------------------


@pytest.mark.unit
def test_valid_structure_passes_silently() -> None:
    assert validate_structure(_SERIES, _TRAIN_END_IDX, (25, 27), _HORIZONS) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("returns", "train_end_idx", "decisions", "horizons", "expected"),
    [
        ((), 0, (1,), (1,), "returns must be non-empty"),
        (_SERIES, -1, (25,), (1,), "train_end_idx must be in [0, 29]; got -1"),
        (_SERIES, 30, (25,), (1,), "train_end_idx must be in [0, 29]; got 30"),
        (_SERIES, 19, (), (1,), "decision_indices must be non-empty"),
        (_SERIES, 19, (30,), (1,), "decision index 30 out of range [0, 29]"),
        (_SERIES, 19, (19,), (1,), "decision index 19 must be after train_end_idx=19"),
        (_SERIES, 19, (25, 25), (1,), "decision_indices must be strictly increasing"),
        (_SERIES, 19, (27, 25), (1,), "decision_indices must be strictly increasing"),
        (_SERIES, 19, (25,), (), "horizons must be non-empty and >= 1; got ()"),
        (_SERIES, 19, (25,), (0,), "horizons must be non-empty and >= 1; got (0,)"),
    ],
)
def test_structural_precondition_raises_with_its_own_message(
    returns: Sequence[float],
    train_end_idx: int,
    decisions: Sequence[int],
    horizons: Sequence[int],
    expected: str,
) -> None:
    """Cada pré-condição ergue pelo SEU motivo — guard a mais não mascara o que falta."""
    with pytest.raises(ValueError) as raised:
        validate_structure(returns, train_end_idx, decisions, horizons)

    assert str(raised.value) == expected


@pytest.mark.unit
def test_c5_non_finite_inside_the_conditioning_window_raises() -> None:
    poisoned = (*_SERIES[:_DECISION], math.nan, *_SERIES[_DECISION + 1 :])

    with pytest.raises(ValueError, match=r"non-finite value in the conditioning window"):
        validate_structure(poisoned, _TRAIN_END_IDX, (_DECISION,), _HORIZONS)


@pytest.mark.unit
def test_c5_ignores_non_finite_strictly_after_the_widest_decision() -> None:
    """A janela é `returns[: max(decisão)+1]` — NaN depois dela não é da chamada.

    Mata o mutante `returns[: widest]` (janela curta demais, deixaria passar o
    NaN NA decisão) e o mutante que varre a série inteira.
    """
    tainted = (*_SERIES[: _DECISION + 1], *(math.nan for _ in _SERIES[_DECISION + 1 :]))

    assert validate_structure(tainted, _TRAIN_END_IDX, (_DECISION,), _HORIZONS) is None


# -- emit_decision: as 5 famílias contra o oráculo de fórmula --------------------


@pytest.mark.unit
def test_zero_return_is_the_degenerate_grid_at_zero_flat_in_horizon() -> None:
    expected = degenerate_grid(value=0.0, levels=_LEVELS)

    assert _emit(_ZERO_SPEC) == {1: expected, 3: expected}


@pytest.mark.unit
def test_historical_mean_uses_only_the_frozen_train_partition() -> None:
    expected = degenerate_grid(value=fmean(_SERIES[: _TRAIN_END_IDX + 1]), levels=_LEVELS)

    assert _emit(_MEAN_SPEC) == {1: expected, 3: expected}


@pytest.mark.unit
def test_ar1_grid_is_the_gaussian_of_the_h_step_forecast_per_horizon() -> None:
    mu, phi, sigma2_eps = _AR1_PARAMS
    expected = {}
    for horizon in _HORIZONS:
        mean, std = ar1_step_forecast(
            mu=mu,
            phi=phi,
            sigma2_eps=sigma2_eps,
            last_return=_SERIES[_DECISION],
            horizon=horizon,
        )
        expected[horizon] = gaussian_grid(mean=mean, std=std, levels=_LEVELS)

    assert _emit(_AR1_SPEC) == expected


@pytest.mark.unit
def test_ar1_without_estimated_params_raises_instead_of_asserting() -> None:
    """Fronteira pública: `ValueError`, não `assert` (que evapora sob `python -O`)."""
    with pytest.raises(ValueError, match=r"ar1 emission requires ar1_params"):
        _emit(_AR1_SPEC, ar1_params=None)


@pytest.mark.unit
def test_ewma_vol_conditions_on_the_window_ending_at_the_decision() -> None:
    sigma2 = ewma_variance_path(returns=_SERIES[: _DECISION + 1], decay_lambda=0.94)[-1]
    expected = gaussian_grid(mean=0.0, std=math.sqrt(sigma2), levels=_LEVELS)

    assert _emit(_EWMA_SPEC) == {1: expected, 3: expected}


@pytest.mark.unit
def test_ewma_vol_refuses_to_emit_a_degenerate_scale_on_an_all_zero_window() -> None:
    with pytest.raises(ValueError, match=r"produced zero variance at decision 25"):
        _emit(_EWMA_SPEC, returns=(0.0,) * 30)


@pytest.mark.unit
def test_historical_quantiles_uses_the_rolling_window_ending_at_the_decision() -> None:
    window = _SERIES[_DECISION - 20 + 1 : _DECISION + 1]
    expected = sample_quantiles_type7(values=window, levels=_LEVELS)

    assert _emit(_HQ_SPEC) == {1: expected, 3: expected}


@pytest.mark.unit
def test_historical_quantiles_raises_when_the_window_does_not_fit_yet() -> None:
    """C1 no limite exato: a decisão 18 tem 19 retornos, W = 20."""
    with pytest.raises(ValueError, match=r"decision 18 has only 19 \(C1\)"):
        _emit(_HQ_SPEC, decision_idx=18)


@pytest.mark.unit
def test_historical_quantiles_accepts_the_first_decision_where_the_window_fits() -> None:
    """Limite de baixo do C1: a decisão 19 tem exatamente W = 20 retornos."""
    expected = sample_quantiles_type7(values=_SERIES[:20], levels=_LEVELS)

    assert _emit(_HQ_SPEC, decision_idx=19) == {1: expected, 3: expected}


@pytest.mark.unit
def test_forged_family_outside_the_canonical_five_raises() -> None:
    forged = BaselineSpec(family="zero_return")
    object.__setattr__(forged, "family", "arma_11")

    with pytest.raises(ValueError, match=r"unknown baseline family 'arma_11'"):
        _emit(forged)


# -- emit_baseline_grids: a composição (a regra que os chamadores não repetem) ---


def _fixed_estimator(
    calls: list[tuple[float, ...]],
) -> object:
    def estimate(train: Sequence[float]) -> tuple[float, float, float]:
        calls.append(tuple(train))
        return _AR1_PARAMS

    return estimate


@pytest.mark.unit
def test_grids_carry_every_requested_decision() -> None:
    calls: list[tuple[float, ...]] = []

    grids = emit_baseline_grids(
        _fixed_estimator(calls),  # type: ignore[arg-type]
        spec=_ZERO_SPEC,
        returns=_SERIES,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=(25, 27),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    assert set(grids) == {25, 27}
    assert all(set(by_horizon) == set(_HORIZONS) for by_horizon in grids.values())


@pytest.mark.unit
def test_the_estimator_is_never_called_outside_the_ar1_family() -> None:
    calls: list[tuple[float, ...]] = []

    emit_baseline_grids(
        _fixed_estimator(calls),  # type: ignore[arg-type]
        spec=_EWMA_SPEC,
        returns=_SERIES,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=(25, 27),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    assert calls == []


@pytest.mark.unit
def test_the_estimator_runs_once_on_the_frozen_train_for_every_decision() -> None:
    """I4/D2: um fit por chamada, sobre `returns[: train_end_idx+1]` — não por decisão."""
    calls: list[tuple[float, ...]] = []

    emit_baseline_grids(
        _fixed_estimator(calls),  # type: ignore[arg-type]
        spec=_AR1_SPEC,
        returns=_SERIES,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=(25, 27, 29),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )

    assert calls == [tuple(_SERIES[: _TRAIN_END_IDX + 1])]


@pytest.mark.unit
def test_structure_is_validated_before_the_estimator_is_ever_reached() -> None:
    """Entrada estruturalmente inválida nunca chega ao estimador (nem ao fit da lib)."""
    calls: list[tuple[float, ...]] = []

    with pytest.raises(ValueError, match=r"decision_indices must be strictly increasing"):
        emit_baseline_grids(
            _fixed_estimator(calls),  # type: ignore[arg-type]
            spec=_AR1_SPEC,
            returns=_SERIES,
            train_end_idx=_TRAIN_END_IDX,
            decision_indices=(27, 25),
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )

    assert calls == []


@pytest.mark.unit
def test_returns_are_coerced_to_float_before_emission() -> None:
    """A fronteira aceita `Sequence[float]` com inteiros e emite float puro."""
    integers = [0] * 25 + [1] * 5

    grids = emit_baseline_grids(
        _fixed_estimator([]),  # type: ignore[arg-type]
        spec=_MEAN_SPEC,
        returns=integers,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=(25,),
        horizons=(1,),
        quantile_levels=_LEVELS,
    )

    assert all(isinstance(value, float) for value in grids[25][1])
