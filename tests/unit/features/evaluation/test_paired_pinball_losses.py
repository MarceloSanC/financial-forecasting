"""Unit test da fábrica `paired_pinball_losses` (A2, C1, I1, I3; ADR 6.2.0001 item 5).

S = 1 é a identidade de `PinballScore.per_point_losses`; S = 3 é a média ponto a ponto.
A grade sintética de 4 níveis diádicos (0,125/0,375/0,625/0,875) com quantis e
realizados diádicos faz cada L_t sair exato em float64 (soma de diádicos e divisão por
K = 4), então a média entre seeds se confere por igualdade (`==`). Cada ramo de erro
da fábrica tem um caso, entre seeds **e** entre modelos. Séries montadas pela fixture
`make_series` do `conftest.py` da 6.1.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

_DYADIC_LEVELS = (0.125, 0.375, 0.625, 0.875)
_OTHER_LEVELS = (0.25, 0.375, 0.625, 0.75)
_N_POINTS = 5
_BASE_GRID = (-1.0, -0.5, 0.5, 1.0)
_REALIZED = (0.25, -0.75, 1.5, 0.0, -2.0)
_LONG_HORIZON = 3


def _grids(shift: float) -> list[tuple[float, ...]]:
    return [
        tuple(value + shift * (point + 1) for value in _BASE_GRID) for point in range(_N_POINTS)
    ]


def _build(make_series: SeriesFactory, shift: float = 0.0, **overrides: object) -> CoverageSeries:
    kwargs: dict[str, object] = {"levels": _DYADIC_LEVELS, "horizon": 1}
    kwargs.update(overrides)
    return make_series(_grids(shift), _REALIZED, **kwargs)


@pytest.mark.unit
def test_factory_single_seed_identity(make_series: SeriesFactory) -> None:
    first, second = _build(make_series, 0.25), _build(make_series, -0.5)
    paired = paired_pinball_losses({"cand": [first], "comp": [second]})
    assert paired.models == ("cand", "comp")
    assert paired.losses_of("cand") == PinballScore.per_point_losses(first)
    assert paired.losses_of("comp") == PinballScore.per_point_losses(second)


@pytest.mark.unit
def test_factory_seed_mean_point_by_point(make_series: SeriesFactory) -> None:
    seeds = [_build(make_series, shift) for shift in (0.25, -0.5, 0.75)]
    per_seed = [PinballScore.per_point_losses(series) for series in seeds]
    expected = tuple((a + b + c) / 3 for a, b, c in zip(*per_seed, strict=True))
    paired = paired_pinball_losses({"cand": seeds, "comp": [_build(make_series)]})
    assert paired.losses_of("cand") == expected
    # a média não é a de nenhuma seed isolada (as três diferem ponto a ponto)
    assert all(paired.losses_of("cand") != losses for losses in per_seed)


@pytest.mark.unit
def test_factory_model_order_follows_mapping(make_series: SeriesFactory) -> None:
    series = _build(make_series)
    paired = paired_pinball_losses({"z": [series], "a": [series], "m": [series]})
    assert paired.models == ("z", "a", "m")


def _mismatch_cases() -> list[Any]:
    # timestamps estritamente crescentes, mas outros que os da fixture (2024-01-02…)
    other_timestamps = tuple(f"2023-06-0{day}T00:00:00+00:00" for day in range(1, 6))
    divergent: Sequence[tuple[str, dict[str, Any], str]] = (
        ("horizon", {"horizon": 2}, "horizon 2 differs from 1"),
        ("timestamps", {"timestamps": other_timestamps}, "target_timestamps differ"),
        ("grid", {"levels": _OTHER_LEVELS}, "levels .* differ"),
    )
    cases = []
    for axis, overrides, message in divergent:
        cases.append(
            pytest.param(
                "seed", overrides, rf"model 'cand', seed 1: {message}", id=f"{axis}-between-seeds"
            )
        )
        cases.append(
            pytest.param(
                "model", overrides, rf"model 'comp', seed 0: {message}", id=f"{axis}-between-models"
            )
        )
    return cases


@pytest.mark.unit
@pytest.mark.parametrize(("where", "overrides", "message"), _mismatch_cases())
def test_factory_mismatch_raises(
    make_series: SeriesFactory, where: str, overrides: dict[str, Any], message: str
) -> None:
    base = _build(make_series)
    divergent = _build(make_series, 0.25, **overrides)
    mapping = (
        {"cand": [base, divergent], "comp": [base]}
        if where == "seed"
        else {"cand": [base], "comp": [divergent]}
    )
    with pytest.raises(ValueError, match=message):
        paired_pinball_losses(mapping)


@pytest.mark.unit
def test_factory_no_series_for_a_model_raises(make_series: SeriesFactory) -> None:
    with pytest.raises(ValueError, match="model 'comp' has no series"):
        paired_pinball_losses({"cand": [_build(make_series)], "comp": []})


@pytest.mark.unit
@pytest.mark.parametrize("n_models", [0, 1])
def test_factory_single_model_raises(make_series: SeriesFactory, n_models: int) -> None:
    mapping = {f"m{index}": [_build(make_series)] for index in range(n_models)}
    with pytest.raises(ValueError, match="k >= 2 models"):
        paired_pinball_losses(mapping)


@pytest.mark.unit
def test_factory_horizon_propagated(make_series: SeriesFactory) -> None:
    """I1: o resultado carrega o horizonte e os timestamps das séries de entrada."""
    first = _build(make_series, 0.25, horizon=_LONG_HORIZON)
    second = _build(make_series, -0.5, horizon=_LONG_HORIZON)
    paired = paired_pinball_losses({"cand": [first], "comp": [second]})
    assert paired.horizon == _LONG_HORIZON
    assert paired.target_timestamps == first.target_timestamps
    assert paired.n_points == _N_POINTS
