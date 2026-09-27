"""Contract test do port `Clock` — paridade Fake ↔ `SystemClock`.

Um ÚNICO contrato parametrizado sobre `[fake, real]` prova a semântica que os
consumidores assumem (ADR 4.2.0002, `created_at_utc` via clock injetado):
`now()` devolve `datetime` **timezone-aware em UTC**, e duas chamadas seguidas são
**não-decrescentes** (monotônico no sentido fraco: o fake devolve sempre o mesmo
instante; o relógio de parede não recua entre duas leituras imediatas).

Fora da parametrização ficam as propriedades próprias de cada perna: o fake
devolve exatamente o instante injetado e recusa instante ingênuo ou fora de UTC;
o real devolve o instante corrente do sistema.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest

from financial_forecasting.shared.application.ports.out.clock import Clock
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.fakes.shared.in_memory_clock import FIXED_NOW, FakeClock


def _build_fake() -> Clock:
    return FakeClock()


def _build_real() -> Clock:
    return SystemClock()


_FACTORIES: list[Callable[[], Clock]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def clock(request: pytest.FixtureRequest) -> Clock:
    """Parametriza o contrato sobre o fake e o `SystemClock`."""
    factory: Callable[[], Clock] = request.param
    return factory()


@pytest.mark.contract
def test_now_is_timezone_aware_utc(clock: Clock) -> None:
    """`now()` carrega tzinfo e o offset é zero (UTC), nunca ingênuo."""
    instant = clock.now()

    assert isinstance(instant, datetime)
    assert instant.tzinfo is not None
    assert instant.utcoffset() == timedelta(0)


@pytest.mark.contract
def test_now_is_non_decreasing_between_calls(clock: Clock) -> None:
    """Duas leituras seguidas não recuam."""
    first = clock.now()
    second = clock.now()

    assert second >= first


@pytest.mark.contract
def test_fake_returns_exactly_the_injected_instant() -> None:
    """Perna fake: devolve o instante injetado, sempre o mesmo, e o default é `FIXED_NOW`."""
    injected = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    clock = FakeClock(injected)

    assert clock.now() == injected
    assert clock.now() == injected
    assert FakeClock().now() == FIXED_NOW


@pytest.mark.contract
@pytest.mark.parametrize(
    "bad_instant",
    [
        datetime(2024, 1, 2, 3, 4, 5),  # ingênuo, de propósito
        datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-3))),
    ],
    ids=["naive", "non-utc"],
)
def test_fake_rejects_instant_the_port_forbids(bad_instant: datetime) -> None:
    """Perna fake: instante ingênuo ou fora de UTC é recusado na construção."""
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        FakeClock(bad_instant)


@pytest.mark.contract
def test_real_returns_the_current_system_instant() -> None:
    """Perna real: `now()` cai entre duas leituras do relógio do sistema."""
    before = datetime.now(tz=UTC)
    instant = SystemClock().now()
    after = datetime.now(tz=UTC)

    assert before <= instant <= after
