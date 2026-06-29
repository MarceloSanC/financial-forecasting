"""Contract test do port `ExchangeCalendarProvider` — paridade Fake ↔ real.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (I8/A9, C5): a janela fechada `[start, end]` é recortada
corretamente; feriados XNYS 2023 conhecidos (`2023-01-02`, `2023-07-04`,
`2023-11-23`, `2023-12-25`) e fins de semana NÃO aparecem; o VO devolvido é
ordenado/sem duplicatas (invariante do `TradingSessions`); `start > end` levanta
`ValueError` (C5).

Na Task 05 a fixture parametriza só o fake; a Task 07 adiciona `_build_real`
(`ExchangeCalendarsProvider()`) para rodar o MESMO contrato sobre `[fake, real]`
— a estrutura já está pronta (mesma postura da Stage 2.1 / ADR 0.0.0021).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)
from financial_forecasting.shared.application.ports.out.exchange_calendar_provider import (
    ExchangeCalendarProvider,
)
from tests.fakes.shared.in_memory_exchange_calendar_provider import (
    FakeExchangeCalendarProvider,
)

# Feriados XNYS 2023 de fechamento total: nunca devem ser sessões em nenhuma janela.
_KNOWN_HOLIDAYS_2023 = (
    date(2023, 1, 2),  # New Year (observed)
    date(2023, 7, 4),  # Independence Day
    date(2023, 11, 23),  # Thanksgiving
    date(2023, 12, 25),  # Christmas
)


def _build_fake() -> ExchangeCalendarProvider:
    return FakeExchangeCalendarProvider()


def _build_real() -> ExchangeCalendarProvider:
    return ExchangeCalendarsProvider()


# Mesmo contrato sobre fake e real (paridade fake↔real, I8/A9/ADR 0.0.0021): o
# real exercita `exchange-calendars` de verdade; os feriados XNYS 2023 conhecidos
# e o recorte de janela devem bater nos dois.
_FACTORIES: list[Callable[[], ExchangeCalendarProvider]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def provider(request: pytest.FixtureRequest) -> ExchangeCalendarProvider:
    """Parametriza o contrato sobre o fake (e o adapter real a partir da Task 07)."""
    factory: Callable[[], ExchangeCalendarProvider] = request.param
    return factory()


@pytest.mark.contract
def test_window_is_clipped_to_closed_range(provider: ExchangeCalendarProvider) -> None:
    """As sessões devolvidas estão todas dentro de `[start, end]` (recorte fechado)."""
    start, end = date(2023, 11, 20), date(2023, 11, 28)
    sessions = provider.sessions(start=start, end=end)

    assert sessions.sessions  # janela não-vazia
    assert all(start <= s <= end for s in sessions.sessions)
    assert sessions.start >= start
    assert sessions.end <= end


@pytest.mark.contract
def test_known_holidays_are_absent(provider: ExchangeCalendarProvider) -> None:
    """Feriados XNYS 2023 conhecidos não aparecem como sessão (I8/A9)."""
    sessions = provider.sessions(start=date(2023, 1, 1), end=date(2023, 12, 31))

    for holiday in _KNOWN_HOLIDAYS_2023:
        assert not sessions.contains(holiday), f"{holiday.isoformat()} must not be a session"


@pytest.mark.contract
def test_weekends_are_absent(provider: ExchangeCalendarProvider) -> None:
    """Sábado e domingo não são sessões."""
    # 2023-11-25 (sábado) e 2023-11-26 (domingo).
    sessions = provider.sessions(start=date(2023, 11, 20), end=date(2023, 11, 28))

    assert not sessions.contains(date(2023, 11, 25))
    assert not sessions.contains(date(2023, 11, 26))


@pytest.mark.contract
def test_known_sessions_are_present(provider: ExchangeCalendarProvider) -> None:
    """Dias de pregão reais ao redor dos feriados estão presentes."""
    sessions = provider.sessions(start=date(2023, 1, 1), end=date(2023, 12, 31))

    # vizinhos imediatos dos feriados-âncora, que SÃO sessões:
    assert sessions.contains(date(2023, 7, 3))  # antes do 4 jul
    assert sessions.contains(date(2023, 7, 5))  # depois do 4 jul
    assert sessions.contains(date(2023, 11, 24))  # sexta pós-Thanksgiving
    assert sessions.contains(date(2023, 12, 26))  # terça pós-Natal


@pytest.mark.contract
def test_returned_vo_is_sorted_without_duplicates(
    provider: ExchangeCalendarProvider,
) -> None:
    """O VO é ordenado e sem duplicatas (invariante do TradingSessions)."""
    sessions = provider.sessions(start=date(2023, 1, 1), end=date(2023, 12, 31))

    raw = sessions.sessions
    assert list(raw) == sorted(raw)
    assert len(set(raw)) == len(raw)


@pytest.mark.contract
def test_start_after_end_raises(provider: ExchangeCalendarProvider) -> None:
    """C5: janela invertida (`start > end`) é erro de chamada."""
    with pytest.raises(ValueError, match="start"):
        provider.sessions(start=date(2023, 12, 31), end=date(2023, 1, 1))


@pytest.mark.contract
def test_single_holiday_window_is_empty(provider: ExchangeCalendarProvider) -> None:
    """Janela legítima sem sessões (só um feriado) devolve VO vazio, não erro."""
    sessions = provider.sessions(start=date(2023, 7, 4), end=date(2023, 7, 4))
    assert sessions.sessions == ()


@pytest.mark.contract
def test_fake_and_real_produce_identical_sessions_2023() -> None:
    """Paridade fake↔real (I8/A9): mesmas sessões XNYS para o ano de 2023 inteiro.

    Gate central da Task 07: o fake in-memory contra o qual a aplicação testa é
    garantidamente idêntico ao XNYS real (`exchange-calendars`) — sem drift.
    """
    start, end = date(2023, 1, 1), date(2023, 12, 31)
    fake = _build_fake().sessions(start=start, end=end)
    real = _build_real().sessions(start=start, end=end)
    assert fake.sessions == real.sessions
