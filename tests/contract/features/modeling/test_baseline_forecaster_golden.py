"""Golden do `BaselineForecaster` — trava numérica das DUAS pernas antes do refactor.

Rede de regressão da issue #66. A movimentação da política de emissão
(`_validate_structure`/`_emit_decision`) para o serviço de domínio
`baseline_emission` é **refactor puro**: nenhum valor emitido e nenhuma
mensagem de erro pode mudar. Este módulo congela, em literais, as saídas
capturadas ANTES da movimentação — se a extração alterar qualquer número ou
qualquer texto de erro, ele fica vermelho.

Três travas, todas parametrizadas sobre `[fake, real]`:

1. **Emissão determinística** — as 4 famílias que não estimam AR(1)
   (`zero_return`, `historical_mean`, `ewma_vol`, `historical_quantiles`)
   emitem bit a bit os mesmos valores nas duas pernas (elas nunca tocam o
   `statsforecast`), e são comparadas por igualdade EXATA com o golden.
2. **Emissão do `ar1`** — a única família em que fake e real legitimamente
   divergem (momentos stdlib vs fit da lib — o *shortcut* de Meszaros). Cada
   perna tem seu próprio golden; a perna real usa tolerância relativa de
   `1e-12` porque o valor vem de um otimizador numérico (qualquer mudança de
   lógica move MUITO mais que isso), a perna fake é exata.
3. **Fronteira de erro** — as 15 bordas estruturais/C1/C4/C5/I7 erguem
   `ValueError` com mensagem IDÊNTICA nas duas pernas; o texto exato está
   congelado. É a trava mais sensível ao refactor, porque é exatamente o
   bloco de 39 linhas duplicado que a issue #66 manda extrair.

A trava 1 é também a evidência da tese da issue: a divergência legítima entre
dublê e real é **localizada** na estimação, e só nela.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
    StatsforecastBaselineForecaster,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from tests.fakes.features.modeling.in_memory_baseline_forecaster import (
    FakeBaselineForecaster,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        BaselineForecaster,
    )


def _build_fake() -> BaselineForecaster:
    return FakeBaselineForecaster()


def _build_real() -> BaselineForecaster:
    return StatsforecastBaselineForecaster()


_BUILDERS: dict[str, Callable[[], BaselineForecaster]] = {
    "fake": _build_fake,
    "real": _build_real,
}
_LEGS = ("fake", "real")

# Tolerância da perna real na família `ar1`: o fit do `statsforecast` é
# numérico, então o último ulp pode oscilar entre builds da lib. 1e-12 é
# ordens de grandeza mais apertado que qualquer mudança de LÓGICA (trocar a
# janela, o horizonte ou a fórmula move o valor na 2ª-3ª casa).
_REAL_FIT_RTOL = 1e-12

# -- fixture determinística (idêntica à do contract test) ----------------------

_HQ_WINDOW = 20  # override de teste do W=252 (ADR 5.2.0003)
_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
_HORIZONS = (1, 3)
_N = 60
_TRAIN_END_IDX = 39
_DECISIONS = (48, 52)
_SPECS = {
    spec.family: spec
    for spec in BaselineSpec.canonical_five(historical_quantiles_window=_HQ_WINDOW)
}


def _ar1_returns(n: int = _N) -> tuple[float, ...]:
    """Série AR(1) sintética determinística (mu=0.001, phi=0.5, sigma_eps=0.01)."""
    rng = random.Random(7)
    mu, phi, sigma_eps = 0.001, 0.5, 0.01
    values = [mu + rng.gauss(0.0, sigma_eps)]
    for _ in range(n - 1):
        values.append(mu + phi * (values[-1] - mu) + rng.gauss(0.0, sigma_eps))
    return tuple(values)


_SERIES = _ar1_returns()


def _forecast(
    forecaster: BaselineForecaster, family: str
) -> Mapping[int, Mapping[int, tuple[float, ...]]]:
    return forecaster.forecast(
        spec=_SPECS[family],
        returns=_SERIES,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=_DECISIONS,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )


# -- golden: famílias sem estimação de AR(1) (idênticas nas duas pernas) --------

_ZERO = (0.0, 0.0, 0.0, 0.0, 0.0)
_HISTORICAL_MEAN_GRID = (
    0.0005223394307406626,
    0.0005223394307406626,
    0.0005223394307406626,
    0.0005223394307406626,
    0.0005223394307406626,
)
_GOLDEN_DETERMINISTIC: dict[str, dict[int, dict[int, tuple[float, ...]]]] = {
    "zero_return": {
        48: {1: _ZERO, 3: _ZERO},
        52: {1: _ZERO, 3: _ZERO},
    },
    "historical_mean": {
        48: {1: _HISTORICAL_MEAN_GRID, 3: _HISTORICAL_MEAN_GRID},
        52: {1: _HISTORICAL_MEAN_GRID, 3: _HISTORICAL_MEAN_GRID},
    },
    "ewma_vol": {
        48: {
            1: (
                -0.01127989187001281,
                -0.005936687726186521,
                0.0,
                0.005936687726186521,
                0.01127989187001281,
            ),
            3: (
                -0.01127989187001281,
                -0.005936687726186521,
                0.0,
                0.005936687726186521,
                0.01127989187001281,
            ),
        },
        52: {
            1: (
                -0.011308609307927549,
                -0.005951801919049414,
                0.0,
                0.005951801919049414,
                0.011308609307927549,
            ),
            3: (
                -0.011308609307927549,
                -0.005951801919049414,
                0.0,
                0.005951801919049414,
                0.011308609307927549,
            ),
        },
    },
    "historical_quantiles": {
        48: {
            1: (
                -0.00995431451299984,
                -0.006464006731130763,
                -0.0034308672436073632,
                0.005229967317454567,
                0.008259269945611875,
            ),
            3: (
                -0.00995431451299984,
                -0.006464006731130763,
                -0.0034308672436073632,
                0.005229967317454567,
                0.008259269945611875,
            ),
        },
        52: {
            1: (
                -0.011964383498127031,
                -0.009684680257316763,
                -0.0034308672436073632,
                0.0021559456232783203,
                0.0058174247350913375,
            ),
            3: (
                -0.011964383498127031,
                -0.009684680257316763,
                -0.0034308672436073632,
                0.0021559456232783203,
                0.0058174247350913375,
            ),
        },
    },
}

# -- golden: `ar1` — uma trava POR PERNA (é aqui, e só aqui, que divergem) ------

_GOLDEN_AR1: dict[str, dict[int, dict[int, tuple[float, ...]]]] = {
    "fake": {
        48: {
            1: (
                -0.013016446691353375,
                -0.008155561798779708,
                -0.002754765777633756,
                0.0026460302435121963,
                0.007506915136085863,
            ),
            3: (
                -0.012580675773657346,
                -0.0068428373184797045,
                -0.00046768222150432505,
                0.005907472875471055,
                0.011645311330648694,
            ),
        },
        52: {
            1: (
                -0.017797538295593836,
                -0.012936653403020169,
                -0.007535857381874215,
                -0.002135061360728263,
                0.002725823531845404,
            ),
            3: (
                -0.014025055465059666,
                -0.008287217009882025,
                -0.0019120619129066453,
                0.004463093184068734,
                0.010200931639246374,
            ),
        },
    },
    "real": {
        48: {
            1: (
                -0.01315082396663644,
                -0.008180963974108415,
                -0.002659088705203142,
                0.002862786563702131,
                0.007832646556230154,
            ),
            3: (
                -0.012666142573330959,
                -0.006816415602742262,
                -0.0003169442419180563,
                0.006182527118906149,
                0.012032254089494846,
            ),
        },
        52: {
            1: (
                -0.01789244651963235,
                -0.012922586527104325,
                -0.007400711258199052,
                -0.0018788359892937794,
                0.003091024003234245,
            ),
            3: (
                -0.0140750456547803,
                -0.008225318684191603,
                -0.0017258473233673982,
                0.004773624037456807,
                0.010623351008045505,
            ),
        },
    },
}

# -- golden: fronteira de erro (mensagem EXATA, idêntica nas duas pernas) -------

_OK_SERIES = tuple(0.001 * (i + 1) * (-1) ** i for i in range(30))
_NAN_SERIES = (*_OK_SERIES[:5], math.nan, *_OK_SERIES[6:])
_ZERO_SERIES = (0.0,) * 30
_MIXED_ZERO_TRAIN = (0.0, 0.0, 0.0, 0.0, 0.0, 0.01, -0.02, 0.03, -0.01, 0.02)

_ZERO_SPEC = BaselineSpec(family="zero_return")
_AR1_SPEC = BaselineSpec(family="ar1")
_EWMA_SPEC = BaselineSpec(family="ewma_vol", decay_lambda=0.94)
_HQ_SPEC = BaselineSpec(family="historical_quantiles", window=_HQ_WINDOW)


def _forged_spec() -> BaselineSpec:
    """Spec com família fora do canônico (bypass do C3 do VO) — I7."""
    forged = BaselineSpec(family="zero_return")
    object.__setattr__(forged, "family", "arma_11")
    return forged


_ErrorCase = tuple[BaselineSpec, Sequence[float], int, Sequence[int], Sequence[int]]

_ERROR_CASES: dict[str, _ErrorCase] = {
    "empty_returns": (_ZERO_SPEC, (), 0, (1,), (1,)),
    "train_end_idx_negative": (_ZERO_SPEC, _OK_SERIES, -1, (5,), (1,)),
    "train_end_idx_too_large": (_ZERO_SPEC, _OK_SERIES, 30, (5,), (1,)),
    "empty_decisions": (_ZERO_SPEC, _OK_SERIES, 10, (), (1,)),
    "decision_out_of_range": (_ZERO_SPEC, _OK_SERIES, 10, (30,), (1,)),
    "decision_not_after_train": (_ZERO_SPEC, _OK_SERIES, 10, (10,), (1,)),
    "decisions_not_increasing": (_ZERO_SPEC, _OK_SERIES, 10, (15, 15), (1,)),
    "empty_horizons": (_ZERO_SPEC, _OK_SERIES, 10, (15,), ()),
    "horizon_below_one": (_ZERO_SPEC, _OK_SERIES, 10, (15,), (0,)),
    "non_finite_window": (_ZERO_SPEC, _NAN_SERIES, 10, (15,), (1,)),
    "hq_window_too_short": (_HQ_SPEC, _OK_SERIES, 5, (10,), (1,)),
    "ewma_zero_variance": (_EWMA_SPEC, _ZERO_SERIES, 10, (15,), (1,)),
    "forged_family": (_forged_spec(), _OK_SERIES, 10, (15,), (1,)),
    "ar1_train_too_short": (_AR1_SPEC, _OK_SERIES, 1, (15,), (1,)),
    "ar1_zero_variance_train": (_AR1_SPEC, _MIXED_ZERO_TRAIN, 4, (8,), (1,)),
}

_GOLDEN_ERROR_MESSAGES: dict[str, str] = {
    "empty_returns": "returns must be non-empty",
    "train_end_idx_negative": "train_end_idx must be in [0, 29]; got -1",
    "train_end_idx_too_large": "train_end_idx must be in [0, 29]; got 30",
    "empty_decisions": "decision_indices must be non-empty",
    "decision_out_of_range": "decision index 30 out of range [0, 29]",
    "decision_not_after_train": "decision index 10 must be after train_end_idx=10",
    "decisions_not_increasing": "decision_indices must be strictly increasing",
    "empty_horizons": "horizons must be non-empty and >= 1; got ()",
    "horizon_below_one": "horizons must be non-empty and >= 1; got (0,)",
    "non_finite_window": (
        "non-finite value in the conditioning window returns[: 16] — "
        "a deterministic baseline never emits (C5)"
    ),
    "hq_window_too_short": (
        "historical_quantiles needs 20 returns up to the decision; decision 10 has only 11 (C1)"
    ),
    "ewma_zero_variance": (
        "ewma_vol conditioning window produced zero variance at decision 15 "
        "(all-zero returns up to t) — refusing to emit a degenerate Gaussian scale"
    ),
    "forged_family": (
        "unknown baseline family 'arma_11'; expected one of "
        "('zero_return', 'historical_mean', 'ar1', 'ewma_vol', "
        "'historical_quantiles') (I7)"
    ),
    "ar1_train_too_short": "ar1 needs at least 3 train observations; got 2 (C1)",
    "ar1_zero_variance_train": (
        "ar1 train series has zero variance (constant returns) — cannot estimate AR(1) moments"
    ),
}


# -- travas --------------------------------------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize("leg", _LEGS)
@pytest.mark.parametrize("family", sorted(_GOLDEN_DETERMINISTIC))
def test_deterministic_families_match_the_frozen_grid_bit_for_bit(leg: str, family: str) -> None:
    """As 4 famílias sem fit emitem EXATAMENTE o golden — nas duas pernas."""
    emitted = _forecast(_BUILDERS[leg](), family)

    got = {
        decision: {h: tuple(grid) for h, grid in by_horizon.items()}
        for decision, by_horizon in emitted.items()
    }
    assert got == _GOLDEN_DETERMINISTIC[family]


@pytest.mark.contract
@pytest.mark.parametrize("family", sorted(_GOLDEN_DETERMINISTIC))
def test_fake_and_real_agree_exactly_outside_the_ar1_estimation(family: str) -> None:
    """A divergência legítima dublê↔real é LOCALIZADA: fora do `ar1` não existe.

    É a tese da issue #66 medida: as famílias que não passam pelo
    `statsforecast` colapsam bit a bit, então o único *shortcut* (Meszaros) do
    fake é a estimação do AR(1).
    """
    from_fake = _forecast(_build_fake(), family)
    from_real = _forecast(_build_real(), family)

    assert from_fake == from_real


@pytest.mark.contract
@pytest.mark.parametrize("leg", _LEGS)
def test_ar1_emission_matches_the_frozen_grid_of_its_own_leg(leg: str) -> None:
    """`ar1` é a única família com golden por perna — fake exato, real a 1e-12."""
    emitted = _forecast(_BUILDERS[leg](), "ar1")

    tolerance = 0.0 if leg == "fake" else _REAL_FIT_RTOL
    golden = _GOLDEN_AR1[leg]
    for decision, by_horizon in golden.items():
        for horizon, grid in by_horizon.items():
            assert emitted[decision][horizon] == pytest.approx(grid, rel=tolerance, abs=tolerance)


@pytest.mark.contract
@pytest.mark.parametrize("leg", _LEGS)
@pytest.mark.parametrize("case", sorted(_ERROR_CASES))
def test_error_boundary_message_is_frozen_and_identical_in_both_legs(leg: str, case: str) -> None:
    """Cada borda ergue `ValueError` com o texto EXATO congelado, nas duas pernas."""
    spec, returns, train_end_idx, decisions, horizons = _ERROR_CASES[case]

    with pytest.raises(ValueError) as raised:
        _BUILDERS[leg]().forecast(
            spec=spec,
            returns=returns,
            train_end_idx=train_end_idx,
            decision_indices=decisions,
            horizons=horizons,
            quantile_levels=_LEVELS,
        )

    assert str(raised.value) == _GOLDEN_ERROR_MESSAGES[case]
