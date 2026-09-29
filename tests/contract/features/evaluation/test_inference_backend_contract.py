"""Contract test do port `InferenceBackend` — suíte ÚNICA para o fake e o oráculo.

Prova (concept 6.2 A3, A6, A11, C3, C4, C9; ADR 6.2.0003 itens 3 e 4; ADR 0.0.0021) que
toda implementação do port concorda, sob tolerância declarada, com **a implementação de
registro do domínio**:

- **DM** em pares aleatórios (`random.Random(_SEED)`; T ∈ {12, 30, 250}, h ∈ {1, 2, 7},
  retangular e Bartlett, candidato melhor e pior): `horizon_used`/`fallback_applied`
  exatos; estatística, d̄ e var̂ sob `math.isclose(rel_tol=1e-11, abs_tol=1e-14)`;
  p-valor sob `_assert_p_close` — na perna `statsmodels` o p vem do `scipy.stats.t`,
  então este é também o cruzamento da `student_t_cdf` do domínio com o scipy (A3);
- o **fallback** analítico (d = ±1, h = 2) nas duas pernas e o diferencial constante
  erguendo o erro de variância nula;
- **Holm** em 200 listas aleatórias (m 1-7): ajustados **iguais** (`==`) aos do domínio
  e rejeição igual para alpha ∈ {0,01; 0,025; 0,05; 0,10; 0,20} (I6: paridade exata na
  fronteira só nesse conjunto);
- **C3/C4 (C9):** as mesmas entradas inválidas erguem `ValueError` com a mensagem do
  validador único em toda perna.

Toda perna devolve tipos **nativos** (`type(v) is float`/`int`/`bool`): `numpy.float64`
passaria num `isinstance(v, float)` e violaria a promessa do port. Pernas: `fake` (só
delega aos primitivos do domínio) e `statsmodels` (`StatsmodelsHac`, Task 10) — **sem
`skipif`**: a lib é dependência do projeto desde a Task 01, então perna pulada é perna
quebrada.
"""

from __future__ import annotations

import gc
import math
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

from financial_forecasting.features.evaluation.adapters.out.inference.statsmodels_hac import (
    StatsmodelsHac,
)
from financial_forecasting.features.evaluation.application.ports.out.inference_backend import (
    InferenceBackend,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMarianoResult,
    DmVarianceEstimator,
    diebold_mariano,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    holm_adjust,
    holm_reject,
)
from tests.fakes.features.evaluation.fake_inference_backend import FakeInferenceBackend

# Tolerâncias declaradas (technical 6.2 §1): ≥ 100x o medido na Fase 3B.
_STAT_REL_TOL = 1e-11
_STAT_ABS_TOL = 1e-14
_P_ABS_TOL = 1e-12
_P_TAIL_REL_TOL = 1e-10
_HALF = 0.5
_SEED = 20260928
_HOLM_LISTS = 200
_MAX_M = 7
_ALPHAS = (0.01, 0.025, 0.05, 0.10, 0.20)

_FACTORIES: dict[str, Callable[[], InferenceBackend]] = {
    "fake": FakeInferenceBackend,
    "statsmodels": StatsmodelsHac,
}


@pytest.fixture(scope="module", autouse=True)
def _frozen_heap() -> Iterator[None]:
    """Congela o heap do processo de teste durante a suíte (só custo, sem efeito no resultado).

    `statsmodels.stats.multitest.multipletests(method="holm")` (0.15) chama `gc.collect()`
    explicitamente a cada chamada; num processo pytest com torch/pandas carregados isso
    custa ~0,25 s por chamada — 1200 chamadas nas pernas de Holm levavam ~5 min. Com o heap
    já existente em `gc.freeze()`, a coleta só varre objetos novos.
    """
    gc.freeze()
    yield
    gc.unfreeze()


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def backend(request: pytest.FixtureRequest) -> InferenceBackend:
    return _FACTORIES[request.param]()


def _assert_p_close(actual: float, expected: float) -> None:
    """|Δp| ≤ 1e-12 sempre e, na cauda (ref < 0,5), |Δp| ≤ 1e-10·ref."""
    assert abs(actual - expected) <= _P_ABS_TOL, (actual, expected)
    if expected < _HALF:
        assert abs(actual - expected) <= _P_TAIL_REL_TOL * expected, (actual, expected)


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_STAT_REL_TOL, abs_tol=_STAT_ABS_TOL)


