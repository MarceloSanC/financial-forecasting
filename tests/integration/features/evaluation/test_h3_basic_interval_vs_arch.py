"""O intervalo básico de H3 é o `arch.conf_int(method="basic")` (Stage 7.3, Task 25; I13).

Oráculo: o `IIDBootstrap` do `arch` 8.0.0 com os MESMOS índices de reamostragem (a
subclasse devolve as linhas da `BootstrapIndices` na ordem) e a função Δ_f das quatro
famílias sobre a matriz T x 8 das séries d_t. Nenhuma réplica tem Σ* <= 0 (todas as
séries positivas), então a regra de infinitos (I14) não entra.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from arch.bootstrap import IIDBootstrap

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContribution,
    linear_quantile,
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

pytestmark = pytest.mark.integration

_KEYS = [(f, h) for f in H3_FAMILIES for h in (1, 7)]


class _FixedIndices(IIDBootstrap):  # type: ignore[misc]
    """`IIDBootstrap` que reamostra pelas linhas dadas, na ordem."""

    def __init__(self, data: np.ndarray, rows: list[list[int]]) -> None:
        super().__init__(data)
        self._rows: Iterator[list[int]] = iter(rows)

    def update_indices(self) -> Any:  # noqa: ANN401
        return np.asarray(next(self._rows), dtype=np.int64)


def _deltas(x: np.ndarray) -> np.ndarray:
    means = dict(zip(_KEYS, x.mean(axis=0), strict=True))
    totals = {h: sum(means[(f, h)] for f in H3_FAMILIES) for h in (1, 7)}
    return np.array([means[(f, 7)] / totals[7] - means[(f, 1)] / totals[1] for f in H3_FAMILIES])


def test_basic_interval_equals_arch_conf_int_basic() -> None:
    rng = random.Random(129)
    n, reps, level = 40, 1000, 0.9875
    series = {key: tuple(rng.uniform(0.1, 3.0) for _ in range(n)) for key in _KEYS}
    rows = [[rng.randrange(n) for _ in range(n)] for _ in range(reps)]
    differentials = FamilyLossDifferentials(
        method="permutation",
        families=H3_FAMILIES,
        horizons=(1, 7),
        decision_timestamps=tuple(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)),
        differentials=series,
        seed_importances={},
        permutation_importances={},
    )
    bootstrap = BootstrapIndices(
        scheme=BootstrapScheme.STATIONARY,
        block_size=1,
        seed=129,
        n_obs=n,
        generator="hand-made",
        indices=tuple(tuple(row) for row in rows),
    )

    report = FamilyContribution.evaluate(differentials, bootstrap=bootstrap, level=level)

    data = np.array([[series[key][t] for key in _KEYS] for t in range(n)])
    oracle = _FixedIndices(data, rows).conf_int(_deltas, reps=reps, method="basic", size=level)
    assert sum(report.nonpositive_replicas.values()) == 0
    for position, family in enumerate(H3_FAMILIES):
        share = next(s for s in report.shares if s.family == family)
        assert share.lower == pytest.approx(float(oracle[0, position]), abs=1e-12)
        assert share.upper == pytest.approx(float(oracle[1, position]), abs=1e-12)


def test_linear_quantile_equals_numpy_percentile_on_finite() -> None:
    rng = random.Random(3)
    values = [rng.gauss(0.0, 1.0) for _ in range(997)]
    for probability in (0.0, 0.00625, 0.025, 0.5, 0.975, 0.99375, 1.0):
        expected = float(np.percentile(values, 100 * probability))
        assert linear_quantile(values, probability) == pytest.approx(expected, abs=1e-12)
