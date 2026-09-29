"""Contract test do port `McsBackend` — suíte ÚNICA para o fake e o gerador de registro.

Prova (concept 6.2 A11, C9; ADR 6.2.0004 itens 3, 5 e 6; ADR 0.0.0021) que toda
implementação do port entrega:

- **índices** com forma reps x n_obs, faixa [0, n_obs), determinismo por seed, seeds
  diferentes → índices diferentes, o pedido ecoado (`scheme`/`block_size`/`seed`/`n_obs`)
  e `generator` preenchido; o **leiaute** de cada esquema — moving-block em blocos
  consecutivos que começam em ≤ n_obs - l; estacionário com a volta `n_obs - 1 → 0`;
- **b̂_sb** finito e ≥ 0 numa série AR(1) (`random.Random(_AR_SEED)`, stdlib);
- **C9:** as mesmas entradas inválidas erguem `ValueError` com a mensagem dos
  validadores únicos do domínio em toda perna.

Pernas: `fake` (`random.Random`) e `arch` (`ArchMcs`, Task 12) — **sem `skipif`**: a lib é
dependência do projeto desde a Task 01, então perna pulada é perna quebrada. A
concordância numérica do MCS com o `arch.MCS` vive na integração
(`tests/integration/features/evaluation/test_mcs_vs_arch.py`).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.application.ports.out.mcs_backend import (
    McsBackend,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
)
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend

_STATIONARY = BootstrapScheme.STATIONARY
_MOVING = BootstrapScheme.MOVING_BLOCK
_N_OBS = 40
_BLOCK = 4
_REPS = 25
_AR_SEED = 62_2026
_AR_POINTS = 250
_AR_PHI = 0.6

_FACTORIES: dict[str, Callable[[], McsBackend]] = {
    "fake": FakeMcsBackend,
}


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def backend(request: pytest.FixtureRequest) -> McsBackend:
    return _FACTORIES[request.param]()


def _draw(  # noqa: PLR0913 — um parâmetro por eixo do pedido (keyword-only)
    backend: McsBackend,
    *,
    scheme: BootstrapScheme,
    seed: int = 1,
    n_obs: int = _N_OBS,
    block_size: int = _BLOCK,
    reps: int = _REPS,
) -> BootstrapIndices:
    return backend.bootstrap_indices(
        n_obs=n_obs, block_size=block_size, reps=reps, seed=seed, scheme=scheme
    )


_SCHEMES = pytest.mark.parametrize("scheme", list(BootstrapScheme))


@pytest.mark.contract
@_SCHEMES
def test_indices_shape(backend: McsBackend, scheme: BootstrapScheme) -> None:
    indices = _draw(backend, scheme=scheme)
    assert type(indices) is BootstrapIndices
    assert indices.reps == _REPS
    assert all(len(row) == _N_OBS for row in indices.indices)


@pytest.mark.contract
@_SCHEMES
def test_indices_range(backend: McsBackend, scheme: BootstrapScheme) -> None:
    indices = _draw(backend, scheme=scheme)
    assert all(type(i) is int and 0 <= i < _N_OBS for row in indices.indices for i in row)


@pytest.mark.contract
@_SCHEMES
def test_indices_determinism(backend: McsBackend, scheme: BootstrapScheme) -> None:
    assert _draw(backend, scheme=scheme, seed=5) == _draw(backend, scheme=scheme, seed=5)


@pytest.mark.contract
@_SCHEMES
def test_indices_seeds_differ(backend: McsBackend, scheme: BootstrapScheme) -> None:
    first = _draw(backend, scheme=scheme, seed=1).indices
    second = _draw(backend, scheme=scheme, seed=2).indices
    assert first != second


@pytest.mark.contract
@_SCHEMES
def test_indices_request_echo(backend: McsBackend, scheme: BootstrapScheme) -> None:
    indices = _draw(backend, scheme=scheme, seed=9, n_obs=31, block_size=3, reps=7)
    assert (indices.scheme, indices.block_size, indices.seed, indices.n_obs, indices.reps) == (
        scheme,
        3,
        9,
        31,
        7,
    )


@pytest.mark.contract
@_SCHEMES
def test_indices_generator_filled(backend: McsBackend, scheme: BootstrapScheme) -> None:
    generator = _draw(backend, scheme=scheme).generator
    assert isinstance(generator, str)
    assert generator.strip()


@pytest.mark.contract
@pytest.mark.parametrize(("n_obs", "block_size"), [(40, 4), (41, 4), (10, 9)])
def test_moving_block_contiguity(backend: McsBackend, n_obs: int, block_size: int) -> None:
    """Cada bloco [j·l, (j+1)·l) da linha é consecutivo e começa em ≤ n_obs - l."""
    indices = _draw(backend, scheme=_MOVING, n_obs=n_obs, block_size=block_size, reps=50)
    for row in indices.indices:
        for start in range(0, n_obs, block_size):
            block = row[start : start + block_size]
            assert block[0] <= n_obs - block_size
            assert list(block) == list(range(block[0], block[0] + len(block)))


@pytest.mark.contract
def test_stationary_wraparound(backend: McsBackend) -> None:
    """n_obs = 5, l = 3, reps = 200: alguma linha passa de n_obs - 1 para 0 (bloco circular)."""
    indices = _draw(backend, scheme=_STATIONARY, n_obs=5, block_size=3, reps=200)
    assert any(
        (row[t], row[t + 1]) == (4, 0) for row in indices.indices for t in range(len(row) - 1)
    )


def _ar1_series() -> list[float]:
    rng = random.Random(_AR_SEED)
    series = [rng.gauss(0.0, 1.0)]
    for _ in range(_AR_POINTS - 1):
        series.append(_AR_PHI * series[-1] + rng.gauss(0.0, 1.0))
    return series


@pytest.mark.contract
def test_block_length_finite_nonnegative(backend: McsBackend) -> None:
    estimate = backend.optimal_block_length(series=_ar1_series())
    assert type(estimate) is float
    assert math.isfinite(estimate)
    assert estimate >= 0.0


_BOOTSTRAP_C9 = [
    pytest.param({"n_obs": 1}, "n_obs must be", id="n-obs-one"),
    pytest.param({"block_size": 0}, "block_size must be", id="block-zero"),
    pytest.param({"reps": 0}, "reps must be", id="reps-zero"),
    pytest.param({"seed": -1}, "seed must be", id="seed-negative"),
    pytest.param({"seed": True}, "seed must be", id="seed-bool"),
    pytest.param({"scheme": "stationary"}, "BootstrapScheme", id="scheme-raw-str"),
    pytest.param(
        {"scheme": _MOVING, "block_size": _N_OBS}, "block_size < n_obs", id="mb-block-n-obs"
    ),
]


@pytest.mark.contract
@pytest.mark.parametrize(("overrides", "message"), _BOOTSTRAP_C9)
def test_c9_bootstrap_parity(
    backend: McsBackend, overrides: dict[str, object], message: str
) -> None:
    request: dict[str, object] = {
        "n_obs": _N_OBS,
        "block_size": _BLOCK,
        "reps": _REPS,
        "seed": 1,
        "scheme": _STATIONARY,
    }
    request.update(overrides)
    with pytest.raises(ValueError, match=message):
        backend.bootstrap_indices(**request)  # type: ignore[arg-type]


_VARYING = [float(i % 3) for i in range(15)]
_BLOCK_LENGTH_C9 = [
    pytest.param(_VARYING[:10], "at least 11", id="ten-points"),
    pytest.param([*_VARYING, math.nan], r"series\[15\]", id="nan"),
    pytest.param([*_VARYING, math.inf], r"series\[15\]", id="inf"),
    pytest.param([0.3] * 30, "non-constant", id="constant"),
]


@pytest.mark.contract
@pytest.mark.parametrize(("series", "message"), _BLOCK_LENGTH_C9)
def test_c9_block_length_parity(backend: McsBackend, series: list[float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        backend.optimal_block_length(series=series)


@pytest.mark.contract
def test_fake_constant_block_length() -> None:
    """Só o fake (fora da parametrização): devolve a constante da construção."""
    series = _ar1_series()
    assert FakeMcsBackend(block_length=2.5).optimal_block_length(series=series) == 2.5  # noqa: PLR2004
    assert FakeMcsBackend().optimal_block_length(series=series) == 1.0
