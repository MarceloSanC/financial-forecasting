"""Unit test do domain service `MultiHorizonPredictionPersister` — coração do rewrite.

Prova VERBATIM a convenção de `target_timestamp` (concept 4.3 A1/A2/A3, I1-I4), o
ponto exato do Gap 6 / bug E4 do old: alinhamento por **dia de pregão** (índice do
array de sessões), sem off-by-one, sem `timedelta` de calendário.

- (a) h=1: `target == dataset_timestamps[k+1]`, `timestamp == dataset_timestamps[k]`.
- (b) h=7: idem com `k+7`, separados por **exatamente 7 posições** no array.
- (c) sex→seg: diff de **calendário** entre os dois timestamps == 3 dias para h=1
  numa sexta — prova indexação por sessão, não por calendário.
- (d) borda + argumentos inválidos: `IncompletePredictionWindowError` / `ValueError`.
"""

from __future__ import annotations

from datetime import date

import pytest

from financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister import (  # noqa: E501
    IncompletePredictionWindowError,
    MultiHorizonPredictionPersister,
    PredictionWindow,
)

# Grade de pregão sintética (dias úteis consecutivos, ISO UTC). Não há fim de semana
# entre estas datas — usada para os casos h=1/h=7 puramente posicionais.
_WEEKDAYS = (
    "2024-01-02T00:00:00+00:00",  # 0 ter
    "2024-01-03T00:00:00+00:00",  # 1 qua
    "2024-01-04T00:00:00+00:00",  # 2 qui
    "2024-01-05T00:00:00+00:00",  # 3 sex
    "2024-01-08T00:00:00+00:00",  # 4 seg
    "2024-01-09T00:00:00+00:00",  # 5 ter
    "2024-01-10T00:00:00+00:00",  # 6 qua
    "2024-01-11T00:00:00+00:00",  # 7 qui
    "2024-01-12T00:00:00+00:00",  # 8 sex
    "2024-01-16T00:00:00+00:00",  # 9 ter (15 = MLK feriado, ausente da grade)
)

_THREE_DAYS = 3
_FOUR_DAYS = 4
_SEVEN = 7


@pytest.mark.unit
def test_h1_target_is_next_session_and_anchor_is_decision_day() -> None:
    """A1/I1/I2/I3: h=1 → alvo é a sessão k+1, âncora é a sessão k."""
    k = 2
    window = MultiHorizonPredictionPersister.build(
        decision_idx=k, horizon=1, dataset_timestamps=_WEEKDAYS
    )

    assert isinstance(window, PredictionWindow)
    assert window.decision_idx == k
    assert window.timestamp_utc == _WEEKDAYS[k]
    assert window.target_timestamp_utc == _WEEKDAYS[k + 1]


@pytest.mark.unit
def test_h7_target_is_seven_sessions_ahead_exactly() -> None:
    """A1/I3: h=7 → decision e target separados por EXATAMENTE 7 posições."""
    k = 1
    horizon = _SEVEN
    window = MultiHorizonPredictionPersister.build(
        decision_idx=k, horizon=horizon, dataset_timestamps=_WEEKDAYS
    )

    assert window.timestamp_utc == _WEEKDAYS[k]
    assert window.target_timestamp_utc == _WEEKDAYS[k + horizon]
    # Prova posicional: o índice do alvo é exatamente decision_idx + horizon.
    assert (
        _WEEKDAYS.index(window.target_timestamp_utc) - _WEEKDAYS.index(window.timestamp_utc)
        == horizon
    )


