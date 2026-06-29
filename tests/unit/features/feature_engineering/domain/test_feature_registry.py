"""Unit tests do domain service `FeatureRegistry` (Stage 3.4 Tasks 02-03, 07).

Cobre (concept 3.4 §11 A2/A3/A4/A7):

- A2: `FEATURE_SPECS` imutável (MappingProxyType), chave == name, construção não
  levanta (toda feature base tem contrato).
- getters: `get_feature_spec`/`list_feature_specs(family=...)`.
- A4/I5: `feature_set_hash` estável, independente da ordem de inserção, e sensível
  a perturbação de qualquer campo de qualquer spec.
- A3/I2: feature sem tag/tft_typing válido é rejeitada pelo VO (logo o registry não
  pode contê-la).

Domínio puro — importa SÓ stdlib + os módulos de domínio (sem pandas/numpy).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    FEATURE_SPECS,
    feature_set_hash,
    get_feature_spec,
    list_feature_specs,
)
from financial_forecasting.features.feature_engineering.domain.value_objects.feature_spec import (
    FeatureSpec,
)

_ALLOWED_FAMILIES = {"price", "technical", "sentiment", "fundamental"}
_ALLOWED_TFT = {"known", "unknown"}
_SHA256_HEXLEN = 64

# Features base esperadas (Task 02), name -> family.
_EXPECTED_BASE: dict[str, str] = {
    "open": "price",
    "high": "price",
    "low": "price",
    "close": "price",
    "volume": "price",
    "rsi_14": "technical",
    "macd": "technical",
    "macd_signal": "technical",
    "ema_10": "technical",
    "ema_50": "technical",
    "ema_100": "technical",
    "ema_200": "technical",
    "volatility_20d": "technical",
    "candle_range": "technical",
    "candle_body": "technical",
    "sentiment_score": "sentiment",
    "news_volume": "sentiment",
    "sentiment_std": "sentiment",
    "has_news": "sentiment",
    "revenue": "fundamental",
    "net_income": "fundamental",
    "operating_cash_flow": "fundamental",
    "total_shareholder_equity": "fundamental",
    "total_liabilities": "fundamental",
}


# =============================================================================
# A2 — FEATURE_SPECS imutável, consistente, cobre as features base
# =============================================================================


@pytest.mark.unit
def test_registry_is_read_only_mapping_proxy() -> None:
    """`FEATURE_SPECS` é um MappingProxyType: mutação levanta `TypeError` (A2)."""
    with pytest.raises(TypeError):
        FEATURE_SPECS["close"] = get_feature_spec("open")  # type: ignore[index]


@pytest.mark.unit
def test_registry_key_matches_spec_name() -> None:
    """A chave do registry é sempre igual ao `name` do spec (consistência)."""
    for key, spec in FEATURE_SPECS.items():
        assert key == spec.name


@pytest.mark.unit
def test_registry_includes_all_base_features() -> None:
    """O registry contém todas as features base com a família esperada (A2)."""
    for name, family in _EXPECTED_BASE.items():
        assert name in FEATURE_SPECS, name
        assert FEATURE_SPECS[name].family == family


@pytest.mark.unit
def test_every_spec_has_valid_family_and_tft_typing() -> None:
    """Toda spec tem family no set de 4 e tft_typing em {known,unknown} (A2/A7)."""
    for spec in FEATURE_SPECS.values():
        assert spec.family in _ALLOWED_FAMILIES
        assert spec.tft_typing in _ALLOWED_TFT


@pytest.mark.unit
def test_has_news_is_int64() -> None:
    """`has_news` é flag inteira (dtype int64), espelhando o old (A2)."""
    assert get_feature_spec("has_news").dtype == "int64"


# =============================================================================
# getters
# =============================================================================


@pytest.mark.unit
def test_get_feature_spec_returns_spec() -> None:
    """`get_feature_spec` devolve o spec pela chave."""
    spec = get_feature_spec("close")
    assert spec.name == "close"
    assert spec.family == "price"


@pytest.mark.unit
def test_get_feature_spec_missing_raises_key_error() -> None:
    """`get_feature_spec` de nome ausente levanta KeyError (análogo ao old)."""
    with pytest.raises(KeyError):
        get_feature_spec("does_not_exist")


@pytest.mark.unit
def test_list_feature_specs_filters_by_family() -> None:
    """`list_feature_specs(family=...)` filtra pela família."""
    price = list_feature_specs(family="price")
    assert price
    assert all(s.family == "price" for s in price)
    assert {s.name for s in price} >= {"open", "high", "low", "close", "volume"}


@pytest.mark.unit
def test_list_feature_specs_without_filter_returns_all() -> None:
    """`list_feature_specs()` sem filtro devolve todas as specs."""
    assert len(list_feature_specs()) == len(FEATURE_SPECS)


@pytest.mark.unit
def test_list_feature_specs_enabled_only() -> None:
    """`enabled_only=True` devolve só specs habilitadas (todas, por default)."""
    enabled = list_feature_specs(enabled_only=True)
    assert all(s.enabled_by_default for s in enabled)
    assert len(enabled) == len(FEATURE_SPECS)


# =============================================================================
# A4 / I5 — feature_set_hash determinístico e sensível
# =============================================================================


@pytest.mark.unit
def test_hash_is_deterministic() -> None:
    """Mesmo set → mesmo hash (A4)."""
    assert feature_set_hash() == feature_set_hash()
    assert feature_set_hash() == feature_set_hash(FEATURE_SPECS)


@pytest.mark.unit
def test_hash_is_sha256_hexdigest() -> None:
    """O hash é um hexdigest sha256 (64 chars hex)."""
    digest = feature_set_hash()
    assert len(digest) == _SHA256_HEXLEN
    assert all(c in "0123456789abcdef" for c in digest)


@pytest.mark.unit
def test_hash_is_independent_of_insertion_order() -> None:
    """Reordenar a inserção dos specs NÃO muda o hash (ordenação por nome — I5)."""
    reordered = dict(reversed(list(FEATURE_SPECS.items())))
    assert feature_set_hash(reordered) == feature_set_hash()


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    [
        "family",
        "source_cols",
        "formula_desc",
        "anti_leakage_tag",
        "warmup_count",
        "tft_typing",
        "null_policy",
        "dtype",
        "enabled_by_default",
    ],
)
def test_hash_changes_when_any_field_perturbed(field: str) -> None:
    """Perturbar QUALQUER campo de um spec MUDA o hash (A4/I5).

    Loop sobre os campos: fecha o buraco de mutação (dropar um campo da string
    canônica passaria batido sem este teste paramétrico).
    """
    perturbed = dict(FEATURE_SPECS)
    original = perturbed["close"]
    new_values: dict[str, object] = {
        "family": "technical",
        "source_cols": ("open",),
        "formula_desc": "perturbed description",
        "anti_leakage_tag": "trailing_window_causal",
        "warmup_count": 99,
        "tft_typing": "known",
        "null_policy": "drop",
        "dtype": "float32",
        "enabled_by_default": False,
    }
    perturbed["close"] = dataclasses.replace(
        original,
        **{field: new_values[field]},  # type: ignore[arg-type]
    )
    assert feature_set_hash(perturbed) != feature_set_hash()


# =============================================================================
# A3 / I2 — feature sem contrato de causalidade é rejeitada
# =============================================================================


@pytest.mark.unit
def test_registry_has_no_spec_outside_the_contract() -> None:
    """Nenhuma spec do registry tem tag/tft_typing fora do contrato (A3/I2)."""
    allowed_tags = {
        "point_in_time_ohlcv",
        "same_timestamp_ohlc_derived",
        "trailing_window_causal",
        "lagged_causal",
        "publication_cutoff_asof",
        "reported_date_asof",
    }
    for spec in FEATURE_SPECS.values():
        assert spec.anti_leakage_tag in allowed_tags
        assert spec.tft_typing in _ALLOWED_TFT


@pytest.mark.unit
def test_spec_without_valid_tag_is_rejected() -> None:
    """Construir uma `FeatureSpec` sem tag válida levanta `ValueError` (A3/I2)."""
    with pytest.raises(ValueError, match="anti_leakage_tag must be one of"):
        FeatureSpec(
            name="bogus",
            family="price",
            source_cols=("close",),
            formula_desc="no contract",
            anti_leakage_tag="lookahead_ok",
            warmup_count=0,
            tft_typing="unknown",
        )


@pytest.mark.unit
def test_spec_without_valid_tft_typing_is_rejected() -> None:
    """Construir uma `FeatureSpec` sem tft_typing válido levanta `ValueError` (A3/I2)."""
    with pytest.raises(ValueError, match="tft_typing must be one of"):
        FeatureSpec(
            name="bogus",
            family="price",
            source_cols=("close",),
            formula_desc="no typing",
            anti_leakage_tag="trailing_window_causal",
            warmup_count=0,
            tft_typing="static",
        )


# =============================================================================
# Task 03 — specs das ~38 derivadas (metadados verbatim do old)
# =============================================================================

# Derivadas esperadas, name -> (family, warmup_count, dtype).
_EXPECTED_DERIVED: dict[str, tuple[str, int, str]] = {
    "log_return_1d": ("price", 1, "float64"),
    "log_return_5d": ("price", 5, "float64"),
    "log_return_21d": ("price", 21, "float64"),
    "momentum_5d": ("price", 5, "float64"),
    "momentum_21d": ("price", 21, "float64"),
    "momentum_63d": ("price", 63, "float64"),
    "reversal_1d": ("price", 1, "float64"),
    "reversal_5d": ("price", 5, "float64"),
    "drawdown_lookback": ("price", 63, "float64"),
    "amihud_illiquidity_proxy": ("price", 1, "float64"),
    "volume_zscore": ("price", 20, "float64"),
    "volume_spike_flag": ("price", 20, "int64"),
    "volatility_parkinson": ("technical", 20, "float64"),
    "volatility_garman_klass": ("technical", 20, "float64"),
    "downside_semivolatility": ("technical", 20, "float64"),
    "vol_of_vol": ("technical", 40, "float64"),
    "volatility_regime": ("technical", 63, "int64"),
    "trend_regime": ("technical", 63, "int64"),
    "stress_tail_return_flag": ("technical", 63, "int64"),
    "sentiment_lag_1": ("sentiment", 1, "float64"),
    "sentiment_lag_3": ("sentiment", 3, "float64"),
    "sentiment_lag_5": ("sentiment", 5, "float64"),
    "sentiment_ema": ("sentiment", 1, "float64"),
    "sentiment_surprise": ("sentiment", 5, "float64"),
    "sentiment_x_volatility": ("sentiment", 20, "float64"),
    "sentiment_x_volume": ("sentiment", 0, "float64"),
    "net_margin": ("fundamental", 0, "float64"),
    "leverage_ratio": ("fundamental", 0, "float64"),
    "cashflow_efficiency": ("fundamental", 0, "float64"),
    "revenue_yoy_growth": ("fundamental", 252, "float64"),
    "net_income_yoy_growth": ("fundamental", 252, "float64"),
}

# Total = 24 base + 31 derivadas.
_EXPECTED_TOTAL = len(_EXPECTED_BASE) + len(_EXPECTED_DERIVED)


@pytest.mark.unit
def test_registry_covers_all_features_base_and_derived() -> None:
    """`FEATURE_SPECS` cobre as features base + todas as derivadas (A2)."""
    assert set(FEATURE_SPECS) == set(_EXPECTED_BASE) | set(_EXPECTED_DERIVED)
    assert len(FEATURE_SPECS) == _EXPECTED_TOTAL


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_EXPECTED_DERIVED))
def test_each_derived_spec_matches_family_warmup_dtype(name: str) -> None:
    """Cada derivada tem family/warmup/dtype verbatim do old (A2/A5/I7)."""
    family, warmup, dtype = _EXPECTED_DERIVED[name]
    spec = FEATURE_SPECS[name]
    assert spec.family == family
    assert spec.warmup_count == warmup
    assert spec.dtype == dtype


@pytest.mark.unit
def test_yoy_features_are_fundamental_with_warmup_252() -> None:
    """`*_yoy_growth` estão na família fundamental com warmup 252 (A5/I7)."""
    yoy = list_feature_specs(family="fundamental")
    names = {s.name for s in yoy}
    assert {"revenue_yoy_growth", "net_income_yoy_growth"} <= names
    for name in ("revenue_yoy_growth", "net_income_yoy_growth"):
        assert get_feature_spec(name).warmup_count == 252  # noqa: PLR2004


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    ["volume_spike_flag", "volatility_regime", "trend_regime", "stress_tail_return_flag"],
)
def test_flags_and_regimes_are_int64(name: str) -> None:
    """Flags e regimes têm dtype int64 (A2)."""
    assert get_feature_spec(name).dtype == "int64"


@pytest.mark.unit
@pytest.mark.parametrize("name", ["sentiment_lag_1", "sentiment_lag_3", "sentiment_lag_5"])
def test_sentiment_lags_are_tagged_lagged_causal(name: str) -> None:
    """`sentiment_lag_*` (puro shift) usa a tag `lagged_causal` (decision §7)."""
    assert get_feature_spec(name).anti_leakage_tag == "lagged_causal"


@pytest.mark.unit
def test_vol_of_vol_effective_warmup_is_40() -> None:
    """`vol_of_vol` tem warmup efetivo 40 = 20 (volatility_20d) + 20 (std) (I7)."""
    assert get_feature_spec("vol_of_vol").warmup_count == 40  # noqa: PLR2004


# Snapshot ancorado do hash do registry completo (base + 31 derivadas). Canário
# contra mudança acidental: alterar QUALQUER spec muda este valor. Atualizar
# conscientemente ao mudar o registry de propósito (regenerar via feature_set_hash()).
_REGISTRY_HASH_SNAPSHOT = "bb34d43689fb570d7de5cf2b62735fe1477fa3bb3b906db93239510f9026884b"


@pytest.mark.unit
def test_hash_is_stable_snapshot() -> None:
    """`feature_set_hash` bate com o snapshot ancorado e é estável (I5).

    Serve de canário: qualquer alteração de spec (campo, derivada nova) muda o
    digest e este teste fica vermelho, forçando atualização consciente.
    """
    digest = feature_set_hash()
    assert digest == feature_set_hash()
    assert digest == _REGISTRY_HASH_SNAPSHOT
