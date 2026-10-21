"""Unit do `JointContribution` — o bootstrap conjunto de H3 (Stage 7.3, C8-1/C8-15; I12).

ADR 7.3.0005 H3-BLOCK (`max_7_ceil_max_bsb_joint_16_series_v1`): o bloco é o das 16
séries dos dois métodos; sem um deles, nenhum bootstrap roda.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services.joint_contribution import (
    JOINT_BLOCK_NEEDS_BOTH,
    JointContribution,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    block_length_rule,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend

pytestmark = pytest.mark.unit

_N = 20


class _Backend(FakeMcsBackend):
    """b̂ distinto por série (1, 2, …, na ordem das chamadas) e registro das chamadas."""

    def __init__(self, *, fail_at: int | None = None) -> None:
        super().__init__()
        self.series: list[tuple[float, ...]] = []
        self.indices: list[dict[str, object]] = []
        self._fail_at = fail_at

    def optimal_block_length(self, *, series: Sequence[float]) -> float:
        self.series.append(tuple(series))
        if self._fail_at is not None and len(self.series) == self._fail_at:
            raise ZeroDivisionError("singular")
        return float(len(self.series))

    def bootstrap_indices(self, **kwargs: object) -> BootstrapIndices:  # type: ignore[override]
        self.indices.append(dict(kwargs))
        return super().bootstrap_indices(**kwargs)  # type: ignore[arg-type]


def _differentials(method: str, seed: int) -> FamilyLossDifferentials:
    rng = random.Random(f"{method}|{seed}")
    return FamilyLossDifferentials(
        method=method,
        families=H3_FAMILIES,
        horizons=(1, 7),
        decision_timestamps=tuple(f"2024-01-{i + 1:02d}T00:00:00+00:00" for i in range(_N)),
        differentials={
            (f, h): tuple(rng.uniform(0.01, 0.05) for _ in range(_N))
            for f in H3_FAMILIES
            for h in (1, 7)
        },
        seed_importances={},
        permutation_importances={},
    )


def _evaluate(backend: _Backend, *, permutation: bool = True, ablation: bool = True) -> object:
    return JointContribution.evaluate(
        permutation=_differentials("permutation", 1) if permutation else None,
        ablation=_differentials("loco", 2) if ablation else None,
        permutation_reason=None if permutation else "permutation assembly failed",
        ablation_reason=None if ablation else "configuration X seed 1 has no run (I11)",
        backend=backend,
        reps=50,
        seed=129,
        level=0.9875,
    )


def test_block_is_the_max_over_the_16_series_with_one_indices_call() -> None:
    """C8-3: b̂ = 1..16 na ordem permutação → LOCO; o máximo (16) é de uma série LOCO."""
    backend = _Backend()
    result = _evaluate(backend)
    assert len(backend.series) == 16  # noqa: PLR2004
    assert result.max_block_estimate == 16.0  # type: ignore[attr-defined]  # noqa: PLR2004
    assert result.block_length == block_length_rule(horizon=7, max_estimate=16.0)  # type: ignore[attr-defined]
    [call] = backend.indices
    assert (call["n_obs"], call["reps"], call["seed"]) == (_N, 50, 129)
    assert call["block_size"] == 16  # noqa: PLR2004
    assert call["scheme"] is BootstrapScheme.STATIONARY
    assert result.permutation.status == "ok"  # type: ignore[attr-defined]
    assert result.ablation.status == "ok"  # type: ignore[attr-defined]


@pytest.mark.parametrize("missing", ["permutation", "ablation"])
def test_without_one_method_no_bootstrap_runs(missing: str) -> None:
    """C8-1: sem um dos métodos não há bloco conjunto — nenhuma chamada ao backend."""
    backend = _Backend()
    result = _evaluate(
        backend, permutation=missing != "permutation", ablation=missing != "ablation"
    )
    assert backend.series == []
    assert backend.indices == []
    assert result.block_length is None  # type: ignore[attr-defined]
    assert result.max_block_estimate is None  # type: ignore[attr-defined]
    defined = result.ablation if missing == "permutation" else result.permutation  # type: ignore[attr-defined]
    undefined = result.permutation if missing == "permutation" else result.ablation  # type: ignore[attr-defined]
    assert defined.status == "undefined"
    assert defined.reason == JOINT_BLOCK_NEEDS_BOTH
    assert "failed" in str(undefined.reason) or "has no run" in str(undefined.reason)
    # C8-11: o método montado mantém a importância das séries d_t
    assert len(defined.importance) == 8  # noqa: PLR2004
    assert undefined.importance == {}


@pytest.mark.parametrize("fail_at", [1, 16])
def test_arithmetic_error_on_any_series_makes_both_undefined(fail_at: int) -> None:
    backend = _Backend(fail_at=fail_at)
    result = _evaluate(backend)
    for report in (result.permutation, result.ablation):  # type: ignore[attr-defined]
        assert report.status == "undefined"
        assert str(report.reason).startswith("bootstrap undefined:")
        assert "ZeroDivisionError" in str(report.reason)
    assert backend.indices == []
