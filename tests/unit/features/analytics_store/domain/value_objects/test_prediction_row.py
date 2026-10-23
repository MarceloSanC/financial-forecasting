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


@pytest.mark.unit
@pytest.mark.parametrize("run_id", ["run-1", "A" * 64, "a" * 63, None])
def test_run_id_must_be_sha256_hex(run_id: object) -> None:
    """#160: o `run_id` é o hash da 1.4 — o construtor cru recusa rótulo."""
    with pytest.raises(ValueError, match="run_id must be a lowercase sha256 hex"):
        _row(run_id=run_id)


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [0, -1, True, 1.0, None])
def test_horizon_must_be_an_int_of_at_least_one(horizon: object) -> None:
    """#160: horizonte em dias de pregão é inteiro >= 1 (bool recusado)."""
    with pytest.raises(ValueError, match="horizon must be an int >= 1"):
        _row(horizon=horizon)


@pytest.mark.unit
@pytest.mark.parametrize("decision_idx", [-1, False, 0.0, None])
def test_decision_idx_must_be_a_non_negative_int(decision_idx: object) -> None:
    """#160: índice na grade do dataset é inteiro >= 0."""
    with pytest.raises(ValueError, match="decision_idx must be an int >= 0"):
        _row(decision_idx=decision_idx)


@pytest.mark.unit
@pytest.mark.parametrize("quantile_level", [0.0, 1.0, -0.1, 1.5, float("nan"), True, "0.5", None])
def test_quantile_level_must_be_in_the_open_unit_interval(quantile_level: object) -> None:
    """#160: o nível entra na PK — fora de (0, 1) (ou não-número) é recusado."""
    with pytest.raises(ValueError, match=r"quantile_level must be in \(0, 1\)"):
        _row(quantile_level=quantile_level)


@pytest.mark.unit
@pytest.mark.parametrize("guardrail_applied", [2, -1, True, False, 1.0, None])
def test_guardrail_applied_must_be_zero_or_one(guardrail_applied: object) -> None:
    """#160: a flag é o int 0/1 do silver — `bool`, float e outros inteiros recusados."""
    with pytest.raises(ValueError, match="guardrail_applied must be 0 or 1"):
        _row(guardrail_applied=guardrail_applied)


@pytest.mark.unit
def test_boundaries_accepted() -> None:
    """Fronteiras válidas: horizon 1, decision_idx 0, flag 1, nível próximo das bordas."""
    row = _row(horizon=1, decision_idx=0, guardrail_applied=1, quantile_level=0.01)

    assert (row.horizon, row.decision_idx, row.guardrail_applied) == (1, 0, 1)
    assert _row(quantile_level=0.99).quantile_level == 0.99  # noqa: PLR2004
