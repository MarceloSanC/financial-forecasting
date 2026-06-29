"""Unit test do use case `PersistPredictions` — grava grade LONG via fake do port.

Prova (concept 4.3 A5/A6/A7, I6/I7/I9, C5) usando o `FakeAnalyticsRepository`
in-memory da 4.2 (fake, NÃO mock; ADR `0_0_0021`):

- (a) grava N linhas LONG por `(decision, h)` (uma por nível) com `value_raw` +
  `value_guardrail` na MESMA linha; PK única por nível ao ler de volta;
- (b) `year == int(timestamp_utc[:4])`, incluindo caso cruzando fronteira de ano
  (decision em dez, target em jan → `year` do DECISION);
- (c) colunas de schema (`schema_version`/`model_version`/`asset`/`feature_set_name`)
  batem com o `command`;
- (d) janela incompleta → linha PULADA, `rows_skipped` incrementado, `y_true` NÃO
  fabricado, demais linhas gravadas;
- (e) `guardrail_applied` chega 1 quando a grade foi reordenada, 0 caso contrário;
- (f) reprocessar mesma PK sem `allow_upsert` → `DuplicateKeyError` propagado.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)

_LAYER = "silver"
_TABLE = "fact_oos_predictions"
_SCHEMA_VERSION = 1
_LEVELS = (0.1, 0.5, 0.9)
_FIVE_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)

# Grade de pregão sintética (ISO UTC). Os índices 8/9 cruzam a virada de ano.
_TIMESTAMPS = (
    "2024-12-26T00:00:00+00:00",  # 0
    "2024-12-27T00:00:00+00:00",  # 1
    "2024-12-30T00:00:00+00:00",  # 2
    "2024-12-31T00:00:00+00:00",  # 3 (decision para o teste de fronteira de ano)
    "2025-01-02T00:00:00+00:00",  # 4 (target h=1 do idx 3 → ano 2025)
    "2025-01-03T00:00:00+00:00",  # 5
    "2025-01-06T00:00:00+00:00",  # 6
    "2025-01-07T00:00:00+00:00",  # 7
)

_THREE_ROWS = 3
_DECISION_YEAR = 2024
_HORIZON_2 = 2


class _FakeClock:
    """Clock determinístico — só para satisfazer o construtor do fake (4.2 I5)."""

    def now(self) -> datetime:
        return datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


def _repo() -> FakeAnalyticsRepository:
    return FakeAnalyticsRepository(clock=_FakeClock())


def _command(
    *,
    decision_idx: int = 0,
    forecasts: dict[int, QuantileForecast] | None = None,
) -> PersistPredictionsCommand:
    if forecasts is None:
        forecasts = {1: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1, 0.5, 0.9))}
    return PersistPredictionsCommand(
        run_id="a" * 64,
        split="test",
        model_version="tft_v1",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=_SCHEMA_VERSION,
        decision_idx=decision_idx,
        dataset_timestamps=_TIMESTAMPS,
        forecasts=forecasts,
    )


@pytest.mark.unit
def test_writes_one_long_row_per_level_with_raw_and_guardrail() -> None:
    """A5/I6 (a): N linhas LONG por (decision, h), value_raw+guardrail na mesma linha."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    result = use_case(_command(decision_idx=0))

    assert result.rows_written == len(_LEVELS)
    assert result.rows_skipped == 0

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    assert len(rows) == len(_LEVELS)
    # Uma linha por nível; cada uma carrega raw E guardrail.
    by_level = {row["quantile_level"]: row for row in rows}
    assert set(by_level) == set(_LEVELS)
    for row in rows:
        assert "value_raw" in row
        assert "value_guardrail" in row
        assert row["timestamp_utc"] == _TIMESTAMPS[0]
        assert row["target_timestamp_utc"] == _TIMESTAMPS[1]


