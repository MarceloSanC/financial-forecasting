"""Medição opt-in do custo dos perfis na forma do cohort r0 (Stage 6.6 Task 20, CA17).

Fora do `check-block`, do `make check` e da CI (o job tem timeout de 30 min): só roda com
`MEASURE_PROFILE_COST=1`. `ProfileReports` sobre amostras sintéticas com a forma do r0 —
6 folds de 252 sessões, 10 seeds do candidato, 7 modelos, h ∈ {1, 7}, a grade de 7
níveis, os 999 sorteios do Monte Carlo do plano — imprime o tempo total e o do Monte
Carlo e exige **zero** unidades `error`. Nenhum dado real (cegamento): o cohort é o da
`_cohort_factory`. O resultado vai à §7 do technical.
"""

from __future__ import annotations

import os
import time

import pytest

from financial_forecasting.features.evaluation.domain.services import profile_reports
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReports,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    ProfileReports,
    ProfileSettings,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from tests.unit.features.evaluation._profile_parameters import profile_parameters
from tests.unit.features.evaluation.gold._cohort_factory import make_cohort

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("MEASURE_PROFILE_COST") != "1",
        reason="medição opt-in: MEASURE_PROFILE_COST=1",
    ),
]

_CANDIDATE = "tft"
_COMPARATORS = ("zero", "mean", "ar1", "ewma", "hq", "gbm")
_FOLDS = tuple(f"f{k}" for k in range(6))
_SESSIONS_PER_FOLD = 252
_HORIZONS = (1, 7)
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_DRAWS = 999
_TOLERANCE = 1e-12


def test_profile_cost_in_the_r0_shape() -> None:
    seeds: dict[str, tuple[int | None, ...]] = {_CANDIDATE: tuple(range(1, 11))}
    seeds |= {model: (None,) for model in _COMPARATORS}
    first_decision = 5
    cohort = make_cohort(
        seeds=seeds,
        folds=_FOLDS,
        horizons=_HORIZONS,
        levels=_LEVELS,
        n_sessions=first_decision + len(_FOLDS) * _SESSIONS_PER_FOLD + max(_HORIZONS),
        first_decision=first_decision,
    )
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=_HORIZONS,
        window_deficits={},
        required_models=frozenset({_CANDIDATE}),
    )
    assert assembled.alignment.findings == ()
    settings = ProfileSettings(
        candidate=_CANDIDATE,
        alpha=0.05,
        variance_estimator=DmVarianceEstimator.RECTANGULAR,
        min_violations=2,
        tolerance=_TOLERANCE,
        draws=_DRAWS,
        seed=128,
        profile_parameters=profile_parameters(),
    )
    monte_carlo_seconds = 0.0
    real = profile_reports._monte_carlo

    def timed(*args: object, **kwargs: object) -> object:
        nonlocal monte_carlo_seconds
        start = time.perf_counter()
        try:
            return real(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            monte_carlo_seconds += time.perf_counter() - start

    profile_reports._monte_carlo = timed  # type: ignore[assignment]
    try:
        started = time.perf_counter()
        errors = 0
        units = 0
        for samples in assembled.horizons:
            paired = paired_pinball_losses({m: samples.common[m] for m in samples.models})
            report = HorizonReports.evaluate(
                samples,
                paired=paired,
                tolerance=_TOLERANCE,
                band_levels=(0.95, 0.975),
                min_violations=2,
                candidate=_CANDIDATE,
                dm_alpha=0.05,
                dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR,),
            )
            profile = ProfileReports.evaluate(
                samples, horizon_report=report, paired=paired, settings=settings
            )
            errors += profile.error_units
            units += len(profile.monte_carlo)
        total = time.perf_counter() - started
    finally:
        profile_reports._monte_carlo = real  # type: ignore[assignment]
    print(  # a medição é o produto deste teste (-s)
        f"\nprofile cost (r0 shape): total={total:.1f}s monte_carlo={monte_carlo_seconds:.1f}s "
        f"mc_units={units} error_units={errors}"
    )
    assert errors == 0
    assert units > 0
