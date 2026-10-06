"""VO `ProfileParameters` — as regras nomeadas dos perfis do scorecard (Stage 6.6).

Value object de domínio **frozen, stdlib-only** (concept 6.6 §4, D1, D2, D3, D5, D10,
I8, I9; ADR `6_6_0001` item 5). É o bloco opcional `[profile_parameters]` de uma revisão
do pré-registro (ausente no r0) e vai inteiro ao `RefreshParameters` e ao manifesto:

- `subset_multiplicity` — DM por fold/seed/τ descritivo: p bruto, sem correção (D3);
- `partial_degeneracy_pairs` — pares simétricos e adjacentes, linhas não degeneradas (D5);
- `mcs_block_sensitivity_scheme` — l = h e l = ⌈√T⌉ só no esquema primário (D10);
- `stationarity` (`StationarityParameters`) — lags da ACF de d_t, teste de quebra
  (CUSUM escalado pela variância do DM primário, p-valor de Kolmogorov) e o alpha dele (D2).

Toda regra é um identificador aceito **só** se o domínio a implementa
(`PROFILE_RULE_CATALOG`, mesmo padrão do `RULE_CATALOG` do `Preregistration`, ADR
6.5.0004 item 2): mudar a regra exige identificador novo, código novo e revisão nova.
O VO é o **dono único** dessa conferência — os serviços recebem o VO já válido.

`as_payload()` é a serialização única (a forma do TOML, JSON-safe; também a do
manifesto) e `from_mapping` a inversa, recusando chave desconhecida/ausente com o
caminho pontuado (`profile_parameters.stationarity.acf_max_lag`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
)
from financial_forecasting.features.evaluation.domain.value_objects._mapping_keys import (
    missing_key_error,
    unknown_key_error,
)

PROFILE_RULE_CATALOG: Final[Mapping[str, str]] = MappingProxyType(
    {
        "subset_multiplicity": "none_raw_p_descriptive_v1",
        "partial_degeneracy_pairs": "symmetric_and_adjacent_non_degenerate_rows_v1",
        "mcs_block_sensitivity_scheme": "primary_scheme",
        "stationarity.acf_max_lag": "min_floor_10_log10_T_T_minus_1",
        "stationarity.break_test": "cusum_mean_dm_primary_variance_kolmogorov_v1",
    }
)
"""Chave pontuada do bloco → o **único** identificador que o domínio implementa."""

_ROOT = "profile_parameters"
_STATIONARITY_KEYS: Final = ("acf_max_lag", "break_test", "break_alpha")
_PROFILE_KEYS: Final = (
    "subset_multiplicity",
    "partial_degeneracy_pairs",
    "mcs_block_sensitivity_scheme",
    "stationarity",
)


def require_profile_rule(key: str, value: object) -> None:
    """Dono da mensagem "regra de perfil não implementada".

    Raises:
        ValueError: `value` diferente do identificador que o domínio implementa.
    """
    expected = PROFILE_RULE_CATALOG[key]
    if value != expected:
        raise ValueError(
            f"{_ROOT}.{key} must be {expected} (the only rule the domain implements), got {value!r}"
        )


def _check_keys(mapping: object, expected: tuple[str, ...], *, path: str) -> Mapping[str, object]:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{path} must be a table, got {mapping!r}")
    unknown = sorted(str(key) for key in mapping if key not in expected)
    if unknown:
        raise unknown_key_error(f"{path}.{unknown[0]}")
    for key in expected:
        if key not in mapping:
            raise missing_key_error(f"{path}.{key}")
    return mapping


def _as_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number, got {value!r}")
    return float(value)


@dataclass(frozen=True, kw_only=True)
class StationarityParameters:
    """Regras do diagnóstico de estacionariedade de d_t (ADR 6.6.0001)."""

    acf_max_lag: str
    break_test: str
    break_alpha: float

    def __post_init__(self) -> None:
        """Identificadores do catálogo; alpha pelo dono (`validate_alpha`), `float` não-`bool`."""
        require_profile_rule("stationarity.acf_max_lag", self.acf_max_lag)
        require_profile_rule("stationarity.break_test", self.break_test)
        alpha = self.break_alpha
        if isinstance(alpha, bool) or not isinstance(alpha, float):
            raise ValueError(f"{_ROOT}.stationarity.break_alpha must be a float, got {alpha!r}")
        validate_alpha(alpha)

    def as_payload(self) -> dict[str, object]:
        """A forma do TOML (e do manifesto)."""
        return {
            "acf_max_lag": self.acf_max_lag,
            "break_test": self.break_test,
            "break_alpha": float(self.break_alpha),
        }

    @classmethod
    def from_mapping(cls, mapping: object) -> StationarityParameters:
        """Inversa de `as_payload` (`break_alpha` aceita `int` não-`bool`, guarda `float`).

        Raises:
            ValueError: chave desconhecida/ausente, tipo ou regra inválidos.
        """
        path = f"{_ROOT}.stationarity"
        fields = _check_keys(mapping, _STATIONARITY_KEYS, path=path)
        return cls(
            acf_max_lag=str(fields["acf_max_lag"]),
            break_test=str(fields["break_test"]),
            break_alpha=_as_float(fields["break_alpha"], field=f"{path}.break_alpha"),
        )


@dataclass(frozen=True, kw_only=True)
class ProfileParameters:
    """As regras nomeadas dos perfis de séries novas (ver docstring do módulo)."""

    subset_multiplicity: str
    partial_degeneracy_pairs: str
    mcs_block_sensitivity_scheme: str
    stationarity: StationarityParameters

    def __post_init__(self) -> None:
        """Cada identificador é o único que o domínio implementa; o bloco é completo."""
        require_profile_rule("subset_multiplicity", self.subset_multiplicity)
        require_profile_rule("partial_degeneracy_pairs", self.partial_degeneracy_pairs)
        require_profile_rule("mcs_block_sensitivity_scheme", self.mcs_block_sensitivity_scheme)
        if not isinstance(self.stationarity, StationarityParameters):
            raise ValueError(
                f"{_ROOT}.stationarity must be a StationarityParameters, got {self.stationarity!r}"
            )

    def as_payload(self) -> dict[str, object]:
        """A forma do TOML — a única serialização (também a do manifesto)."""
        return {
            "subset_multiplicity": self.subset_multiplicity,
            "partial_degeneracy_pairs": self.partial_degeneracy_pairs,
            "mcs_block_sensitivity_scheme": self.mcs_block_sensitivity_scheme,
            "stationarity": self.stationarity.as_payload(),
        }

    @classmethod
    def from_mapping(cls, mapping: object) -> ProfileParameters:
        """Inversa de `as_payload`.

        Raises:
            ValueError: chave desconhecida/ausente (caminho pontuado), tipo ou regra
                inválidos.
        """
        fields = _check_keys(mapping, _PROFILE_KEYS, path=_ROOT)
        return cls(
            subset_multiplicity=str(fields["subset_multiplicity"]),
            partial_degeneracy_pairs=str(fields["partial_degeneracy_pairs"]),
            mcs_block_sensitivity_scheme=str(fields["mcs_block_sensitivity_scheme"]),
            stationarity=StationarityParameters.from_mapping(fields["stationarity"]),
        )
