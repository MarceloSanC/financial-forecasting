"""Unit dos DTOs do port `ServingGoldReader` e do fake (Stage 7.4, Task 01).

Cada recusa de `__post_init__` tem caso (technical 7.4 §1 "Contratos"; concept I6-I8);
`ServingGold.unpublished` é válido; `+inf` é aceito; o fake sem carga ergue.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    LOWER,
    OK,
    UNAVAILABLE,
    UPPER,
    ConformalCorrectionRecord,
    H3ReadingRecord,
    H3ShareRecord,
    ServingGold,
    VsnRecord,
)
from tests.fakes.features.inference.in_memory_serving_gold_reader import (
    InMemoryServingGoldReader,
)

pytestmark = pytest.mark.unit

_FINITE_LOWER = -0.2
_LABELS = {"conformal_label": "rótulo c", "h3_label": "rótulo h3", "vsn_label": "rótulo vsn"}


def _correction(**overrides: object) -> ConformalCorrectionRecord:
    fields: dict[str, Any] = {
        "fold_raw": "3",
        "seed": 1,
        "horizon": 1,
        "lower_level": 0.1,
        "upper_level": 0.9,
        "variant": "split_cqr_asymmetric_unweighted_v1",
        "tail": LOWER,
        "tail_level": 0.1,
        "status": OK,
        "reason": None,
        "n": 200,
        "rank": 21,
        "correction": 0.004,
    }
    fields.update(overrides)
    return ConformalCorrectionRecord(**fields)


def _share(**overrides: object) -> H3ShareRecord:
    fields: dict[str, Any] = {
        "method": "permutation",
        "family": "price",
        "share_h1": 0.4,
        "share_h7": 0.3,
        "delta": -0.1,
        "lower": -0.2,
        "upper": 0.05,
        "level": 0.9,
        "side": "two_sided",
        "excludes_zero": False,
        "status": OK,
        "reason": None,
    }
    fields.update(overrides)
    return H3ShareRecord(**fields)


def _reading(**overrides: object) -> H3ReadingRecord:
    fields: dict[str, Any] = {
        "reading_rule": "regra",
        "heterogeneous_permutation": True,
        "heterogeneous_ablation": False,
        "sustained": False,
        "agreeing_families": ("price",),
        "n_points": 1505,
        "status": OK,
        "reason": None,
    }
    fields.update(overrides)
    return H3ReadingRecord(**fields)


def _vsn(**overrides: object) -> VsnRecord:
    fields: dict[str, Any] = {
        "kind": "family",
        "name": "price",
        "family": "price",
        "p10": 0.1,
        "p50": 0.2,
        "p90": 0.3,
        "n_decisions": 1505,
        "status": OK,
        "reason": None,
    }
    fields.update(overrides)
    return VsnRecord(**fields)


def _published(**overrides: object) -> ServingGold:
    fields: dict[str, Any] = {
        "published": True,
        "generation_status": "COMPLETED",
        "preregistration_ref": "config/preregistration/aapl_confirmatory-r3.toml",
        "candidate": "tft_quantile",
        "finished_at": "2026-10-21T12:00:00+00:00",
        "conformal_status": AVAILABLE,
        "conformal_reason": None,
        "explainability_status": AVAILABLE,
        "explainability_reason": None,
        "corrections": (_correction(), _correction(tail=UPPER, tail_level=0.9)),
        "shares": (_share(),),
        "reading": _reading(),
        "vsn": (_vsn(),),
        **_LABELS,
    }
    fields.update(overrides)
    return ServingGold(**fields)


# --- ConformalCorrectionRecord ------------------------------------------------------


def test_correction_accepts_ok_tail_and_plus_infinity() -> None:
    record = _correction(correction=math.inf)
    assert record.correction == math.inf


def test_correction_accepts_non_ok_tail_without_correction_or_n() -> None:
    record = _correction(status="undefined", reason="n < 1/alpha", n=None, rank=None)
    assert record.correction is not None  # o valor gravado é aceito; só `ok` o exige
    assert _correction(status="error", reason="x", correction=None, n=None).n is None


def test_correction_refuses_invalid_tail() -> None:
    with pytest.raises(ValueError, match="tail"):
        _correction(tail="middle")


def test_correction_refuses_invalid_status() -> None:
    with pytest.raises(ValueError, match="status"):
        _correction(status="skipped")


def test_correction_refuses_ok_without_correction() -> None:
    with pytest.raises(ValueError, match="correction and n"):
        _correction(correction=None)


def test_correction_refuses_ok_without_n() -> None:
    with pytest.raises(ValueError, match="correction and n"):
        _correction(n=None)


def test_correction_refuses_nan() -> None:
    with pytest.raises(ValueError, match="NaN"):
        _correction(correction=math.nan)


# --- H3ShareRecord, H3ReadingRecord, VsnRecord -------------------------------------


def test_share_accepts_infinite_bounds_and_finite_bounds_when_not_ok() -> None:
    assert _share(lower=-math.inf, upper=math.inf).upper == math.inf
    not_ok = _share(status="undefined", reason="poucos pontos", lower=_FINITE_LOWER, upper=None)
    assert not_ok.lower == _FINITE_LOWER


@pytest.mark.parametrize("bound", ["lower", "upper"])
def test_share_refuses_ok_without_a_bound(bound: str) -> None:
    with pytest.raises(ValueError, match="both interval bounds"):
        _share(**{bound: None})


@pytest.mark.parametrize("field", ["share_h1", "share_h7", "delta", "lower", "upper", "level"])
def test_share_refuses_nan(field: str) -> None:
    with pytest.raises(ValueError, match="NaN"):
        _share(**{field: math.nan})


def test_share_refuses_empty_status() -> None:
    with pytest.raises(ValueError, match="status"):
        _share(status="")


def test_reading_refuses_empty_rule_and_status() -> None:
    with pytest.raises(ValueError, match="reading_rule"):
        _reading(reading_rule="")
    with pytest.raises(ValueError, match="status"):
        _reading(status="")


def test_vsn_accepts_undefined_with_null_measures() -> None:
    record = _vsn(status="undefined", reason="sem pesos", p10=None, p50=None, p90=None)
    assert record.p50 is None


def test_vsn_refuses_nan_and_empty_status() -> None:
    with pytest.raises(ValueError, match="NaN"):
        _vsn(p90=math.nan)
    with pytest.raises(ValueError, match="status"):
        _vsn(status="")


# --- ServingGold ---------------------------------------------------------------------


def test_published_gold_with_both_blocks_is_valid() -> None:
    gold = _published()
    assert gold.corrections[1].tail == UPPER
    assert gold.reading is not None


def test_unpublished_factory_is_valid() -> None:
    gold = ServingGold.unpublished(reason="gold não publicado para o cohort c", **_LABELS)
    assert not gold.published
    assert (gold.conformal_status, gold.explainability_status) == (UNAVAILABLE, UNAVAILABLE)
    assert (
        gold.conformal_reason == gold.explainability_reason == "gold não publicado para o cohort c"
    )
    assert (gold.corrections, gold.shares, gold.reading, gold.vsn) == ((), (), None, ())
    assert (gold.conformal_label, gold.h3_label, gold.vsn_label) == tuple(_LABELS.values())
    assert gold.generation_status is gold.candidate is gold.finished_at is None


def test_unavailable_blocks_on_published_gold_are_valid() -> None:
    gold = _published(
        generation_status="BLOCKED",
        conformal_status=UNAVAILABLE,
        conformal_reason="geração gold BLOCKED",
        corrections=(),
        explainability_status=UNAVAILABLE,
        explainability_reason="geração gold BLOCKED",
        shares=(),
        reading=None,
        vsn=(),
    )
    assert gold.published


@pytest.mark.parametrize("reason", [None, ""])
def test_unavailable_conformal_needs_a_reason(reason: str | None) -> None:
    with pytest.raises(ValueError, match="unavailable conformal block needs a reason"):
        _published(conformal_status=UNAVAILABLE, conformal_reason=reason, corrections=())


def test_unavailable_conformal_carries_no_records() -> None:
    with pytest.raises(ValueError, match="unavailable conformal block carries no records"):
        _published(conformal_status=UNAVAILABLE, conformal_reason="x")


@pytest.mark.parametrize(
    "records",
    [
        {"shares": (_share(),), "reading": None, "vsn": ()},
        {"shares": (), "reading": _reading(), "vsn": ()},
        {"shares": (), "reading": None, "vsn": (_vsn(),)},
    ],
)
def test_unavailable_explainability_carries_no_records(records: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="unavailable explainability block carries no records"):
        _published(explainability_status=UNAVAILABLE, explainability_reason="x", **records)


def test_unavailable_explainability_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="unavailable explainability block needs a reason"):
        _published(
            explainability_status=UNAVAILABLE,
            explainability_reason=None,
            shares=(),
            reading=None,
            vsn=(),
        )


@pytest.mark.parametrize("block", ["conformal", "explainability"])
def test_available_block_carries_no_reason(block: str) -> None:
    with pytest.raises(ValueError, match=f"available {block} block carries no reason"):
        _published(**{f"{block}_reason": "motivo"})


@pytest.mark.parametrize("block", ["conformal", "explainability"])
def test_block_status_outside_the_catalogue_is_refused(block: str) -> None:
    with pytest.raises(ValueError, match=f"{block}_status"):
        _published(**{f"{block}_status": "partial"})


@pytest.mark.parametrize("block", ["conformal", "explainability"])
def test_unpublished_gold_has_no_available_block(block: str) -> None:
    base = ServingGold.unpublished(reason="gold não publicado", **_LABELS)
    with pytest.raises(ValueError, match="unpublished gold has no available block"):
        replace(base, **{f"{block}_status": AVAILABLE, f"{block}_reason": None})


@pytest.mark.parametrize(
    "field", ["generation_status", "preregistration_ref", "candidate", "finished_at"]
)
def test_unpublished_gold_carries_no_generation_fields(field: str) -> None:
    base = ServingGold.unpublished(reason="gold não publicado", **_LABELS)
    with pytest.raises(ValueError, match="unpublished gold carries no generation fields"):
        replace(base, **{field: "x"})


@pytest.mark.parametrize(
    "field", ["generation_status", "preregistration_ref", "candidate", "finished_at"]
)
def test_published_gold_carries_every_generation_field(field: str) -> None:
    with pytest.raises(ValueError, match="published gold carries every generation field"):
        _published(**{field: None})


@pytest.mark.parametrize("label", ["conformal_label", "h3_label", "vsn_label"])
def test_empty_label_is_refused(label: str) -> None:
    with pytest.raises(ValueError, match="labels must not be empty"):
        _published(**{label: ""})
    with pytest.raises(ValueError, match="labels must not be empty"):
        ServingGold.unpublished(reason="gold não publicado", **{**_LABELS, label: ""})


# --- Fake ---------------------------------------------------------------------------


def test_fake_returns_the_loaded_gold_and_records_calls() -> None:
    gold = _published()
    reader = InMemoryServingGoldReader({("AAPL", "c1"): gold})
    assert reader.read(asset="AAPL", cohort_id="c1") is gold
    assert reader.calls == [("AAPL", "c1")]


def test_fake_without_load_raises_key_error() -> None:
    reader = InMemoryServingGoldReader({})
    with pytest.raises(KeyError):
        reader.read(asset="AAPL", cohort_id="c1")
    assert reader.calls == [("AAPL", "c1")]


def test_fake_raises_the_configured_error() -> None:
    error = RuntimeError("geração corrompida")
    reader = InMemoryServingGoldReader({("AAPL", "c1"): _published()}, error=error)
    with pytest.raises(RuntimeError, match="geração corrompida"):
        reader.read(asset="AAPL", cohort_id="c1")
