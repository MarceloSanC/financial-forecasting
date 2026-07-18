"""Testes unitários do value object `BaselineSpec` (domínio puro).

Cobrem construção válida de cada família, imutabilidade (frozen), cada ramo de
validação C3 (família desconhecida, parâmetro obrigatório ausente, parâmetro
proibido presente, `window < 20`, `decay_lambda` fora de (0, 1)) e a fábrica
`canonical_five()` (A1 — 5 specs, ordem canônica, `model_version` correto).
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BASELINE_FAMILIES,
    BaselineSpec,
)

_CANONICAL_LAMBDA = 0.94
_CANONICAL_WINDOW = 252
_REDUCED_WINDOW = 20
_FAMILIES_COUNT = 5


@pytest.mark.unit
def test_baseline_families_canonical_order() -> None:
    """A constante lista as 5 famílias na ordem do doc de domínio §3.8."""
    assert BASELINE_FAMILIES == (
        "zero_return",
        "historical_mean",
        "ar1",
        "ewma_vol",
        "historical_quantiles",
    )


@pytest.mark.unit
@pytest.mark.parametrize("family", ["zero_return", "historical_mean", "ar1"])
def test_construct_parameterless_families(family: str) -> None:
    """Famílias sem parâmetros constroem com defaults None."""
    spec = BaselineSpec(family=family)

    assert spec.family == family
    assert spec.window is None
    assert spec.decay_lambda is None


@pytest.mark.unit
def test_construct_ewma_vol_with_decay_lambda() -> None:
    """`ewma_vol` válido carrega o λ e nenhuma janela."""
    spec = BaselineSpec(family="ewma_vol", decay_lambda=0.94)

    assert spec.decay_lambda == _CANONICAL_LAMBDA
    assert spec.window is None


@pytest.mark.unit
def test_construct_historical_quantiles_with_window() -> None:
    """`historical_quantiles` válido carrega o W e nenhum λ."""
    spec = BaselineSpec(family="historical_quantiles", window=252)

    assert spec.window == _CANONICAL_WINDOW
    assert spec.decay_lambda is None


@pytest.mark.unit
def test_is_frozen() -> None:
    """VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    spec = BaselineSpec(family="zero_return")

    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.family = "ar1"  # type: ignore[misc]


@pytest.mark.unit
def test_equality_by_value() -> None:
    """Igualdade estrutural (VO): mesmos campos -> iguais."""
    a = BaselineSpec(family="ewma_vol", decay_lambda=0.94)
    b = BaselineSpec(family="ewma_vol", decay_lambda=0.94)

    assert a == b


@pytest.mark.unit
def test_model_version_prefixes_family() -> None:
    """`model_version` é `baseline_<family>` (casa o padrão `baseline_*`)."""
    spec = BaselineSpec(family="ar1")

    assert spec.model_version == "baseline_ar1"


@pytest.mark.unit
def test_unknown_family_raises() -> None:
    """Família fora do canônico é rejeitada na construção (C3)."""
    with pytest.raises(ValueError, match="family"):
        BaselineSpec(family="naive_drift")


@pytest.mark.unit
def test_ewma_vol_missing_decay_lambda_raises() -> None:
    """`ewma_vol` sem λ é rejeitado (parâmetro obrigatório ausente — C3)."""
    with pytest.raises(ValueError, match="decay_lambda"):
        BaselineSpec(family="ewma_vol")


@pytest.mark.unit
@pytest.mark.parametrize("bad_lambda", [0.0, 1.0, -0.1, 1.5])
def test_ewma_vol_decay_lambda_out_of_open_interval_raises(bad_lambda: float) -> None:
    """λ fora de (0, 1) é rejeitado (C3)."""
    with pytest.raises(ValueError, match="decay_lambda"):
        BaselineSpec(family="ewma_vol", decay_lambda=bad_lambda)


@pytest.mark.unit
def test_ewma_vol_forbids_window() -> None:
    """`ewma_vol` com janela é rejeitado (parâmetro proibido — C3)."""
    with pytest.raises(ValueError, match="window"):
        BaselineSpec(family="ewma_vol", decay_lambda=0.94, window=252)


@pytest.mark.unit
def test_historical_quantiles_missing_window_raises() -> None:
    """`historical_quantiles` sem W é rejeitado (obrigatório ausente — C3)."""
    with pytest.raises(ValueError, match="window"):
        BaselineSpec(family="historical_quantiles")


@pytest.mark.unit
@pytest.mark.parametrize("bad_window", [19, 1, 0, -252])
def test_historical_quantiles_window_below_minimum_raises(bad_window: int) -> None:
    """W < 20 é rejeitado (C3)."""
    with pytest.raises(ValueError, match="window"):
        BaselineSpec(family="historical_quantiles", window=bad_window)


@pytest.mark.unit
def test_historical_quantiles_forbids_decay_lambda() -> None:
    """`historical_quantiles` com λ é rejeitado (parâmetro proibido — C3)."""
    with pytest.raises(ValueError, match="decay_lambda"):
        BaselineSpec(family="historical_quantiles", window=252, decay_lambda=0.94)


@pytest.mark.unit
@pytest.mark.parametrize("family", ["zero_return", "historical_mean", "ar1"])
def test_parameterless_families_forbid_window(family: str) -> None:
    """Famílias sem parâmetros rejeitam `window` (proibido — C3)."""
    with pytest.raises(ValueError, match="window"):
        BaselineSpec(family=family, window=252)


@pytest.mark.unit
@pytest.mark.parametrize("family", ["zero_return", "historical_mean", "ar1"])
def test_parameterless_families_forbid_decay_lambda(family: str) -> None:
    """Famílias sem parâmetros rejeitam `decay_lambda` (proibido — C3)."""
    with pytest.raises(ValueError, match="decay_lambda"):
        BaselineSpec(family=family, decay_lambda=0.94)


@pytest.mark.unit
def test_canonical_five_returns_the_five_preregistered_specs() -> None:
    """`canonical_five()` = exatamente 5 specs, na ordem canônica (A1)."""
    specs = BaselineSpec.canonical_five()

    assert len(specs) == _FAMILIES_COUNT
    assert tuple(spec.family for spec in specs) == BASELINE_FAMILIES
    assert tuple(spec.model_version for spec in specs) == (
        "baseline_zero_return",
        "baseline_historical_mean",
        "baseline_ar1",
        "baseline_ewma_vol",
        "baseline_historical_quantiles",
    )


@pytest.mark.unit
def test_canonical_five_preregistered_defaults() -> None:
    """Defaults pré-registrados: λ = 0.94 (ADR 0.0.0052) e W = 252 (ADR 5.2.0003)."""
    specs = BaselineSpec.canonical_five()
    by_family = {spec.family: spec for spec in specs}

    assert by_family["ewma_vol"].decay_lambda == _CANONICAL_LAMBDA
    assert by_family["historical_quantiles"].window == _CANONICAL_WINDOW


@pytest.mark.unit
def test_canonical_five_window_override_for_tests() -> None:
    """Override de W (sancionado pelo ADR 5.2.0003) só muda `historical_quantiles`."""
    specs = BaselineSpec.canonical_five(historical_quantiles_window=20)
    by_family = {spec.family: spec for spec in specs}

    assert by_family["historical_quantiles"].window == _REDUCED_WINDOW
    assert by_family["ewma_vol"].decay_lambda == _CANONICAL_LAMBDA
