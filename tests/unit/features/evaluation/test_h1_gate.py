"""Unit test do `H1Gate` (Stage 6.5, A5, I8, I11, C9; ADR 6.5.0006 itens 1-5).

Evidência sintética montada à mão: as bandas saem das médias entre seeds (nunca
S·T) e são iguais (`==`) ao `WilsonBand` chamado à mão; degeneração média acima
do limiar reprova, exatamente no limiar passa; n̄ = 0 é "não aplicável" e reprova;
LR_uc de 3 estados, DGT (nível 1 - alpha/(2h)) e amostra comum como sensibilidades,
com as divergências nos dois sentidos; o resultado carrega n̄, T, aviso e o poder
em n = round(n̄).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services import h1_gate as h1_gate_module
from financial_forecasting.features.evaluation.domain.services.chi_square import chi_square_sf
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    lr_uc_three_state,
)
from financial_forecasting.features.evaluation.domain.services.h1_gate import (
    COMMON_SAMPLE_SENSITIVITY,
    LR_UC_SENSITIVITY,
    H1Gate,
)
from financial_forecasting.features.evaluation.domain.services.h1_gate_power import H1GatePower
from financial_forecasting.features.evaluation.domain.services.wilson_band import WilsonBand
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    violation_rate_for,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    CalibrationEvidence,
    DgtTailEvidence,
    HorizonEvidence,
    SeedTailCounts,
    TailEvidence,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload

_SPEC = Preregistration.from_mapping(valid_payload()).h1_gate
_LOWER_NOMINAL = violation_rate_for(HitKind.LOWER_TAIL, (_SPEC.lower_level,))
_UPPER_NOMINAL = violation_rate_for(HitKind.UPPER_TAIL, (_SPEC.upper_level,))

# (seed, violações, pontos) por seed
Counts = Sequence[tuple[int, int, int]]
_CALIBRATED: Counts = ((1, 100, 1000), (2, 100, 1000))


def _tail(level: float, counts: Counts, degeneracy: float) -> TailEvidence:
    return TailEvidence(
        level=level, seeds=tuple(SeedTailCounts(s, c, n, degeneracy) for s, c, n in counts)
    )


def _split(counts: Counts, parts: int) -> Counts:
    return tuple((s, c // parts, n // parts) for s, c, n in counts)


def _calibration(  # noqa: PLR0913 — um parâmetro por eixo da evidência
    sample: str,
    horizon: int,
    lower: Counts,
    upper: Counts,
    *,
    degeneracy: float = 0.0,
    with_dgt: bool = True,
) -> CalibrationEvidence:
    dgt: tuple[DgtTailEvidence, ...] = ()
    if horizon > 1 and with_dgt:
        dgt = tuple(
            DgtTailEvidence(
                offset,
                horizon,
                _tail(0.1, _split(lower, horizon), degeneracy),
                _tail(0.9, _split(upper, horizon), degeneracy),
            )
            for offset in range(horizon)
        )
    return CalibrationEvidence(
        sample=sample,
        lower=_tail(0.1, lower, degeneracy),
        upper=_tail(0.9, upper, degeneracy),
        dgt=dgt,
    )


def _evidence(  # noqa: PLR0913 — um parâmetro por eixo da evidência (keyword-only)
    *,
    horizon: int = 1,
    lower: Counts = _CALIBRATED,
    upper: Counts = _CALIBRATED,
    degeneracy: float = 0.0,
    common_lower: Counts = _CALIBRATED,
    common_upper: Counts = _CALIBRATED,
    common_points: int = 250,
) -> HorizonEvidence:
    return HorizonEvidence(
        horizon=horizon,
        common_points=common_points,
        gate=_calibration("model_full", horizon, lower, upper, degeneracy=degeneracy),
        common=_calibration("common", horizon, common_lower, common_upper, with_dgt=False),
        comparators_calibration=(),
        mean_pinball={},
        dm=(),
        mcs=(),
    )


@pytest.mark.unit
def test_gate_seed_mean_not_st() -> None:
    lower = ((1, 10, 100), (2, 18, 140))
    upper = ((1, 9, 100), (2, 15, 140))

    result = H1Gate.evaluate(_SPEC, _evidence(lower=lower, upper=upper))

    by_hand = WilsonBand.evaluate(
        horizon=1, count=14.0, n=120.0, nominal=_LOWER_NOMINAL, band_level=0.975
    )
    stacked = WilsonBand.evaluate(
        horizon=1, count=28.0, n=240.0, nominal=_LOWER_NOMINAL, band_level=0.975
    )
    assert result.lower_band == by_hand
    assert result.lower_band != stacked
    assert result.upper_band == WilsonBand.evaluate(
        horizon=1, count=12.0, n=120.0, nominal=_UPPER_NOMINAL, band_level=0.975
    )
    assert result.mean_observed == 120.0  # noqa: PLR2004


@pytest.mark.unit
def test_gate_degeneracy_over_threshold_fails() -> None:
    result = H1Gate.evaluate(_SPEC, _evidence(degeneracy=0.011))

    assert result.lower_band.contains_nominal is True
    assert result.upper_band.contains_nominal is True
    assert result.degeneracy_above_threshold is True
    assert result.mean_degeneracy_rate == pytest.approx(0.011)
    assert result.passed is False


@pytest.mark.unit
def test_gate_degeneracy_at_threshold_passes() -> None:
    result = H1Gate.evaluate(_SPEC, _evidence(degeneracy=0.01))

    assert result.mean_degeneracy_rate == _SPEC.degeneracy_threshold
    assert result.degeneracy_above_threshold is False
    assert result.passed is True


@pytest.mark.unit
def test_gate_not_applicable_fails() -> None:
    empty = ((1, 0, 0), (2, 0, 0))

    result = H1Gate.evaluate(_SPEC, _evidence(lower=empty, upper=empty, degeneracy=1.0))

    assert result.lower_band.applicable is False
    assert result.upper_band.applicable is False
    assert result.passed is False
    assert (result.lr_uc, result.dgt, result.common_sample_passed) == (None, None, None)
    assert result.divergences == ()
    assert result.power == ()


@pytest.mark.unit
def test_gate_calls_count_kernels(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[dict[str, object]]] = {"wilson": [], "lr_uc": [], "chi2": []}
    real_evaluate = WilsonBand.evaluate

    class _SpyBand:
        @staticmethod
        def evaluate(**kwargs: float) -> object:
            calls["wilson"].append(dict(kwargs))
            return real_evaluate(**kwargs)  # type: ignore[arg-type]

    def spy_lr_uc(**kwargs: float) -> float:
        calls["lr_uc"].append(dict(kwargs))
        return lr_uc_three_state(**kwargs)

    def spy_chi2(statistic: float, *, df: int) -> float:
        calls["chi2"].append({"statistic": statistic, "df": df})
        return chi_square_sf(statistic, df=df)

    monkeypatch.setattr(h1_gate_module, "WilsonBand", _SpyBand)
    monkeypatch.setattr(h1_gate_module, "lr_uc_three_state", spy_lr_uc)
    monkeypatch.setattr(h1_gate_module, "chi_square_sf", spy_chi2)
    lower = ((1, 10, 100), (2, 18, 140))
    upper = ((1, 9, 100), (2, 15, 140))

    H1Gate.evaluate(_SPEC, _evidence(lower=lower, upper=upper))

    gate_calls = calls["wilson"][:2]
    assert [(c["count"], c["n"], c["band_level"]) for c in gate_calls] == [
        (14.0, 120.0, 0.975),
        (12.0, 120.0, 0.975),
    ]
    assert calls["lr_uc"] == [
        {
            "lower_count": 14.0,
            "upper_count": 12.0,
            "n": 120.0,
            "lower_rate": _LOWER_NOMINAL,
            "upper_rate": _UPPER_NOMINAL,
        }
    ]
    assert calls["chi2"][0]["df"] == 2  # noqa: PLR2004


@pytest.mark.unit
def test_gate_lr_uc_sensitivity() -> None:
    lower = ((1, 119, 1000),)
    upper = ((1, 81, 1000),)

    result = H1Gate.evaluate(
        _SPEC, _evidence(lower=lower, upper=upper, common_lower=lower, common_upper=upper)
    )

    statistic = lr_uc_three_state(
        lower_count=119.0,
        upper_count=81.0,
        n=1000.0,
        lower_rate=_LOWER_NOMINAL,
        upper_rate=_UPPER_NOMINAL,
    )
    assert result.lr_uc is not None
    assert result.lr_uc.statistic == statistic
    assert result.lr_uc.p_value == chi_square_sf(statistic, df=2)
    assert result.lr_uc.rejected is (result.lr_uc.p_value < _SPEC.sensitivity_alpha)


@pytest.mark.unit
def test_gate_dgt_bonferroni_level() -> None:
    lower = ((1, 99, 990), (2, 99, 990))

    result = H1Gate.evaluate(_SPEC, _evidence(horizon=3, lower=lower, upper=lower))

    assert result.dgt is not None
    assert result.dgt.band_level == 1.0 - 0.05 / 6
    assert len(result.dgt.bands) == 6  # noqa: PLR2004
    assert all(band.band_level == result.dgt.band_level for band in result.dgt.bands)
    assert result.dgt.bands[0] == WilsonBand.evaluate(
        horizon=3, count=33.0, n=330.0, nominal=_LOWER_NOMINAL, band_level=1.0 - 0.05 / 6
    )
    assert result.dgt.passed is True


@pytest.mark.unit
def test_gate_single_step_no_dgt() -> None:
    result = H1Gate.evaluate(_SPEC, _evidence(horizon=1))

    assert result.dgt is None
    assert result.power_assumes_independence is False
    assert result.serial_dependence_warning is False


@pytest.mark.unit
def test_gate_common_sample_sensitivity() -> None:
    miscalibrated = ((1, 200, 1000), (2, 200, 1000))

    result = H1Gate.evaluate(_SPEC, _evidence(common_lower=miscalibrated))

    assert result.passed is True
    assert result.common_sample_passed is False
    assert COMMON_SAMPLE_SENSITIVITY in result.divergences


@pytest.mark.unit
def test_gate_divergence_both_directions() -> None:
    lower, upper = ((1, 119, 1000),), ((1, 81, 1000),)
    gate_passes = H1Gate.evaluate(
        _SPEC, _evidence(lower=lower, upper=upper, common_lower=lower, common_upper=upper)
    )
    assert gate_passes.passed is True
    assert gate_passes.lr_uc is not None
    assert gate_passes.lr_uc.rejected is True
    assert gate_passes.divergences == (LR_UC_SENSITIVITY,)

    miscalibrated = ((1, 150, 1000),)
    gate_fails = H1Gate.evaluate(_SPEC, _evidence(lower=miscalibrated, upper=((1, 100, 1000),)))
    assert gate_fails.passed is False
    assert gate_fails.common_sample_passed is True
    assert COMMON_SAMPLE_SENSITIVITY in gate_fails.divergences


@pytest.mark.unit
def test_gate_result_carries_n_t_warning() -> None:
    lower = ((1, 70, 700), (2, 77, 770))

    result = H1Gate.evaluate(
        _SPEC, _evidence(horizon=7, lower=lower, upper=lower, common_points=612)
    )

    assert result.horizon == 7  # noqa: PLR2004
    assert result.mean_observed == 735.0  # noqa: PLR2004
    assert result.common_points == 612  # noqa: PLR2004
    assert result.serial_dependence_warning is True
    assert result.power_assumes_independence is True
    assert result.mean_of_seed_rates == (pytest.approx(0.1), pytest.approx(0.1))


@pytest.mark.unit
def test_gate_power_rounded_n() -> None:
    lower = ((1, 10, 100), (2, 10, 101), (3, 10, 101))

    result = H1Gate.evaluate(_SPEC, _evidence(lower=lower, upper=lower))

    assert result.mean_observed == pytest.approx(302 / 3)
    assert [power.label for power in result.power] == [s.label for s in _SPEC.power_scenarios]
    assert {power.n for power in result.power} == {101}
    first = _SPEC.power_scenarios[0]
    assert result.power[0].role is first.role
    assert result.power[0].failure_probability == H1GatePower.failure_probability(
        n=101, spec=_SPEC, deviation=first
    )
