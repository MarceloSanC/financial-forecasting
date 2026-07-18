"""Contract test do port `BaselineForecaster` — suite ÚNICA fake ↔ adapter real.

Prova o contrato SEMÂNTICO do port (concept 5.2 §4/§5/§6; A4/A7/A8) sobre as 5
specs canônicas (`historical_quantiles_window=20` — override de teste sancionado
pelo ADR 5.2.0003, para a fixture curta caber):

- **I3 — causalidade por truncamento, POR DECISÃO:** mutar/truncar `returns`
  após a decisão `t` não muda a grade em `t` — todas as famílias, inclusive
  para uma decisão INTERMEDIÁRIA de uma chamada multi-decisão (a grade em t
  reproduz a chamada truncada em `returns[: t+1]` e é invariante a mutação em
  `(t, decisão_seguinte]`) — mata o mutante que condiciona toda decisão em
  `returns[: max(decision_indices)+1]`.
- **I4 — estimação congelada no train (recorte por família — ADR 5.2.0002
  Implementation notes):** para `ar1`/`historical_mean`, mutar
  `returns[train_end_idx+1 : t]` (excluindo o r_t condicionante no caso `ar1`)
  não muda a emissão em `t`; para `zero_return`, qualquer mutação pós-train é
  inócua. Para `ewma_vol`/`historical_quantiles` NÃO se asserta invariância de
  emissão — o caminho causal legitimamente entra; o freeze é lambda/W virem da spec.
- **C5:** NaN na janela condicionante → ergue (nunca emite).
- **C1:** `historical_quantiles` com menos de `window` retornos até a decisão
  ergue; train trivialmente insuficiente para `ar1` ergue.
- **Forma:** toda decisão pedida presente; toda grade com
  `len == len(quantile_levels)`; `zero_return` constante 0; flat em h para as
  famílias flat; variância crescente em h para `ar1` (concept §3).

Na Task 05 a fixture parametriza só o fake; a Task 07 adiciona `_build_real`
(`StatsforecastBaselineForecaster()`) a `_FACTORIES`/`_IDS` para rodar o MESMO
contrato sobre `[fake, real]` — mesma estrutura do contract test do
`MedallionStore` (skill `pytest-with-fakes`).
"""

from __future__ import annotations

import math
import random
from statistics import fmean
from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
    StatsforecastBaselineForecaster,
)
from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ewma_variance_path,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    degenerate_grid,
    gaussian_grid,
    sample_quantiles_type7,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BASELINE_FAMILIES,
    BaselineSpec,
)
from tests.fakes.features.modeling.in_memory_baseline_forecaster import (
    FakeBaselineForecaster,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        BaselineForecaster,
    )


def _build_fake() -> BaselineForecaster:
    return FakeBaselineForecaster()


def _build_real() -> BaselineForecaster:
    return StatsforecastBaselineForecaster()


