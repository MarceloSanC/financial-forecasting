"""Os ids de variante do catálogo do evaluation são os do `ConformalVariant` (Stage 7.2, Task 11).

I16 e I17: os ids existem em dois slices, porque o `bc-independence` não deixa um
importar o outro em `src/`. Este teste compõe os dois e trava a duplicação: o catálogo
aceita exatamente as duas variantes que o domain do `inference` implementa.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    CONFORMAL_RULE_CATALOG,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalVariant,
)

pytestmark = pytest.mark.integration


def test_catalog_variant_ids_are_exactly_the_conformal_variant_values() -> None:
    catalog = {CONFORMAL_RULE_CATALOG["variant_of_record"], CONFORMAL_RULE_CATALOG["sensitivity"]}
    assert catalog == {variant.value for variant in ConformalVariant}
    assert CONFORMAL_RULE_CATALOG["variant_of_record"] == ConformalVariant.SPLIT_CQR.value
    assert CONFORMAL_RULE_CATALOG["sensitivity"] == ConformalVariant.NEXCP.value
