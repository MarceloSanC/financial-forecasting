"""Contrato do port `ConformalBackend` — suíte única para o fake e o oráculo (ADR 7.2.0002 item 4).

Prova que toda implementação do port devolve as correções (Q_lo, Q_hi) do domain
de registro (`ConformalCalibrator.calibrate(..., SPLIT_CQR)`) em todos os tamanhos de
coincidência do helper `_coincidence_sizes` (n >= 50, n = 252 incluído) e nos três
pares do plano, com escores distintos (`random.Random(20261017)`, sem empates).

Pernas: `fake` (`FakeConformalBackend`, posto exato do domain, igualdade exata) e
`mapie` (`MapieCqrBackend`, sem `skipif`: o `mapie` é dependência do projeto). No
MAPIE cada Q sai por subtração q - L (ou U - q), então a perna `mapie` compara com
`abs_tol = 1e-12`.

Só na perna `mapie`: o posto +1 num tamanho divergente (a razão de o domain, e não
o MAPIE, ser o registro), a recusa de n pequeno (C5, medida contra o MAPIE 1.5.0) e
zero avisos do MAPIE com os estimadores `prefit` do adapter.
"""

from __future__ import annotations

import math
import random
import warnings
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.inference.adapters.out.mapie import (
    mapie_cqr_backend as mapie_module,
)
from financial_forecasting.features.inference.adapters.out.mapie.mapie_cqr_backend import (
    MapieCqrBackend,
)
from financial_forecasting.features.inference.application.ports.out.conformal_backend import (
    ConformalBackend,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    exact_level,
    split_conformal_rank,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)
from tests.contract.features.inference._coincidence_sizes import (
    COINCIDENCE_COUNT,
    DIVERGENT_SIZES,
    TAIL_ALPHAS,
    coincidence_sizes,
    divergent_sizes,
    domain_rank,
    mapie_rank,
)
from tests.fakes.features.inference.fake_conformal_backend import FakeConformalBackend

pytestmark = pytest.mark.contract

_SEED = 20261017
_PAIRS = tuple((alpha, float(1 - exact_level(alpha))) for alpha in TAIL_ALPHAS)
_FACTORIES: dict[str, Callable[[], ConformalBackend]] = {
    "fake": FakeConformalBackend,
    "mapie": MapieCqrBackend,
}
_ABS_TOL = {"fake": 0.0, "mapie": 1e-12}  # Q do MAPIE por subtração q - L
_START = datetime(2000, 1, 3, 21, tzinfo=UTC)


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def leg(request: pytest.FixtureRequest) -> tuple[ConformalBackend, float]:
    return _FACTORIES[request.param](), _ABS_TOL[request.param]


def _close(got: tuple[float, float], expected: tuple[float, float], tol: float) -> bool:
    return all(
        math.isclose(g, e, rel_tol=0.0, abs_tol=tol) for g, e in zip(got, expected, strict=True)
    )


def _calib_values(rng: random.Random, n: int) -> tuple[list[float], list[float], list[float]]:
    """q_lo < q_hi e y independentes: escores das duas caudas distintos (sem empate)."""
    lower = [rng.uniform(-2.0, -0.5) for _ in range(n)]
    upper = [rng.uniform(0.5, 2.0) for _ in range(n)]
    realized = [rng.gauss(0.0, 1.0) for _ in range(n)]
    return lower, upper, realized


def _domain(
    lower: list[float], upper: list[float], realized: list[float], pair: tuple[float, float]
) -> tuple[float, float]:
    points = tuple(
        CalibrationPoint(
            decision_timestamp=(_START + timedelta(days=i)).isoformat(),
            target_timestamp=(_START + timedelta(days=i + 1)).isoformat(),
            lower=lo,
            upper=hi,
            realized=y,
        )
        for i, (lo, hi, y) in enumerate(zip(lower, upper, realized, strict=True))
    )
    calib = CalibrationSet(
        fold_index=0,
        seed=1,
        horizon=1,
        lower_level=pair[0],
        upper_level=pair[1],
        points=points,
        test_start=(_START + timedelta(days=len(points) + 2)).isoformat(),
    )
    correction = ConformalCalibrator.calibrate(calib, variant=ConformalVariant.SPLIT_CQR)
    return correction.lower.correction, correction.upper.correction


def test_helper_sizes_include_252() -> None:
    sizes = coincidence_sizes()
    assert 252 in sizes  # noqa: PLR2004 — o tamanho do calib do cohort
    assert min(sizes) >= 50  # noqa: PLR2004 — piso do MAPIE (C5)
    # TA-6: contagem e lista congeladas com ==
    assert len(sizes) == COINCIDENCE_COUNT
    assert divergent_sizes() == DIVERGENT_SIZES
    assert sizes == tuple(n for n in range(50, 400) if n not in DIVERGENT_SIZES)


def test_corrections_match_the_domain_at_coincidence_sizes(
    leg: tuple[ConformalBackend, float],
) -> None:
    backend, tol = leg
    rng = random.Random(_SEED)
    for n in coincidence_sizes():
        lower, upper, realized = _calib_values(rng, n)
        for pair in _PAIRS:
            got = backend.split_cqr_corrections(
                calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=pair[0]
            )
            assert _close(got, _domain(lower, upper, realized, pair), tol), (n, pair)


