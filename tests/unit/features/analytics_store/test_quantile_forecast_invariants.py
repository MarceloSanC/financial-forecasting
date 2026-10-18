"""Unit test do VO `QuantileForecast` — grade densa + guardrail monotônico.

Prova (concept 4.3 A4, I5/C3/C4; ADR `4_3_0002`):

- (a) grade desordenada → `guardrail_values` reordenado (`sorted`),
  `guardrail_applied = True`, `raw_values` intactos;
- (b) grade já-monotônica → `guardrail_values == raw_values`, `applied = False`;
- (c) não-finito (`inf`/`nan`) / `None` → valores preservados, `applied = False`;
- (d) caso base triplet p10/p50/p90 reproduz o `enforce_monotonic_triplet` do old;
- (e) construção inválida (`len` divergente, níveis não-crescentes/duplicados,
  níveis fora de `(0, 1)`) → `ValueError`;
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
@pytest.mark.parametrize(
    "bad_levels",
    [
        (0.0, 0.5, 0.9),  # borda inferior inclusiva (0 não é quantil interior)
        (0.1, 0.5, 1.0),  # borda superior inclusiva
        (0.1, 0.5, 1.5),  # acima de 1
        (-0.1, 0.5, 0.9),  # negativo
        (0.1, math.nan, 0.9),  # nan não é comparável → rejeitado
    ],
)
def test_levels_outside_open_unit_interval_raise_value_error(
    bad_levels: tuple[float, ...],
) -> None:
    """#64: nível fora de `(0, 1)` → ValueError (entra na PK de `fact_oos_predictions`)."""
    with pytest.raises(ValueError, match=r"in \(0, 1\)"):
        QuantileForecast.from_raw(levels=bad_levels, raw_values=(0.1, 0.5, 0.9))


@pytest.mark.unit
def test_levels_just_inside_open_unit_interval_are_accepted() -> None:
    """#64: níveis colados nas bordas, mas interiores, passam (faixa é aberta, não fechada)."""
    levels = (1e-9, 0.5, 1.0 - 1e-9)
    forecast = QuantileForecast.from_raw(levels=levels, raw_values=(0.1, 0.5, 0.9))
    assert forecast.levels == levels


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


# -- construtor cru (issue #160): a forma da grade vale fora do `from_raw` -----------


def _direct(**overrides: object) -> QuantileForecast:
    fields: dict[str, object] = {
        "levels": _TRIPLET_LEVELS,
        "raw_values": (0.2, 0.1, 0.3),
        "guardrail_values": (0.1, 0.2, 0.3),
        "guardrail_applied": True,
    }
    fields.update(overrides)
    return QuantileForecast(**fields)  # type: ignore[arg-type]


@pytest.mark.unit
def test_direct_constructor_keeps_persisted_values_untouched() -> None:
    """I6 (6.4): o caminho cru não recomputa o guardrail — guarda o que foi persistido.

    Inclusive um `guardrail_values` cruzado ou com não-finito: ordem e finitude do
    vetor pontuado são da `CoverageSeries`, não da forma do VO.
    """
    forecast = _direct(guardrail_values=(0.3, 0.1, math.nan), guardrail_applied=False)

    assert forecast.raw_values == (0.2, 0.1, 0.3)
    assert forecast.guardrail_values[:2] == (0.3, 0.1)
    assert forecast.guardrail_applied is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"raw_values": (0.1, 0.2)}, "levels and raw_values must align", id="raw"),
        pytest.param(
            {"guardrail_values": (0.1, 0.2, 0.3, 0.4)},
            "levels and guardrail_values must align",
            id="guardrail",
        ),
        pytest.param(
            {"levels": (), "raw_values": (), "guardrail_values": ()},
            "non-empty",
            id="empty",
        ),
        pytest.param({"levels": (0.0, 0.5, 0.9)}, r"in \(0, 1\)", id="closed-bound"),
        pytest.param({"levels": (0.1, math.nan, 0.9)}, r"in \(0, 1\)", id="nan-level"),
        pytest.param({"levels": (0.9, 0.5, 0.1)}, "strictly increasing", id="decreasing"),
        pytest.param({"levels": (0.1, 0.1, 0.9)}, "strictly increasing", id="duplicate"),
        pytest.param({"guardrail_applied": 1}, "guardrail_applied must be a bool", id="int"),
        pytest.param({"guardrail_applied": None}, "guardrail_applied must be a bool", id="none"),
    ],
)
def test_direct_constructor_rejects_malformed_grid(
    overrides: dict[str, object], message: str
) -> None:
    """#160: `QuantileForecast(...)` cru recusa o que o `from_raw` recusaria."""
    with pytest.raises(ValueError, match=message):
        _direct(**overrides)
