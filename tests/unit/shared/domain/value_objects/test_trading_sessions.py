"""Testes do VO `TradingSessions` (Task 01).

Cobrem construção válida, `start`/`end`, `contains` (hit/miss), `in_window`
(dentro/fora), rejeição de desordenado e de duplicata (C4), e o caso de VO vazio.
"""

from __future__ import annotations

from datetime import date

import pytest

from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)


def _sessions(*days: tuple[int, int, int]) -> TradingSessions:
    return TradingSessions(sessions=tuple(date(y, m, d) for (y, m, d) in days))


def test_valid_construction_keeps_sessions() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 4), (2023, 1, 5))
    assert vo.sessions == (date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5))


def test_start_and_end_are_first_and_last() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 4), (2023, 1, 6))
    assert vo.start == date(2023, 1, 3)
    assert vo.end == date(2023, 1, 6)


def test_contains_hit() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 4), (2023, 1, 6))
    assert vo.contains(date(2023, 1, 4)) is True


def test_contains_miss_inside_window() -> None:
    # 2023-01-05 está entre start e end, mas não é sessão (não está na tupla).
    vo = _sessions((2023, 1, 3), (2023, 1, 4), (2023, 1, 6))
    assert vo.contains(date(2023, 1, 5)) is False


def test_contains_miss_outside_window() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 4))
    assert vo.contains(date(2022, 12, 31)) is False
    assert vo.contains(date(2023, 1, 10)) is False


def test_in_window_inside() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 6))
    # 2023-01-05 não é sessão, mas está dentro de [start, end].
    assert vo.in_window(date(2023, 1, 5)) is True
    assert vo.in_window(date(2023, 1, 3)) is True
    assert vo.in_window(date(2023, 1, 6)) is True


def test_in_window_outside() -> None:
    vo = _sessions((2023, 1, 3), (2023, 1, 6))
    assert vo.in_window(date(2023, 1, 2)) is False
    assert vo.in_window(date(2023, 1, 7)) is False


def test_unordered_sessions_raise() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        _sessions((2023, 1, 4), (2023, 1, 3))


def test_duplicate_sessions_raise() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        _sessions((2023, 1, 3), (2023, 1, 3))


def test_empty_vo_has_no_bounds() -> None:
    vo = TradingSessions(sessions=())
    with pytest.raises(ValueError, match="empty"):
        _ = vo.start
    with pytest.raises(ValueError, match="empty"):
        _ = vo.end


def test_empty_vo_contains_and_in_window_are_false() -> None:
    vo = TradingSessions(sessions=())
    assert vo.contains(date(2023, 1, 3)) is False
    assert vo.in_window(date(2023, 1, 3)) is False


def test_vo_is_frozen() -> None:
    vo = _sessions(
        (2023, 1, 3),
    )
    with pytest.raises(AttributeError):
        vo.sessions = ()  # type: ignore[misc]
