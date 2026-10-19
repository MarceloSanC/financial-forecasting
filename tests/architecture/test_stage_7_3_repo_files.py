"""Arquivos do repo da Stage 7.3 — o rascunho do cohort de ablação e o confirmatório intacto.

Fica em `tests/architecture/` porque lê arquivos do repo (`config/cohorts/`), o que os
testes unitários não fazem (technical 7.3 §1, premissas). CA1 (hash do TOML
confirmatório inalterado) e CA3 (o rascunho real carrega, sem congelar, com a
partição da registry).

O id e o hash do cohort confirmatório não são escritos aqui como literal (guarda I14 da
6.6, `test_no_test_or_script_reads_the_real_cohort`): a referência é o bloco `[cohort]`
da revisão r2 ANCORADA do pré-registro, que é a âncora pública desses valores.
"""

from __future__ import annotations

import importlib
import tomllib
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
_ANCHORED_PLAN = _REPO / "config" / "preregistration" / "aapl_confirmatory-r2.toml"


def _anchored_cohort() -> dict[str, str]:
    """O `[cohort]` da r2 ancorada: `cohort_id` e `cohort_hash` do confirmatório."""
    with _ANCHORED_PLAN.open("rb") as handle:
        block: dict[str, str] = tomllib.load(handle)["cohort"]
    return block


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
    anchored = _anchored_cohort()
    assert spec.base_cohort_id == anchored["cohort_id"]
    assert spec.base_cohort_hash == anchored["cohort_hash"]
    assert dict(spec.family_partition) == registry_family_partition()
    assert tuple(c.name for c in spec.configurations) == ABLATION_CONFIGURATIONS
    for configuration in spec.configurations:
        assert configuration.feature_set_hash == tft_feature_set_hash(configuration.excluded_family)


def test_confirmatory_cohort_file_hash_unchanged() -> None:
    spec = cohort_file.load(_REPO / _CONFIRMATORY)
    digest = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    anchored = _anchored_cohort()
    assert digest.value == anchored["cohort_hash"]
    assert spec.cohort_id(digest) == anchored["cohort_id"]
