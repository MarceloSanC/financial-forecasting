"""Unit test de `CohortGeometry` (Stage 5.5, A1 / I8 / D6).

Contra o `WalkForwardSplitter` REAL: a geometria exploratória tem treino e
early_stop idênticos aos do fold 0 confirmatório; a contagem esperada de linhas
bate com as sessões de teste do splitter real sob a regra do persister (decisão
cujo alvo `t + h` cai além do painel é pulada); na geometria do cohort AAPL,
3528 linhas nos folds 0 a 4 e 3472 no fold 5; `fits` recusa geometria sem treino.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister import (  # noqa: E501
    IncompletePredictionWindowError,
    MultiHorizonPredictionPersister,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    GeometryDoesNotFitError,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions

_FRIDAY = 4
_HORIZONS = (1, 7)
_N_LEVELS = 7
_SMALL = CohortGeometry(n_folds=3, test_size=10, val_size=8, calib_size=6, embargo=2)
_SCOPE = ScopeSpec(asset_id="AAPL", feature_set_name="fs_all", max_horizon=max(_HORIZONS))
_AAPL = CohortGeometry(n_folds=6, test_size=252, val_size=252, calib_size=252, embargo=7)


def _weekday_sessions(count: int) -> tuple[date, ...]:
    days: list[date] = []
    current = date(2021, 1, 4)
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _split(geometry: CohortGeometry, sessions: tuple[date, ...]) -> tuple:  # type: ignore[type-arg]
    splitter = WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))
    return splitter.split(
        sessions,
        _SCOPE,
        n_folds=geometry.n_folds,
        test_size=geometry.test_size,
        val_size=geometry.val_size,
        calib_size=geometry.calib_size,
        embargo=geometry.embargo,
        hasher=CanonicalJsonHasher(),
    )


def test_exploratory_fold_trains_and_early_stops_exactly_like_fold_zero() -> None:
    sessions = _weekday_sessions(120)

    (sweep_fold,) = _split(_SMALL.exploratory(), sessions)
    fold_zero = _split(_SMALL, sessions)[0]

    assert sweep_fold.train == fold_zero.train
    assert sweep_fold.early_stop == fold_zero.early_stop
    assert sweep_fold.test[0] == fold_zero.test[0]


def test_exploratory_geometry_is_one_fold_over_the_whole_oos_tail() -> None:
    assert _SMALL.exploratory() == CohortGeometry(
        n_folds=1, test_size=30, val_size=8, calib_size=6, embargo=2
    )


def _persisted_rows(fold: object, sessions: tuple[date, ...], horizons: tuple[int, ...]) -> int:
    """Conta pelo persister REAL: decisão cuja janela é incompleta é pulada."""
    timestamps = tuple(day.isoformat() for day in sessions)
    index = {day: i for i, day in enumerate(timestamps)}
    persisted = 0
    for day in fold.test:  # type: ignore[attr-defined]
        for h in horizons:
            try:
                MultiHorizonPredictionPersister.build(
                    decision_idx=index[day], horizon=h, dataset_timestamps=timestamps
                )
            except IncompletePredictionWindowError:
                continue
            persisted += 1
    return persisted * _N_LEVELS


@pytest.mark.parametrize(
    ("geometry", "horizons"),
    [
        (_SMALL, _HORIZONS),
        # h > test_size: o penúltimo fold também perde decisões.
        (CohortGeometry(n_folds=3, test_size=5, val_size=8, calib_size=6, embargo=2), (1, 7)),
    ],
    ids=["small", "h-beyond-test-size"],
)
def test_expected_rows_match_the_real_persister_on_the_real_splitter(
    geometry: CohortGeometry, horizons: tuple[int, ...]
) -> None:
    sessions = _weekday_sessions(120)
    scope = ScopeSpec(asset_id="AAPL", feature_set_name="fs_all", max_horizon=max(horizons))
    splitter = WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))
    folds = splitter.split(
        sessions,
        scope,
        n_folds=geometry.n_folds,
        test_size=geometry.test_size,
        val_size=geometry.val_size,
        calib_size=geometry.calib_size,
        embargo=geometry.embargo,
        hasher=CanonicalJsonHasher(),
    )

    for fold_index, fold in enumerate(folds):
        assert _persisted_rows(fold, sessions, horizons) == geometry.expected_prediction_rows(
            fold_index=fold_index, horizons=horizons, n_levels=_N_LEVELS
        )


def test_aapl_cohort_expected_rows_per_fold() -> None:
    per_fold = [
        _AAPL.expected_prediction_rows(fold_index=i, horizons=_HORIZONS, n_levels=_N_LEVELS)
        for i in range(_AAPL.n_folds)
    ]

    assert per_fold == [3528] * 5 + [3472]
    assert sum(per_fold) == 21112  # noqa: PLR2004 — contagem do run-set (concept A8)


def test_fold0_train_size_matches_the_real_splitter() -> None:
    sessions = _weekday_sessions(120)

    fold_zero = _split(_SMALL, sessions)[0]

    assert len(fold_zero.train) == _SMALL.fold0_train_size(
        n_sessions=len(sessions), max_horizon=_SCOPE.max_horizon
    )


def test_fits_rejects_a_geometry_without_fold0_training() -> None:
    with pytest.raises(GeometryDoesNotFitError, match="fold 0 would train on"):
        _AAPL.fits(n_sessions=2000, max_horizon=7)

    _AAPL.fits(n_sessions=4023, max_horizon=7)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_folds": 0},
        {"test_size": 0},
        {"val_size": 0},
        {"calib_size": 0},
        {"embargo": -1},
    ],
)
def test_invalid_geometry_is_rejected(kwargs: dict[str, int]) -> None:
    base = {"n_folds": 2, "test_size": 5, "val_size": 5, "calib_size": 5, "embargo": 0}

    with pytest.raises(ValueError, match="CohortGeometry"):
        CohortGeometry(**{**base, **kwargs})


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"fold_index": 3, "horizons": (1,), "n_levels": 7}, "fold_index"),
        ({"fold_index": 0, "horizons": (), "n_levels": 7}, "horizons"),
        ({"fold_index": 0, "horizons": (0,), "n_levels": 7}, "horizons"),
        ({"fold_index": 0, "horizons": (1,), "n_levels": 0}, "n_levels"),
        ({"fold_index": 0, "horizons": (1, 1), "n_levels": 7}, "unique"),
    ],
)
def test_expected_rows_rejects_invalid_arguments(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _SMALL.expected_prediction_rows(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_fits_boundary_is_one_training_session() -> None:
    """Auditoria de testes (mutação g): na geometria AAPL, 1512 (OOS) + 252 + 252 +
    3 x 14 (gaps) = 2058 sessões consumidas — 2059 deixa 1 de treino, 2058 deixa 0."""
    aapl = CohortGeometry(n_folds=6, test_size=252, val_size=252, calib_size=252, embargo=7)

    aapl.fits(n_sessions=2059, max_horizon=7)
    with pytest.raises(GeometryDoesNotFitError):
        aapl.fits(n_sessions=2058, max_horizon=7)
