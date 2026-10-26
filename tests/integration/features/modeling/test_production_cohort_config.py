"""O modelo de produção versionado (Stage 8.4, Task 03 / CA5; ADR 8.4.0001 item 2).

Lê os dois arquivos reais de `config/cohorts/` pelo leitor do `modeling`. Prova: o
modelo de produção é o confirmatório r0 com só os campos declarados trocados (nome,
`n_folds`, seeds, `dataset_start`) e sem impressão digital do dado; não está
congelado, então o `run` confirmatório o recusa; e a rodada derivada dele está
congelada.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortNotFrozenError,
)
from tests.unit.features.modeling.application import test_run_confirmatory_cohort as runner

cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)

_COHORTS = Path(__file__).resolve().parents[4] / "config" / "cohorts"


def _load(name: str) -> Any:  # noqa: ANN401
    return cohort_file.load(_COHORTS / f"{name}.toml")


def test_production_model_is_r0_with_only_the_declared_changes() -> None:
    confirmatory = _load("aapl_confirmatory")
    production = _load("aapl_production")

    expected = replace(
        confirmatory,
        name="aapl_production",
        geometry=replace(confirmatory.geometry, n_folds=1),
        seeds=(1, 2, 3),
        dataset_start=date(2010, 4, 20),
        dataset_fingerprint=None,
    )

    assert production == expected
    assert confirmatory.revision == 0


def test_production_model_is_not_frozen_and_the_confirmatory_run_refuses_it() -> None:
    production = _load("aapl_production")

    assert not production.is_frozen()
    harness = runner._Harness()
    with pytest.raises(CohortNotFrozenError):
        harness.run(production)
    assert harness.calls == []


def test_a_round_derived_from_the_model_is_frozen() -> None:
    production = _load("aapl_production")

    round_spec = production.production_round("d" * 64)

    assert round_spec.is_frozen()
    assert cohort_file.parse(cohort_file.dump(round_spec)) == round_spec
