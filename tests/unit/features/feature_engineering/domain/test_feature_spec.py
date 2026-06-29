"""Unit tests do value-object `FeatureSpec` (Stage 3.4 Task 01).

Cobre (concept 3.4 §6 C1-C5, §11 A1):

- happy path: spec válido constrói; defaults; frozen.
- C1: `name` vazio → `ValueError`.
- C2: `warmup_count < 0` → `ValueError`.
- C3: `family` fora de `{price, technical, sentiment, fundamental}` → `ValueError`.
- C4: `anti_leakage_tag` fora do vocabulário fixo → `ValueError` (espinha do DoD).
- C5: `tft_typing` fora de `{known, unknown}` → `ValueError`.

Domínio puro — importa SÓ stdlib + o módulo de domínio (sem pandas/numpy).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.feature_engineering.domain.value_objects.feature_spec import (
    FeatureSpec,
)

_VALID_WARMUP = 5


def _valid_spec(**overrides: object) -> FeatureSpec:
    """Constrói um `FeatureSpec` válido, permitindo sobrescrever campos pontuais."""
    kwargs: dict[str, object] = {
        "name": "log_return_5d",
        "family": "price",
        "source_cols": ("close",),
        "formula_desc": "log(close_t / close_t-5)",
        "anti_leakage_tag": "trailing_window_causal",
        "warmup_count": _VALID_WARMUP,
        "tft_typing": "unknown",
    }
    kwargs.update(overrides)
    return FeatureSpec(**kwargs)  # type: ignore[arg-type]


# =============================================================================
# A1 — happy path / defaults / frozen
# =============================================================================


@pytest.mark.unit
def test_valid_feature_spec_constructs_with_defaults() -> None:
    """Um `FeatureSpec` válido constrói; defaults de null_policy/dtype/enabled."""
    spec = _valid_spec()
    assert spec.name == "log_return_5d"
    assert spec.family == "price"
    assert spec.warmup_count == _VALID_WARMUP
    assert spec.tft_typing == "unknown"
    assert spec.null_policy == "allow"
    assert spec.dtype == "float64"
    assert spec.enabled_by_default is True


@pytest.mark.unit
def test_feature_spec_is_frozen() -> None:
    """Atribuir um campo de um `FeatureSpec` levanta `FrozenInstanceError` (A1)."""
    spec = _valid_spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.warmup_count = 99  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize("family", sorted({"price", "technical", "sentiment", "fundamental"}))
def test_all_four_families_are_accepted(family: str) -> None:
    """As 4 famílias do vocabulário são aceitas (I4)."""
    spec = _valid_spec(family=family)
    assert spec.family == family


@pytest.mark.unit
@pytest.mark.parametrize("tft_typing", ["known", "unknown"])
def test_both_tft_typings_are_accepted(tft_typing: str) -> None:
    """`tft_typing` aceita known e unknown (I3)."""
    spec = _valid_spec(tft_typing=tft_typing)
    assert spec.tft_typing == tft_typing


# =============================================================================
# C1-C5 - invariantes de construção
# =============================================================================


@pytest.mark.unit
def test_empty_name_raises() -> None:
    """C1 — `name` vazio → `ValueError`."""
    with pytest.raises(ValueError, match="non-empty"):
        _valid_spec(name="")


@pytest.mark.unit
def test_negative_warmup_raises() -> None:
    """C2 — `warmup_count < 0` → `ValueError`."""
    with pytest.raises(ValueError, match="warmup_count must be >= 0"):
        _valid_spec(warmup_count=-1)


@pytest.mark.unit
def test_invalid_family_raises() -> None:
    """C3 — `family` fora do set de 4 → `ValueError`."""
    with pytest.raises(ValueError, match="family must be one of"):
        _valid_spec(family="baseline")


@pytest.mark.unit
def test_invalid_anti_leakage_tag_raises() -> None:
    """C4 — `anti_leakage_tag` fora do vocabulário fixo → `ValueError`."""
    with pytest.raises(ValueError, match="anti_leakage_tag must be one of"):
        _valid_spec(anti_leakage_tag="lookahead_ok")


@pytest.mark.unit
def test_invalid_tft_typing_raises() -> None:
    """C5 — `tft_typing` fora de `{known, unknown}` → `ValueError`."""
    with pytest.raises(ValueError, match="tft_typing must be one of"):
        _valid_spec(tft_typing="static")
