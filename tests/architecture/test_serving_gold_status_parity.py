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
