"""Testes do contrato de leitura do dataset TFT (issue #159).

Os valores são pinados: o par `(layer, table)` e a coluna-alvo endereçam dado já
materializado (`data/processed/dataset_tft/...`) e cohorts congelados. Renomear é ato
deliberado que tem de quebrar este teste junto com a migração do dado — nunca deriva
silenciosa.
"""

from __future__ import annotations

from financial_forecasting.features.feature_engineering.domain.services.dataset_tft_contract import (  # noqa: E501
    DATASET_TFT_LAYER,
    DATASET_TFT_TABLE,
    TARGET_COLUMN,
)


def test_dataset_tft_address_is_the_read_only_processed_pair() -> None:
    assert (DATASET_TFT_LAYER, DATASET_TFT_TABLE) == ("processed", "dataset_tft")


def test_target_column_is_target_return() -> None:
    assert TARGET_COLUMN == "target_return"
