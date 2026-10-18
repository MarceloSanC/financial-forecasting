"""A correção depende só do calib dedicado (Stage 7.2, Task 08) — concept §5 I7.

Mudar qualquer valor ou a grade dos pontos de teste não muda nenhuma correção
(propriedade, 50 perturbações de `random.Random(20261017)`); mudar um valor do calib
muda (não vacuidade).
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
    ConformalUnitResult,
)

_SEED = 20261017
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_PAIRS = ((0.02, 0.98), (0.1, 0.9), (0.25, 0.75))
_VARIANTS = ("split_cqr_asymmetric_unweighted_v1", "nexcp_fixed_geometric_weights_v1")
_START = datetime(2020, 1, 6, 21, tzinfo=UTC)
_N_CALIB = 120
_N_TEST = 10


def _ts(day: int) -> str:
    return (_START + timedelta(days=day)).isoformat()


def _grid(rng: random.Random) -> dict[float, float]:
    center = rng.uniform(-0.01, 0.01)
    width = rng.uniform(0.05, 0.1)
    return {level: center + (level - 0.5) * width for level in _LEVELS}


def _unit(rng: random.Random, calib: tuple[ConformalPointInput, ...]) -> ConformalUnitInput:
    test = tuple(
        ConformalPointInput(
            decision_timestamp=_ts(_N_CALIB + 2 + j),
            target_timestamp=_ts(_N_CALIB + 3 + j),
            grid=_grid(rng),
            realized=None if rng.random() < 0.5 else rng.gauss(0, 1),  # noqa: PLR2004
        )
        for j in range(_N_TEST)
    )
    return ConformalUnitInput(fold_index=0, seed=1, horizon=1, calib=calib, test=test)


def _calib(rng: random.Random) -> tuple[ConformalPointInput, ...]:
    return tuple(
        ConformalPointInput(
            decision_timestamp=_ts(i),
            target_timestamp=_ts(i + 1),
            grid=_grid(rng),
            realized=rng.gauss(0.0, 0.03),
        )
        for i in range(_N_CALIB)
    )


def _corrections(unit: ConformalUnitInput) -> list[tuple[object, ...]]:
    command = CalibrateConformalCommand(
        units=(unit,), pairs=_PAIRS, variants=_VARIANTS, nexcp_rho=0.99
    )
    rows: tuple[ConformalUnitResult, ...] = CalibrateConformal()(command).units
    return [(r.variant, r.lower_level, r.status, r.lower, r.upper, r.lower_beta) for r in rows]


def test_corrections_invariant_to_any_test_value() -> None:
    rng = random.Random(_SEED)
    calib = _calib(rng)
    reference = _corrections(_unit(rng, calib))
    for _ in range(50):
        assert _corrections(_unit(rng, calib)) == reference


def test_changing_a_calib_value_changes_the_correction() -> None:
    rng = random.Random(_SEED)
    calib = list(_calib(rng))
    unit = _unit(rng, tuple(calib))
    reference = _corrections(unit)
    # empurra um realizado para muito acima de toda grade: o escore superior desse
    # ponto vira o maior, e as correções superiores da cauda 0,02 mudam
    point = calib[60]
    calib[60] = ConformalPointInput(
        decision_timestamp=point.decision_timestamp,
        target_timestamp=point.target_timestamp,
        grid=point.grid,
        realized=10.0,
    )
    changed = _corrections(ConformalUnitInput(0, 1, 1, tuple(calib), unit.test))
    assert changed != reference
