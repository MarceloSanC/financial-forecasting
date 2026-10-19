"""Arquivos do repo da Stage 7.3 — o rascunho do cohort de ablação e o confirmatório intacto.

Fica em `tests/architecture/` porque lê arquivos do repo (`config/cohorts/`), o que os
testes unitários não fazem (technical 7.3 §1, premissas). CA1 (hash do TOML
confirmatório inalterado) e CA3 (o rascunho real carrega, sem congelar, com a
partição da registry).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    ABLATION_FEATURE_SET_NAME,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    registry_family_partition,
    tft_feature_set_hash,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_CONFIRMATORY = "config/cohorts/aapl_confirmatory.toml"
_ABLATION = _REPO / "config" / "cohorts" / "aapl_ablation.toml"
_CONFIRMATORY_HASH = "665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1"

cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)
ablation_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.ablation_cohort_file"
)


def _load_base(declared: str) -> Any:  # noqa: ANN401
    return cohort_file.load(_REPO / declared)


def test_ablation_draft_loads_unfrozen_with_registry_partition() -> None:
    spec = ablation_file.load_ablation_cohort(
        _ABLATION, hasher=CanonicalJsonHasher(), load_base=_load_base
    )

    assert not spec.is_frozen()
    assert spec.seeds == ()
    assert spec.torch_build is None
    assert spec.device == "rocm"
    assert spec.feature_set_name == ABLATION_FEATURE_SET_NAME
    assert spec.base_cohort_file == _CONFIRMATORY
    assert spec.base_cohort_id == "aapl_confirmatory-r0-665f45d9169a"
    assert spec.base_cohort_hash == _CONFIRMATORY_HASH
    assert dict(spec.family_partition) == registry_family_partition()
    assert tuple(c.name for c in spec.configurations) == ABLATION_CONFIGURATIONS
    for configuration in spec.configurations:
        assert configuration.feature_set_hash == tft_feature_set_hash(configuration.excluded_family)


def test_confirmatory_cohort_file_hash_unchanged() -> None:
    spec = cohort_file.load(_REPO / _CONFIRMATORY)
    digest = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    assert digest.value == _CONFIRMATORY_HASH
