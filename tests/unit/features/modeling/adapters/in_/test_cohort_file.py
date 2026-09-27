"""Unit test do arquivo do cohort (Stage 5.5, Task 27 / concept D1 e §6).

Prova: `parse(dump(spec)) == spec` para o rascunho e para o congelado (o
`dump` sem dependência nova é validado pela ida e volta com `tomllib`); campo
ausente, campo desconhecido, tipo errado, seed repetida e revisão negativa
erguem `CohortFileError` nomeando o campo.

O módulo vive sob `adapters/in/` (keyword `in`): carregado por `importlib`
(LAYOUT §8); a pasta deste teste é `in_` pelo mesmo motivo.
"""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)

cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)
CohortFileError = cohort_file.CohortFileError

_DRAFT_PLAN = SweepPlan(
    tft_space=(
        SearchDimension(name="hidden_size", low=8, high=64, kind="int", log=True),
        SearchDimension(name="dropout", low=0.0, high=0.3, kind="float"),
        SearchDimension(name="learning_rate", low=1e-4, high=0.05, kind="float", log=True),
    ),
    tft_base_params=TftTrainingParams(seed=0, max_epochs=30),
    gbm_space=(
        SearchDimension(name="num_leaves", low=8, high=128, kind="int", log=True),
        SearchDimension(name="learning_rate", low=0.01, high=0.3, kind="float", log=True),
    ),
    gbm_base_params=GbmTrainingParams(seed=0),
    n_trials=None,
    sampler_seed=2026,
)


def _draft() -> CohortSpec:
    return CohortSpec(
        name="aapl_confirmatory",
        revision=0,
        asset_id="AAPL",
        feature_set_name="fs_all",
        feature_set_hash="f" * 64,
        pipeline_version="2",
        horizons=(1, 7),
        quantile_levels=(0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98),
        geometry=CohortGeometry(n_folds=6, test_size=252, val_size=252, calib_size=252, embargo=7),
        device="cpu",
        seeds=(),
        sweep=_DRAFT_PLAN,
        tft_params=None,
        gbm_params=None,
        baseline_specs=BaselineSpec.canonical_five(),
        provenance=None,
        dataset_fingerprint=None,
    )


def _frozen() -> CohortSpec:
    return replace(
        _draft(),
        seeds=(11, 22, 33, 44, 55),
        sweep=replace(_DRAFT_PLAN, n_trials=40),
        tft_params=TftTrainingParams(seed=0, hidden_size=24, dropout=0.137, learning_rate=3.3e-4),
        gbm_params=GbmTrainingParams(seed=0, num_leaves=17, learning_rate=0.0421),
        provenance=SweepProvenance(
            tft_study_id="tft-study",
            tft_best_trial=4,
            tft_best_objective=0.012345678901,
            gbm_study_id="gbm-study",
            gbm_best_trial=7,
            gbm_best_objective=0.011,
            dataset_fingerprint="a" * 64,
        ),
        dataset_fingerprint="a" * 64,
    )


@pytest.mark.unit
@pytest.mark.parametrize("make", [_draft, _frozen], ids=["draft", "frozen"])
def test_parse_of_dump_is_the_identity(make: Callable[[], CohortSpec]) -> None:
    spec = make()

    text = cohort_file.dump(spec)

    assert cohort_file.parse(text) == spec
    tomllib.loads(text)  # o texto é TOML válido por si só


@pytest.mark.unit
def test_draft_dump_omits_the_freeze_fields() -> None:
    raw = tomllib.loads(cohort_file.dump(_draft()))

    for key in ("tft_params", "gbm_params", "provenance", "dataset_fingerprint"):
        assert key not in raw
    assert "n_trials" not in raw["sweep"]
    assert raw["seeds"] == []


@pytest.mark.unit
def test_load_names_the_file_in_the_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("name = ", encoding="utf-8")

    with pytest.raises(CohortFileError, match=r"broken\.toml"):
        cohort_file.load(path)


