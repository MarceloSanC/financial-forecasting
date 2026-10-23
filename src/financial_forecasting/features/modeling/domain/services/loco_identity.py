"""Identidade das configurações da ablação LOCO — regra única nome ↔ família (Stage 7.3).

Domínio puro (stdlib). A configuração `full` não tira família; `minus_<f>` tira a
família `f` (uma das `TFT_FAMILIES`, ordem do ADR 0.0.0016). O `model_version` de uma
configuração é `tft_quantile_loco_<nome>` (ADR 7.3.0003 item 2). O DTO do cohort de
ablação e a validação do `TrainTftCommand` usam estas funções, e nenhum dos dois
redeclara a regra (achado C2-9 do Checkpoint C 05-08).
"""

from __future__ import annotations

from typing import Final

TFT_FAMILIES: Final = ("price", "technical", "sentiment", "fundamental")
FULL_CONFIGURATION: Final = "full"
_MINUS = "minus_"
ABLATION_CONFIGURATIONS: Final = (
    FULL_CONFIGURATION,
    *(f"{_MINUS}{family}" for family in TFT_FAMILIES),
)
_LOCO_PREFIX = "tft_quantile_loco_"


def loco_model_version(configuration: str) -> str:
    """`model_version` de uma configuração da ablação: `tft_quantile_loco_<nome>`."""
    return _LOCO_PREFIX + configuration


def excluded_family_of(configuration: str) -> str | None:
    """A família que a configuração tira (`None` em `full`).

    Raises:
        ValueError: configuração fora de `ABLATION_CONFIGURATIONS`.
    """
    if configuration not in ABLATION_CONFIGURATIONS:
        raise ValueError(
            f"configuration must be one of {list(ABLATION_CONFIGURATIONS)}, got {configuration!r}"
        )
    return None if configuration == FULL_CONFIGURATION else configuration.removeprefix(_MINUS)


def configuration_of(excluded_family: str | None) -> str:
    """A configuração que tira `excluded_family` (`full` com `None`).

    Raises:
        ValueError: família fora de `TFT_FAMILIES`.
    """
    if excluded_family is None:
        return FULL_CONFIGURATION
    if excluded_family not in TFT_FAMILIES:
        raise ValueError(
            f"excluded_family must be one of {list(TFT_FAMILIES)} or None, got {excluded_family!r}"
        )
    return f"{_MINUS}{excluded_family}"
