"""Unit tests do domínio `IndicatorSpec` + `INDICATOR_SPECS` + `indicator_registry_hash`.

Cobre (concept 3.1 A2/A3, technical Task 01):

- C1: `IndicatorSpec` válido + cada violação de invariante → `ValueError`.
- `INDICATOR_SPECS`: exatamente os 11 com warmups/tags/dtype/source_cols exatos.
- I10: `indicator_registry_hash()` determinístico e sensível a perturbação de spec.

Domínio puro — o teste importa SÓ stdlib + o módulo de domínio (sem pandas/numpy).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.feature_engineering.domain.services.indicator_spec import (
    INDICATOR_SPECS,
    IndicatorSpec,
    indicator_registry_hash,
)

# -- forma esperada do registry (concept 3.1 §4) --------------------------------
# name -> (family, source_cols, warmup, anti_leakage_tag)
_EXPECTED: dict[str, tuple[str, tuple[str, ...], int, str]] = {
    "rsi_14": ("momentum", ("close",), 14, "trailing_window_causal"),
    "macd": ("trend", ("close",), 26, "trailing_window_causal"),
    "macd_signal": ("trend", ("close",), 35, "trailing_window_causal"),
    "ema_10": ("trend", ("close",), 10, "trailing_window_causal"),
    "ema_50": ("trend", ("close",), 50, "trailing_window_causal"),
    "ema_100": ("trend", ("close",), 100, "trailing_window_causal"),
    "ema_200": ("trend", ("close",), 200, "trailing_window_causal"),
    "volatility_20d": ("volatility", ("close",), 20, "trailing_window_causal"),
    "candle_range": ("ohlc_derived", ("high", "low"), 0, "same_timestamp_ohlc_derived"),
    "candle_body": ("ohlc_derived", ("open", "close"), 0, "same_timestamp_ohlc_derived"),
}
# 10 COLUNAS/chaves produzidas (= o set `TECHNICAL_INDICATORS` do old, H-2 EXATO).
# O concept fala em "11 indicadores", mas a §4 nota esclarece: são 10 nomes de
# coluna; o "11º" é o par macd/macd_signal contado como UMA chamada `ta.macd`.
# A autoridade H-2 é o set do old (10 entradas). Ver [decision] no technical §7.
_EXPECTED_COUNT = 10
_RSI_WARMUP = 14
_SHA256_HEXLEN = 64


# =============================================================================
# C1 — invariantes de construção do IndicatorSpec
# =============================================================================


@pytest.mark.unit
def test_valid_indicator_spec_constructs() -> None:
    """Um `IndicatorSpec` válido constrói com `dtype` default `float32` (frozen)."""
    spec = IndicatorSpec(
        name="rsi_14",
        family="momentum",
        source_cols=("close",),
        warmup=14,
        anti_leakage_tag="trailing_window_causal",
    )
    assert spec.dtype == "float32"
    assert spec.warmup == _RSI_WARMUP
    # frozen: atribuição levanta erro
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.warmup = 99  # type: ignore[misc]


@pytest.mark.unit
def test_empty_name_raises() -> None:
    """`name` vazio → `ValueError` (C1)."""
    with pytest.raises(ValueError, match="non-empty"):
        IndicatorSpec(
            name="",
            family="trend",
            source_cols=("close",),
            warmup=0,
            anti_leakage_tag="trailing_window_causal",
        )


@pytest.mark.unit
def test_negative_warmup_raises() -> None:
    """`warmup < 0` → `ValueError` (C1)."""
    with pytest.raises(ValueError, match="warmup must be >= 0"):
        IndicatorSpec(
            name="ema_10",
            family="trend",
            source_cols=("close",),
            warmup=-1,
            anti_leakage_tag="trailing_window_causal",
        )


@pytest.mark.unit
def test_invalid_dtype_raises() -> None:
    """`dtype` fora de `{'float32'}` → `ValueError` (C1)."""
    with pytest.raises(ValueError, match="dtype must be one of"):
        IndicatorSpec(
            name="ema_10",
            family="trend",
            source_cols=("close",),
            warmup=10,
            anti_leakage_tag="trailing_window_causal",
            dtype="float64",
        )


@pytest.mark.unit
def test_invalid_anti_leakage_tag_raises() -> None:
    """`anti_leakage_tag` fora do conjunto permitido → `ValueError` (C1)."""
    with pytest.raises(ValueError, match="anti_leakage_tag must be one of"):
        IndicatorSpec(
            name="ema_10",
            family="trend",
            source_cols=("close",),
            warmup=10,
            anti_leakage_tag="lookahead_ok",
        )


# =============================================================================
# INDICATOR_SPECS — registry estático dos 11 (H-2)
# =============================================================================


@pytest.mark.unit
def test_registry_has_exactly_expected_keys() -> None:
    """O registry tem EXATAMENTE os nomes do set `TECHNICAL_INDICATORS` do old (H-2)."""
    assert len(INDICATOR_SPECS) == _EXPECTED_COUNT
    assert set(INDICATOR_SPECS.keys()) == set(_EXPECTED)


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_each_spec_matches_expected_shape(name: str) -> None:
    """Cada spec tem family/source_cols/warmup/tag exatos e `dtype='float32'`."""
    family, source_cols, warmup, tag = _EXPECTED[name]
    spec = INDICATOR_SPECS[name]
    assert spec.name == name
    assert spec.family == family
    assert spec.source_cols == source_cols
    assert spec.warmup == warmup
    assert spec.anti_leakage_tag == tag
    assert spec.dtype == "float32"


@pytest.mark.unit
def test_registry_key_matches_spec_name() -> None:
    """A chave do registry é sempre igual ao `name` do spec (consistência)."""
    for key, spec in INDICATOR_SPECS.items():
        assert key == spec.name


# =============================================================================
# I10 — indicator_registry_hash determinístico e sensível a perturbação
# =============================================================================


@pytest.mark.unit
def test_registry_hash_is_deterministic() -> None:
    """Duas chamadas sobre o mesmo registry → mesmo hash (I10)."""
    assert indicator_registry_hash() == indicator_registry_hash()
    assert indicator_registry_hash() == indicator_registry_hash(INDICATOR_SPECS)


@pytest.mark.unit
def test_registry_hash_is_sha256_hexdigest() -> None:
    """O hash é um hexdigest sha256 (64 chars hex)."""
    digest = indicator_registry_hash()
    assert len(digest) == _SHA256_HEXLEN
    assert all(c in "0123456789abcdef" for c in digest)


@pytest.mark.unit
def test_registry_hash_changes_when_warmup_changes() -> None:
    """Perturbar o `warmup` de um spec MUDA o hash (I10)."""
    perturbed = dict(INDICATOR_SPECS)
    original = perturbed["ema_10"]
    perturbed["ema_10"] = dataclasses.replace(original, warmup=11)
    assert indicator_registry_hash(perturbed) != indicator_registry_hash()


@pytest.mark.unit
def test_registry_hash_changes_when_tag_changes() -> None:
    """Perturbar a `anti_leakage_tag` de um spec MUDA o hash (I10)."""
    perturbed = dict(INDICATOR_SPECS)
    perturbed["candle_range"] = dataclasses.replace(
        perturbed["candle_range"], anti_leakage_tag="trailing_window_causal"
    )
    assert indicator_registry_hash(perturbed) != indicator_registry_hash()