# Suite única rodando idêntica sobre fake e adapter real (A7) — mesma estrutura
# do contract test do `MedallionStore` (skill `pytest-with-fakes`).
_FACTORIES: list[Callable[[], BaselineForecaster]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def forecaster(request: pytest.FixtureRequest) -> BaselineForecaster:
    """Parametriza o contrato sobre o fake (e o adapter real a partir da Task 07)."""
    factory: Callable[[], BaselineForecaster] = request.param
    return factory()


# -- fixture de dados ----------------------------------------------------------

_HQ_WINDOW = 20  # override de teste do W=252 (ADR 5.2.0003)
_SPECS = {
    spec.family: spec
    for spec in BaselineSpec.canonical_five(historical_quantiles_window=_HQ_WINDOW)
}
_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
_HORIZONS = (1, 3)
_N = 60
_TRAIN_END_IDX = 39
_DECISIONS = (48, 52)
_LAST_DECISION = 52
_MUTATION = 5.0  # valor implausível: qualquer contaminação muda a emissão


def _ar1_returns(n: int = _N) -> tuple[float, ...]:
    """Série AR(1) sintética determinística (mu=0.001, phi=0.5, sigma_eps=0.01)."""
    rng = random.Random(7)
    mu, phi, sigma_eps = 0.001, 0.5, 0.01
    values = [mu + rng.gauss(0.0, sigma_eps)]
    for _ in range(n - 1):
        values.append(mu + phi * (values[-1] - mu) + rng.gauss(0.0, sigma_eps))
    return tuple(values)


def _forecast(
    forecaster: BaselineForecaster,
    spec: BaselineSpec,
    returns: tuple[float, ...],
    decisions: tuple[int, ...] = _DECISIONS,
) -> dict[int, dict[int, tuple[float, ...]]]:
    result = forecaster.forecast(
        spec=spec,
        returns=returns,
        train_end_idx=_TRAIN_END_IDX,
        decision_indices=decisions,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
    )
    return {d: dict(grids) for d, grids in result.items()}


# -- I3: causalidade por truncamento (todas as famílias) ------------------------


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_i3_emission_invariant_to_post_decision_mutation(
    forecaster: BaselineForecaster, family: str
) -> None:
    """I3: mutar `returns` DEPOIS da decisão t não muda a grade em t."""
    returns = _ar1_returns()
    baseline = _forecast(forecaster, _SPECS[family], returns)

    mutated = returns[: _LAST_DECISION + 1] + tuple(
        _MUTATION for _ in returns[_LAST_DECISION + 1 :]
    )
    contaminated = _forecast(forecaster, _SPECS[family], mutated)

    assert contaminated == baseline


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_i3_emission_invariant_to_truncation_at_decision(
    forecaster: BaselineForecaster, family: str
) -> None:
    """I3: truncar `returns` logo após a decisão t reproduz a grade em t."""
    returns = _ar1_returns()
    full = _forecast(forecaster, _SPECS[family], returns, decisions=(_LAST_DECISION,))

    truncated = _forecast(
        forecaster,
        _SPECS[family],
        returns[: _LAST_DECISION + 1],
        decisions=(_LAST_DECISION,),
    )

    assert truncated == full


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_i3_intermediate_decision_matches_truncated_call(
    forecaster: BaselineForecaster, family: str
) -> None:
    """I3 POR DECISÃO: a grade numa decisão intermediária t de uma chamada
    multi-decisão é idêntica à da chamada truncada em `returns[: t+1]`.

    Mata o mutante que condiciona toda decisão em
    `returns[: max(decision_indices)+1]` (Checkpoint C, MAJOR-1).
    """
    returns = _ar1_returns()
    intermediate = _DECISIONS[0]  # 48 — NÃO é a última decisão da chamada
    multi = _forecast(forecaster, _SPECS[family], returns)  # decisões (48, 52)

    truncated = _forecast(
        forecaster,
        _SPECS[family],
        returns[: intermediate + 1],
        decisions=(intermediate,),
    )

    assert multi[intermediate] == truncated[intermediate]


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_i3_intermediate_decision_invariant_to_mutation_before_next_decision(
    forecaster: BaselineForecaster, family: str
) -> None:
    """I3 POR DECISÃO: mutar `returns` em `(t, decisão_seguinte]` não muda a
    grade na decisão intermediária t (a da decisão seguinte pode mudar)."""
    returns = _ar1_returns()
    intermediate = _DECISIONS[0]  # 48
    baseline = _forecast(forecaster, _SPECS[family], returns)

    mutated = (
        returns[: intermediate + 1]
        + tuple(_MUTATION for _ in range(intermediate + 1, _LAST_DECISION + 1))
        + returns[_LAST_DECISION + 1 :]
    )
    contaminated = _forecast(forecaster, _SPECS[family], mutated)

    assert contaminated[intermediate] == baseline[intermediate]


# -- I4: estimação congelada no train (recorte por família) ---------------------


@pytest.mark.contract
@pytest.mark.parametrize("family", ["historical_mean", "zero_return"])
def test_i4_post_train_mutation_is_innocuous_for_train_only_families(
    forecaster: BaselineForecaster, family: str
) -> None:
    """I4: para famílias que só estimam no train, mutação pós-train não muda nada."""
    returns = _ar1_returns()
    baseline = _forecast(forecaster, _SPECS[family], returns)

    mutated = returns[: _TRAIN_END_IDX + 1] + tuple(
        _MUTATION for _ in returns[_TRAIN_END_IDX + 1 :]
    )
    contaminated = _forecast(forecaster, _SPECS[family], mutated)

    assert contaminated == baseline


@pytest.mark.contract
def test_i4_ar1_parameters_frozen_on_train(forecaster: BaselineForecaster) -> None:
    """I4: mutar `returns[train_end+1 : t]` (preservando r_t) não muda o `ar1` em t."""
    returns = _ar1_returns()
    decision = _LAST_DECISION
    baseline = _forecast(forecaster, _SPECS["ar1"], returns, decisions=(decision,))

    # Muta o trecho pós-train ANTES da decisão, preservando o r_t condicionante
    # (e a cauda pós-decisão, já coberta por I3).
    mutated = (
        returns[: _TRAIN_END_IDX + 1]
        + tuple(_MUTATION for _ in range(_TRAIN_END_IDX + 1, decision))
        + returns[decision:]
    )
    contaminated = _forecast(forecaster, _SPECS["ar1"], mutated, decisions=(decision,))

    assert contaminated == baseline


# -- C5: não-finito na janela condicionante ergue -------------------------------


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_c5_nan_in_conditioning_window_raises(
    forecaster: BaselineForecaster, family: str
) -> None:
    """C5: NaN dentro da janela condicionante (aqui: no r_t da decisão) ergue."""
    returns = _ar1_returns()
    poisoned = (*returns[:_LAST_DECISION], math.nan, *returns[_LAST_DECISION + 1 :])

    with pytest.raises(ValueError, match=r"(?i)finite|nan"):
        _forecast(forecaster, _SPECS[family], poisoned)


# -- C1: janela/train insuficiente ergue ----------------------------------------


@pytest.mark.contract
def test_c1_historical_quantiles_window_not_filled_raises(
    forecaster: BaselineForecaster,
) -> None:
    """C1: decisão com menos de `window` retornos disponíveis ergue."""
    returns = _ar1_returns(30)
    early_train_end = 5
    early_decision = 10  # 11 retornos até t < window=20

    with pytest.raises(ValueError):
        forecaster.forecast(
            spec=_SPECS["historical_quantiles"],
            returns=returns,
            train_end_idx=early_train_end,
            decision_indices=(early_decision,),
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )


@pytest.mark.contract
def test_c1_ar1_constant_train_raises(forecaster: BaselineForecaster) -> None:
    """`ar1` com train constante (≠ 0, variância zero) ergue nas DUAS pernas.

    Erguer, não fabricar (Checkpoint C MAJOR-1): sem o guard, o fit real numa
    série constante devolve sigma2_eps ~ 1e-38 > 0 (passa o C4 `<= 0`) e a
    emissão fabricaria uma escala gaussiana degenerada; o fake já erguia — a
    paridade observável (mesma condição e mensagem) é contrato.
    """
    constant = 0.001  # ≠ 0: isola a variância zero do train (não a borda ewma)
    returns = tuple(constant for _ in range(_N))

    with pytest.raises(ValueError, match=r"zero variance"):
        forecaster.forecast(
            spec=_SPECS["ar1"],
            returns=returns,
            train_end_idx=_TRAIN_END_IDX,
            decision_indices=_DECISIONS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )


@pytest.mark.contract
def test_c1_ar1_trivially_insufficient_train_raises(
    forecaster: BaselineForecaster,
) -> None:
    """C1: train trivialmente insuficiente (2 pontos) para estimar o AR(1) ergue."""
    returns = _ar1_returns(30)

    with pytest.raises(ValueError):
        forecaster.forecast(
            spec=_SPECS["ar1"],
            returns=returns,
            train_end_idx=1,
            decision_indices=(10,),
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
        )


# -- Oráculos de emissão exata (auditoria 5.2 — mutantes off-by-one) ------------


@pytest.mark.contract
def test_historical_mean_emission_is_train_mean_oracle(
    forecaster: BaselineForecaster,
) -> None:
    """`historical_mean` emite EXATAMENTE `degenerate_grid(fmean(train))` com
    train = `returns[: train_end_idx + 1]` (I4/D2 — tolerância 1e-12).

    Mata o mutante off-by-one que encurta o train (`returns[: train_end_idx]`):
    remover o último ponto desloca a média em ~1e-4 >> tolerância.
    """
    tolerance = 1e-12  # tolerância declarada (ADR 0.0.0021)
    returns = _ar1_returns()
    expected = degenerate_grid(
        value=fmean(returns[: _TRAIN_END_IDX + 1]), levels=_LEVELS
    )

    result = _forecast(forecaster, _SPECS["historical_mean"], returns)

    for decision in _DECISIONS:
        for horizon in _HORIZONS:
            assert result[decision][horizon] == pytest.approx(expected, abs=tolerance)


@pytest.mark.contract
def test_historical_quantiles_window_ends_at_decision_oracle(
    forecaster: BaselineForecaster,
) -> None:
    """`historical_quantiles` na decisão t emite EXATAMENTE
    `sample_quantiles_type7(returns[t-W+1 : t+1])` — janela termina EM t
    (ADR 5.2.0003, Implementation note; tolerância 1e-12).

    Um outlier em `returns[t]` desloca materialmente os quantis: a janela SEM
    r_t (`returns[t-W : t]`, o mutante off-by-one) produz grade diferente — o
    teste asserta essa discriminação para não passar por coincidência numérica.
    """
    tolerance = 1e-12  # tolerância declarada (ADR 0.0.0021)
    decision = _LAST_DECISION
    window = _HQ_WINDOW
    base = _ar1_returns()
    outlier = 0.5  # implausível na série (~1e-2): desloca os ranks de todos os quantis
    returns = (*base[:decision], outlier, *base[decision + 1 :])

    expected = sample_quantiles_type7(
        values=returns[decision - window + 1 : decision + 1], levels=_LEVELS
    )
    mutant_window = sample_quantiles_type7(
        values=returns[decision - window : decision], levels=_LEVELS
    )
    # A fixture DISCRIMINA o mutante: sem o r_t (outlier) a grade muda materialmente.
    assert expected != pytest.approx(mutant_window, abs=tolerance)

    result = _forecast(
        forecaster, _SPECS["historical_quantiles"], returns, decisions=(decision,)
    )

    for horizon in _HORIZONS:
        assert result[decision][horizon] == pytest.approx(expected, abs=tolerance)


# -- I7: dispatch exaustivo — família forjada ergue nas duas pernas -------------


@pytest.mark.contract
def test_i7_unknown_family_forged_spec_raises(forecaster: BaselineForecaster) -> None:
    """I7: spec forjada com família desconhecida (bypass do C3 do VO via
    `object.__setattr__`) ergue o MESMO ValueError nas DUAS pernas.

    Checkpoint C MINOR-2: dispatch exaustivo com ramo explícito — nunca um
    assert (que evapora sob `python -O`)."""
    forged_spec = BaselineSpec(family="zero_return")
    object.__setattr__(forged_spec, "family", "arma_11")  # contorna o __post_init__

    with pytest.raises(ValueError, match=r"unknown baseline family 'arma_11'"):
        _forecast(forecaster, forged_spec, _ar1_returns())


# -- Forma: presença, alinhamento e comportamento em h --------------------------


@pytest.mark.contract
@pytest.mark.parametrize("family", BASELINE_FAMILIES)
def test_shape_every_decision_and_horizon_present_and_aligned(
    forecaster: BaselineForecaster, family: str
) -> None:
    """Toda decisão pedida presente; toda grade alinhada 1:1 a `quantile_levels`."""
    result = _forecast(forecaster, _SPECS[family], _ar1_returns())

    assert set(result) == set(_DECISIONS)
    for grids in result.values():
        assert set(grids) == set(_HORIZONS)
        for grid in grids.values():
            assert len(grid) == len(_LEVELS)
            assert all(math.isfinite(v) for v in grid)


@pytest.mark.contract
def test_shape_zero_return_is_constant_zero(forecaster: BaselineForecaster) -> None:
    """`zero_return` emite a grade degenerada em 0 para toda decisão x horizonte."""
    result = _forecast(forecaster, _SPECS["zero_return"], _ar1_returns())

    for grids in result.values():
        for grid in grids.values():
            assert grid == tuple(0.0 for _ in _LEVELS)


@pytest.mark.contract
@pytest.mark.parametrize(
    "family", ["zero_return", "historical_mean", "ewma_vol", "historical_quantiles"]
)
def test_shape_flat_families_are_flat_in_horizon(
    forecaster: BaselineForecaster, family: str
) -> None:
    """Famílias flat emitem a MESMA grade para todo horizonte de uma decisão."""
    result = _forecast(forecaster, _SPECS[family], _ar1_returns())

    for grids in result.values():
        reference = grids[_HORIZONS[0]]
        assert all(grid == reference for grid in grids.values())


@pytest.mark.contract
def test_ewma_vol_decay_lambda_comes_from_spec(forecaster: BaselineForecaster) -> None:
    """O λ do `ewma_vol` vem da spec, nunca hardcoded (freeze I4 do ADR 5.2.0002).

    Com `decay_lambda=0.5`, a emissão deve casar o oráculo de domínio
    `ewma_variance_path(..., 0.5)` + `gaussian_grid` (tolerância 1e-12) e
    diferir da grade com o λ canônico 0.94 — mata implementação que
    hardcodeia 0.94 (Checkpoint C, MINOR-5).
    """
    alt_lambda = 0.5
    tolerance = 1e-12  # tolerância declarada (ADR 0.0.0021)
    returns = _ar1_returns()
    spec_alt = BaselineSpec(family="ewma_vol", decay_lambda=alt_lambda)

    result = _forecast(forecaster, spec_alt, returns)
    canonical = _forecast(forecaster, _SPECS["ewma_vol"], returns)

    for decision in _DECISIONS:
        sigma2 = ewma_variance_path(
            returns=returns[: decision + 1], decay_lambda=alt_lambda
        )[-1]
        expected = gaussian_grid(mean=0.0, std=math.sqrt(sigma2), levels=_LEVELS)
        for horizon in _HORIZONS:
            assert result[decision][horizon] == pytest.approx(expected, abs=tolerance)
            assert result[decision][horizon] != pytest.approx(
                canonical[decision][horizon], abs=tolerance
            )


@pytest.mark.contract
def test_shape_ar1_spread_grows_with_horizon(forecaster: BaselineForecaster) -> None:
    """`ar1`: a dispersão da grade cresce com h (variância h-step crescente)."""
    result = _forecast(forecaster, _SPECS["ar1"], _ar1_returns())

    for grids in result.values():
        spread_h1 = grids[1][-1] - grids[1][0]
        spread_h3 = grids[3][-1] - grids[3][0]
        assert spread_h3 > spread_h1