@pytest.mark.unit
def test_pk_is_unique_per_level_within_decision_horizon() -> None:
    """A5/I6: PK única por nível — nenhuma colisão dentro de um (decision, h)."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    use_case(_command(decision_idx=0))

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    pks = {
        (
            row["run_id"],
            row["split"],
            row["horizon"],
            row["timestamp_utc"],
            row["target_timestamp_utc"],
            row["quantile_level"],
        )
        for row in rows
    }
    assert len(pks) == len(rows)  # todas distintas


@pytest.mark.unit
def test_year_is_decision_day_year_across_year_boundary() -> None:
    """A6/I7 (b): decision em 31/dez/2024 → year=2024 mesmo com target em 2025."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    # decision_idx=3 (31/12/2024); h=1 → target idx=4 (02/01/2025).
    result = use_case(_command(decision_idx=3))

    assert result.rows_written == len(_LEVELS)
    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    for row in rows:
        assert row["timestamp_utc"] == "2024-12-31T00:00:00+00:00"
        assert row["target_timestamp_utc"] == "2025-01-02T00:00:00+00:00"
        assert row["year"] == _DECISION_YEAR  # ano do DECISION, não do target


@pytest.mark.unit
def test_schema_columns_match_command() -> None:
    """A6/I7 (c): schema_version/model_version/asset/feature_set_name vêm do command."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    use_case(_command(decision_idx=0))

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    for row in rows:
        assert row["schema_version"] == _SCHEMA_VERSION
        assert row["model_version"] == "tft_v1"
        assert row["asset"] == "AAPL"
        assert row["feature_set_name"] == "fs_all"
        assert row["run_id"] == "a" * 64
        assert row["split"] == "test"


@pytest.mark.unit
def test_incomplete_window_skips_horizon_without_fabricating_y_true() -> None:
    """A7/I4/C1 (d): janela incompleta → pula níveis, conta rows_skipped, grava o resto."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    # decision_idx=6: h=1 → idx 7 (válido); h=2 → idx 8 (fora do range, len=8).
    forecasts = {
        1: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1, 0.5, 0.9)),
        2: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.2, 0.6, 1.0)),
    }
    result = use_case(_command(decision_idx=6, forecasts=forecasts))

    # h=1 grava 3 linhas; h=2 (incompleto) pula 3 níveis.
    assert result.rows_written == len(_LEVELS)
    assert result.rows_skipped == len(_LEVELS)

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    assert len(rows) == _THREE_ROWS
    # Só o horizonte válido (h=1) ficou; nenhum y_true fabricado para h=2.
    assert all(row["horizon"] == 1 for row in rows)
    # `fact_oos_predictions` não tem coluna y_true — o use case nem a inventa.
    assert all("y_true" not in row for row in rows)


@pytest.mark.unit
def test_nothing_written_when_all_windows_incomplete() -> None:
    """A7/C1: se todos os horizontes são incompletos, nada é gravado (write não chamado)."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    # decision_idx=7 (última posição): h=1 → idx 8 fora do range.
    result = use_case(_command(decision_idx=7))

    assert result.rows_written == 0
    assert result.rows_skipped == len(_LEVELS)
    assert repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"}) == []


@pytest.mark.unit
def test_guardrail_applied_flag_reflects_reordering() -> None:
    """A5/I5 (e): guardrail_applied=1 em grade reordenada, 0 em grade monotônica."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    forecasts = {
        1: QuantileForecast.from_raw(  # desordenado → reordena
            levels=_FIVE_LEVELS, raw_values=(0.3, 0.1, 0.5, 0.2, 0.9)
        ),
        2: QuantileForecast.from_raw(  # já monotônico → não aplica
            levels=_FIVE_LEVELS, raw_values=(0.1, 0.2, 0.3, 0.5, 0.9)
        ),
    }
    use_case(_command(decision_idx=0, forecasts=forecasts))

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    h1_flags = {row["guardrail_applied"] for row in rows if row["horizon"] == 1}
    h2_flags = {row["guardrail_applied"] for row in rows if row["horizon"] == _HORIZON_2}
    assert h1_flags == {1}  # reordenado
    assert h2_flags == {0}  # intacto


_EXPECTED_COLUMNS = frozenset(
    {
        "schema_version",
        "run_id",
        "model_version",
        "asset",
        "feature_set_name",
        "split",
        "horizon",
        "decision_idx",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
        "value_raw",
        "value_guardrail",
        "guardrail_applied",
        "year",
    }
)


