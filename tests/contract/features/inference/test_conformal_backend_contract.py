"""Contrato do port `ConformalBackend` — suíte única para o fake e o oráculo (ADR 7.2.0002 item 4).

Prova que toda implementação do port devolve as correções (Q_lo, Q_hi) do domain
de registro (`ConformalCalibrator.calibrate(..., SPLIT_CQR)`) em todos os tamanhos de
coincidência do helper `_coincidence_sizes` (n >= 50, n = 252 incluído) e nos três
pares do plano, com escores distintos (`random.Random(20261017)`, sem empates).

Pernas: `fake` (`FakeConformalBackend`, posto exato do domain). A perna `mapie`
(`MapieCqrBackend`) entra na Task 07.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.inference.application.ports.out.conformal_backend import (
    ConformalBackend,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    exact_level,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)
from tests.contract.features.inference._coincidence_sizes import (
    TAIL_ALPHAS,
    coincidence_sizes,
)
from tests.fakes.features.inference.fake_conformal_backend import FakeConformalBackend

pytestmark = pytest.mark.contract

_SEED = 20261017
_PAIRS = tuple((alpha, float(1 - exact_level(alpha))) for alpha in TAIL_ALPHAS)
_FACTORIES: dict[str, Callable[[], ConformalBackend]] = {
    "fake": FakeConformalBackend,
}
_START = datetime(2000, 1, 3, 21, tzinfo=UTC)


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def backend(request: pytest.FixtureRequest) -> ConformalBackend:
    return _FACTORIES[request.param]()


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
    assert len(sizes) >= 100  # noqa: PLR2004
    assert min(sizes) >= 50  # noqa: PLR2004 — piso do MAPIE (C5)


def test_corrections_match_the_domain_at_coincidence_sizes(backend: ConformalBackend) -> None:
    rng = random.Random(_SEED)
    for n in coincidence_sizes():
        lower, upper, realized = _calib_values(rng, n)
        for pair in _PAIRS:
            got = backend.split_cqr_corrections(
                calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=pair[0]
            )
            assert got == _domain(lower, upper, realized, pair), (n, pair)


def test_corrections_returned_as_lower_then_upper(backend: ConformalBackend) -> None:
    # y sempre 1 abaixo de q_lo (E_lo = 1) e 3 abaixo de q_hi (E_hi = -3): troca de ordem
    # ou de sinal muda o par devolvido
    n = 252
    lower = [i / 64 for i in range(n)]
    realized = [q - 1.0 for q in lower]
    upper = [q + 2.0 for q in lower]
    got = backend.split_cqr_corrections(
        calib_lower=lower, calib_upper=upper, calib_realized=realized, tail_alpha=0.1
    )
    assert got == (1.0, -3.0)
