"""Unit do `VsnSummary` (Stage 7.3, Task 26; ADR 7.3.0005 H3-VSN)."""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    linear_quantile,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import (
    VSN_LABEL,
    VsnEntry,
    VsnSummary,
    VsnSummaryReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_run_weights import (
    VsnRunWeights,
)
from tests.unit.features.evaluation._h3_parameters import h3_parameters

pytestmark = pytest.mark.unit

_D = [f"2024-01-{i + 2:02d}T00:00:00+00:00" for i in range(6)]
# a partição sintética do helper: price = log_return, range_pct; technical = rsi_14, macd
_VARIABLES = ("log_return", "range_pct", "rsi_14", "macd", "relative_time_idx")


def _weights(seed: int, decisions: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for decision in decisions:
        position = _D.index(decision)
        raw = [1.0 + ((seed * 7 + position * 3 + i) % 5) for i in range(len(_VARIABLES))]
        total = sum(raw)
        out[decision] = {v: w / total for v, w in zip(_VARIABLES, raw, strict=True)}
    return out


def _reductions(seeds: tuple[int, ...] = (1, 2)) -> list[VsnRunWeights]:
    return [
        VsnRunWeights(
            run_id=f"r{seed}{fold}", seed=seed, fold_index=fold, weights=_weights(seed, d)
        )
        for seed in seeds
        for fold, d in ((0, _D[:3]), (1, _D[3:]))
    ]


def _summary(reductions: list[VsnRunWeights] | None = None) -> VsnSummaryReport:
    return VsnSummary.summarize(
        _reductions() if reductions is None else reductions,
        parameters=h3_parameters(),
        seeds=(1, 2),
    )


def _entry(report: VsnSummaryReport, kind: str, name: str) -> VsnEntry:
    return next(e for e in report.entries if (e.kind, e.name) == (kind, name))


def _seed_mean(variable: str) -> list[float]:
    one, two = _weights(1, _D), _weights(2, _D)
    return [(one[d][variable] + two[d][variable]) / 2 for d in _D]


def test_vsn_per_decision_seed_mean_then_percentiles() -> None:
    report = _summary()

    entry = _entry(report, "variable", "rsi_14")
    values = _seed_mean("rsi_14")
    assert (entry.p10, entry.p50, entry.p90) == pytest.approx(
        (linear_quantile(values, 0.1), linear_quantile(values, 0.5), linear_quantile(values, 0.9))
    )
    assert entry.n_decisions == len(_D)
    assert entry.family == "technical"
    assert report.status == "ok"


def test_vsn_family_is_the_sum_of_its_variables() -> None:
    report = _summary()

    entry = _entry(report, "family", "price")
    sums = [a + b for a, b in zip(_seed_mean("log_return"), _seed_mean("range_pct"), strict=True)]
    assert entry.p50 == pytest.approx(linear_quantile(sums, 0.5))
    assert entry.p10 == pytest.approx(linear_quantile(sums, 0.1))
    assert {e.name for e in report.entries if e.kind == "family"} == {
        "price",
        "technical",
        "sentiment",
        "fundamental",
    }
    assert _entry(report, "family", "sentiment").p90 == 0.0  # nenhuma variável da família


def test_non_family_variables_reported_apart() -> None:
    report = _summary()

    entry = _entry(report, "variable", "relative_time_idx")
    assert entry.family == "none"
    assert ("family", "none") not in {(e.kind, e.name) for e in report.entries}


@pytest.mark.parametrize(
    ("damage", "message"),
    [("missing-seed", "seed 2 has no vsn weights"), ("other-decisions", "decisions differ")],
)
def test_incoherent_reductions_are_undefined(damage: str, message: str) -> None:
    reductions = _reductions()
    if damage == "missing-seed":
        reductions = [r for r in reductions if r.seed != 2]  # noqa: PLR2004
    else:
        reductions[-1] = VsnRunWeights(
            run_id="r21", seed=2, fold_index=1, weights=_weights(2, _D[3:5])
        )
    report = _summary(reductions)
    assert report.status == "undefined"
    assert message in str(report.reason)
    assert report.entries == ()


def test_vsn_label_is_exact() -> None:
    assert VSN_LABEL == "horizonte-invariante; descreve quanto o modelo usa cada família"
    assert _summary().label == VSN_LABEL