@pytest.mark.unit
def test_row_carries_exactly_the_fifteen_schema_columns_and_decision_idx() -> None:
    """A5/A6/I6/I7: cada Row LONG tem EXATAMENTE as 15 colunas do schema e o decision_idx.

    Fecha o gap em que o fake do port não valida `pandera`: uma coluna a menos
    (ex.: `decision_idx` esquecido) ou a mais passaria silenciosamente. Trava o
    mapeamento DTO→Row contra o schema `fact_oos_predictions` (4.1, strict=True).
    """
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    decision = 2
    use_case(_command(decision_idx=decision))

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    assert rows
    for row in rows:
        # Conjunto EXATO de colunas — nem a menos (decision_idx) nem a mais.
        assert set(row) == _EXPECTED_COLUMNS
        # `decision_idx` materializado na linha LONG bate com o decision do command.
        assert row["decision_idx"] == decision


@pytest.mark.unit
def test_value_raw_and_value_guardrail_carry_distinct_correct_values() -> None:
    """A5/I5/I6: numa grade reordenada, value_raw=bruto e value_guardrail=ordenado.

    Fecha o gap em que os testes só conferiam a PRESENÇA das colunas: um mutante
    que trocasse `value_raw`↔`value_guardrail` (ou mapeasse guardrail no lugar do
    raw) sobreviveria. Aqui os dois valores são DISTINTOS por nível e checados.
    """
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    raw = (0.3, 0.1, 0.5, 0.2, 0.9)
    expected_guardrail = (0.1, 0.2, 0.3, 0.5, 0.9)  # sorted(raw)
    forecast = QuantileForecast.from_raw(levels=_FIVE_LEVELS, raw_values=raw)
    assert forecast.guardrail_applied is True  # pré-condição: a ordem mudou

    use_case(_command(decision_idx=0, forecasts={1: forecast}))

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    by_level = {row["quantile_level"]: row for row in rows}
    for level, raw_value, guardrail_value in zip(
        _FIVE_LEVELS, raw, expected_guardrail, strict=True
    ):
        row = by_level[level]
        assert row["value_raw"] == raw_value
        assert row["value_guardrail"] == guardrail_value
    # Em pelo menos um nível raw != guardrail — prova que não são a mesma coluna.
    assert any(
        by_level[lvl]["value_raw"] != by_level[lvl]["value_guardrail"] for lvl in _FIVE_LEVELS
    )


@pytest.mark.unit
def test_multiple_valid_horizons_persist_all_rows_with_unique_pk() -> None:
    """A5/I6: dois horizontes válidos do mesmo decision → todas as linhas, PK distinta.

    Fecha o gap em que a unicidade de PK só era provada para 1 horizonte: aqui h=1 e
    h=2 partilham (run_id, split, timestamp_utc) mas diferem em horizon E
    target_timestamp_utc — todas as 2*N linhas coexistem sem colisão.
    """
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    forecasts = {
        1: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1, 0.5, 0.9)),
        2: QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.2, 0.6, 1.0)),
    }
    result = use_case(_command(decision_idx=0, forecasts=forecasts))

    assert result.rows_written == 2 * len(_LEVELS)
    assert result.rows_skipped == 0

    rows = repo.read(layer=_LAYER, table=_TABLE, filters={"asset": "AAPL"})
    assert len(rows) == 2 * len(_LEVELS)
    pks = {
        (
            row["run_id"],
            row["split"],
            row["horizon"],
            row["timestamp_utc"],
            row["target_timestamp_utc"],
            row["quantile_level"],
        )
        for row in rows
    }
    assert len(pks) == len(rows)  # todas distintas entre os dois horizontes
    # h=1 e h=2 têm target_timestamp_utc distintos (sessão+1 vs sessão+2).
    targets = {row["horizon"]: row["target_timestamp_utc"] for row in rows}
    assert targets[1] == _TIMESTAMPS[1]
    assert targets[_HORIZON_2] == _TIMESTAMPS[2]


@pytest.mark.unit
def test_duplicate_pk_propagates_without_upsert() -> None:
    """A5/C5 (f): reprocessar mesma PK sem allow_upsert → DuplicateKeyError propagado."""
    repo = _repo()
    use_case = PersistPredictions(repository=repo)

    use_case(_command(decision_idx=0))
    # Mesma decision/horizon/níveis → colisão de PK lógica na 2ª gravação.
    with pytest.raises(DuplicateKeyError):
        use_case(_command(decision_idx=0))
