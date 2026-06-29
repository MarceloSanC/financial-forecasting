"""Unit test do VO `PredictionRow` (Stage 4.1, task-04).

Prova (concept 4.1 A2/A3/I1/I5): igualdade por valor + FrozenInstanceError; e —
crucial para H-1 — que `quantile_level` é um campo e que NÃO existe nenhuma coluna
`quantile_p10/p50/p90` (nem variante `_post_guardrail`); a grade de quantis NÃO está
fixada no VO.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.prediction_row import (
    PredictionRow,
)


def _row(**overrides: object) -> PredictionRow:
    base: dict[str, object] = {
        "run_id": "a" * 64,
        "split": "test",
        "horizon": 1,
        "decision_idx": 100,
        "timestamp_utc": "2024-01-02T00:00:00Z",
        "target_timestamp_utc": "2024-01-03T00:00:00Z",
        "quantile_level": 0.5,
        "value_raw": 0.012,
        "value_guardrail": 0.012,
        "guardrail_applied": 0,
    }
    base.update(overrides)
    return PredictionRow(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_equality_and_hash_by_value() -> None:
    """I9: duas linhas com os mesmos campos são iguais e hasheiam igual."""
    a = _row()
    b = _row()

    assert a == b
    assert hash(a) == hash(b)


@pytest.mark.unit
def test_distinct_quantile_level_breaks_equality() -> None:
    """I5/I9: o nível de quantil participa da identidade da linha longa."""
    assert _row(quantile_level=0.1) != _row(quantile_level=0.9)


@pytest.mark.unit
def test_frozen_raises_on_reassignment() -> None:
    """I1: o VO é frozen — reatribuir um campo levanta FrozenInstanceError."""
    row = _row()

    with pytest.raises(dataclasses.FrozenInstanceError):
        row.value_raw = 0.99  # type: ignore[misc]


@pytest.mark.unit
def test_quantile_level_is_a_field() -> None:
    """A3/I5: `quantile_level` existe como campo (formato longo, H-1)."""
    field_names = {f.name for f in dataclasses.fields(PredictionRow)}

    assert "quantile_level" in field_names


@pytest.mark.unit
def test_no_per_quantile_columns_exist() -> None:
    """A3/I5 (H-1): NENHUMA coluna por quantil hardcoded — a grade não é fixada.

    Anti-regressão contra portar o layout largo do old (`quantile_p10/p50/p90`
    e variantes `_post_guardrail`).
    """
    field_names = {f.name for f in dataclasses.fields(PredictionRow)}
    forbidden = {
        "quantile_p10",
        "quantile_p50",
        "quantile_p90",
        "quantile_p10_post_guardrail",
        "quantile_p50_post_guardrail",
        "quantile_p90_post_guardrail",
    }

    leaked = field_names & forbidden
    assert not leaked, f"colunas por quantil proibidas (H-1) vazaram no VO: {sorted(leaked)}"
    assert not any(f.startswith("quantile_p") for f in field_names)
