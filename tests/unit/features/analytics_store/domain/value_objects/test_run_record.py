"""Unit test do VO `RunRecord` (Stage 4.1, task-03).

Prova (concept 4.1 A2/I1/I9/I10): igualdade por valor + hash; imutabilidade
(`FrozenInstanceError` ao reatribuir); campos opcionais aceitam ``None``; os
campos de fingerprint são `str` (hashes da 1.4, não recomputados).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)


def _record(**overrides: object) -> RunRecord:
    base: dict[str, object] = {
        "run_id": "a" * 64,
        "asset": "AAPL",
        "parent_sweep_id": "sweep-1",
        "feature_set_name": "all_features",
        "config_signature": "c" * 64,
        "split_fingerprint": "s" * 64,
        "fold": "fold-0",
        "seed": 42,
        "model_version": "tft_v1",
        "schema_version": 1,
    }
    base.update(overrides)
    return RunRecord(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_equality_and_hash_by_value() -> None:
    """I9: dois RunRecord com os mesmos campos são iguais e hasheiam igual."""
    a = _record()
    b = _record()

    assert a == b
    assert hash(a) == hash(b)
    assert a is not b


@pytest.mark.unit
def test_distinct_run_id_breaks_equality() -> None:
    """I9: run_id distinto quebra a igualdade por valor."""
    assert _record() != _record(run_id="b" * 64)


@pytest.mark.unit
def test_frozen_raises_on_reassignment() -> None:
    """I1: o VO é frozen — reatribuir um campo levanta FrozenInstanceError."""
    record = _record()

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.run_id = "z" * 64  # type: ignore[misc]


@pytest.mark.unit
def test_optional_fields_accept_none() -> None:
    """parent_sweep_id/fold/seed são opcionais e aceitam None."""
    record = _record(parent_sweep_id=None, fold=None, seed=None)

    assert record.parent_sweep_id is None
    assert record.fold is None
    assert record.seed is None


@pytest.mark.unit
def test_fingerprints_are_stored_as_strings() -> None:
    """I10: config_signature/split_fingerprint guardam o hash hex (str), não recomputado."""
    record = _record()

    assert isinstance(record.config_signature, str)
    assert isinstance(record.split_fingerprint, str)
