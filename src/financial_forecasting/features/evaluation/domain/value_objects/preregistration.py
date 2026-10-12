"""VO `Preregistration` — o plano confirmatório congelado, uma revisão (Stage 6.5).

Value object de domínio **frozen, stdlib-only** (concept 6.5 §4 "Domínio", D1, D2,
D4, D9, I1-I4, I14, C1; ADRs `6_5_0001` item 2, `6_5_0002` item 1, `6_5_0004`
itens 1-2, `6_5_0009`, `6_5_0010`). Um arquivo TOML por revisão é lido pelo
adapter e entregue aqui como mapeamento; `Preregistration.from_mapping`:

1. recusa chave desconhecida e chave ausente, nomeando o caminho pontuado (as
   chaves opcionais são `blinding_statement` e o bloco `profile_parameters` —
   Stage 6.6, conferido pelo seu VO, ADR 6.6.0001 item 5; os três campos de emenda
   são proibidos em r0 e obrigatórios em r ≥ 1 — ADR 6.5.0002);
2. coage cada número ao tipo declarado — `float` aceita `int`/`float` não-`bool`
   e guarda `float` (`0` e `0.0` são o mesmo plano); `int` aceita só `int`
   não-`bool` (float, mesmo integral, é erro);
3. valida cada valor pelos **validadores públicos donos** (`validate_alpha`,
   `validate_rate`, `validate_tolerance`, `validate_min_violations`,
   `validate_mcs_reps`, `validate_bootstrap_parameters`,
   `validate_draws_and_seed`, `validate_horizon`, `validate_path_identifier`) —
   nenhuma segunda escrita de regra;
4. aplica as regras cruzadas (níveis de comparadores disjuntos e sem o
   candidato, seeds e déficits de todo modelo, par do gate na grade, cenários
   de poder, horizontes não avaliados, emenda).

Toda regra que o scorecard aplica é nomeada por um identificador aceito só se o
domínio o implementa (`RULE_CATALOG`, ADR 6.5.0004 item 2): mudar a regra exige
identificador novo, código novo e hash novo.

`as_payload()` é a serialização canônica única (as chaves do TOML; tuplas como
listas, enums pelo valor, `SeedSpec` sem seed como `"seedless"`); o hash é do
`PreregistrationHash` de shared sobre ela e `reference(digest)` é a única
função da referência `"<name>-r<rev>-<hash12>"` (ADR 6.5.0001 itens 3-4).

Direção de import: este VO chama validadores que moram em `services/` (os donos
públicos) — aresta VO → serviço deliberada (technical 6.5 §7 `[decision]`
Task 02); nenhum desses módulos importa este.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    validate_draws_and_seed,
    validate_min_violations,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    MCS_STATISTIC,
    validate_block_sensitivities,
    validate_mcs_reps,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects._mapping_keys import (
    missing_key_error,
    unknown_key_error,
)
from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
    validate_bootstrap_parameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    is_symmetric_pair,
)
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    ProfileParameters,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
        PreregistrationHash,
    )

RULE_CATALOG: Final[Mapping[str, str]] = MappingProxyType(
    {
        "primary_metric": "mean_pinball_grid",
        "secondary_roles": "profile_only",
        "dm.direction": "candidate_lower_loss_one_sided",
        "dm.kernel_lag": "rectangular_lag_h_minus_1",
        "dm.small_sample": "hln_student_t_T_minus_1",
        "dm.negative_variance_fallback": "recompute_with_h_1_and_record",
        "mcs.statistic": MCS_STATISTIC,
        "mcs.block_rule": "max_h_ceil_max_bsb",
        "exclusions": "none",
        "seed_aggregation": "mean_losses_mean_counts",
        "h1_gate.form": "per_tail_wilson_model_full_masked_seed_mean_v1",
        "verdict.form": "h1_gate_then_h2_tree_v1",
        "success_criterion": "h1_not_rejected_in_at_least_one_horizon",
    }
)
"""Chave pontuada de `[rules]` → o **único** identificador que o domínio implementa."""

PROFILE_CATALOG: Final[tuple[str, ...]] = (
    "dm_bartlett",
    "mcs_moving_block",
    "mcs_block_h",
    "mcs_block_sqrt_t",
    "gate_common_sample",
    "gate_lr_uc_three_state",
    "gate_dgt",
    "band_95_isolated",
    "without_gaps_variant",
    "comparators_calibration",
    "dm_effect_ci",
    "dm_fallback_applied",
    "tier_outcomes",
    "lowest_mean_pinball",
    "metrics_descriptors",
    "christoffersen_monte_carlo_h1",
    "dm_per_fold",
    "dm_per_seed",
    "dm_per_tau",
    "dm_differential_stationarity",
    "partial_degeneracy_per_pair",
    "sharpness_diagram",
)
"""Perfis declaráveis (ADR 6.5.0008 item 1)."""

REALIZED_SOURCES: Final[tuple[str, ...]] = ("training_grid_target_return",)
"""Fontes do realizado que o domínio implementa (ADR 6.4.0009)."""

SEEDLESS: Final = "seedless"
"""Grafia, no TOML, de um modelo sem seed (baselines; gravados com `None`)."""

_SHA256_HEX: Final = re.compile(r"[0-9a-f]{64}")
_CENTRAL_LEVEL: Final = 0.5


class ScenarioRole(StrEnum):
    """Papel de um cenário de poder do gate (ADR 6.5.0010, P3)."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class BlindStatus(StrEnum):
    """Se a emenda foi feita sem ver resultado confirmatório (ADR 6.5.0002)."""

    BLINDED = "blinded"
    UNBLINDED = "unblinded"


