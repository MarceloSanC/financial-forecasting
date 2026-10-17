"""O registry de features bate com o `feature_set_hash` do cohort congelado (issue #151).

Teste de integração sobre **arquivos versionados** (nenhum dado): lê o cohort pelo
carregador da `modeling` (`cohort_file.load`) e compara com `feature_set_hash()` do
registry. A família de cada feature entra no hash (`feature_set_hash` serializa
`family`), e o runner do cohort recusa um hash diferente do registry
(`run_confirmatory_cohort`). Sem este teste, reclassificar uma feature (ex.: as seis
de volatilidade de `technical` para `price`, a alternativa descartada na #151)
passaria verde no CI e só quebraria ao rodar o cohort — e invalidaria o cohort já
treinado e o pré-registro da 6.5 que o citam. Mudar o registry de propósito exige
nova revisão do cohort; este teste força a decisão a ser consciente.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)

pytestmark = pytest.mark.integration

# `in` é palavra reservada: o pacote `adapters/in/` entra por `importlib` (LAYOUT §8).
cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)

_REPO = Path(__file__).resolve().parents[4]
_COHORT_FILE = _REPO / "config" / "cohorts" / "aapl_confirmatory.toml"


def test_registry_hash_matches_the_frozen_cohort() -> None:
    spec = cohort_file.load(_COHORT_FILE)

    assert spec.feature_set_hash == feature_set_hash(), (
        "o registry de features divergiu do cohort congelado: mudar family/qualquer "
        "campo de spec exige nova revisão do cohort (ADR 5.5.0001), não só o snapshot"
    )
