"""Unit test do VO `QuantileForecast` — grade densa + guardrail monotônico.

Prova (concept 4.3 A4, I5/C3/C4; ADR `4_3_0002`):

- (a) grade desordenada → `guardrail_values` reordenado (`sorted`),
  `guardrail_applied = True`, `raw_values` intactos;
- (b) grade já-monotônica → `guardrail_values == raw_values`, `applied = False`;
- (c) não-finito (`inf`/`nan`) / `None` → valores preservados, `applied = False`;
- (d) caso base triplet p10/p50/p90 reproduz o `enforce_monotonic_triplet` do old;
- (e) construção inválida (`len` divergente, níveis não-crescentes/duplicados)
  → `ValueError`;
- separação do gate de degeneração (`q_low == q_high` passa intacto).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)

_DENSE_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
_TRIPLET_LEVELS = (0.1, 0.5, 0.9)
_FIRST = 0.3
_SECOND = 0.1


@pytest.mark.unit
def test_disordered_grid_is_reordered_and_flagged() -> None:
    """A4 (a): grade desordenada → guardrail ordena, applied=True, raw intacto."""
    raw = (0.3, 0.1, 0.5, 0.2, 0.9)
    forecast = QuantileForecast.from_raw(levels=_DENSE_LEVELS, raw_values=raw)

    assert forecast.raw_values == raw  # raw preservado
    assert forecast.guardrail_values == (0.1, 0.2, 0.3, 0.5, 0.9)
    assert forecast.guardrail_applied is True
    assert forecast.levels == _DENSE_LEVELS


@pytest.mark.unit
def test_already_monotone_grid_is_unchanged() -> None:
    """A4 (b): grade já não-decrescente → guardrail_values == raw, applied=False."""
    raw = (-0.05, -0.01, 0.0, 0.02, 0.07)
    forecast = QuantileForecast.from_raw(levels=_DENSE_LEVELS, raw_values=raw)

    assert forecast.guardrail_values == raw
    assert forecast.guardrail_applied is False


@pytest.mark.unit
def test_equal_quantiles_pass_through_without_flag() -> None:
    """I5: gate de degeneração é SEPARADO — `q_low == q_high` passa intacto (Step 6)."""
    raw = (0.5, 0.5, 0.5, 0.5, 0.5)
    forecast = QuantileForecast.from_raw(levels=_DENSE_LEVELS, raw_values=raw)

    # `sorted` de iguais == os mesmos valores → applied=False; nada é "consertado".
    assert forecast.guardrail_values == raw
    assert forecast.guardrail_applied is False


@pytest.mark.unit
@pytest.mark.parametrize("bad_value", [math.inf, -math.inf, math.nan])
def test_non_finite_value_is_preserved_without_guardrail(bad_value: float) -> None:
    """A4 (c): inf/nan → valores preservados, applied=False (postura defensiva)."""
    raw = (0.3, 0.1, bad_value, 0.2, 0.9)
    forecast = QuantileForecast.from_raw(levels=_DENSE_LEVELS, raw_values=raw)

    assert forecast.guardrail_applied is False
    # Preserva a ordem original (não reordena), inclusive o valor não-finito.
    assert forecast.guardrail_values[0] == _FIRST
    assert forecast.guardrail_values[1] == _SECOND
    if math.isnan(bad_value):
        assert math.isnan(forecast.guardrail_values[2])
    else:
        assert forecast.guardrail_values[2] == bad_value


@pytest.mark.unit
def test_none_value_is_preserved_without_guardrail() -> None:
    """A4 (c): `None` na grade → valores preservados, applied=False (defensivo)."""
    raw = (0.3, None, 0.5, 0.2, 0.9)
    forecast = QuantileForecast.from_raw(
        levels=_DENSE_LEVELS,
        raw_values=raw,  # type: ignore[arg-type]
    )

    assert forecast.guardrail_applied is False
    assert forecast.guardrail_values == raw  # ordem original preservada com o None


@pytest.mark.unit
def test_triplet_base_case_reproduces_old_enforce_monotonic() -> None:
    """A4 (d): triplet p10/p50/p90 reproduz `enforce_monotonic_triplet` do old."""
    # Desordenado (p10 > p50): old ordenava e marcava applied=True.
    disordered = QuantileForecast.from_raw(levels=_TRIPLET_LEVELS, raw_values=(0.9, 0.1, 0.5))
    assert disordered.guardrail_values == (0.1, 0.5, 0.9)
    assert disordered.guardrail_applied is True

    # Já-monotônico: applied=False, valores intactos.
    ordered = QuantileForecast.from_raw(levels=_TRIPLET_LEVELS, raw_values=(0.1, 0.5, 0.9))
    assert ordered.guardrail_values == (0.1, 0.5, 0.9)
    assert ordered.guardrail_applied is False


@pytest.mark.unit
def test_length_mismatch_raises_value_error() -> None:
    """A4 (e)/C3: `len(levels) != len(raw_values)` → ValueError."""
    with pytest.raises(ValueError, match="must align"):
        QuantileForecast.from_raw(levels=_TRIPLET_LEVELS, raw_values=(0.1, 0.5))


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_levels",
    [
        (0.5, 0.1, 0.9),  # não-crescente
        (0.1, 0.5, 0.5),  # duplicata
        (0.9, 0.5, 0.1),  # decrescente
    ],
)
def test_non_increasing_or_duplicate_levels_raise_value_error(
    bad_levels: tuple[float, ...],
) -> None:
    """A4 (e)/C3: níveis não estritamente crescentes / duplicados → ValueError."""
    with pytest.raises(ValueError, match="strictly increasing"):
        QuantileForecast.from_raw(levels=bad_levels, raw_values=(0.1, 0.5, 0.9))


@pytest.mark.unit
def test_empty_levels_raise_value_error() -> None:
    """C3: grade vazia → ValueError (não há quantil a persistir)."""
    with pytest.raises(ValueError, match="non-empty"):
        QuantileForecast.from_raw(levels=(), raw_values=())


@pytest.mark.unit
def test_vo_is_frozen() -> None:
    """I8: o VO é frozen — reatribuir um campo levanta FrozenInstanceError."""
    forecast = QuantileForecast.from_raw(levels=_TRIPLET_LEVELS, raw_values=(0.1, 0.5, 0.9))
    with pytest.raises(dataclasses.FrozenInstanceError):
        forecast.guardrail_applied = True  # type: ignore[misc]


@pytest.mark.unit
def test_bool_values_are_treated_as_non_finite_and_preserved() -> None:
    """C4: `bool` (subclasse de int) não é quantil legítimo → preserva, applied=False."""
    raw = (0.3, True, 0.5, 0.2, 0.9)
    forecast = QuantileForecast.from_raw(
        levels=_DENSE_LEVELS,
        raw_values=raw,  # type: ignore[arg-type]
    )
    assert forecast.guardrail_applied is False
    assert forecast.guardrail_values == raw