@pytest.mark.unit
def test_load_reads_a_dumped_file(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text(cohort_file.dump(_frozen()), encoding="utf-8")

    assert cohort_file.load(path) == _frozen()


def _without(text: str, line_prefix: str) -> str:
    lines = text.splitlines()
    kept = [line for line in lines if not line.startswith(line_prefix)]
    assert len(kept) == len(lines) - 1, line_prefix
    return "\n".join(kept) + "\n"


def _replaced(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


_BASE = cohort_file.dump(_frozen())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "field"),
    [
        (_without(_BASE, "asset_id = "), "'asset_id'"),
        (_without(_BASE, "n_folds = "), "'geometry.n_folds'"),
        (_without(_BASE, "sampler_seed = "), "'sweep.sampler_seed'"),
        (_without(_BASE, "window = "), "baselines"),
    ],
    ids=["top", "geometry", "sweep", "baseline"],
)
def test_missing_field_is_named(text: str, field: str) -> None:
    with pytest.raises(CohortFileError, match=field):
        cohort_file.parse(text)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("revision = 0", 'revision = "0"', "'revision'"),
        ("n_folds = 6", "n_folds = 6.0", "'geometry.n_folds'"),
        ("device = ", "device = 1\nx_device = ", "x_device"),
        ("seeds = [11, 22", 'seeds = ["11", 22', r"'seeds\[0\]'"),
        ("sampler_seed = 2026", "sampler_seed = true", "'sweep.sampler_seed'"),
        ("num_leaves = 17", "num_leaves = 17\nnum_leafs = 3", "num_leafs"),
    ],
    ids=["str-for-int", "float-for-int", "unknown-top", "array-item", "bool-for-int", "typo"],
)
def test_wrong_type_or_unknown_key_is_named(old: str, new: str, field: str) -> None:
    with pytest.raises(CohortFileError, match=field):
        cohort_file.parse(_replaced(_BASE, old, new))


@pytest.mark.unit
def test_integer_is_accepted_where_a_float_is_declared() -> None:
    text = _replaced(_BASE, "gbm_best_objective = 0.011", "gbm_best_objective = 1")

    assert cohort_file.parse(text).provenance.gbm_best_objective == 1.0


@pytest.mark.unit
def test_repeated_seed_is_rejected_naming_the_field() -> None:
    text = _replaced(_BASE, "seeds = [11, 22", "seeds = [11, 11")

    with pytest.raises(CohortFileError, match="seeds"):
        cohort_file.parse(text)


@pytest.mark.unit
def test_negative_revision_is_rejected_naming_the_field() -> None:
    text = _replaced(_BASE, "revision = 0", "revision = -1")

    with pytest.raises(CohortFileError, match="revision"):
        cohort_file.parse(text)


@pytest.mark.unit
def test_invalid_value_inside_a_table_names_the_table() -> None:
    text = _replaced(_BASE, "num_leaves = 17", "num_leaves = 1")

    with pytest.raises(CohortFileError, match=r"\[gbm_params\]"):
        cohort_file.parse(text)


@pytest.mark.unit
def test_invalid_toml_is_a_cohort_file_error() -> None:
    with pytest.raises(CohortFileError, match="not valid TOML"):
        cohort_file.parse("name = = 1")


@pytest.mark.unit
def test_non_finite_float_cannot_be_written() -> None:
    frozen = _frozen()
    assert frozen.provenance is not None
    nan_provenance = replace(frozen.provenance, gbm_best_objective=float("nan"))
    spec = replace(frozen, provenance=nan_provenance)

    with pytest.raises(CohortFileError, match="non-finite"):
        cohort_file.dump(spec)


@pytest.mark.unit
def test_strings_with_control_and_non_ascii_characters_round_trip() -> None:
    """F4 (Checkpoint C 24-31): U+007F cru é proibido em string básica TOML."""
    spec = replace(_draft(), name='odd\x7f"name\\ção\n')

    text = cohort_file.dump(spec)

    assert text.isascii()
    assert cohort_file.parse(text) == spec
