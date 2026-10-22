"""Paridade dos status da geração gold entre o `inference` e o `evaluation` (Stage 7.4, C1-4).

O `inference` não importa o `evaluation` (ADR 7.4.0001 item 7), então repete em
`dtos/serving_gold.py` os valores do `RefreshStatus`. Este teste prende a cópia ao dono:
se o `RefreshStatus` ganhar, perder ou renomear um status, o build fica vermelho antes que
a regra "outro candidato" do `ServeInference` (só com gold `COMPLETED`) passe a ler um
valor que não existe mais.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.inference.application.dtos.serving_gold import (
    BLOCKED,
    COMPLETED,
    GENERATION_STATUSES,
    OK,
    UNIT_STATUSES,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    UnitStatus,
)

pytestmark = pytest.mark.unit


def test_completed_and_blocked_are_the_refresh_status_values() -> None:
    assert RefreshStatus.COMPLETED.value == COMPLETED
    assert RefreshStatus.BLOCKED.value == BLOCKED


def test_the_catalogue_is_exactly_the_refresh_status() -> None:
    assert (
        {status.value for status in RefreshStatus}
        == GENERATION_STATUSES
        == {
            COMPLETED,
            BLOCKED,
        }
    )


def test_unit_statuses_are_the_conformal_unit_status() -> None:
    """Os status de unidade que o gold servido aceita são os que a 7.2 grava (F2)."""
    assert {status.value for status in UnitStatus} == UNIT_STATUSES
    assert UnitStatus.OK.value == OK
