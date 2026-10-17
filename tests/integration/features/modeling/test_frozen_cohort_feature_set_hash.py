"""O cohort congelado da 5.5 continua íntegro: registry e hash (issues #151 e #122).

Teste de integração sobre **arquivos versionados** (nenhum dado): lê o cohort pelo
carregador da `modeling` (`cohort_file.load`) e compara com `feature_set_hash()` do
registry. A família de cada feature entra no hash (`feature_set_hash` serializa
`family`), e o runner do cohort recusa um hash diferente do registry
(`run_confirmatory_cohort`). Sem este teste, reclassificar uma feature (ex.: as seis
de volatilidade de `technical` para `price`, a alternativa descartada na #151)
passaria verde no CI e só quebraria ao rodar o cohort — e invalidaria o cohort já
treinado e o pré-registro da 6.5 que o citam. Mudar o registry de propósito exige
nova revisão do cohort; este teste força a decisão a ser consciente.

O segundo teste fixa o `cohort_hash` do arquivo congelado no valor citado pelo
pré-registro (`config/preregistration/aapl_confirmatory-r*.toml`). Campo novo no
`CohortSpec` (ex.: `dataset_start`, #122) que entre no payload mesmo ausente
mudaria esse hash e desancoraria a 5.5 e a 6.5 sem nenhum outro teste falhar.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

pytestmark = pytest.mark.integration

# `in` é palavra reservada: o pacote `adapters/in/` entra por `importlib` (LAYOUT §8).
cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)

_REPO = Path(__file__).resolve().parents[4]
_COHORT_FILE = _REPO / "config" / "cohorts" / "aapl_confirmatory.toml"
# O hash que a 5.5 ancorou e o pré-registro da 6.5 cita (docs/preregistration).
_FROZEN_COHORT_HASH = "665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1"


def test_registry_hash_matches_the_frozen_cohort() -> None:
    spec = cohort_file.load(_COHORT_FILE)

    assert spec.feature_set_hash == feature_set_hash(), (
        "o registry de features divergiu do cohort congelado: mudar family/qualquer "
        "campo de spec exige nova revisão do cohort (ADR 5.5.0001), não só o snapshot"
    )


def test_the_frozen_cohort_keeps_its_anchored_hash() -> None:
    spec = cohort_file.load(_COHORT_FILE)
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())

    assert cohort_hash.value == _FROZEN_COHORT_HASH, (
        "o hash do cohort congelado mudou: campo novo do CohortSpec precisa ficar fora "
        "do payload quando ausente (#122), ou a mudança exige nova revisão (ADR 5.5.0001)"
    )
    assert spec.cohort_id(cohort_hash) == "aapl_confirmatory-r0-665f45d9169a"
