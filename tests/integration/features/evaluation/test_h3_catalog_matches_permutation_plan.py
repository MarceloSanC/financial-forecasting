"""O plano de permutação do catálogo de H3 é o do `inference` (Stage 7.3, Task 21; I17).

O algoritmo, o `K_p` e a semente da permutação existem em dois slices: o `bc-independence`
não deixa o `evaluation` importar o `permutation_plan` do `inference` em `src/`. Este
teste compõe os dois e trava a duplicação: o que o bloco `[h3]` aceita é exatamente o que
o `RunPermutationInference` grava. A mesma regra vale para o nome dos modelos LOCO, que
repete o `loco_model_version` do `modeling`.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    H3_RULE_CATALOG,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
)
from financial_forecasting.features.inference.domain.value_objects.permutation_plan import (
    K_P,
    PERMUTATION_ALGORITHM,
    PERMUTATION_SEED,
)
from financial_forecasting.features.modeling.domain.services.loco_identity import (
    TFT_FAMILIES,
    loco_model_version,
)
from tests.unit.features.evaluation._h3_parameters import h3_parameters

pytestmark = pytest.mark.integration


def test_catalog_algorithm_k_p_and_seed_equal_the_inference_plan() -> None:
    parameters = h3_parameters()

    assert H3_RULE_CATALOG["permutation_algorithm"] == PERMUTATION_ALGORITHM
    assert parameters.permutation_algorithm == PERMUTATION_ALGORITHM
    assert parameters.k_p == K_P
    assert parameters.permutation_seed == PERMUTATION_SEED


def test_families_and_loco_models_equal_the_modeling_ones() -> None:
    assert H3_FAMILIES == TFT_FAMILIES
    assert loco_model_version("full") == LOCO_REFERENCE_MODEL
    for family in TFT_FAMILIES:
        assert loco_model_version(f"minus_{family}") == loco_model_of(family)
