"""Unit test do kernel `chi_square_sf` e do piso numérico `floor_lr_statistic`.

Prova (concept 6.3 A3, I7, I13, C3; ADR 6.3.0001 item 8): a sobrevivência em forma
fechada acerta os valores críticos de 5 % de χ²(1) e χ²(2) (medidos no technical §1),
vale 1 em x = 0, o piso leva `[-1e-9, 0)` a 0 e ergue abaixo, e df/estatística
inválidos erguem. Fixture analítica (ADR 0.0.0021): sem oráculo de biblioteca.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.chi_square import (
    LR_NEGATIVE_FLOOR,
    chi_square_sf,
    floor_lr_statistic,
)

# Tolerância declarada (ADR 0.0.0021): identidade de float64.
_ABS_TOL = 1e-12
_FIVE_PERCENT = 0.05
# Valores críticos de 5 % (technical 6.3 §1, medidos em float64).
_CHI2_1_CRITICAL = 3.841458820694124
_CHI2_2_CRITICAL = 5.991464547107979
_TINY_NEGATIVE = -1e-14
_BELOW_FLOOR = -2e-9
# I13 / ADR 6.3.0001 item 8: o valor do piso fixado pelo contrato.
_CONTRACT_FLOOR = -1e-9


@pytest.mark.unit
@pytest.mark.parametrize(
    ("statistic", "df"),
    [(_CHI2_1_CRITICAL, 1), (_CHI2_2_CRITICAL, 2)],
    ids=["df1", "df2"],
)
def test_chi2_critical_value_gives_five_percent(statistic: float, df: int) -> None:
    """A3/I7: o valor crítico de 5 % devolve 0.05 (±1e-12) pela forma fechada."""
    assert abs(chi_square_sf(statistic, df=df) - _FIVE_PERCENT) <= _ABS_TOL


@pytest.mark.unit
@pytest.mark.parametrize("df", [1, 2])
def test_chi2_critical_zero_statistic_has_unit_survival(df: int) -> None:
    """A3: x = 0 → P(χ² > 0) = 1 nos dois df."""
    assert chi_square_sf(0.0, df=df) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize("df", [1, 2])
def test_chi2_floor_tiny_negative_statistic_is_clamped(df: int) -> None:
    """A3/I13: -1e-14 (ruído de log-somas) vira 0 antes do erfc/exp → 1.0."""
    assert chi_square_sf(_TINY_NEGATIVE, df=df) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [_TINY_NEGATIVE, LR_NEGATIVE_FLOOR, -0.0],
    ids=["tiny-negative", "floor-inclusive", "negative-zero"],
)
def test_chi2_floor_clamps_values_in_floor_band_to_zero(value: float) -> None:
    """I13: `[LR_NEGATIVE_FLOOR, 0]` → +0.0 — a fronteira -1e-9 é inclusa e o `-0.0`
    sai sem sinal (nenhum relatório carrega zero com sinal)."""
    assert LR_NEGATIVE_FLOOR == _CONTRACT_FLOOR
    floored = floor_lr_statistic(value)
    assert floored == 0.0
    assert math.copysign(1.0, floored) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize("value", [0.0, 3.5], ids=["zero", "positive"])
def test_chi2_floor_leaves_non_negative_values_unchanged(value: float) -> None:
    """I13: valores ≥ 0 atravessam o piso inalterados."""
    assert floor_lr_statistic(value) == value


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [math.nextafter(LR_NEGATIVE_FLOOR, -math.inf), _BELOW_FLOOR],
    ids=["just-below-floor", "minus-2e-9"],
)
def test_chi2_floor_raises_below_the_floor(value: float) -> None:
    """I13: abaixo de -1e-9 é bug, não ruído — ergue."""
    with pytest.raises(ValueError, match="below the numerical floor"):
        floor_lr_statistic(value)


@pytest.mark.unit
@pytest.mark.parametrize("value", [math.nan, math.inf, True], ids=["nan", "inf", "bool"])
def test_chi2_floor_raises_on_non_finite_or_bool(value: float) -> None:
    """I13/C3: o piso recusa não-finito e `bool` (predicado único do slice)."""
    with pytest.raises(ValueError, match="must be a finite number"):
        floor_lr_statistic(value)


@pytest.mark.unit
@pytest.mark.parametrize("df", [0, 3, True, 1.0], ids=["zero", "three", "bool", "float"])
def test_chi2_invalid_df_raises(df: int) -> None:
    """A3/C3: df fora de {1, 2}, `bool` ou não-`int` ergue."""
    with pytest.raises(ValueError, match="df must be an int"):
        chi_square_sf(1.0, df=df)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("statistic", "match"),
    [
        (math.nan, "must be a finite number"),
        (math.inf, "must be a finite number"),
        (True, "must be a finite number"),
        (_BELOW_FLOOR, "below the numerical floor"),
    ],
    ids=["nan", "inf", "bool", "below-floor"],
)
@pytest.mark.parametrize("df", [1, 2])
def test_chi2_invalid_statistic_raises(statistic: float, match: str, df: int) -> None:
    """A3/C3/I13: estatística não-finita, `bool` ou negativa além do piso ergue."""
    with pytest.raises(ValueError, match=match):
        chi_square_sf(statistic, df=df)
