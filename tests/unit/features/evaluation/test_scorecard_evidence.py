"""Unit test dos VOs de evidência do scorecard (Stage 6.5; ADR 6.5.0006 itens 1-2).

Cada invariante com um caso; a estimativa da banda é a razão de médias c̄/n̄ e a
média das taxas por seed só difere dela quando os n_observed variam entre seeds;
`SeedSpread` é o dono da agregação entre seeds dos descritores.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    CalibrationEvidence,
    ComparatorCalibration,
    DgtTailEvidence,
    DmEvidence,
    HorizonEvidence,
    McsEvidence,
    SeedSpread,
    SeedTailCounts,
    TailEvidence,
)


def _tail(
    level: float, *counts: tuple[int | None, int, int], degeneracy: float = 0.0
) -> TailEvidence:
    return TailEvidence(
        level=level,
        seeds=tuple(SeedTailCounts(seed, c, n, degeneracy) for seed, c, n in counts),
    )


def _calibration(sample: str, horizon: int, seeds: tuple[int, ...] = (1, 2)) -> CalibrationEvidence:
    lower = _tail(0.1, *((s, 10, 100) for s in seeds))
    upper = _tail(0.9, *((s, 10, 100) for s in seeds))
    dgt = (
        tuple(DgtTailEvidence(k, horizon, lower, upper) for k in range(horizon))
        if horizon > 1 and sample == "model_full"
        else ()
    )
    return CalibrationEvidence(sample=sample, lower=lower, upper=upper, dgt=dgt)


def _dm(comparator: str, estimator: DmVarianceEstimator, n_points: int = 100) -> DmEvidence:
    return DmEvidence(
        comparator=comparator,
        estimator=estimator,
        n_points=n_points,
        mean_differential=-0.1,
        statistic=-2.5,
        adjusted_p_value=0.01,
        rejected=True,
        fallback_applied=False,
    )


def _horizon(horizon: int = 1, **changes: object) -> HorizonEvidence:
    fields: dict[str, object] = {
        "horizon": horizon,
        "common_points": 100,
        "gate": _calibration("model_full", horizon),
        "common": _calibration("common", horizon),
        "comparators_calibration": (),
        "mean_pinball": {"cand": 0.1, "comp": 0.2},
        "dm": (
            _dm("comp", DmVarianceEstimator.RECTANGULAR),
            _dm("comp", DmVarianceEstimator.BARTLETT),
        ),
        "mcs": (
            McsEvidence(BootstrapScheme.STATIONARY, "cand", included=True),
            McsEvidence(BootstrapScheme.STATIONARY, "comp", included=False),
        ),
    }
    fields.update(changes)
    return HorizonEvidence(**fields)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("counts", "message"),
    [
        pytest.param((1, 11, 10, 0.0), "n_violations must be <= n_observed", id="c-over-n"),
        pytest.param((1, -1, 10, 0.0), "n_violations must be an int >= 0", id="negative"),
        pytest.param((1, True, 10, 0.0), "n_violations must be an int >= 0", id="bool"),
        pytest.param((1, 1, 10.0, 0.0), "n_observed must be an int >= 0", id="float-n"),
        pytest.param(
            (1, 1, 10, 1.5), r"degeneracy_rate must be a finite number in \[0, 1\]", id="deg"
        ),
        pytest.param((-1, 1, 10, 0.0), "seed must be an int >= 0", id="negative-seed"),
    ],
)
def test_evidence_seed_counts_invalid(
    counts: tuple[object, object, object, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SeedTailCounts(*counts)  # type: ignore[arg-type]


@pytest.mark.unit
def test_evidence_seed_counts_invalid_tail_shape() -> None:
    with pytest.raises(ValueError, match="seeds must be distinct"):
        _tail(0.1, (1, 1, 10), (1, 2, 10))
    with pytest.raises(ValueError, match="seeds must be a non-empty tuple"):
        TailEvidence(level=0.1, seeds=())
    with pytest.raises(ValueError, match=r"level must be in \(0, 1\)"):
        _tail(1.0, (1, 1, 10))


@pytest.mark.unit
def test_evidence_tail_ratio_of_means() -> None:
    tail = _tail(0.1, (1, 10, 100), (2, 30, 200), degeneracy=0.02)

    assert tail.mean_violations == 20.0  # noqa: PLR2004
    assert tail.mean_observed == 150.0  # noqa: PLR2004
    assert tail.mean_violations / tail.mean_observed == pytest.approx(20 / 150)
    assert tail.mean_of_seed_rates == pytest.approx((0.10 + 0.15) / 2)
    assert tail.mean_of_seed_rates != pytest.approx(tail.mean_violations / tail.mean_observed)
    assert tail.mean_degeneracy == pytest.approx(0.02)
    same_n = _tail(0.1, (1, 10, 100), (2, 30, 100))
    assert same_n.mean_of_seed_rates == pytest.approx(same_n.mean_violations / same_n.mean_observed)
    assert _tail(0.1, (1, 0, 0)).mean_of_seed_rates is None


@pytest.mark.unit
def test_evidence_dgt_offsets_complete() -> None:
    full = _calibration("model_full", 3)

    with pytest.raises(ValueError, match=r"offsets must be 0..2"):
        dataclasses.replace(full, dgt=full.dgt[:1] + full.dgt[2:])
    with pytest.raises(ValueError, match=r"gate.dgt must hold the 3 sub-series"):
        _horizon(3, gate=dataclasses.replace(full, dgt=()))
    with pytest.raises(ValueError, match="offset must be < step"):
        DgtTailEvidence(3, 3, full.lower, full.upper)
    other_seeds = _calibration("model_full", 3, seeds=(1, 3))
    with pytest.raises(ValueError, match="same seeds"):
        dataclasses.replace(full, dgt=other_seeds.dgt)
    assert len(_horizon(3).gate.dgt) == 3  # noqa: PLR2004


@pytest.mark.unit
def test_evidence_single_step_without_dgt() -> None:
    with pytest.raises(ValueError, match="horizon 1 has no DGT"):
        _horizon(1, gate=_calibration("model_full", 2))
    with pytest.raises(ValueError, match="step must be >= 2"):
        DgtTailEvidence(0, 1, _tail(0.1, (1, 1, 10)), _tail(0.9, (1, 1, 10)))
    assert _horizon(1).gate.dgt == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"gate": _calibration("common", 1)}, "gate.sample must be", id="gate-sample"),
        pytest.param(
            {"common": _calibration("model_full", 1)}, "common.sample must be", id="common-sample"
        ),
        pytest.param({"common_points": 99}, "must equal common_points", id="dm-points"),
        pytest.param({"mean_pinball": {"cand": float("nan")}}, "finite number", id="pinball"),
    ],
)
def test_evidence_horizon_incoherent(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _horizon(1, **changes)


@pytest.mark.unit
def test_evidence_horizon_incoherent_tail_seeds() -> None:
    gate = _calibration("model_full", 1)

    with pytest.raises(ValueError, match="the two tails must have the same seeds"):
        dataclasses.replace(gate, upper=_tail(0.9, (1, 1, 10)))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("upper", "id_"),
    [
        pytest.param(((1, 10, 99), (2, 10, 100)), "n", id="n-observed-differs"),
        pytest.param(((1, 10, 100), (2, 10, 100)), "degeneracy", id="degeneracy-differs"),
    ],
)
def test_evidence_horizon_incoherent_tail_series(
    upper: tuple[tuple[int, int, int], ...], id_: str
) -> None:
    """n_observed e degeneracy_rate são da série: iguais nas duas caudas, por seed."""
    lower = _tail(0.1, (1, 10, 100), (2, 10, 100))
    upper_tail = _tail(0.9, *upper, degeneracy=0.02 if id_ == "degeneracy" else 0.0)
    message = "same n_observed and degeneracy_rate"
    with pytest.raises(ValueError, match=message):
        CalibrationEvidence(sample="model_full", lower=lower, upper=upper_tail, dgt=())
    with pytest.raises(ValueError, match=message):
        DgtTailEvidence(0, 2, lower, upper_tail)
    with pytest.raises(ValueError, match=message):
        ComparatorCalibration(model="m", lower=lower, upper=upper_tail)


@pytest.mark.unit
def test_evidence_dm_pair_repeated() -> None:
    repeated = (
        _dm("comp", DmVarianceEstimator.RECTANGULAR),
        _dm("comp", DmVarianceEstimator.RECTANGULAR),
    )

    with pytest.raises(ValueError, match=r"repeats a \(comparator, estimator\) pair"):
        _horizon(1, dm=repeated)
    mcs = (
        McsEvidence(BootstrapScheme.STATIONARY, "cand", included=True),
        McsEvidence(BootstrapScheme.STATIONARY, "cand", included=False),
    )
    with pytest.raises(ValueError, match=r"repeats a \(scheme, model\) pair"):
        _horizon(1, mcs=mcs)


@pytest.mark.unit
def test_evidence_seed_spread() -> None:
    single = SeedSpread.of([0.25])
    spread = SeedSpread.of([0.1, 0.4, 0.2])

    assert (single.mean, single.minimum, single.maximum, single.n_seeds) == (0.25, 0.25, 0.25, 1)
    assert spread.mean == pytest.approx(0.7 / 3)
    assert (spread.minimum, spread.maximum, spread.n_seeds) == (0.1, 0.4, 3)
    with pytest.raises(ValueError, match="at least one value"):
        SeedSpread.of([])
    with pytest.raises(ValueError, match="finite numbers"):
        SeedSpread.of([0.1, float("inf")])
