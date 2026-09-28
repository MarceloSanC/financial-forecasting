"""Contract test do port `ScoringBackend` — suíte ÚNICA para o fake e os oráculos.

Prova (concept 6.1 A8, C7; ADR 6.1.0001 itens 2 e 4; ADR 0.0.0021) que toda
implementação do port concorda, sob tolerância declarada, com:

- **fixtures analíticas:** os dois exemplos oficiais do docstring de
  `sklearn.metrics.mean_pinball_loss` (0.0333… e 0.3); empate y = q → 0; Dirac com
  grade simétrica (CRPS_Q = |y - x|; IS = (2/alpha)|y - x|); os três casos do IS
  (y < l, l ≤ y ≤ u com as bordas, y > u);
- **a implementação de registro do domínio** em grades aleatórias sem empate
  (`random.Random(_SEED)`, K = 7 simétrico, T = 200), nos três métodos;
- **C7:** nível/miscobertura fora de (0, 1), tamanhos diferentes, grade desalinhada,
  `lower > upper` e sequência vazia erguem `ValueError`.

Pernas: `fake` (delega às funções de série do domínio), `sklearn`
(`SklearnScoring`, Task 10) e `scoringrules` (`ScoringrulesBackend`, Task 11) —
**sem `skipif`**: as libs são dependências do projeto desde a Task 08, então perna
pulada é perna quebrada.
Toda perna devolve `float` **nativo** (`type(v) is float`): `numpy.float64` passaria
num `isinstance(v, float)` e violaria a promessa do port.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.adapters.out.scoring.scoringrules_backend import (
    ScoringrulesBackend,
)
from financial_forecasting.features.evaluation.adapters.out.scoring.sklearn_scoring import (
    SklearnScoring,
)
from financial_forecasting.features.evaluation.application.ports.out.scoring_backend import (
    ScoringBackend,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import (
    mean_crps_quantile,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    mean_interval_score,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    mean_pinball,
)
from tests.fakes.features.evaluation.fake_scoring_backend import FakeScoringBackend

# Tolerâncias declaradas (ADR 0.0.0021; ADR 6.1.0001 Implementation notes): as
# bibliotecas somam em outra ordem (numpy pairwise x math.fsum) — ruído float64 da
# ordem de 1e-12 sobre valores O(1e-2).
_REL_TOL = 1e-12
_ABS_TOL = 1e-12
# Seed declarada das grades aleatórias sem empate.
_SEED = 61_2026
_RANDOM_POINTS = 200
_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_PAIRS = ((0, 6), (1, 5), (2, 4))

_SKLEARN_Y = (1.0, 2.0, 3.0)
_SKLEARN_LEVEL = 0.1

_FACTORIES: dict[str, Callable[[], ScoringBackend]] = {
    "fake": FakeScoringBackend,
    "sklearn": SklearnScoring,
    "scoringrules": ScoringrulesBackend,
}


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def backend(request: pytest.FixtureRequest) -> ScoringBackend:
    return _FACTORIES[request.param]()


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _random_grids() -> tuple[list[float], list[tuple[float, ...]]]:
    """T = 200 grades ordenadas de K = 7 e realizados, sem empate (contínuos)."""
    rng = random.Random(_SEED)
    grids = [tuple(sorted(rng.gauss(0.0, 0.02) for _ in _LEVELS)) for _ in range(_RANDOM_POINTS)]
    realized = [rng.gauss(0.0, 0.02) for _ in range(_RANDOM_POINTS)]
    return realized, grids


# --- Fixtures analíticas ----------------------------------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize(
    ("quantiles", "expected"),
    [((0.0, 2.0, 3.0), 0.1 / 3), ((1.0, 2.0, 4.0), 0.3)],
    ids=["sklearn-doc-0.0333", "sklearn-doc-0.3"],
)
def test_mean_pinball_official_sklearn_fixtures(
    backend: ScoringBackend, quantiles: tuple[float, ...], expected: float
) -> None:
    value = backend.mean_pinball(realized=_SKLEARN_Y, quantiles=quantiles, level=_SKLEARN_LEVEL)

    assert type(value) is float
    assert _close(value, expected)


@pytest.mark.contract
def test_every_method_returns_native_float(backend: ScoringBackend) -> None:
    """O port promete `float` nativo — nunca `numpy.float64` (que passa em isinstance)."""
    realized, grids = _random_grids()
    values = (
        backend.mean_pinball(realized=realized, quantiles=[g[0] for g in grids], level=0.05),
        backend.mean_crps_quantile(realized=realized, quantile_grid=grids, levels=_LEVELS),
        backend.mean_interval_score(
            realized=realized,
            lower=[g[0] for g in grids],
            upper=[g[-1] for g in grids],
            miscoverage=0.1,
        ),
    )

    assert all(type(value) is float for value in values)


@pytest.mark.contract
def test_mean_pinball_is_zero_on_ties(backend: ScoringBackend) -> None:
    assert backend.mean_pinball(realized=[0.01, -0.02], quantiles=[0.01, -0.02], level=0.3) == 0.0


@pytest.mark.contract
@pytest.mark.parametrize(("y", "x"), [(0.03, -0.01), (-0.02, 0.01)], ids=["y>x", "y<x"])
def test_crps_on_symmetric_dirac_is_abs_error(backend: ScoringBackend, y: float, x: float) -> None:
    value = backend.mean_crps_quantile(
        realized=[y], quantile_grid=[(x,) * len(_LEVELS)], levels=_LEVELS
    )

    assert _close(value, abs(y - x))


@pytest.mark.contract
@pytest.mark.parametrize(("y", "x"), [(0.03, -0.01), (-0.02, 0.01)], ids=["y>x", "y<x"])
def test_interval_score_on_dirac_is_scaled_abs_error(
    backend: ScoringBackend, y: float, x: float
) -> None:
    miscoverage = 0.1
    value = backend.mean_interval_score(realized=[y], lower=[x], upper=[x], miscoverage=miscoverage)

    assert _close(value, (2 / miscoverage) * abs(y - x))


@pytest.mark.contract
@pytest.mark.parametrize(
    ("y", "expected"),
    [
        (-0.03, 0.02 + 20 * 0.02),
        (-0.01, 0.02),
        (0.0, 0.02),
        (0.01, 0.02),
        (0.04, 0.02 + 20 * 0.03),
    ],
    ids=["below", "at-lower", "inside", "at-upper", "above"],
)
def test_interval_score_three_cases(backend: ScoringBackend, y: float, expected: float) -> None:
    value = backend.mean_interval_score(realized=[y], lower=[-0.01], upper=[0.01], miscoverage=0.1)

    assert _close(value, expected)


# --- Concordância com a implementação de registro (grades aleatórias sem empate) -------


@pytest.mark.contract
@pytest.mark.parametrize("k", range(len(_LEVELS)))
def test_mean_pinball_agrees_with_domain_on_random_grid(backend: ScoringBackend, k: int) -> None:
    realized, grids = _random_grids()
    column = [grid[k] for grid in grids]

    value = backend.mean_pinball(realized=realized, quantiles=column, level=_LEVELS[k])

    assert _close(value, mean_pinball(realized=realized, quantiles=column, level=_LEVELS[k]))


@pytest.mark.contract
def test_mean_crps_quantile_agrees_with_domain_on_random_grid(backend: ScoringBackend) -> None:
    realized, grids = _random_grids()

    value = backend.mean_crps_quantile(realized=realized, quantile_grid=grids, levels=_LEVELS)

    expected = mean_crps_quantile(realized=realized, quantile_grid=grids, levels=_LEVELS)
    assert _close(value, expected)


@pytest.mark.contract
@pytest.mark.parametrize(("k_low", "k_high"), _PAIRS, ids=["0.05-0.95", "0.1-0.9", "0.25-0.75"])
def test_mean_interval_score_agrees_with_domain_on_random_grid(
    backend: ScoringBackend, k_low: int, k_high: int
) -> None:
    realized, grids = _random_grids()
    lower = [grid[k_low] for grid in grids]
    upper = [grid[k_high] for grid in grids]
    miscoverage = 2 * _LEVELS[k_low]

    value = backend.mean_interval_score(
        realized=realized, lower=lower, upper=upper, miscoverage=miscoverage
    )

    expected = mean_interval_score(
        realized=realized, lower=lower, upper=upper, miscoverage=miscoverage
    )
    assert _close(value, expected)


# --- C7 — mesmo contrato de entrada em todas as pernas ----------------------------------


@pytest.mark.contract
@pytest.mark.parametrize("level", [0.0, 1.0, 1.5, math.nan], ids=["zero", "one", "above", "nan"])
def test_mean_pinball_rejects_level_outside_unit_interval(
    backend: ScoringBackend, level: float
) -> None:
    with pytest.raises(ValueError, match="level must be"):
        backend.mean_pinball(realized=[1.0], quantiles=[1.0], level=level)


@pytest.mark.contract
def test_mean_pinball_rejects_different_lengths(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="same length"):
        backend.mean_pinball(realized=[1.0, 2.0], quantiles=[1.0], level=0.5)


@pytest.mark.contract
def test_mean_pinball_rejects_empty_sequence(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        backend.mean_pinball(realized=[], quantiles=[], level=0.5)


@pytest.mark.contract
def test_mean_crps_quantile_rejects_level_outside_unit_interval(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="level must be"):
        backend.mean_crps_quantile(realized=[0.0], quantile_grid=[(0.0, 1.0)], levels=(0.0, 0.9))


@pytest.mark.contract
def test_mean_crps_quantile_rejects_different_lengths(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="same length"):
        backend.mean_crps_quantile(
            realized=[0.0, 1.0], quantile_grid=[(0.0, 1.0)], levels=(0.25, 0.75)
        )


@pytest.mark.contract
def test_mean_crps_quantile_rejects_misaligned_grid(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="must align"):
        backend.mean_crps_quantile(
            realized=[0.0], quantile_grid=[(0.0, 1.0, 2.0)], levels=(0.25, 0.75)
        )


@pytest.mark.contract
def test_mean_crps_quantile_rejects_empty_grid(backend: ScoringBackend) -> None:
    """C7: grade vazia (K = 0) ergue — a média (2/K)·soma é indefinida."""
    with pytest.raises(ValueError, match="at least one level"):
        backend.mean_crps_quantile(realized=[0.0], quantile_grid=[()], levels=())


@pytest.mark.contract
def test_mean_crps_quantile_rejects_empty_sequence(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        backend.mean_crps_quantile(realized=[], quantile_grid=[], levels=(0.25, 0.75))


@pytest.mark.contract
@pytest.mark.parametrize(
    "miscoverage", [0.0, 1.0, 1.5, math.nan], ids=["zero", "one", "above", "nan"]
)
def test_mean_interval_score_rejects_miscoverage_outside_unit_interval(
    backend: ScoringBackend, miscoverage: float
) -> None:
    with pytest.raises(ValueError, match="miscoverage must be"):
        backend.mean_interval_score(
            realized=[0.0], lower=[-1.0], upper=[1.0], miscoverage=miscoverage
        )


@pytest.mark.contract
def test_mean_interval_score_rejects_different_lengths(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="same length"):
        backend.mean_interval_score(
            realized=[0.0], lower=[-1.0, -1.0], upper=[1.0], miscoverage=0.1
        )


@pytest.mark.contract
def test_mean_interval_score_rejects_crossed_bounds(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="must not exceed upper"):
        backend.mean_interval_score(realized=[0.0], lower=[1.0], upper=[-1.0], miscoverage=0.1)


@pytest.mark.contract
def test_mean_interval_score_rejects_empty_sequence(backend: ScoringBackend) -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        backend.mean_interval_score(realized=[], lower=[], upper=[], miscoverage=0.1)