@dataclass(frozen=True)
class _DmCase:
    id: str
    candidate: tuple[float, ...]
    comparator: tuple[float, ...]
    horizon: int
    estimator: DmVarianceEstimator


def _random_dm_cases() -> list[_DmCase]:
    rng = random.Random(_SEED)
    cases = []
    for n_points in (12, 30, 250):
        for horizon in (1, 2, 7):
            for estimator in DmVarianceEstimator:
                for side, scale in (("better", 0.8), ("worse", 1.2)):
                    comparator = tuple(abs(rng.gauss(0.0, 1.0)) for _ in range(n_points))
                    candidate = tuple(scale * abs(rng.gauss(0.0, 1.0)) for _ in range(n_points))
                    cases.append(
                        _DmCase(
                            id=f"t{n_points}-h{horizon}-{estimator.value}-{side}",
                            candidate=candidate,
                            comparator=comparator,
                            horizon=horizon,
                            estimator=estimator,
                        )
                    )
    return cases


_DM_CASES = _random_dm_cases()


def _assert_native(result: DieboldMarianoResult) -> None:
    assert type(result) is DieboldMarianoResult
    for name in ("mean_differential", "long_run_variance", "statistic", "p_value"):
        assert type(getattr(result, name)) is float, name
    for name in ("horizon", "horizon_used", "n_points", "degrees_of_freedom"):
        assert type(getattr(result, name)) is int, name
    assert type(result.fallback_applied) is bool


@pytest.mark.contract
@pytest.mark.parametrize("case", _DM_CASES, ids=[case.id for case in _DM_CASES])
def test_dm_random_matches_domain(backend: InferenceBackend, case: _DmCase) -> None:
    expected = diebold_mariano(
        candidate_losses=case.candidate,
        comparator_losses=case.comparator,
        horizon=case.horizon,
        variance_estimator=case.estimator,
    )
    actual = backend.diebold_mariano(
        candidate_losses=case.candidate,
        comparator_losses=case.comparator,
        horizon=case.horizon,
        variance_estimator=case.estimator,
    )
    _assert_native(actual)
    assert (actual.horizon, actual.horizon_used, actual.fallback_applied) == (
        expected.horizon,
        expected.horizon_used,
        expected.fallback_applied,
    )
    assert (actual.n_points, actual.degrees_of_freedom) == (
        expected.n_points,
        expected.degrees_of_freedom,
    )
    assert actual.variance_estimator is case.estimator
    assert _close(actual.mean_differential, expected.mean_differential)
    assert _close(actual.long_run_variance, expected.long_run_variance)
    assert _close(actual.statistic, expected.statistic)
    _assert_p_close(actual.p_value, expected.p_value)


@pytest.mark.contract
@pytest.mark.parametrize("estimator", list(DmVarianceEstimator))
def test_dm_fallback_both_legs(backend: InferenceBackend, estimator: DmVarianceEstimator) -> None:
    """d = ±1 alternado, h = 2: retangular cai no fallback (h = 1); Bartlett não."""
    result = backend.diebold_mariano(
        candidate_losses=(3.0, 1.0) * 5,
        comparator_losses=(2.0,) * 10,
        horizon=2,
        variance_estimator=estimator,
    )
    rectangular = estimator is DmVarianceEstimator.RECTANGULAR
    assert result.fallback_applied is rectangular
    assert result.horizon_used == (1 if rectangular else 2)
    assert _close(result.long_run_variance, 0.1 if rectangular else 0.01)
    assert abs(result.statistic) <= _STAT_ABS_TOL
    _assert_p_close(result.p_value, _HALF)


@pytest.mark.contract
@pytest.mark.parametrize("horizon", [1, 2])
def test_dm_constant_raises(backend: InferenceBackend, horizon: int) -> None:
    with pytest.raises(ValueError, match=r"^Variance of DM statistic is zero$"):
        backend.diebold_mariano(
            candidate_losses=(3.0, 4.0, 5.0, 6.0, 7.0),
            comparator_losses=(1.0, 2.0, 3.0, 4.0, 5.0),
            horizon=horizon,
            variance_estimator=DmVarianceEstimator.RECTANGULAR,
        )