# --- regras de forma (privadas; os valores passam pelos donos) -------------------------


def require_implemented_rule(key: str, value: object) -> None:
    """Dono da mensagem "regra não implementada" (ADR 6.5.0004 item 2).

    Chamado pelo `RuleIdentifiers` na construção e, como defesa, pelo
    `ConfirmatoryScorecard.decide` sobre as regras que ele e o `H1Gate` aplicam.

    Raises:
        ValueError: `value` diferente do identificador que o domínio implementa.
    """
    expected = RULE_CATALOG[key]
    if value != expected:
        raise ValueError(
            f"rules.{key} must be {expected} (the only rule the domain implements), got {value!r}"
        )


def _check_text(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty str, got {value!r}")


def _check_sha256(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase sha256 hex of 64 characters, got {value!r}")


def _check_int_at_least(value: object, *, field: str, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an int >= {minimum}, got {value!r}")


def _check_texts(values: object, *, field: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{field} must be a non-empty list, got {values!r}")
    for value in values:
        _check_text(value, field=field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not repeat values, got {list(values)}")


def _check_strictly_increasing(values: tuple[float, ...], *, field: str) -> None:
    if any(later <= earlier for earlier, later in pairwise(values)):
        raise ValueError(f"{field} must be strictly increasing, got {list(values)}")


def _check_enum(value: object, enum: type[StrEnum], *, field: str) -> None:
    if not isinstance(value, enum):
        raise ValueError(f"{field} must be a {enum.__name__}, got {value!r}")


def _check_sensitivities(
    primary: StrEnum, sensitivities: object, enum: type[StrEnum], *, field: str
) -> None:
    if not isinstance(sensitivities, tuple):
        raise ValueError(f"{field} must be a list, got {sensitivities!r}")
    for value in sensitivities:
        _check_enum(value, enum, field=field)
    if len(set(sensitivities)) != len(sensitivities):
        raise ValueError(f"{field} must not repeat values, got {[str(s) for s in sensitivities]}")
    if primary in sensitivities:
        raise ValueError(f"{field} must not hold the primary {primary.value!r}")


# --- VOs aninhados (um por bloco do TOML) ----------------------------------------------


@dataclass(frozen=True)
class CohortReference:
    """O cohort julgado, por referência: id e hash completo (ADR 6.5.0004 item 1)."""

    cohort_id: str
    cohort_hash: str

    def __post_init__(self) -> None:
        """Identificador de caminho e sha256 hex minúsculo."""
        validate_path_identifier(self.cohort_id, field="cohort.cohort_id")
        _check_sha256(self.cohort_hash, field="cohort.cohort_hash")


@dataclass(frozen=True)
class RealizedSource:
    """De onde vem o realizado e com qual impressão digital (ADR 6.4.0009)."""

    source: str
    dataset_fingerprint: str

    def __post_init__(self) -> None:
        """Fonte do catálogo e sha256 hex minúsculo."""
        if self.source not in REALIZED_SOURCES:
            raise ValueError(
                f"realized.source must be one of {list(REALIZED_SOURCES)} (the only sources "
                f"the domain implements), got {self.source!r}"
            )
        _check_sha256(self.dataset_fingerprint, field="realized.dataset_fingerprint")


@dataclass(frozen=True)
class HorizonNotEvaluated:
    """Horizonte declarado e não avaliado, com o motivo (doc §8.1, §8.8)."""

    horizon: int
    reason: str

    def __post_init__(self) -> None:
        """Horizonte pelo dono; motivo não vazio."""
        validate_horizon(self.horizon, field="horizons_not_evaluated.horizon")
        _check_text(self.reason, field="horizons_not_evaluated.reason")


@dataclass(frozen=True)
class ComparatorTiers:
    """Os três níveis de comparadores do overview §4 (ADR 6.5.0007 item 1)."""

    naive: tuple[str, ...]
    strong_statistical: tuple[str, ...]
    ml: tuple[str, ...]

    def __post_init__(self) -> None:
        """Níveis não vazios, sem repetição e disjuntos."""
        for name in ("naive", "strong_statistical", "ml"):
            _check_texts(getattr(self, name), field=f"comparators.{name}")
        seen: set[str] = set()
        for model in self.all:
            if model in seen:
                raise ValueError(f"comparator tiers must be disjoint, {model!r} is in two tiers")
            seen.add(model)

    @property
    def all(self) -> tuple[str, ...]:
        """Os comparadores na ordem naive → estatístico forte → ML."""
        return self.naive + self.strong_statistical + self.ml

    @property
    def strong(self) -> tuple[str, ...]:
        """Os fortes do veredito: estatístico forte + ML (ADR 6.5.0007 item 1)."""
        return self.strong_statistical + self.ml


@dataclass(frozen=True)
class SeedSpec:
    """As seeds de um modelo; `None` = modelo sem seed (`"seedless"` no TOML)."""

    seeds: tuple[int, ...] | None

    def __post_init__(self) -> None:
        """Lista não vazia de inteiros ≥ 0 distintos, ou `None`."""
        if self.seeds is None:
            return
        if not isinstance(self.seeds, tuple) or not self.seeds:
            raise ValueError(f"seeds must be a non-empty list or {SEEDLESS!r}, got {self.seeds!r}")
        for seed in self.seeds:
            _check_int_at_least(seed, field="seed", minimum=0)
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"seeds must not repeat, got {list(self.seeds)}")

    def as_payload(self) -> object:
        """`"seedless"` ou a lista das seeds."""
        return SEEDLESS if self.seeds is None else list(self.seeds)


def _rule_field(key: str) -> str:
    return key.replace(".", "_")


@dataclass(frozen=True, kw_only=True)
class RuleIdentifiers:
    """Os identificadores das regras aplicadas (ADR 6.5.0004 item 2)."""

    primary_metric: str
    secondary_roles: str
    dm_direction: str
    dm_kernel_lag: str
    dm_small_sample: str
    dm_negative_variance_fallback: str
    mcs_statistic: str
    mcs_block_rule: str
    exclusions: str
    seed_aggregation: str
    h1_gate_form: str
    verdict_form: str
    success_criterion: str

    def __post_init__(self) -> None:
        """Cada identificador é o único que o domínio implementa."""
        for key in RULE_CATALOG:
            require_implemented_rule(key, getattr(self, _rule_field(key)))

    def value_of(self, key: str) -> str:
        """O identificador guardado para a chave pontuada do catálogo."""
        value: str = getattr(self, _rule_field(key))
        return value


@dataclass(frozen=True)
class DmSpec:
    """Diebold-Mariano: alpha de Holm, estimador primário e sensibilidades."""

    alpha: float
    primary_estimator: DmVarianceEstimator
    sensitivity_estimators: tuple[DmVarianceEstimator, ...]

    def __post_init__(self) -> None:
        """alpha pelo dono; estimadores do enum; sensibilidades sem o primário."""
        validate_alpha(self.alpha)
        _check_enum(self.primary_estimator, DmVarianceEstimator, field="dm.primary_estimator")
        _check_sensitivities(
            self.primary_estimator,
            self.sensitivity_estimators,
            DmVarianceEstimator,
            field="dm.sensitivity_estimators",
        )


@dataclass(frozen=True)
class McsSpec:
    """MCS: alpha, réplicas, seed, esquema primário e sensibilidades (ADR 6.5.0009)."""

    alpha: float
    reps: int
    seed: int
    primary_scheme: BootstrapScheme
    sensitivity_schemes: tuple[BootstrapScheme, ...]
    block_sensitivities: tuple[str, ...]

    def __post_init__(self) -> None:
        """alpha, réplicas e seed pelos donos; esquemas do enum; blocos do catálogo."""
        validate_alpha(self.alpha)
        # tipo antes do piso: `validate_mcs_reps` só compara (precedente RefreshParameters)
        validate_bootstrap_parameters(reps=self.reps, seed=self.seed)
        validate_mcs_reps(self.reps)
        _check_enum(self.primary_scheme, BootstrapScheme, field="mcs.primary_scheme")
        _check_sensitivities(
            self.primary_scheme,
            self.sensitivity_schemes,
            BootstrapScheme,
            field="mcs.sensitivity_schemes",
        )
        validate_block_sensitivities(self.block_sensitivities, field="mcs.block_sensitivities")


@dataclass(frozen=True)
class TailDeviation:
    """Cenário de poder: taxas verdadeiras de violação por cauda (ADR 6.5.0006 item 5)."""

    label: str
    role: ScenarioRole
    lower_rate: float
    upper_rate: float

    def __post_init__(self) -> None:
        """Rótulo, papel, taxas em (0, 1) pelo dono e soma < 1."""
        _check_text(self.label, field="h1_gate.power_scenarios.label")
        _check_enum(self.role, ScenarioRole, field="h1_gate.power_scenarios.role")
        validate_rate(self.lower_rate, field="h1_gate.power_scenarios.lower_rate")
        validate_rate(self.upper_rate, field="h1_gate.power_scenarios.upper_rate")
        if self.lower_rate + self.upper_rate >= 1.0:
            raise ValueError(
                f"power scenario {self.label!r}: lower_rate + upper_rate must be < 1, got "
                f"{self.lower_rate!r} + {self.upper_rate!r}"
            )


@dataclass(frozen=True, kw_only=True)
class H1GateSpec:
    """O gate H1 e as suas sensibilidades (ADRs 6.5.0006, 6.5.0009, 6.5.0010)."""

    lower_level: float
    upper_level: float
    gate_band_level: float
    profile_band_level: float
    degeneracy_threshold: float
    degeneracy_tolerance: float
    sensitivity_alpha: float
    power_scenarios: tuple[TailDeviation, ...]

    def __post_init__(self) -> None:
        """Níveis e limiares pelos donos; par simétrico em torno de 0,5; cenários."""
        for name in (
            "lower_level",
            "upper_level",
            "gate_band_level",
            "profile_band_level",
            "degeneracy_threshold",
        ):
            validate_rate(getattr(self, name), field=f"h1_gate.{name}")
        validate_tolerance(self.degeneracy_tolerance, field="h1_gate.degeneracy_tolerance")
        validate_alpha(self.sensitivity_alpha)
        if not self.lower_level < _CENTRAL_LEVEL < self.upper_level:
            raise ValueError(
                "h1_gate needs lower_level < 0.5 < upper_level, got "
                f"({self.lower_level!r}, {self.upper_level!r})"
            )
        if not is_symmetric_pair(self.lower_level, self.upper_level):
            raise ValueError(
                "h1_gate needs lower_level + upper_level == 1 (a central pair), got "
                f"({self.lower_level!r}, {self.upper_level!r})"
            )
        self._check_scenarios()

    def _check_scenarios(self) -> None:
        scenarios = self.power_scenarios
        if not isinstance(scenarios, tuple) or not scenarios:
            raise ValueError(f"h1_gate.power_scenarios must be a non-empty list, got {scenarios!r}")
        for scenario in scenarios:
            if not isinstance(scenario, TailDeviation):
                raise ValueError(
                    f"h1_gate.power_scenarios must hold TailDeviation, got {scenario!r}"
                )
        labels = [scenario.label for scenario in scenarios]
        if len(set(labels)) != len(labels):
            raise ValueError(f"h1_gate.power_scenarios labels must be unique, got {labels}")
        if not any(scenario.role is ScenarioRole.PRIMARY for scenario in scenarios):
            raise ValueError("h1_gate.power_scenarios needs at least one primary scenario")


@dataclass(frozen=True)
class MonteCarloSpec:
    """Monte Carlo de Christoffersen em h+1 (perfil): N e seed (ADR 6.5.0009)."""

    draws: int
    seed: int

    def __post_init__(self) -> None:
        """Pelo dono (`validate_draws_and_seed`)."""
        validate_draws_and_seed(self.draws, self.seed)


@dataclass(frozen=True)
class ProfileSpec:
    """Perfis declarados (ADR 6.5.0008 item 1)."""

    declared: tuple[str, ...]

    def __post_init__(self) -> None:
        """Identificadores do catálogo, sem repetição."""
        if not isinstance(self.declared, tuple):
            raise ValueError(f"profiles.declared must be a list, got {self.declared!r}")
        unknown = [profile for profile in self.declared if profile not in PROFILE_CATALOG]
        if unknown:
            raise ValueError(
                f"profiles.declared holds profiles outside the catalog (the only profiles the "
                f"domain declares): {unknown}"
            )
        if len(set(self.declared)) != len(self.declared):
            raise ValueError(f"profiles.declared must not repeat values, got {list(self.declared)}")


@dataclass(frozen=True)
class Amendment:
    """Campos de emenda de uma revisão r ≥ 1 (ADR 6.5.0002)."""

    amends: str
    justification: str
    blind_status: BlindStatus

    def __post_init__(self) -> None:
        """Textos não vazios e o status do enum."""
        _check_text(self.amends, field="amends")
        _check_text(self.justification, field="justification")
        _check_enum(self.blind_status, BlindStatus, field="blind_status")


# --- esquema das chaves ---------------------------------------------------------------

_LEAF: Final = None
_OPEN: Final = "open"  # tabela de chaves livres (nomes de modelo), conferida contra o plano

_SCHEMA: Final[Mapping[str, object]] = {
    "name": _LEAF,
    "revision": _LEAF,
    "asset": _LEAF,
    "horizons": _LEAF,
    "quantile_levels": _LEAF,
    "candidate": _LEAF,
    "cohort": {"cohort_id": _LEAF, "cohort_hash": _LEAF},
    "realized": {"source": _LEAF, "dataset_fingerprint": _LEAF},
    "horizons_not_evaluated": [{"horizon": _LEAF, "reason": _LEAF}],
    "comparators": {"naive": _LEAF, "strong_statistical": _LEAF, "ml": _LEAF},
    "seeds": _OPEN,
    "window_deficits": _OPEN,
    "rules": {
        "primary_metric": _LEAF,
        "secondary_roles": _LEAF,
        "exclusions": _LEAF,
        "seed_aggregation": _LEAF,
        "success_criterion": _LEAF,
        "dm": {
            "direction": _LEAF,
            "kernel_lag": _LEAF,
            "small_sample": _LEAF,
            "negative_variance_fallback": _LEAF,
        },
        "mcs": {"statistic": _LEAF, "block_rule": _LEAF},
        "h1_gate": {"form": _LEAF},
        "verdict": {"form": _LEAF},
    },
    "dm": {"alpha": _LEAF, "primary_estimator": _LEAF, "sensitivity_estimators": _LEAF},
    "mcs": {
        "alpha": _LEAF,
        "reps": _LEAF,
        "seed": _LEAF,
        "primary_scheme": _LEAF,
        "sensitivity_schemes": _LEAF,
        "block_sensitivities": _LEAF,
    },
    "h1_gate": {
        "lower_level": _LEAF,
        "upper_level": _LEAF,
        "gate_band_level": _LEAF,
        "profile_band_level": _LEAF,
        "degeneracy_threshold": _LEAF,
        "degeneracy_tolerance": _LEAF,
        "sensitivity_alpha": _LEAF,
        "power_scenarios": [
            {"label": _LEAF, "role": _LEAF, "lower_rate": _LEAF, "upper_rate": _LEAF}
        ],
    },
    "backtests": {"min_violations": _LEAF, "monte_carlo": {"draws": _LEAF, "seed": _LEAF}},
    "profiles": {"declared": _LEAF},
}
_OPTIONAL_KEYS: Final = frozenset({"blinding_statement", "profile_parameters"})
_AMENDMENT_KEYS: Final = ("amends", "justification", "blind_status")


def _check_keys(mapping: object, schema: Mapping[str, object], *, path: str) -> None:
    """Chaves desconhecidas e ausentes, recursivamente, nomeando o caminho pontuado."""
    where = path.rstrip(".") or "preregistration"
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{where} must be a table, got {mapping!r}")
    allowed = set(schema) | (_OPTIONAL_KEYS | set(_AMENDMENT_KEYS) if not path else set())
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        raise unknown_key_error(f"{path}{unknown[0]}")
    for key, sub in schema.items():
        if key not in mapping:
            raise missing_key_error(f"{path}{key}")
        value = mapping[key]
        if isinstance(sub, Mapping):
            _check_keys(value, sub, path=f"{path}{key}.")
        elif isinstance(sub, list):
            if not isinstance(value, list | tuple):
                raise ValueError(f"{path}{key} must be a list of tables, got {value!r}")
            for index, item in enumerate(value):
                _check_keys(item, sub[0], path=f"{path}{key}[{index}].")
        elif sub == _OPEN and not isinstance(value, Mapping):
            raise ValueError(f"{path}{key} must be a table, got {value!r}")


# --- coerção de tipo (from_mapping) ---------------------------------------------------


def _as_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number, got {value!r}")
    return float(value)


def _as_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int, got {value!r}")
    return value


def _as_str(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a str, got {value!r}")
    return value


def _as_list(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field} must be a list, got {value!r}")
    return value


def _as_floats(value: object, *, field: str) -> tuple[float, ...]:
    return tuple(
        _as_float(item, field=f"{field}[{i}]")
        for i, item in enumerate(_as_list(value, field=field))
    )


def _as_ints(value: object, *, field: str) -> tuple[int, ...]:
    return tuple(
        _as_int(item, field=f"{field}[{i}]") for i, item in enumerate(_as_list(value, field=field))
    )


def _as_strs(value: object, *, field: str) -> tuple[str, ...]:
    return tuple(
        _as_str(item, field=f"{field}[{i}]") for i, item in enumerate(_as_list(value, field=field))
    )


def _as_enum[E: StrEnum](value: object, enum: type[E], *, field: str) -> E:
    try:
        return enum(_as_str(value, field=field))
    except ValueError:
        raise ValueError(
            f"{field} must be one of {[member.value for member in enum]}, got {value!r}"
        ) from None


def _as_enums[E: StrEnum](value: object, enum: type[E], *, field: str) -> tuple[E, ...]:
    return tuple(
        _as_enum(item, enum, field=f"{field}[{i}]")
        for i, item in enumerate(_as_list(value, field=field))
    )


def _as_table(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a table, got {value!r}")
    return value


def _table(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _as_table(mapping[key], field=key)


def _as_seed_spec(value: object, *, field: str) -> SeedSpec:
    if value == SEEDLESS:
        return SeedSpec(None)
    seeds = _as_ints(value, field=field)
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"{field} must not repeat seeds, got {list(seeds)}")
    for index, seed in enumerate(seeds):
        _check_int_at_least(seed, field=f"{field}[{index}]", minimum=0)
    if not seeds:
        raise ValueError(f"{field} must be a non-empty list or {SEEDLESS!r}, got {value!r}")
    return SeedSpec(seeds)


# --- o plano ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Preregistration:
    """Uma revisão do pré-registro confirmatório (ver docstring do módulo).

    Raises:
        ValueError: plano malformado (C1), pela mensagem do validador dono.
    """

    name: str
    revision: int
    asset: str
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    candidate: str
    cohort: CohortReference
    realized: RealizedSource
    horizons_not_evaluated: tuple[HorizonNotEvaluated, ...]
    comparator_tiers: ComparatorTiers
    seeds: Mapping[str, SeedSpec]
    window_deficits: Mapping[str, int]
    rules: RuleIdentifiers
    dm: DmSpec
    mcs: McsSpec
    h1_gate: H1GateSpec
    min_violations: int
    monte_carlo: MonteCarloSpec
    profiles: ProfileSpec
    blinding_statement: str | None
    amendment: Amendment | None
    profile_parameters: ProfileParameters | None

    def __post_init__(self) -> None:
        """Forma dos campos de topo pelos donos e as regras cruzadas (C1)."""
        validate_path_identifier(self.name, field="name")
        _check_int_at_least(self.revision, field="revision", minimum=0)
        validate_path_identifier(self.asset, field="asset")
        self._check_grid()
        _check_text(self.candidate, field="candidate")
        if self.blinding_statement is not None:
            _check_text(self.blinding_statement, field="blinding_statement")
        if self.profile_parameters is not None and not isinstance(
            self.profile_parameters, ProfileParameters
        ):
            raise ValueError(
                f"profile_parameters must be a ProfileParameters, got {self.profile_parameters!r}"
            )
        validate_min_violations(self.min_violations)
        if self.candidate in self.comparator_tiers.all:
            raise ValueError(f"candidate {self.candidate!r} must not be a comparator tier member")
        object.__setattr__(self, "seeds", self._per_model(self.seeds, block="seeds"))
        object.__setattr__(
            self, "window_deficits", self._per_model(self.window_deficits, block="window_deficits")
        )
        for model, deficit in self.window_deficits.items():
            _check_int_at_least(deficit, field=f"window_deficits.{model}", minimum=0)
        for model, spec in self.seeds.items():
            if not isinstance(spec, SeedSpec):
                raise ValueError(f"seeds.{model} must be a SeedSpec, got {spec!r}")
        for name in ("lower_level", "upper_level"):
            level = getattr(self.h1_gate, name)
            if level not in self.quantile_levels:
                raise ValueError(
                    f"h1_gate.{name} must be a level of quantile_levels "
                    f"{list(self.quantile_levels)}, got {level!r}"
                )
        self._check_not_evaluated()
        self._check_amendment()

    def _check_grid(self) -> None:
        if not isinstance(self.horizons, tuple) or not self.horizons:
            raise ValueError(f"horizons must be a non-empty list, got {self.horizons!r}")
        for index, horizon in enumerate(self.horizons):
            validate_horizon(horizon, field=f"horizons[{index}]")
        _check_strictly_increasing(self.horizons, field="horizons")
        levels = self.quantile_levels
        if not isinstance(levels, tuple) or not levels:
            raise ValueError(f"quantile_levels must be a non-empty list, got {levels!r}")
        for index, level in enumerate(levels):
            validate_rate(level, field=f"quantile_levels[{index}]")
        _check_strictly_increasing(levels, field="quantile_levels")

    def _per_model(self, values: object, *, block: str) -> Mapping[str, object]:
        if not isinstance(values, Mapping):
            raise ValueError(f"{block} must be a table, got {values!r}")
        models = self.models
        extra = [key for key in values if key not in models]
        if extra:
            raise ValueError(
                f"preregistration has unknown key '{block}.{extra[0]}' (not a model of the plan)"
            )
        missing = [model for model in models if model not in values]
        if missing:
            raise ValueError(
                f"preregistration misses the key '{block}.{missing[0]}' (every model needs one)"
            )
        return MappingProxyType({model: values[model] for model in models})

    def _check_not_evaluated(self) -> None:
        entries = self.horizons_not_evaluated
        if not isinstance(entries, tuple):
            raise ValueError(f"horizons_not_evaluated must be a list, got {entries!r}")
        horizons = [entry.horizon for entry in entries]
        if len(set(horizons)) != len(horizons):
            raise ValueError(f"horizons_not_evaluated must not repeat horizons, got {horizons}")
        overlap = sorted(set(horizons) & set(self.horizons))
        if overlap:
            raise ValueError(
                f"horizons_not_evaluated must be disjoint from horizons, got {overlap} in both"
            )

    def _check_amendment(self) -> None:
        if self.revision == 0 and self.amendment is not None:
            raise ValueError(
                "amendment fields (amends, justification, blind_status) are forbidden in revision 0"
            )
        if self.revision == 0 and self.profile_parameters is not None:
            raise ValueError(
                "profile_parameters is forbidden in revision 0 (profile rules the anchored r0 "
                "does not name enter by a blinded amendment, ADR 6.6.0001)"
            )
        if self.revision >= 1 and self.amendment is None:
            raise ValueError(
                f"revision {self.revision} requires the amendment fields (amends, "
                "justification, blind_status)"
            )

    # --- leitura ----------------------------------------------------------------------

    @property
    def comparators(self) -> tuple[str, ...]:
        """Os seis comparadores, na ordem naive → estatístico forte → ML."""
        return self.comparator_tiers.all

    @property
    def models(self) -> tuple[str, ...]:
        """Candidato + comparadores (o M0 do MCS)."""
        return (self.candidate, *self.comparator_tiers.all)

    @property
    def strong(self) -> tuple[str, ...]:
        """Os fortes do veredito: estatístico forte + ML."""
        return self.comparator_tiers.strong

    def reference(self, digest: PreregistrationHash) -> str:
        """`"<name>-r<rev>-<hash12>"` — a única função da referência (ADR 6.5.0001 item 4)."""
        return f"{self.name}-r{self.revision}-{digest.value[:12]}"

    # --- (de)serialização -------------------------------------------------------------

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> Preregistration:
        """O plano a partir do mapeamento lido do TOML (ver docstring do módulo).

        Raises:
            ValueError: chave desconhecida/ausente, tipo não coagível, identificador não
                implementado, valor fora do dono ou regra cruzada violada (C1).
        """
        _check_keys(mapping, _SCHEMA, path="")
        return cls(
            name=_as_str(mapping["name"], field="name"),
            revision=_as_int(mapping["revision"], field="revision"),
            asset=_as_str(mapping["asset"], field="asset"),
            horizons=_as_ints(mapping["horizons"], field="horizons"),
            quantile_levels=_as_floats(mapping["quantile_levels"], field="quantile_levels"),
            candidate=_as_str(mapping["candidate"], field="candidate"),
            cohort=_cohort_from(_table(mapping, "cohort")),
            realized=_realized_from(_table(mapping, "realized")),
            horizons_not_evaluated=_not_evaluated_from(mapping["horizons_not_evaluated"]),
            comparator_tiers=_tiers_from(_table(mapping, "comparators")),
            seeds={
                str(model): _as_seed_spec(value, field=f"seeds.{model}")
                for model, value in _table(mapping, "seeds").items()
            },
            window_deficits={
                str(model): _as_int(value, field=f"window_deficits.{model}")
                for model, value in _table(mapping, "window_deficits").items()
            },
            rules=_rules_from(_table(mapping, "rules")),
            dm=_dm_from(_table(mapping, "dm")),
            mcs=_mcs_from(_table(mapping, "mcs")),
            h1_gate=_h1_gate_from(_table(mapping, "h1_gate")),
            min_violations=_as_int(
                _table(mapping, "backtests")["min_violations"], field="backtests.min_violations"
            ),
            monte_carlo=_monte_carlo_from(_table(_table(mapping, "backtests"), "monte_carlo")),
            profiles=ProfileSpec(
                _as_strs(_table(mapping, "profiles")["declared"], field="profiles.declared")
            ),
            blinding_statement=(
                _as_str(mapping["blinding_statement"], field="blinding_statement")
                if "blinding_statement" in mapping
                else None
            ),
            amendment=_amendment_from(mapping),
            profile_parameters=(
                ProfileParameters.from_mapping(mapping["profile_parameters"])
                if "profile_parameters" in mapping
                else None
            ),
        )

    def as_payload(self) -> dict[str, object]:
        """Serialização canônica única: as chaves do TOML (ADR 6.5.0001 item 2)."""
        payload: dict[str, object] = {
            "name": self.name,
            "revision": self.revision,
            "asset": self.asset,
            "horizons": list(self.horizons),
            "quantile_levels": [float(level) for level in self.quantile_levels],
            "candidate": self.candidate,
        }
        if self.blinding_statement is not None:
            payload["blinding_statement"] = self.blinding_statement
        if self.amendment is not None:
            payload["amends"] = self.amendment.amends
            payload["justification"] = self.amendment.justification
            payload["blind_status"] = self.amendment.blind_status.value
        payload |= {
            "cohort": {
                "cohort_id": self.cohort.cohort_id,
                "cohort_hash": self.cohort.cohort_hash,
            },
            "realized": {
                "source": self.realized.source,
                "dataset_fingerprint": self.realized.dataset_fingerprint,
            },
            "horizons_not_evaluated": [
                {"horizon": entry.horizon, "reason": entry.reason}
                for entry in self.horizons_not_evaluated
            ],
            "comparators": {
                "naive": list(self.comparator_tiers.naive),
                "strong_statistical": list(self.comparator_tiers.strong_statistical),
                "ml": list(self.comparator_tiers.ml),
            },
            "seeds": {model: spec.as_payload() for model, spec in self.seeds.items()},
            "window_deficits": dict(self.window_deficits),
            "rules": self._rules_payload(),
            "dm": {
                "alpha": float(self.dm.alpha),
                "primary_estimator": self.dm.primary_estimator.value,
                "sensitivity_estimators": [e.value for e in self.dm.sensitivity_estimators],
            },
            "mcs": {
                "alpha": float(self.mcs.alpha),
                "reps": self.mcs.reps,
                "seed": self.mcs.seed,
                "primary_scheme": self.mcs.primary_scheme.value,
                "sensitivity_schemes": [s.value for s in self.mcs.sensitivity_schemes],
                "block_sensitivities": list(self.mcs.block_sensitivities),
            },
            "h1_gate": self._h1_gate_payload(),
            "backtests": {
                "min_violations": self.min_violations,
                "monte_carlo": {"draws": self.monte_carlo.draws, "seed": self.monte_carlo.seed},
            },
            "profiles": {"declared": list(self.profiles.declared)},
        }
        if self.profile_parameters is not None:
            payload["profile_parameters"] = self.profile_parameters.as_payload()
        return payload

    def _rules_payload(self) -> dict[str, object]:
        rules = self.rules
        return {
            "primary_metric": rules.primary_metric,
            "secondary_roles": rules.secondary_roles,
            "exclusions": rules.exclusions,
            "seed_aggregation": rules.seed_aggregation,
            "success_criterion": rules.success_criterion,
            "dm": {
                "direction": rules.dm_direction,
                "kernel_lag": rules.dm_kernel_lag,
                "small_sample": rules.dm_small_sample,
                "negative_variance_fallback": rules.dm_negative_variance_fallback,
            },
            "mcs": {"statistic": rules.mcs_statistic, "block_rule": rules.mcs_block_rule},
            "h1_gate": {"form": rules.h1_gate_form},
            "verdict": {"form": rules.verdict_form},
        }

    def _h1_gate_payload(self) -> dict[str, object]:
        gate = self.h1_gate
        return {
            "lower_level": float(gate.lower_level),
            "upper_level": float(gate.upper_level),
            "gate_band_level": float(gate.gate_band_level),
            "profile_band_level": float(gate.profile_band_level),
            "degeneracy_threshold": float(gate.degeneracy_threshold),
            "degeneracy_tolerance": float(gate.degeneracy_tolerance),
            "sensitivity_alpha": float(gate.sensitivity_alpha),
            "power_scenarios": [
                {
                    "label": scenario.label,
                    "role": scenario.role.value,
                    "lower_rate": float(scenario.lower_rate),
                    "upper_rate": float(scenario.upper_rate),
                }
                for scenario in gate.power_scenarios
            ],
        }


# --- montagem dos blocos (from_mapping) ------------------------------------------------


def _cohort_from(block: Mapping[str, object]) -> CohortReference:
    return CohortReference(
        cohort_id=_as_str(block["cohort_id"], field="cohort.cohort_id"),
        cohort_hash=_as_str(block["cohort_hash"], field="cohort.cohort_hash"),
    )


def _realized_from(block: Mapping[str, object]) -> RealizedSource:
    return RealizedSource(
        source=_as_str(block["source"], field="realized.source"),
        dataset_fingerprint=_as_str(
            block["dataset_fingerprint"], field="realized.dataset_fingerprint"
        ),
    )


def _not_evaluated_from(value: object) -> tuple[HorizonNotEvaluated, ...]:
    entries: list[HorizonNotEvaluated] = []
    for index, raw in enumerate(_as_list(value, field="horizons_not_evaluated")):
        path = f"horizons_not_evaluated[{index}]"
        item = _as_table(raw, field=path)
        entries.append(
            HorizonNotEvaluated(
                horizon=_as_int(item["horizon"], field=f"{path}.horizon"),
                reason=_as_str(item["reason"], field=f"{path}.reason"),
            )
        )
    return tuple(entries)


def _tiers_from(block: Mapping[str, object]) -> ComparatorTiers:
    return ComparatorTiers(
        naive=_as_strs(block["naive"], field="comparators.naive"),
        strong_statistical=_as_strs(
            block["strong_statistical"], field="comparators.strong_statistical"
        ),
        ml=_as_strs(block["ml"], field="comparators.ml"),
    )


def _rules_from(block: Mapping[str, object]) -> RuleIdentifiers:
    values: dict[str, str] = {}
    for key in RULE_CATALOG:
        target: Mapping[str, object] = block
        *blocks, leaf = key.split(".")
        for sub in blocks:
            target = _table(target, sub)
        values[_rule_field(key)] = _as_str(target[leaf], field=f"rules.{key}")
    return RuleIdentifiers(**values)


def _dm_from(block: Mapping[str, object]) -> DmSpec:
    primary = _as_enum(
        block["primary_estimator"], DmVarianceEstimator, field="dm.primary_estimator"
    )
    return DmSpec(
        alpha=_as_float(block["alpha"], field="dm.alpha"),
        primary_estimator=primary,
        sensitivity_estimators=_as_enums(
            block["sensitivity_estimators"], DmVarianceEstimator, field="dm.sensitivity_estimators"
        ),
    )


def _mcs_from(block: Mapping[str, object]) -> McsSpec:
    return McsSpec(
        alpha=_as_float(block["alpha"], field="mcs.alpha"),
        reps=_as_int(block["reps"], field="mcs.reps"),
        seed=_as_int(block["seed"], field="mcs.seed"),
        primary_scheme=_as_enum(
            block["primary_scheme"], BootstrapScheme, field="mcs.primary_scheme"
        ),
        sensitivity_schemes=_as_enums(
            block["sensitivity_schemes"], BootstrapScheme, field="mcs.sensitivity_schemes"
        ),
        block_sensitivities=_as_strs(block["block_sensitivities"], field="mcs.block_sensitivities"),
    )


def _h1_gate_from(block: Mapping[str, object]) -> H1GateSpec:
    scenarios: list[TailDeviation] = []
    raw_scenarios = _as_list(block["power_scenarios"], field="h1_gate.power_scenarios")
    for index, raw in enumerate(raw_scenarios):
        path = f"h1_gate.power_scenarios[{index}]"
        item = _as_table(raw, field=path)
        scenarios.append(
            TailDeviation(
                label=_as_str(item["label"], field=f"{path}.label"),
                role=_as_enum(item["role"], ScenarioRole, field=f"{path}.role"),
                lower_rate=_as_float(item["lower_rate"], field=f"{path}.lower_rate"),
                upper_rate=_as_float(item["upper_rate"], field=f"{path}.upper_rate"),
            )
        )

    def number(name: str) -> float:
        return _as_float(block[name], field=f"h1_gate.{name}")

    return H1GateSpec(
        lower_level=number("lower_level"),
        upper_level=number("upper_level"),
        gate_band_level=number("gate_band_level"),
        profile_band_level=number("profile_band_level"),
        degeneracy_threshold=number("degeneracy_threshold"),
        degeneracy_tolerance=number("degeneracy_tolerance"),
        sensitivity_alpha=number("sensitivity_alpha"),
        power_scenarios=tuple(scenarios),
    )


def _monte_carlo_from(block: Mapping[str, object]) -> MonteCarloSpec:
    return MonteCarloSpec(
        draws=_as_int(block["draws"], field="backtests.monte_carlo.draws"),
        seed=_as_int(block["seed"], field="backtests.monte_carlo.seed"),
    )


def _amendment_from(mapping: Mapping[str, object]) -> Amendment | None:
    present = [key for key in _AMENDMENT_KEYS if key in mapping]
    if not present:
        return None
    missing = [key for key in _AMENDMENT_KEYS if key not in mapping]
    if missing:
        raise ValueError(
            f"preregistration misses the key {missing[0]!r} (an amendment needs amends, "
            "justification and blind_status)"
        )
    return Amendment(
        amends=_as_str(mapping["amends"], field="amends"),
        justification=_as_str(mapping["justification"], field="justification"),
        blind_status=_as_enum(mapping["blind_status"], BlindStatus, field="blind_status"),
    )
