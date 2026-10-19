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


# --- Task 32: o rascunho cego da r3 (CA11 rascunho; I17, I18; ADR 7.3.0005 itens 1-2) ------

_PREREGISTRATION = _REPO / "config" / "preregistration"
_DRAFT = _REPO / "docs" / "stages" / "7.3-explainability" / "aapl_confirmatory-r3.draft.toml"
_FILLED = _PREREGISTRATION / "aapl_confirmatory-r3.toml"
_AMENDMENT = ("revision", "amends", "justification", "blind_status")
_SENTINEL = "__FILL_AFTER_FREEZE__"
_FILLED_FIELDS = ("cohort_id", "cohort_hash", "seeds")


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _reference(payload: dict[str, Any]) -> str:
    from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (  # noqa: PLC0415
        Preregistration,
    )
    from financial_forecasting.shared.domain.value_objects.preregistration_hash import (  # noqa: PLC0415
        PreregistrationHash,
    )

    plan = Preregistration.from_mapping(payload)
    return plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )


def _filled(draft: dict[str, Any]) -> dict[str, Any]:
    """O rascunho com valores sintéticos nas três sentinelas (nada do cohort real)."""
    import copy  # noqa: PLC0415

    filled = copy.deepcopy(draft)
    filled["h3"]["ablation"].update(
        cohort_id="synthetic_ablation-r0-0123456789ab", cohort_hash="c" * 64, seeds=[1, 2, 3]
    )
    return filled


def test_r3_draft_is_r2_plus_amendment_plus_h3() -> None:
    draft, r2 = _toml(_DRAFT), _toml(_PREREGISTRATION / "aapl_confirmatory-r2.toml")
    common = [key for key in r2 if key not in _AMENDMENT]
    assert {key: draft[key] for key in common} == {key: r2[key] for key in common}
    assert set(draft) == set(r2) | {"h3"}
    assert draft["revision"] == 3  # noqa: PLR2004
    assert draft["amends"] == _reference(r2)
    assert draft["blind_status"] == "blinded"
    assert draft["justification"].strip()
    assert draft["justification"] != r2["justification"]


def test_r3_draft_filled_with_synthetic_values_parses() -> None:
    from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (  # noqa: PLC0415
        Preregistration,
    )

    plan = Preregistration.from_mapping(_filled(_toml(_DRAFT)))
    assert plan.revision == 3  # noqa: PLR2004
    assert plan.h3 is not None
    assert plan.h3.interval_level == 0.9875  # noqa: PLR2004
    assert plan.conformal is not None and plan.profile_parameters is not None


def test_r3_draft_unfilled_is_refused() -> None:
    """C11: o rascunho com as sentinelas não vira plano."""
    from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (  # noqa: PLC0415
        Preregistration,
    )

    draft = _toml(_DRAFT)
    assert {draft["h3"]["ablation"][field] for field in _FILLED_FIELDS} == {_SENTINEL}
    with pytest.raises(ValueError, match="draft sentinel"):
        Preregistration.from_mapping(draft)


def test_partition_hash_literal_recomputes() -> None:
    from financial_forecasting.shared.domain.value_objects.family_partition_hash import (  # noqa: PLC0415
        FamilyPartitionHash,
    )

    block = _toml(_DRAFT)["h3"]
    partition = {f: tuple(v) for f, v in block["partition"].items() if f != "partition_hash"}
    recomputed = FamilyPartitionHash.compute(
        hasher=CanonicalJsonHasher(),
        feature_set_hash=block["feature_set_hash"],
        partition=partition,
    )
    assert recomputed.value == block["partition"]["partition_hash"]
    assert block["feature_set_hash"] == tft_feature_set_hash(None)


def test_r3_partition_equals_registry_and_ablation_draft() -> None:
    block = _toml(_DRAFT)["h3"]["partition"]
    partition = {f: tuple(v) for f, v in block.items() if f != "partition_hash"}
    ablation = {f: tuple(v) for f, v in _toml(_ABLATION)["partition"].items()}
    assert partition == registry_family_partition() == ablation


def test_r3_k_p_seed_algorithm_equal_the_inference_plan() -> None:
    """I17: o VALOR da r3 é a trava de K_p e da semente (o catálogo só fixa o algoritmo)."""
    from financial_forecasting.features.inference.domain.value_objects.permutation_plan import (  # noqa: PLC0415
        K_P,
        PERMUTATION_ALGORITHM,
        PERMUTATION_SEED,
    )

    block = _toml(_DRAFT)["h3"]
    assert (block["k_p"], block["permutation_seed"], block["permutation_algorithm"]) == (
        K_P,
        PERMUTATION_SEED,
        PERMUTATION_ALGORITHM,
    )


def _frozen_ablation_values(spec: Any) -> dict[str, object]:  # noqa: ANN401
    """O que a r3 tem de declarar do cohort de ablação CONGELADO: id, hash e seeds (C8-6)."""
    assert spec.is_frozen(), "the ablation spec must be frozen (L4) before the r3 (L7)"
    digest = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    return {
        "cohort_id": spec.cohort_id(digest),
        "cohort_hash": digest.value,
        "seeds": list(spec.seeds),
    }


def test_frozen_ablation_values_come_from_the_spec_hash() -> None:
    """A regra da L7 sobre um spec congelado sintético (o real só existe depois da L4)."""
    from tests.unit.features.modeling.adapters.in_.test_ablation_cohort_file import (  # noqa: PLC0415
        _draft,
    )

    spec = _draft().with_freeze(seeds=(1, 2, 3), torch_build="2.5.1+rocm6.2")
    values = _frozen_ablation_values(spec)
    digest = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    assert values == {
        "cohort_id": f"aapl_ablation-r0-{digest.value[:12]}",
        "cohort_hash": digest.value,
        "seeds": [1, 2, 3],
    }
    with pytest.raises(AssertionError, match="must be frozen"):
        _frozen_ablation_values(_draft())


@pytest.mark.skipif(not _FILLED.exists(), reason="a r3 preenchida só existe no Linux (L7)")
def test_filled_r3_differs_from_draft_only_in_h3_ablation() -> None:
    draft, filled = _toml(_DRAFT), _toml(_FILLED)
    draft_ablation = dict(draft["h3"].pop("ablation"))
    filled_ablation = dict(filled["h3"].pop("ablation"))
    assert filled == draft
    # C8-6: os três valores são os do spec congelado pelo loader, com o hash recalculado
    spec = ablation_file.load_ablation_cohort(
        _ABLATION, hasher=CanonicalJsonHasher(), load_base=_load_base
    )
    expected = _frozen_ablation_values(spec)
    assert {field: filled_ablation[field] for field in _FILLED_FIELDS} == expected
    for field in _FILLED_FIELDS:
        draft_ablation.pop(field)
        assert filled_ablation.pop(field) != _SENTINEL, field
    assert filled_ablation == draft_ablation


@pytest.mark.parametrize("revision", [0, 1, 2])
def test_r0_to_r2_files_unchanged(revision: int) -> None:
    """Cada revisão ancorada continua com a referência que a sua âncora publicou (I18)."""
    plan = _toml(_PREREGISTRATION / f"aapl_confirmatory-r{revision}.toml")
    anchor = _toml(_PREREGISTRATION / f"aapl_confirmatory-r{revision}.anchor.toml")
    assert anchor["tag"] == f"preregistration/{_reference(plan)}"
