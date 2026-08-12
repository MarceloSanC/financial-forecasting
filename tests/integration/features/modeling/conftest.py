"""Helpers de fixture compartilhados pelos e2e do BC `modeling`.

Vieram do e2e da Stage 5.3, onde eram privados do módulo. Moveram para cá na
Stage 5.4 porque o e2e do TFT precisa exatamente da mesma construção, e uma
SEGUNDA cópia seria de uma fixture cuja correção é sutil em três pontos:

1. **As sessões têm de ser pregões XNYS REAIS e contíguos.** O
   `WalkForwardSplitter` valida isso (`_assert_trading_day_gap`), então uma
   grade de `date + timedelta` reprova — mesmo "parecendo" dias úteis.
2. **O parquet precisa de TODAS as colunas do schema 3.5**, incluindo as que a
   tipagem exclui de propósito (`time_idx`, `fundamentals_effective_date`):
   é o que prova a exclusão também no e2e, e não só no unit.
3. **O ruído é determinístico sem RNG global** — dois testes no mesmo processo
   não podem interferir um no outro pela semente do módulo `random`.

`n_sessions` é parâmetro: a 5.3 usa 120 e o TFT pode precisar de outra
contagem, e a constante de módulo que existia antes travava isso.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pandas as pd

from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date
    from pathlib import Path

_CALENDAR_START = "2021-01-04"
_CALENDAR_END = "2021-12-31"
_DAY_OF_WEEK = "day_of_week"
_MONTH = "month"


def xnys_sessions(n_sessions: int) -> tuple[date, ...]:
    """`n_sessions` pregões XNYS REAIS a partir de 2021-01-04.

    Reais, e não `date + timedelta`: o splitter resolve purga e embargo em DIAS
    DE PREGÃO e reprova uma grade que não seja de sessões contíguas do
    calendário.
    """
    window = ExchangeCalendarsProvider().sessions(
        start=datetime.fromisoformat(_CALENDAR_START).date(),
        end=datetime.fromisoformat(_CALENDAR_END).date(),
    )
    if len(window.sessions) < n_sessions:
        msg = (
            f"calendário XNYS de {_CALENDAR_START} a {_CALENDAR_END} tem "
            f"{len(window.sessions)} sessões, menos que as {n_sessions} pedidas"
        )
        raise ValueError(msg)
    return tuple(window.sessions[:n_sessions])


def lcg(seed: int) -> float:
    """Ruído determinístico em [-0.5, 0.5), sem tocar o RNG global."""
    return ((seed * 1103515245 + 12345) % 2**31) / 2**31 - 0.5


def seed_dataset(
    data_root: Path,
    sessions: Sequence[date],
    feature_names: Sequence[str],
    *,
    asset: str,
) -> None:
    """Materializa o parquet físico da 3.5 com TODAS as colunas esperadas.

    As colunas de feature vêm da lista passada pelo chamador (fonte única — uma
    lista paralela desatualizada faria C6 reprovar); `day_of_week`/`month` são
    os ordinais REAIS das sessões; `time_idx` e
    `fundamentals_effective_date` entram presentes para provar, também no e2e,
    que a tipagem nunca as adota.
    """
    count = len(sessions)
    frame_data: dict[str, object] = {
        "timestamp": [
            datetime(day.year, day.month, day.day, tzinfo=UTC) for day in sessions
        ],
        "asset_id": [asset] * count,
        "target_return": [0.001 + 0.01 * lcg(31 + index) for index in range(count)],
        "time_idx": list(range(count)),
        "fundamentals_effective_date": [None] * count,
    }
    for position, name in enumerate(feature_names):
        if name == _DAY_OF_WEEK:
            frame_data[name] = [day.weekday() for day in sessions]
        elif name == _MONTH:
            frame_data[name] = [day.month for day in sessions]
        else:
            frame_data[name] = [
                lcg(1_000_000 + position * count + index) for index in range(count)
            ]
    target_dir = data_root / "processed" / "dataset_tft" / asset
    target_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(frame_data).to_parquet(
        target_dir / f"dataset_tft_{asset}.parquet", index=False
    )
