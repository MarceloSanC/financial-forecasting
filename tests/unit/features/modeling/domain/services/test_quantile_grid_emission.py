"""Testes dos serviços de emissão da grade (domínio puro) contra oráculos.

Oráculos com tolerância declarada (ADR 0.0.0021 — a duplicação É a verificação):

- `gaussian_grid`: z_tau tabulados (tabela da normal padrão; AS241) — tolerância
  `_Z_TOLERANCE`.
- `sample_quantiles_type7`: paridade com `numpy.quantile(..., method="linear")`
  (oráculo SÓ no teste — o domínio segue stdlib-only) — tolerância
  `_ORACLE_TOLERANCE`; mais caso analítico curto conferido à mão.
- `degenerate_grid`: constante em todo nível; composição com
  `QuantileForecast.from_raw` produz `guardrail_applied=False` (I5 — empate
  degenerado passa; metade da A2).

Cobre também todos os ramos de erro (`ValueError`) das três funções.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    degenerate_grid,
    gaussian_grid,
    sample_quantiles_type7,
)

# Tolerâncias declaradas (ADR 0.0.0021).
_Z_TOLERANCE = 1e-9
_ORACLE_TOLERANCE = 1e-12

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)

# z_tau tabulados da normal padrão (Phi^-1); fonte: tabelas clássicas / AS241.
_TABULATED_Z = {
    0.05: -1.6448536269514722,
    0.1: -1.2815515655446004,
    0.25: -0.6744897501960817,
    0.5: 0.0,
    0.75: 0.6744897501960817,
    0.9: 1.2815515655446004,
    0.95: 1.6448536269514722,
}


# --------------------------------------------------------------------------- #
# degenerate_grid
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_degenerate_grid_repeats_value_at_every_level() -> None:
    """Grade degenerada: o mesmo valor em todo nível, alinhada 1:1 a levels."""
    grid = degenerate_grid(value=0.0123, levels=_LEVELS)

    assert grid == tuple(0.0123 for _ in _LEVELS)
    assert len(grid) == len(_LEVELS)


@pytest.mark.unit
def test_degenerate_grid_zero_value() -> None:
    """`zero_return`: grade degenerada em 0 para qualquer grade de níveis."""
    grid = degenerate_grid(value=0.0, levels=(0.1, 0.5, 0.9))

    assert grid == (0.0, 0.0, 0.0)


@pytest.mark.unit
def test_degenerate_grid_passes_guardrail_unapplied() -> None:
    """Composição com o guardrail 4.3: empate degenerado passa intacto (I5/A2).

    `q_low == q_high` não viola ordenação fraca — `guardrail_applied` é False e
    os valores atravessam inalterados (gate de degeneração é Step 6).
    """
    grid = degenerate_grid(value=0.0042, levels=_LEVELS)

    forecast = QuantileForecast.from_raw(levels=_LEVELS, raw_values=grid)

    assert forecast.guardrail_applied is False
    assert forecast.guardrail_values == grid


@pytest.mark.unit
@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_degenerate_grid_non_finite_value_raises(bad_value: float) -> None:
    """Valor não-finito ergue — baseline determinístico nunca emite NaN/Inf (C5)."""
    with pytest.raises(ValueError, match="finite"):
        degenerate_grid(value=bad_value, levels=_LEVELS)


# --------------------------------------------------------------------------- #
# gaussian_grid
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_gaussian_grid_standard_normal_matches_tabulated_z() -> None:
    """Com mean=0, std=1 a grade é exatamente z_tau (oráculo tabulado, tol 1e-9)."""
    grid = gaussian_grid(mean=0.0, std=1.0, levels=_LEVELS)

    for tau, got in zip(_LEVELS, grid, strict=True):
        assert got == pytest.approx(_TABULATED_Z[tau], abs=_Z_TOLERANCE)


@pytest.mark.unit
def test_gaussian_grid_location_scale_shift() -> None:
    """`q_tau = mean + std * z_tau` (QRM Eq. (2.19)) com locação/escala materiais."""
    mean, std = 0.0005, 0.02

    grid = gaussian_grid(mean=mean, std=std, levels=_LEVELS)

    for tau, got in zip(_LEVELS, grid, strict=True):
        assert got == pytest.approx(mean + std * _TABULATED_Z[tau], abs=_Z_TOLERANCE)


@pytest.mark.unit
def test_gaussian_grid_median_is_mean() -> None:
    """Phi^-1(0.5) = 0: o nível 0.5 devolve exatamente a média."""
    grid = gaussian_grid(mean=0.0042, std=0.3, levels=(0.25, 0.5, 0.75))

    assert grid[1] == pytest.approx(0.0042, abs=_Z_TOLERANCE)


@pytest.mark.unit
def test_gaussian_grid_symmetric_around_mean() -> None:
    """Níveis simétricos tau/1-tau equidistam da média (simetria da normal)."""
    mean = 0.001
    grid = gaussian_grid(mean=mean, std=0.05, levels=(0.05, 0.5, 0.95))

    assert (grid[2] - mean) == pytest.approx(mean - grid[0], abs=_Z_TOLERANCE)


@pytest.mark.unit
@pytest.mark.parametrize("bad_std", [0.0, -0.01, math.nan, math.inf])
def test_gaussian_grid_non_positive_or_non_finite_std_raises(bad_std: float) -> None:
    """std <= 0 ou não-finito ergue (C5)."""
    with pytest.raises(ValueError, match="std"):
        gaussian_grid(mean=0.0, std=bad_std, levels=_LEVELS)


@pytest.mark.unit
@pytest.mark.parametrize("bad_mean", [math.nan, math.inf, -math.inf])
def test_gaussian_grid_non_finite_mean_raises(bad_mean: float) -> None:
    """mean não-finito ergue (C5)."""
    with pytest.raises(ValueError, match="mean"):
        gaussian_grid(mean=bad_mean, std=1.0, levels=_LEVELS)


# --------------------------------------------------------------------------- #
# sample_quantiles_type7
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_type7_analytic_short_case() -> None:
    """Caso curto à mão: n=4, p=0.5 -> h=2.5 -> interpola x_(2) e x_(3)."""
    grid = sample_quantiles_type7(values=(4.0, 1.0, 3.0, 2.0), levels=(0.5,))

    assert grid == (2.5,)


@pytest.mark.unit
def test_type7_exact_order_statistic_without_interpolation() -> None:
    """p que cai exatamente numa estatística de ordem devolve o próprio valor.

    n=5, p=0.25 -> h = (5-1)*0.25 + 1 = 2 -> x_(2) = 20 (sem interpolação).
    """
    grid = sample_quantiles_type7(values=(50.0, 10.0, 30.0, 20.0, 40.0), levels=(0.25,))

    assert grid == (20.0,)


@pytest.mark.unit
def test_type7_single_observation_returns_it_for_all_levels() -> None:
    """n=1: todo nível devolve a única observação (h = 1 para todo p)."""
    grid = sample_quantiles_type7(values=(7.5,), levels=(0.1, 0.5, 0.9))

    assert grid == (7.5, 7.5, 7.5)


@pytest.mark.unit
@pytest.mark.parametrize(
    "values",
    [
        (0.01, -0.02, 0.005, 0.03, -0.015, 0.0, 0.008),
        tuple(float(v) for v in range(1, 12)),
        (-1.5, -1.5, 0.0, 2.25, 2.25, 3.0),  # empates
    ],
    ids=["returns-like", "integers", "with-ties"],
)
def test_type7_parity_with_numpy_linear_oracle(values: tuple[float, ...]) -> None:
    """Paridade com `numpy.quantile(..., method='linear')` (oráculo; tol 1e-12).

    Inclui os níveis extremos da grade densa (0.05/0.95) e níveis interiores.
    """
    grid = sample_quantiles_type7(values=values, levels=_LEVELS)

    oracle = np.quantile(np.asarray(values), np.asarray(_LEVELS), method="linear")
    for got, expected in zip(grid, oracle.tolist(), strict=True):
        assert got == pytest.approx(expected, abs=_ORACLE_TOLERANCE)


@pytest.mark.unit
def test_type7_parity_with_numpy_on_extreme_levels() -> None:
    """Níveis bem extremos (0.01/0.99) também casam com o oráculo NumPy."""
    values = tuple(float(v) ** 1.5 for v in range(1, 30))
    levels = (0.01, 0.99)

    grid = sample_quantiles_type7(values=values, levels=levels)

    oracle = np.quantile(np.asarray(values), np.asarray(levels), method="linear")
    for got, expected in zip(grid, oracle.tolist(), strict=True):
        assert got == pytest.approx(expected, abs=_ORACLE_TOLERANCE)


@pytest.mark.unit
def test_type7_is_insensitive_to_input_order() -> None:
    """A ordenação é interna: qualquer permutação da amostra emite a mesma grade."""
    values = (0.01, -0.02, 0.005, 0.03, -0.015)

    assert sample_quantiles_type7(values=values, levels=_LEVELS) == sample_quantiles_type7(
        values=tuple(reversed(values)), levels=_LEVELS
    )


@pytest.mark.unit
def test_type7_empty_values_raises() -> None:
    """Amostra vazia ergue (não há o que estimar — alimenta C1)."""
    with pytest.raises(ValueError, match="non-empty"):
        sample_quantiles_type7(values=(), levels=_LEVELS)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_type7_non_finite_value_raises(bad: float) -> None:
    """NaN/Inf na amostra ergue (C5)."""
    with pytest.raises(ValueError, match="finite"):
        sample_quantiles_type7(values=(0.01, bad, 0.02), levels=_LEVELS)


# --------------------------------------------------------------------------- #
# validação comum de levels (via qualquer função)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_empty_levels_raises() -> None:
    """Grade de níveis vazia ergue."""
    with pytest.raises(ValueError, match="non-empty"):
        degenerate_grid(value=0.0, levels=())


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_levels",
    [(0.0, 0.5), (0.5, 1.0), (-0.1, 0.5), (0.5, 1.5), (0.1, math.nan)],
    ids=["zero", "one", "negative", "above-one", "nan"],
)
def test_levels_out_of_open_interval_raise(bad_levels: tuple[float, ...]) -> None:
    """Níveis fora de (0, 1) — inclusive NaN — erguem."""
    with pytest.raises(ValueError, match=r"\(0, 1\)"):
        gaussian_grid(mean=0.0, std=1.0, levels=bad_levels)


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_levels",
    [(0.5, 0.1), (0.1, 0.1, 0.5)],
    ids=["decreasing", "duplicated"],
)
def test_non_increasing_or_duplicated_levels_raise(
    bad_levels: tuple[float, ...],
) -> None:
    """Níveis não estritamente crescentes (ou duplicados) erguem."""
    with pytest.raises(ValueError, match="strictly increasing"):
        sample_quantiles_type7(values=(1.0, 2.0, 3.0), levels=bad_levels)