def test_corrections_returned_as_lower_then_upper(leg: tuple[ConformalBackend, float]) -> None:
    backend, tol = leg
    # y sempre 1 abaixo de q_lo (E_lo = 1) e 3 abaixo de q_hi (E_hi = -3): troca de ordem
    # ou de sinal muda o par devolvido
    n = 252
    lower = [i / 64 for i in range(n)]
    realized = [q - 1.0 for q in lower]
    upper = [q + 2.0 for q in lower]
    got = backend.split_cqr_corrections(
        calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.1
    )
    assert _close(got, (1.0, -3.0), tol)


# --- só a perna `mapie` -------------------------------------------------------


def test_mapie_rank_differs_by_one_at_a_divergent_size() -> None:
    # o primeiro n divergente com o +1 numa cauda de 0,25
    n = next(m for m in divergent_sizes() if mapie_rank(m, 0.25) != domain_rank(m, 0.25))
    k = domain_rank(n, 0.25)
    assert mapie_rank(n, 0.25) == k + 1
    rng = random.Random(_SEED + 1)
    lower, upper, realized = _calib_values(rng, n)
    got = MapieCqrBackend().split_cqr_corrections(
        calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.25
    )
    lower_scores = sorted(q - y for q, y in zip(lower, realized, strict=True))
    upper_scores = sorted(y - q for q, y in zip(upper, realized, strict=True))
    # o MAPIE escolhe o (k+1)-ésimo escore do domain; o domain, o k-ésimo
    assert math.isclose(got[0], lower_scores[k], rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(got[1], upper_scores[k], rel_tol=0.0, abs_tol=1e-12)
    domain = _domain(lower, upper, realized, (0.25, 0.75))
    assert domain == (lower_scores[k - 1], upper_scores[k - 1])
    fake = FakeConformalBackend().split_cqr_corrections(
        calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.25
    )
    assert fake == domain  # o fake não reproduz o defeito


@pytest.mark.parametrize("n", [24, 30, 49])
def test_mapie_refuses_small_n(n: int) -> None:
    # C5 medido contra o MAPIE 1.5.0: n = 24 já no `conformalize` (alpha_par = 0,04);
    # n = 30 e 49 no `predict_interval` (alpha_par / 2 = 0,02)
    lower, upper, realized = _calib_values(random.Random(_SEED + n), n)
    with pytest.raises(ValueError, match="Number of samples of the score is too low"):
        MapieCqrBackend().split_cqr_corrections(
            calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.02
        )


def test_mapie_leg_emits_no_warning() -> None:
    lower, upper, realized = _calib_values(random.Random(_SEED + 2), 252)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        MapieCqrBackend().split_cqr_corrections(
            calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.1
        )
    assert [str(w.message) for w in caught] == []


_PREFIT = mapie_module._PrefitPredictions  # o original, antes de qualquer monkeypatch


class _WithoutFeatures:
    """Como o `_PrefitPredictions`, sem `n_features_in_`."""

    def __init__(self, values: object) -> None:
        self._inner = _PREFIT(values)

    def fit(self, X: object, y: object) -> _WithoutFeatures:
        return self

    def predict(self, X: object) -> object:
        return self._inner.predict(X)

    def __sklearn_is_fitted__(self) -> bool:
        return True


class _WithoutFittedHook:
    """Como o `_PrefitPredictions`, sem `__sklearn_is_fitted__`."""

    n_features_in_ = 1

    def __init__(self, values: object) -> None:
        self._inner = _PREFIT(values)

    def fit(self, X: object, y: object) -> _WithoutFittedHook:
        return self

    def predict(self, X: object) -> object:
        return self._inner.predict(X)


def _warnings_with(estimator: type, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(mapie_module, "_PrefitPredictions", estimator)
    lower, upper, realized = _calib_values(random.Random(_SEED + 3), 252)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        MapieCqrBackend().split_cqr_corrections(
            calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.1
        )
    return [str(w.message) for w in caught]


def test_mapie_warns_without_n_features_in(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _warnings_with(_WithoutFeatures, monkeypatch)
    assert any("does not appear fitted" in m for m in messages)


def test_mapie_is_silent_without_the_fitted_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _warnings_with(_WithoutFittedHook, monkeypatch) == []


def test_mapie_refuses_misaligned_calib() -> None:
    """F1: listas de calib de tamanhos diferentes erguem antes de chamar o MAPIE."""
    with pytest.raises(ValueError, match="must align"):
        MapieCqrBackend().split_cqr_corrections(
            calib_lower=[0.0, 0.1], calib_upper=[0.2], calib_realized=[0.0, 0.1], tail_alpha=0.1
        )


def test_prefit_predictions_fit_is_a_no_op_and_reports_fitted() -> None:
    """F1: o `fit` devolve o próprio estimador (o MAPIE nunca reajusta) e o gancho do
    sklearn diz ajustado; o `predict` lê pelo índice da linha."""
    import numpy as np  # noqa: PLC0415 — numpy só nesta perna (contrato do adapter)

    estimator = _PREFIT(np.array([1.0, 2.0, 3.0]))
    assert estimator.fit(np.zeros((3, 1)), np.zeros(3)) is estimator
    assert estimator.__sklearn_is_fitted__() is True
    assert list(estimator.predict(np.array([[2.0], [0.0]]))) == [3.0, 1.0]


def test_integer_rank_of_the_helper_equals_the_domain_rank() -> None:
    """TA-6: o posto por inteiros do helper (independente) confere com o do domain."""
    for n in range(50, 400):
        for alpha in TAIL_ALPHAS:
            assert domain_rank(n, alpha) == split_conformal_rank(n, exact_level(alpha)), (n, alpha)
