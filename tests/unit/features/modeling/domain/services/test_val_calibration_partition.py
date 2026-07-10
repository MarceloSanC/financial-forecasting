"""Testes do `WalkForwardSplitter`: partição da validação em early-stop + calib.

Foca no invariante do conformal (Step 7.2 / ADR 5.1.0002): a região de validação
é particionada em early-stop e um calib dedicado, adjacente ao test (mais recente),
disjunto e intocado; e a impressão do fold é 4-vias determinística.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.domain.services.trading_calendar import (
    TradingCalendar,
)
from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_VAL_SIZE = 4
_CALIB_SIZE = 3
_TEST_SIZE = 2
_FRIDAY = 4  # datetime.weekday(): 0=segunda ... 4=sexta


def _weekday_sessions(count: int, *, start: date = date(2021, 1, 4)) -> tuple[date, ...]:
    """`count` dias uteis contiguos (seg a sex) a partir de `start`."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _split() -> tuple:
    sessions = _weekday_sessions(50)
    scope = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=2)
    folds = WalkForwardSplitter(
        TradingCalendar(TradingSessions(sessions=sessions))
    ).split(
        sessions,
        scope,
        n_folds=2,
        test_size=_TEST_SIZE,
        val_size=_VAL_SIZE,
        calib_size=_CALIB_SIZE,
        embargo=1,
        hasher=FakeHasher(),
    )
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    return folds, index


@pytest.mark.unit
def test_block_sizes_respect_parameters() -> None:
    """early_stop=val_size, calib=calib_size, test=test_size por fold."""
    folds, _ = _split()

    for fold in folds:
        assert len(fold.early_stop) == _VAL_SIZE
        assert len(fold.calib) == _CALIB_SIZE
        assert len(fold.test) == _TEST_SIZE


@pytest.mark.unit
def test_calib_is_dedicated_and_disjoint_from_early_stop() -> None:
    """I5: calib e early_stop são disjuntos (calib nunca é o early-stop)."""
    folds, _ = _split()

    for fold in folds:
        assert set(fold.calib).isdisjoint(fold.early_stop)


@pytest.mark.unit
def test_calib_is_the_most_recent_validation_block_before_test() -> None:
    """I5: ordem temporal early_stop < calib < test (calib adjacente ao test)."""
    folds, index = _split()

    for fold in folds:
        assert index[fold.early_stop[-1]] < index[fold.calib[0]]
        assert index[fold.calib[-1]] < index[fold.test[0]]


@pytest.mark.unit
def test_fingerprint_is_deterministic_and_reflects_calib() -> None:
    """I8: impressão 4-vias determinística e sensível ao bloco de calib."""
    folds, _ = _split()
    hasher = FakeHasher()

    for fold in folds:
        recomputed = SplitFingerprint.compute(
            hasher=hasher,
            train=list(fold.train),
            val=list(fold.early_stop),
            test=list(fold.test),
            calib=list(fold.calib),
        )
        assert fold.fingerprint == recomputed
        # a impressão 4-vias difere da 3-vias que ignora o calib (calib first-class)
        three_way = SplitFingerprint.compute(
            hasher=hasher,
            train=list(fold.train),
            val=list(fold.early_stop),
            test=list(fold.test),
        )
        assert fold.fingerprint != three_way


@pytest.mark.unit
def test_calib_size_change_shifts_only_the_calib_block() -> None:
    """Aumentar calib_size cresce o calib sem invadir o test (dedicação)."""
    sessions = _weekday_sessions(50)
    scope = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=2)
    splitter = WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))
    common = {
        "n_folds": 2,
        "test_size": _TEST_SIZE,
        "val_size": _VAL_SIZE,
        "embargo": 1,
        "hasher": FakeHasher(),
    }

    small_calib, large_calib = 2, 4
    small = splitter.split(sessions, scope, calib_size=small_calib, **common)  # type: ignore[arg-type]
    large = splitter.split(sessions, scope, calib_size=large_calib, **common)  # type: ignore[arg-type]

    for small_fold, large_fold in zip(small, large, strict=True):
        assert len(small_fold.calib) == small_calib
        assert len(large_fold.calib) == large_calib
        # o test não muda quando só o calib_size muda (test ancora na cauda)
        assert small_fold.test == large_fold.test
