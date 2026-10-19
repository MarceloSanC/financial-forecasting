"""Os ids de variante do catálogo do evaluation são os do `ConformalVariant` (Stage 7.2, Task 11).

I16 e I17: os ids existem em dois slices, porque o `bc-independence` não deixa um
importar o outro em `src/`. Este teste compõe os dois e trava a duplicação: o catálogo
aceita exatamente as duas variantes que o domain do `inference` implementa.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    CONFORMAL_RULE_CATALOG,
    ConformalParameters,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformalCommand,
    validate_command,
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


# --- paridade das regras de par e de rho entre os dois slices (Checkpoint C, C3-4) ----


def _evaluation_accepts(**changes: object) -> bool:
    from tests.unit.features.evaluation._conformal_parameters import (  # noqa: PLC0415
        conformal_block,
    )

    try:
        ConformalParameters.from_mapping({**conformal_block(), **changes})
    except ValueError:
        return False
    return True


def _inference_accepts(
    *, pairs: tuple[tuple[float, float], ...], variants: tuple[str, ...], rho: object
) -> bool:
    command = CalibrateConformalCommand(units=(), pairs=pairs, variants=variants, nexcp_rho=rho)  # type: ignore[arg-type]
    try:
        validate_command(command)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize(
    ("pair", "accepted"),
    [
        ((0.1, 0.9), True),
        ((0.02, 0.98), True),
        ((0.4, 0.6000000000000001), False),
        # C4-3: o nível central, os extremos fora de (0, 1) e o par invertido
        ((0.5, 0.5), False),
        ((0.0, 1.0), False),
        ((0.6, 0.4), False),
    ],
)
def test_pair_rule_parity(pair: tuple[float, float], accepted: bool) -> None:
    evaluation = _evaluation_accepts(pairs=[list(pair)], primary_pair=list(pair))
    inference = _inference_accepts(
        pairs=(pair,), variants=(ConformalVariant.SPLIT_CQR.value,), rho=None
    )
    assert evaluation == inference == accepted


@pytest.mark.parametrize(
    ("rho", "accepted"),
    [
        (0.99, True),
        (0, False),
        (1, True),
        (1.0000001, False),
        (math.nan, False),
        (True, False),
        # C4-3: int enorme (o float() estoura) e negativo
        (10**400, False),
        (-0.5, False),
    ],
)
def test_rho_rule_parity(rho: object, accepted: bool) -> None:
    evaluation = _evaluation_accepts(nexcp_rho=rho)
    inference = _inference_accepts(
        pairs=((0.1, 0.9),), variants=(ConformalVariant.NEXCP.value,), rho=rho
    )
    assert evaluation == inference == accepted
