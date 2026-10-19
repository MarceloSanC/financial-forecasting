"""Arquivo do cohort de ablação (Stage 7.3, Task 06; CA3 carga e recusas, I4, C2).

Arquivos em `tmp_path` e base sintética (o `_spec()` de `test_cohort_spec.py`). O módulo
vive sob `adapters/in/` (keyword `in`): carregado por `importlib` (LAYOUT §8).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    ABLATION_FEATURE_SET_NAME,
    AblationCohortSpec,
    AblationConfiguration,
    AblationDeclarationError,
    excluded_family_of,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    registry_family_partition,
    tft_feature_set_hash,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from tests.unit.features.modeling.application.test_cohort_spec import _spec as _base_spec

ablation_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.ablation_cohort_file"
)
AblationFileError = ablation_file.AblationFileError

pytestmark = pytest.mark.unit

_BASE = _base_spec()
_BASE_HASH = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=_BASE.hash_payload())
_BASE_FILE = "config/cohorts/base.toml"


def _draft(**overrides: Any) -> AblationCohortSpec:  # noqa: ANN401
    fields: dict[str, Any] = {
        "name": "aapl_ablation",
        "revision": 0,
        "base_cohort_file": _BASE_FILE,
        "base_cohort_id": _BASE.cohort_id(_BASE_HASH),
        "base_cohort_hash": _BASE_HASH.value,
        "feature_set_name": ABLATION_FEATURE_SET_NAME,
        "configurations": tuple(
            AblationConfiguration.of(
                name, feature_set_hash=tft_feature_set_hash(excluded_family_of(name))
            )
            for name in ABLATION_CONFIGURATIONS
        ),
        "family_partition": registry_family_partition(),
        "seeds": (),
        "device": "rocm",
        "torch_build": None,
    }
    fields.update(overrides)
    return AblationCohortSpec(**fields)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ablation.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _load(path: Path, base: Any = _BASE) -> AblationCohortSpec:  # noqa: ANN401
    requested: list[str] = []

    def load_base(declared: str) -> Any:  # noqa: ANN401
        requested.append(declared)
        return base

    spec = ablation_file.load_ablation_cohort(
        path, hasher=CanonicalJsonHasher(), load_base=load_base
    )
    assert requested == [_BASE_FILE]
    return spec


def test_draft_shape_loads_unfrozen(tmp_path: Path) -> None:
    text = ablation_file.dump_ablation_cohort(_draft())
    assert "torch_build" not in text
    spec = _load(_write(tmp_path, text))
    assert spec == _draft()
    assert not spec.is_frozen()


def test_base_hash_mismatch_refused(tmp_path: Path) -> None:
    other_base = _base_spec(revision=1)
    path = _write(tmp_path, ablation_file.dump_ablation_cohort(_draft()))
    with pytest.raises(AblationDeclarationError, match="hashes to"):
        _load(path, base=other_base)


def test_base_cohort_id_mismatch_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, ablation_file.dump_ablation_cohort(_draft(base_cohort_id="x-r0-0")))
    with pytest.raises(AblationDeclarationError, match="base cohort id"):
        _load(path)


def test_partition_different_from_registry_refused(tmp_path: Path) -> None:
    partition = dict(registry_family_partition())
    moved = partition["price"][-1]
    partition["price"] = partition["price"][:-1]
    partition["technical"] = (*partition["technical"], moved)
    path = _write(tmp_path, ablation_file.dump_ablation_cohort(_draft(family_partition=partition)))
    with pytest.raises(AblationDeclarationError, match=r"\[partition\]"):
        _load(path)


def test_declared_subset_hash_different_from_registry_refused(tmp_path: Path) -> None:
    configurations = list(_draft().configurations)
    configurations[2] = AblationConfiguration.of("minus_technical", feature_set_hash="0" * 64)
    path = _write(
        tmp_path, ablation_file.dump_ablation_cohort(_draft(configurations=tuple(configurations)))
    )
    with pytest.raises(AblationDeclarationError, match="minus_technical"):
        _load(path)


@pytest.mark.parametrize(
    ("snippet", "field"),
    [
        ('tft_params = "x"\n', "tft_params"),
        ('geometry = "x"\n', "geometry"),
        ("horizons = [1, 7]\n", "horizons"),
        ("quantile_levels = [0.5]\n", "quantile_levels"),
        ('dataset_fingerprint = "x"\n', "dataset_fingerprint"),
        ('pipeline_version = "2"\n', "pipeline_version"),
    ],
)
def test_procedure_fields_in_the_ablation_file_refused(
    tmp_path: Path, snippet: str, field: str
) -> None:
    text = snippet + ablation_file.dump_ablation_cohort(_draft())
    with pytest.raises(AblationFileError, match=f"unknown field '{field}'"):
        _load(_write(tmp_path, text))


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("[base]\n", '[base]\ngeometry = "x"\n', "base.geometry"),
        (
            "[configurations.full]\n",
            '[configurations.full]\nmodel_version = "tft_quantile"\n',
            "configurations.full.model_version",
        ),
        ("[configurations.full]\n", "[configurations.full_v2]\n", "configurations.full_v2"),
    ],
)
def test_unknown_key_refused_with_dotted_path(
    tmp_path: Path, old: str, new: str, field: str
) -> None:
    text = ablation_file.dump_ablation_cohort(_draft()).replace(old, new, 1)
    with pytest.raises(AblationFileError, match=f"'{field}'"):
        _load(_write(tmp_path, text))


def test_confirmatory_feature_set_name_in_the_file_refused(tmp_path: Path) -> None:
    """C2-1: `feature_set_name = "fs_all"` no TOML é erro tipado, não spec carregado."""
    text = ablation_file.dump_ablation_cohort(_draft()).replace(
        'feature_set_name = "fs_all_ablation"', 'feature_set_name = "fs_all"'
    )
    with pytest.raises(AblationFileError, match="feature_set_name"):
        _load(_write(tmp_path, text))


def test_missing_required_field_refused(tmp_path: Path) -> None:
    text = ablation_file.dump_ablation_cohort(_draft()).replace('device = "rocm"\n', "")
    with pytest.raises(AblationFileError, match="missing required field 'device'"):
        _load(_write(tmp_path, text))


def test_dump_then_load_round_trip(tmp_path: Path) -> None:
    frozen = _draft().with_freeze(seeds=(1, 2, 3), torch_build="2.13.0+rocm6.4")
    path = _write(tmp_path, ablation_file.dump_ablation_cohort(frozen))
    loaded = _load(path)
    assert loaded == frozen
    assert loaded.is_frozen()