@pytest.mark.unit
def test_friday_to_monday_calendar_gap_proves_session_indexing() -> None:
    """A2/I2: h=1 numa sexta → diff de CALENDÁRIO == 3 dias (pula o fim de semana).

    Coração do bug E4: indexar por sessão (array) e não por `pd.Timedelta(days=h)`.
    Sexta = índice 3 (`2024-01-05`); h=1 → segunda = índice 4 (`2024-01-08`).
    """
    friday_idx = 3
    window = MultiHorizonPredictionPersister.build(
        decision_idx=friday_idx, horizon=1, dataset_timestamps=_WEEKDAYS
    )

    decision_day = date.fromisoformat(window.timestamp_utc[:10])
    target_day = date.fromisoformat(window.target_timestamp_utc[:10])
    calendar_diff = (target_day - decision_day).days

    # Diff de calendário (3 dias) != horizon (1) — prova que indexa por SESSÃO.
    assert calendar_diff == _THREE_DAYS
    assert window.timestamp_utc == "2024-01-05T00:00:00+00:00"
    assert window.target_timestamp_utc == "2024-01-08T00:00:00+00:00"


@pytest.mark.unit
def test_holiday_gap_also_skipped_by_session_indexing() -> None:
    """A2/I2: feriado intra-grade (MLK 15/jan ausente) também é pulado por sessão.

    Índice 8 (sex 12/jan) + h=1 → índice 9 (ter 16/jan); 15/jan (feriado) não está
    na grade — diff de calendário de 4 dias, prova adicional de indexação por sessão.
    """
    window = MultiHorizonPredictionPersister.build(
        decision_idx=8, horizon=1, dataset_timestamps=_WEEKDAYS
    )

    decision_day = date.fromisoformat(window.timestamp_utc[:10])
    target_day = date.fromisoformat(window.target_timestamp_utc[:10])

    # sex 12 -> ter 16 (sab/dom/feriado MLK ausente): diff de calendario de 4 dias.
    assert (target_day - decision_day).days == _FOUR_DAYS
    assert window.target_timestamp_utc == _WEEKDAYS[9]


@pytest.mark.unit
def test_target_out_of_range_raises_incomplete_window() -> None:
    """A3/I4/C1: `decision_idx + horizon >= len` → IncompletePredictionWindowError."""
    last = len(_WEEKDAYS) - 1
    with pytest.raises(IncompletePredictionWindowError):
        MultiHorizonPredictionPersister.build(
            decision_idx=last, horizon=1, dataset_timestamps=_WEEKDAYS
        )


@pytest.mark.unit
def test_decision_idx_out_of_range_raises_incomplete_window() -> None:
    """A3/I4/C1: `decision_idx >= len` → IncompletePredictionWindowError."""
    with pytest.raises(IncompletePredictionWindowError):
        MultiHorizonPredictionPersister.build(
            decision_idx=len(_WEEKDAYS), horizon=1, dataset_timestamps=_WEEKDAYS
        )


@pytest.mark.unit
def test_incomplete_window_is_value_error_subclass() -> None:
    """C1: `IncompletePredictionWindowError` é `ValueError` (caller captura o tipo)."""
    assert issubclass(IncompletePredictionWindowError, ValueError)


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [0, -1])
def test_invalid_horizon_raises_value_error(horizon: int) -> None:
    """A3/C2: `horizon < 1` → ValueError puro (bug do caller, não skip)."""
    with pytest.raises(ValueError, match="horizon must be >= 1") as exc_info:
        MultiHorizonPredictionPersister.build(
            decision_idx=0, horizon=horizon, dataset_timestamps=_WEEKDAYS
        )
    # Não é a subclasse de janela incompleta — é erro de argumento.
    assert not isinstance(exc_info.value, IncompletePredictionWindowError)


@pytest.mark.unit
def test_negative_decision_idx_raises_value_error() -> None:
    """A3/C2: `decision_idx < 0` → ValueError puro (bug do caller, não skip)."""
    with pytest.raises(ValueError, match="decision_idx must be >= 0") as exc_info:
        MultiHorizonPredictionPersister.build(
            decision_idx=-1, horizon=1, dataset_timestamps=_WEEKDAYS
        )
    assert not isinstance(exc_info.value, IncompletePredictionWindowError)
