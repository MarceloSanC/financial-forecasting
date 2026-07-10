"""Testes do `WalkForwardSplitter`: janela expansiva, ladrilhamento e purga+embargo.

Usa um universo de sessões sintético mas **contíguo** (dias úteis seg-sex), sobre
o qual `TradingCalendar` opera de forma auto-consistente: um deslocamento de N
índices é exatamente N dias de pregão, então o gap de purga+embargo pode ser
verificado por contagem de índices (resistente a off-by-one).
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
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.shared.in_memory_hasher import FakeHasher

_FRIDAY = 4  # datetime.weekday(): 0=segunda ... 4=sexta


def _weekday_sessions(count: int, *, start: date = date(2021, 1, 4)) -> tuple[date, ...]:
    """`count` dias uteis contiguos (seg a sex) a partir de `start` (uma segunda)."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _splitter(sessions: tuple[date, ...]) -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions)))


_SCOPE = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=2)


@pytest.mark.unit
def test_expanding_window_train_anchored_and_growing() -> None:
    """I6: todo fold ancora train em sessions[0]; train cresce com o fold."""
    sessions = _weekday_sessions(30)
    folds = _splitter(sessions).split(
        sessions,
        _SCOPE,
        n_folds=2,
        test_size=2,
        val_size=2,
        calib_size=2,
        embargo=1,
        hasher=FakeHasher(),
    )

    first_session = sessions[0].isoformat()
    assert all(fold.train[0] == first_session for fold in folds)
    assert len(folds[1].train) > len(folds[0].train)


@pytest.mark.unit
def test_test_blocks_tile_the_tail() -> None:
    """I7: os n_folds blocos de test são contíguos, disjuntos, e cobrem a cauda."""
    n_folds, test_size = 3, 2
    sessions = _weekday_sessions(30)
    iso = [d.isoformat() for d in sessions]
    folds = _splitter(sessions).split(
        sessions,
        _SCOPE,
        n_folds=n_folds,
        test_size=test_size,
        val_size=2,
        calib_size=2,
        embargo=1,
        hasher=FakeHasher(),
    )

    tests = [fold.test for fold in folds]
    assert all(len(t) == test_size for t in tests)
    # contíguos e ancorados na cauda: concatenados = os últimos n_folds*test_size
    flattened = [ts for block in tests for ts in block]
    assert flattened == iso[-(n_folds * test_size) :]


@pytest.mark.unit
@pytest.mark.parametrize(("max_horizon", "embargo"), [(1, 0), (2, 1), (3, 2)])
def test_purge_embargo_gap_equals_max_horizon_plus_embargo(
    max_horizon: int, embargo: int
) -> None:
    """I3/I4: entre blocos há exatamente max_horizon+embargo sessões excluídas.

    Falha se a purga não escalar com max_horizon (mutação: purga fixa) ou se o
    embargo for ignorado.
    """
    sessions = _weekday_sessions(60)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    scope = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=max_horizon)
    folds = _splitter(sessions).split(
        sessions,
        scope,
        n_folds=2,
        test_size=3,
        val_size=3,
        calib_size=3,
        embargo=embargo,
        hasher=FakeHasher(),
    )
    expected_gap = max_horizon + embargo

    for fold in folds:
        for upstream, downstream in (
            (fold.train, fold.early_stop),
            (fold.early_stop, fold.calib),
            (fold.calib, fold.test),
        ):
            excluded = index[downstream[0]] - index[upstream[-1]] - 1
            assert excluded == expected_gap


@pytest.mark.unit
def test_no_overlap_across_all_partitions() -> None:
    """I1: nenhuma sessão aparece em duas partições, em nenhum fold."""
    sessions = _weekday_sessions(40)
    folds = _splitter(sessions).split(
        sessions,
        _SCOPE,
        n_folds=2,
        test_size=2,
        val_size=2,
        calib_size=2,
        embargo=1,
        hasher=FakeHasher(),
    )

    for fold in folds:
        blocks = [set(fold.train), set(fold.early_stop), set(fold.calib), set(fold.test)]
        union_size = sum(len(b) for b in blocks)
        merged: set[str] = set().union(*blocks)
        assert len(merged) == union_size


@pytest.mark.unit
def test_insufficient_history_raises() -> None:
    """Janela curta demais para train+gaps+val+calib+test ergue ValueError (sem clamp)."""
    sessions = _weekday_sessions(12)
    with pytest.raises(ValueError, match="insufficient history"):
        _splitter(sessions).split(
            sessions,
            _SCOPE,
            n_folds=2,
            test_size=2,
            val_size=2,
            calib_size=2,
            embargo=1,
            hasher=FakeHasher(),
        )


@pytest.mark.unit
def test_test_blocks_do_not_fit_raises() -> None:
    """n_folds*test_size maior que a grade ergue ValueError."""
    sessions = _weekday_sessions(20)
    with pytest.raises(ValueError, match="tile"):
        _splitter(sessions).split(
            sessions,
            _SCOPE,
            n_folds=11,
            test_size=2,
            val_size=2,
            calib_size=2,
            embargo=1,
            hasher=FakeHasher(),
        )


@pytest.mark.unit
def test_non_contiguous_grid_raises() -> None:
    """Grade que pula uma sessão do calendário ergue ValueError."""
    sessions = _weekday_sessions(30)
    calendar = TradingCalendar(TradingSessions(sessions=sessions))
    gappy = sessions[:10] + sessions[11:]  # remove uma sessão interna
    with pytest.raises(ValueError, match="contiguous run"):
        WalkForwardSplitter(calendar).split(
            gappy,
            _SCOPE,
            n_folds=2,
            test_size=2,
            val_size=2,
            calib_size=2,
            embargo=1,
            hasher=FakeHasher(),
        )


@pytest.mark.unit
def test_non_session_in_grid_raises() -> None:
    """Grade contendo um dia que não é sessão do calendário ergue ValueError."""
    sessions = _weekday_sessions(30)
    calendar = TradingCalendar(TradingSessions(sessions=sessions))
    intruder = sessions[5] + timedelta(days=1)  # provável sábado/dia fora da grade
    tainted = (*sessions[:6], intruder, *sessions[6:])
    with pytest.raises(ValueError, match=r"non-trading day|strictly increasing|contiguous"):
        WalkForwardSplitter(calendar).split(
            tainted,
            _SCOPE,
            n_folds=2,
            test_size=2,
            val_size=2,
            calib_size=2,
            embargo=1,
            hasher=FakeHasher(),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_folds": 0}, "n_folds"),
        ({"test_size": 0}, "test_size"),
        ({"val_size": 0}, "val_size"),
        ({"calib_size": 0}, "calib_size"),
        ({"embargo": -1}, "embargo"),
    ],
)
def test_invalid_params_raise(kwargs: dict[str, int], match: str) -> None:
    """Cada parâmetro de geometria inválido ergue ValueError."""
    sessions = _weekday_sessions(40)
    base: dict[str, int] = {
        "n_folds": 2,
        "test_size": 2,
        "val_size": 2,
        "calib_size": 2,
        "embargo": 1,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=match):
        _splitter(sessions).split(sessions, _SCOPE, hasher=FakeHasher(), **base)