_RECT = DmVarianceEstimator.RECTANGULAR


def _c3(
    cand: tuple[float, ...], comp: tuple[float, ...], horizon: object, estimator: object
) -> dict[str, object]:
    return {
        "candidate_losses": cand,
        "comparator_losses": comp,
        "horizon": horizon,
        "variance_estimator": estimator,
    }


_C3_CASES = [
    pytest.param(_c3((1.0, 2.0, 3.0), (1.0, 2.0), 1, _RECT), "same length", id="length"),
    pytest.param(_c3((1.0,), (2.0,), 1, _RECT), "T >= 2", id="single-point"),
    pytest.param(_c3((1.0, math.nan, 3.0), (1.0, 2.0, 3.0), 1, _RECT), "finite", id="nan"),
    pytest.param(_c3((1.0, 2.0, 3.0), (1.0, math.inf, 3.0), 1, _RECT), "finite", id="inf"),
    pytest.param(_c3((1.0, 2.0, 3.0), (1.0, -0.5, 3.0), 1, _RECT), ">= 0", id="negative"),
    pytest.param(_c3((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 0, _RECT), "int >= 1", id="h-zero"),
    pytest.param(_c3((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 3, _RECT), "T > h", id="h-equals-t"),
    pytest.param(_c3((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 4, _RECT), "T > h", id="h-above-t"),
    pytest.param(
        _c3((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), 1, "rectangular"), "DmVarianceEstimator", id="raw-str"
    ),
]


@pytest.mark.contract
@pytest.mark.parametrize(("request_kwargs", "message"), _C3_CASES)
def test_dm_c3_parity(
    backend: InferenceBackend, request_kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        backend.diebold_mariano(**request_kwargs)  # type: ignore[arg-type]


_C4_CASES = [
    pytest.param("adjusted", [], None, "at least one", id="adjusted-empty"),
    pytest.param("adjusted", [0.2, -0.1], None, r"p_values\[1\]", id="adjusted-negative"),
    pytest.param("adjusted", [1.1], None, r"p_values\[0\]", id="adjusted-above-one"),
    pytest.param("adjusted", [math.nan], None, r"p_values\[0\]", id="adjusted-nan"),
    pytest.param("rejected", [], 0.05, "at least one", id="rejected-empty"),
    pytest.param("rejected", [0.2, 1.5], 0.05, r"p_values\[1\]", id="rejected-above-one"),
    pytest.param("rejected", [0.2], 0.0, "alpha must be", id="alpha-zero"),
    pytest.param("rejected", [0.2], 1.0, "alpha must be", id="alpha-one"),
]


@pytest.mark.contract
@pytest.mark.parametrize(("method", "p_values", "alpha", "message"), _C4_CASES)
def test_holm_c4_parity(
    backend: InferenceBackend,
    method: str,
    p_values: list[float],
    alpha: float | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        if method == "adjusted":
            backend.holm_adjusted(p_values=p_values)
        else:
            assert alpha is not None
            backend.holm_rejected(p_values=p_values, alpha=alpha)


def _random_p_lists() -> list[list[float]]:
    rng = random.Random(_SEED + 1)
    return [[rng.random() for _ in range(rng.randint(1, _MAX_M))] for _ in range(_HOLM_LISTS)]


_P_LISTS = _random_p_lists()


@pytest.mark.contract
def test_holm_adjusted_equal(backend: InferenceBackend) -> None:
    for p_values in _P_LISTS:
        adjusted = backend.holm_adjusted(p_values=p_values)
        assert type(adjusted) is tuple
        assert all(type(value) is float for value in adjusted)
        assert adjusted == holm_adjust(p_values), p_values


@pytest.mark.contract
@pytest.mark.parametrize("alpha", _ALPHAS)
def test_holm_rejected_equal(backend: InferenceBackend, alpha: float) -> None:
    for p_values in _P_LISTS:
        rejected = backend.holm_rejected(p_values=p_values, alpha=alpha)
        assert type(rejected) is tuple
        assert all(type(value) is bool for value in rejected)
        assert rejected == holm_reject(p_values, alpha=alpha), p_values
