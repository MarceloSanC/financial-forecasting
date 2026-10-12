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

from financial_forecasting.features.evaluation.domain.services import (
    paired_pinball_losses as paired_pinball_losses_module,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.value_objects import (
    paired_loss_series as paired_loss_series_module,
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
    realized = kwargs.pop("realized", _REALIZED)
    return make_series(_grids(shift), realized, **kwargs)


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
        # mesmo horizonte, timestamps e grade, outro y_t: o diferencial viria do alvo
        ("realized", {"realized": (0.25, -0.75, 1.5, 0.0, -1.0)}, "realized values differ"),
    )
    cases = []
    for axis, overrides, message in divergent:
        cases.append(
            pytest.param(
                "seed",
                overrides,
                rf"model 'cand', seed index 1: {message}",
                id=f"{axis}-between-seeds",
            )
        )
        cases.append(
            pytest.param(
                "model",
                overrides,
                rf"model 'comp', seed index 0: {message}",
                id=f"{axis}-between-models",
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


@pytest.mark.unit
def test_factory_imports_min_models() -> None:
    """A fábrica usa o `MIN_MODELS` do VO (mesmo objeto), sem cópia privada (6.4 Task 01)."""
    assert paired_pinball_losses_module.MIN_MODELS is paired_loss_series_module.MIN_MODELS
    assert not hasattr(paired_pinball_losses_module, "_MIN_MODELS")


# --- Stage 6.6 Task 04: perda por nível (DM por τ) e série por seed ------------------


@pytest.mark.unit
def test_per_point_losses_at_mean_over_levels_is_the_grid_loss(make_series: SeriesFactory) -> None:
    """A média dos K vetores rho_τ, ponto a ponto, é L_t (diádicos: igualdade exata)."""
    series = _build(make_series, 0.25)
    per_level = [PinballScore.per_point_losses_at(series, level) for level in _DYADIC_LEVELS]
    grid = PinballScore.per_point_losses(series)
    for point in range(_N_POINTS):
        assert sum(column[point] for column in per_level) / len(_DYADIC_LEVELS) == grid[point]


@pytest.mark.unit
def test_per_point_losses_at_refuses_a_level_outside_the_grid(make_series: SeriesFactory) -> None:
    with pytest.raises(ValueError, match="is not in the grid"):
        PinballScore.per_point_losses_at(_build(make_series), 0.5)


@pytest.mark.unit
def test_factory_level_uses_the_loss_of_that_level(make_series: SeriesFactory) -> None:
    """`level=τ`: a coluna é rho_τ por ponto, média entre seeds igual à de L_t."""
    seeds = [_build(make_series, shift) for shift in (0.25, -0.5, 0.75)]
    other = _build(make_series, -0.25)
    level = _DYADIC_LEVELS[1]
    paired = paired_pinball_losses({"cand": seeds, "comp": [other]}, level=level)
    per_seed = [PinballScore.per_point_losses_at(series, level) for series in seeds]
    expected = tuple(sum(point) / len(seeds) for point in zip(*per_seed, strict=True))
    assert paired.losses_of("cand") == expected
    assert paired.losses_of("comp") == PinballScore.per_point_losses_at(other, level)


@pytest.mark.unit
def test_factory_default_level_keeps_the_grid_loss(make_series: SeriesFactory) -> None:
    first, second = _build(make_series, 0.25), _build(make_series, -0.5)
    default = paired_pinball_losses({"cand": [first], "comp": [second]})
    explicit = paired_pinball_losses({"cand": [first], "comp": [second]}, level=None)
    assert default == explicit
    assert default.losses_of("cand") == PinballScore.per_point_losses(first)


@pytest.mark.unit
def test_factory_one_candidate_seed_is_the_per_seed_series(make_series: SeriesFactory) -> None:
    """Série por seed (DM por seed da 6.6): a fábrica com a seed s do candidato, sem código
    novo; os comparadores seguem com a média das suas seeds."""
    seeds = [_build(make_series, shift) for shift in (0.25, -0.5)]
    comparator_seeds = [_build(make_series, shift) for shift in (0.5, -0.75)]
    paired = paired_pinball_losses({"cand": [seeds[1]], "comp": comparator_seeds})
    assert paired.losses_of("cand") == PinballScore.per_point_losses(seeds[1])
    full = paired_pinball_losses({"cand": seeds, "comp": comparator_seeds})
    assert paired.losses_of("comp") == full.losses_of("comp")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        # q = -1,0; y = (0,25, -0,75, 1,5, 0,0, -2,0); u = y - q; rho = u (tau - 1{u<0})
        (0.125, (0.15625, 0.03125, 0.3125, 0.125, 0.875)),
        # q = 1,0; u = (-0,75, -1,75, 0,5, -1,0, -3,0)
        (0.875, (0.09375, 0.21875, 0.4375, 0.125, 0.375)),
    ],
)
def test_per_point_losses_at_absolute_values(
    make_series: SeriesFactory, level: float, expected: tuple[float, ...]
) -> None:
    """Checkpoint C bloco 2 (T1): oráculo absoluto (diádicos, `==`) — pega devolver L_t ou
    trocar o nível pelo espelhado, que a identidade da média sobre os níveis não pega."""
    series = _build(make_series, 0.0)
    assert PinballScore.per_point_losses_at(series, level) == expected
    assert PinballScore.per_point_losses_at(series, 0.125) != PinballScore.per_point_losses_at(
        series, 0.875
    )


@pytest.mark.unit
def test_factory_level_outside_the_grid_raises(make_series: SeriesFactory) -> None:
    """Checkpoint C bloco 2 (N1): nível fora da grade recusado pelo dono (`per_point_losses_at`)."""
    first, second = _build(make_series, 0.25), _build(make_series, -0.5)
    with pytest.raises(ValueError, match="is not in the grid"):
        paired_pinball_losses({"cand": [first], "comp": [second]}, level=0.5)
