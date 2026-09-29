"""Conftest do subpacote `gold`: reexporta a fábrica de cohort sintético.

A fábrica pura mora em `_cohort_factory.py` (módulo neutro, importável também pela
suíte de contrato — `tests/contract/features/evaluation/_gold_inputs.py` — sem importar
um conftest). Este arquivo só a reexporta para quem a procurar pelo nome antigo.
"""

from __future__ import annotations

from tests.unit.features.evaluation.gold._cohort_factory import (
    DEFAULT_HORIZONS,
    DEFAULT_SEEDS,
    FEATURE_SET,
    GOLD_LEVELS,
    Cohort,
    Special,
    add_records,
    at_point,
    drop_records,
    make_cohort,
    of_series,
    replace_records,
    replace_runs,
    run_id,
    session,
    special_point,
    targets_of,
    with_special,
)

__all__ = [
    "DEFAULT_HORIZONS",
    "DEFAULT_SEEDS",
    "FEATURE_SET",
    "GOLD_LEVELS",
    "Cohort",
    "Special",
    "add_records",
    "at_point",
    "drop_records",
    "make_cohort",
    "of_series",
    "replace_records",
    "replace_runs",
    "run_id",
    "session",
    "special_point",
    "targets_of",
    "with_special",
]
